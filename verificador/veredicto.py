"""Post-proceso del veredicto: el contrato entre el modelo y la interfaz.

Toda respuesta final del modelo pasa por aquí antes de llegar al usuario:
se valida el bloque ```json de cierre (y se repara si falta), se comprueba la
consistencia de las citas [n], se aplican las etiquetas del registro curado,
se adjuntan los extractos de la traza y se recalcula la solidez a partir de
las fuentes reales. Nunca lanza: ante datos imposibles degrada campo a campo;
la prosa siempre sobrevive.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable
from typing import NamedTuple
from urllib.parse import urlparse

from . import fuentes
from .urls import normalizar_url

_log = logging.getLogger(__name__)

# `informativo` y `no_verificable` ya no viven aquí: el primero era un tipo
# disfrazado de veredicto (y por eso nunca tuvo sello) y el segundo es un
# rechazo que se resuelve antes de investigar.
VEREDICTOS = {
    "verdadero", "falso", "enganoso", "fuera_de_contexto",
    "prediccion", "sin_evidencia",
}
TIPOS = {"afirmacion", "pregunta", "mecanismo"}
CREDIBILIDADES = {"alta", "media", "baja", "no_fiable"}
MANIPULACIONES = {"ninguna", "sesgo", "enganosa", "desinformadora"}

_JSON_RE = re.compile(r"```json\s*([\s\S]*?)```\s*$", re.IGNORECASE)
_CITA_RE = re.compile(r"\[(\d+)\]")


def partir(texto: str) -> tuple[str, dict | None]:
    """Separa la prosa del bloque ```json final. Meta ``None`` si falta o no parsea."""
    m = _JSON_RE.search(texto or "")
    if not m:
        return (texto or "").strip(), None
    prosa = texto[: m.start()].strip()
    try:
        meta = json.loads(m.group(1).strip())
    except Exception:  # noqa: BLE001 — JSON inválido: se tratará como ausente
        meta = None
    return prosa, meta if isinstance(meta, dict) else None


def validar_meta(meta) -> dict | None:
    """Meta validado campo a campo (lo inválido se descarta, no todo-o-nada)."""
    if not isinstance(meta, dict):
        return None
    out: dict = {}
    t = meta.get("tipo")
    out["tipo"] = t.lower().strip() if isinstance(t, str) and t.lower().strip() in TIPOS else "afirmacion"
    # El sello solo existe para afirmaciones. Si el modelo manda uno en una
    # pregunta, se descarta: no hay nada que juzgar.
    if out["tipo"] == "afirmacion":
        v = meta.get("veredicto")
        if isinstance(v, str) and v.lower().strip() in VEREDICTOS:
            out["veredicto"] = v.lower().strip()
    try:
        c = float(meta.get("confianza"))
        out["confianza"] = int(round(min(100.0, max(0.0, c))))
    except (TypeError, ValueError):
        out["confianza"] = 0
    for campo in ("resumen", "pais"):
        val = meta.get(campo)
        if isinstance(val, str) and val.strip():
            out[campo] = val.strip()
    out["fuentes"] = []
    vistos_n: set[int] = set()
    for f in meta.get("fuentes") or []:
        if not isinstance(f, dict):
            continue
        try:
            n = int(f.get("n"))
        except (TypeError, ValueError):
            continue
        if n < 1 or n in vistos_n:
            continue
        vistos_n.add(n)
        # Un string como "false" no puede convertirse con bool(): en Python
        # sería True e inflaría la confianza. Solo aceptamos el booleano JSON.
        coincide = f.get("coincide")
        fu: dict = {"n": n, "coincide": coincide if isinstance(coincide, bool) else False}
        url = f.get("url")
        if isinstance(url, str):
            try:
                parsed = urlparse(url)
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    fu["url"] = url
            except (TypeError, ValueError):
                pass
        medio = f.get("medio")
        if isinstance(medio, str) and medio.strip():
            fu["medio"] = medio.strip()
        for campo, validos in (("credibilidad", CREDIBILIDADES),
                               ("manipulacion", MANIPULACIONES)):
            val = f.get(campo)
            if isinstance(val, str) and val.lower().strip() in validos:
                fu[campo] = val.lower().strip()
        t = f.get("tendencia")
        if isinstance(t, str) and t.strip():
            fu["tendencia"] = t.lower().strip()
        out["fuentes"].append(fu)
    return out


def marcar_citas(prosa: str, meta: dict) -> dict:
    """Marca cada fuente con ``citada`` y avisa (log) de citas sin fuente."""
    citadas = {int(n) for n in _CITA_RE.findall(prosa or "")}
    enumeradas = {f["n"] for f in meta.get("fuentes") or []}
    huerfanas = citadas - enumeradas
    if huerfanas:
        _log.warning("citas sin fuente en el JSON de cierre: %s", sorted(huerfanas))
    for f in meta.get("fuentes") or []:
        f["citada"] = f["n"] in citadas
    return meta


def aplicar_registro(meta: dict) -> dict:
    """Para dominios curados, la etiqueta del registro manda sobre la del modelo."""
    for f in meta.get("fuentes") or []:
        ficha = fuentes.clasificar(f.get("url") or "")
        if ficha is None:
            f["registro_curado"] = False
            continue
        f["registro_curado"] = True
        f["credibilidad"] = ficha.credibilidad
        f["manipulacion"] = ficha.manipulacion
        f["tendencia"] = ficha.tendencia
        f["tipo_fuente"] = ficha.tipo
    return meta


def adjuntar_extractos(meta: dict, extractos: dict[str, str] | None) -> dict:
    """Adjunta a cada fuente el extracto leído en la traza (casado por URL canónica)."""
    if not extractos:
        return meta
    por_url = {normalizar_url(u): x for u, x in extractos.items() if u and x}
    for f in meta.get("fuentes") or []:
        x = por_url.get(normalizar_url(f.get("url") or ""))
        if x:
            f["extracto"] = x
    return meta


_PESO_CRED = {"alta": 1.0, "media": 0.6, "baja": 0.25, "no_fiable": 0.0}
_IZQ = {"izquierda", "centro-izquierda"}
_DER = {"derecha", "centro-derecha"}


def _dominio_fuente(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except (TypeError, ValueError):
        return ""


def _fuentes_utiles(meta: dict) -> list[dict]:
    """Fuentes que cuentan: abiertas, citadas, con URL comprobable y dominio único.

    La solidez se deriva del ledger de la consulta, no de lo que el modelo diga
    de sí mismo. Una fuente que no se abrió no es evidencia.
    """
    # El contenedor también lo propone el modelo: "fuentes" puede no ser una
    # lista, o traer elementos que ni siquiera son objetos.
    fuentes_meta = meta.get("fuentes") if isinstance(meta, dict) else None
    if not isinstance(fuentes_meta, list):
        return []
    utiles: list[dict] = []
    dominios: set[str] = set()
    for f in fuentes_meta:
        if not isinstance(f, dict):
            continue
        url = f.get("url")
        dominio = _dominio_fuente(url) if isinstance(url, str) else ""
        if not dominio or dominio in dominios or f.get("citada") is not True:
            continue
        if not isinstance(f.get("extracto"), str) or not f["extracto"].strip():
            continue
        dominios.add(dominio)
        utiles.append(f)
    return utiles


def _campo_texto(f: dict, campo: str) -> str:
    """``campo`` en minúsculas si es texto real; si no, cadena vacía.

    Estos campos los propone un modelo de lenguaje: un ``None``, un número o
    una lista donde se esperaba texto no puede tirar abajo el cálculo de
    solidez, así que un tipo inesperado se trata como "sin dato".
    """
    val = f.get(campo)
    return val.lower() if isinstance(val, str) else ""


def _peso_credibilidad(f: dict) -> float:
    """Peso 0-1 de una fuente, ya descontada su deshonestidad."""
    if _campo_texto(f, "manipulacion") in ("enganosa", "desinformadora"):
        return 0.0
    cred = _PESO_CRED.get(_campo_texto(f, "credibilidad"), 0.25)
    # El tope castiga a los dominios que nadie ha revisado. Una fuente primaria
    # oficial no necesita revisión editorial: es la fuente.
    if f.get("registro_curado") is not True and f.get("tipo_fuente") != "primaria_oficial":
        cred = min(cred, 0.6)
    return cred


def _solidez_afirmacion(utiles: list[dict]) -> int:
    """Curva para lo que está en disputa: cuentan confirmaciones independientes.

    Una sola fuente nunca basta, por buena que sea; que fuentes que trabajan por
    separado —y mejor de tendencias opuestas— lleguen al mismo dato, sí.
    """
    peso = penal = contrapeso = 0.0
    tendencias: set[str] = set()
    for f in utiles:
        if _campo_texto(f, "manipulacion") in ("enganosa", "desinformadora"):
            if f.get("coincide"):
                penal += 0.15
            continue
        cred = _peso_credibilidad(f)
        if not f.get("coincide"):
            # Evidencia leída que no respalda el fallo reduce su solidez. No la
            # tratamos como una refutación total porque el contrato actual solo
            # distingue "respalda" de "matiza".
            contrapeso += cred * 0.12
            continue
        peso += cred
        t = _campo_texto(f, "tendencia")
        if t:
            tendencias.add(t)
    contraste = bool(
        (tendencias & _IZQ and tendencias & _DER)
        or ("verificador" in tendencias and len(tendencias) > 1)
    )
    if contraste:
        peso *= 1.25
    # Techo asintótico: ni un aluvión de fuentes llega a 100.
    conf = 95.0 * (1.0 - math.exp(-0.7 * peso))
    conf *= max(0.0, 1.0 - penal - contrapeso)
    return int(round(conf))


def _solidez_explicativa(utiles: list[dict]) -> int:
    """Curva para preguntas y mecanismos: manda la MEJOR fuente disponible.

    Aquí no hay nada en disputa, así que el contraste editorial no aporta: nadie
    necesita que un medio de izquierda y otro de derecha coincidan en qué hace
    un banco central. Lo que importa es si lo dice quien tiene autoridad.
    """
    # Solo corrobora quien pesa. Contar por cabezas dejaba que dos fuentes
    # desinformadoras, que pesan cero, llevaran la respuesta al techo.
    respaldan = [f for f in utiles
                 if f.get("coincide") is not False and _peso_credibilidad(f) > 0]
    if not respaldan:
        return 0
    mejor = max(_peso_credibilidad(f) for f in respaldan)
    if any(f.get("tipo_fuente") == "primaria_oficial" for f in respaldan):
        base = 88.0
    else:
        base = 70.0 * mejor
    # Corroborar suma, pero poco: no es lo que decide.
    extra = min(2, len(respaldan) - 1) * 4.0
    # Aquí no hay bono por contraste editorial —nadie necesita que izquierda y
    # derecha coincidan en qué hace un banco central— pero una fuente leída que
    # dice lo contrario sí resta, igual que en la curva de afirmación.
    contrapeso = sum(_peso_credibilidad(f) for f in utiles
                     if f.get("coincide") is False) * 0.12
    return int(round(min(95.0, base + extra) * max(0.0, 1.0 - contrapeso)))


def calcular_solidez(meta: dict) -> int:
    """Solidez 0-100 calculada de las fuentes reales, no autodeclarada.

    Dos curvas, porque "qué tan respaldado está esto" significa cosas distintas
    según lo que te hayan preguntado.
    """
    utiles = _fuentes_utiles(meta)
    if not utiles:
        return 0
    if meta.get("tipo", "afirmacion") == "afirmacion":
        return _solidez_afirmacion(utiles)
    return _solidez_explicativa(utiles)


def resumir_evidencia(meta: dict) -> dict:
    """Resumen auditable de la evidencia usada por el cálculo de solidez."""
    # Mismo contenedor propuesto por el modelo que en `_fuentes_utiles`: puede
    # no ser una lista, o traer elementos que ni siquiera son objetos.
    fuentes_meta = meta.get("fuentes") if isinstance(meta, dict) else None
    if not isinstance(fuentes_meta, list):
        fuentes_meta = []
    else:
        fuentes_meta = [f for f in fuentes_meta if isinstance(f, dict)]
    leidas = [
        f for f in fuentes_meta
        if isinstance(f.get("extracto"), str) and f["extracto"].strip()
    ]
    citadas = [f for f in leidas if f.get("citada") is True]
    dominios = {
        _dominio_fuente(f["url"]) for f in citadas if isinstance(f.get("url"), str)
    }
    dominios.discard("")
    tendencias = {_campo_texto(f, "tendencia") for f in citadas}
    tendencias.discard("")
    return {
        "listadas": len(fuentes_meta),
        "leidas": len(leidas),
        "citadas": len(citadas),
        "dominios_independientes": len(dominios),
        "respaldan": sum(1 for f in citadas if f.get("coincide") is True),
        "matizan": sum(1 for f in citadas if f.get("coincide") is not True),
        "diversidad_editorial": len(tendencias),
    }


class Procesado(NamedTuple):
    """Resultado del post-proceso: texto re-serializado, prosa y meta validado."""

    texto: str
    prosa: str
    meta: dict | None


def reserializar(prosa: str, meta: dict | None) -> str:
    """Vuelve a unir prosa + bloque ```json (o la prosa sola si no hay meta)."""
    if meta is None:
        return prosa
    bloque = json.dumps(meta, ensure_ascii=False, indent=2)
    return f"{prosa}\n\n```json\n{bloque}\n```"


def procesar(
    texto: str,
    extractos: dict[str, str] | None = None,
    reparar: Callable[[str], str | None] | None = None,
) -> Procesado:
    """Pipeline completo: partir → (reparar) → validar → citas → registro →
    extractos → solidez → re-serializar. Nunca lanza."""
    prosa, bruto = partir(texto)
    if bruto is None and reparar is not None:
        try:
            arreglo = reparar(prosa)
        except Exception:  # noqa: BLE001 — la reparación jamás rompe la respuesta
            arreglo = None
        if arreglo:
            _, bruto = partir(arreglo)
            if bruto is None:
                # A veces el modelo devuelve el JSON pelado, sin la valla.
                try:
                    cand = json.loads(arreglo.strip())
                    bruto = cand if isinstance(cand, dict) else None
                except Exception:  # noqa: BLE001
                    bruto = None
    meta = validar_meta(bruto)
    if meta is None:
        return Procesado(prosa, prosa, None)
    marcar_citas(prosa, meta)
    aplicar_registro(meta)
    adjuntar_extractos(meta, extractos)
    meta["solidez_modelo"] = meta.pop("confianza", 0)
    meta["solidez"] = calcular_solidez(meta)
    meta["evidencia"] = resumir_evidencia(meta)
    # Degradar informando, jamás borrando. La prosa que el modelo escribió ya
    # viajó al navegador por streaming: sustituirla es borrar una respuesta
    # delante del usuario. Se anota qué le falta y por qué.
    if meta["evidencia"]["leidas"] == 0:
        if meta["evidencia"]["listadas"] == 0:
            meta["aviso"] = {
                "codigo": "nada_encontrado",
                "texto": "No encontré ninguna fuente sobre esto.",
            }
        else:
            meta["aviso"] = {
                "codigo": "sin_abrir",
                "texto": ("Encontré fuentes pero no pude abrir ninguna, así que "
                          "no puedo respaldar esto con lo que dicen por dentro."),
            }
        meta["solidez"] = 0
    return Procesado(reserializar(prosa, meta), prosa, meta)
