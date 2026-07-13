"""Post-proceso del veredicto: el contrato entre el modelo y la interfaz.

Toda respuesta final del modelo pasa por aquí antes de llegar al usuario:
se valida el bloque ```json de cierre (y se repara si falta), se comprueba la
consistencia de las citas [n], se aplican las etiquetas del registro curado,
se adjuntan los extractos de la traza y se recalcula la confianza a partir de
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

VEREDICTOS = {
    "verdadero", "falso", "enganoso", "fuera_de_contexto",
    "prediccion", "sin_evidencia", "informativo", "no_verificable",
}
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


def calcular_confianza(meta: dict) -> int:
    """Confianza 0-100 calculada de las fuentes reales, no autodeclarada.

    Suman las fuentes que coinciden, ponderadas por credibilidad; el contraste
    real (tendencias opuestas o verificador + otra) da un bono; las fuentes
    deshonestas nunca suman y, si "apoyan", restan solidez. Techo asintótico:
    ni un aluvión de fuentes llega a 100.
    """
    peso = 0.0
    penal = 0.0
    contrapeso = 0.0
    tendencias: set[str] = set()
    dominios: set[str] = set()
    for f in meta.get("fuentes") or []:
        # La confianza se deriva del ledger de la consulta: una fuente debe
        # haber sido abierta (extracto), citada y tener una URL comprobable.
        url = f.get("url") or ""
        dominio = _dominio_fuente(url)
        if not dominio or dominio in dominios or f.get("citada") is not True:
            continue
        if not isinstance(f.get("extracto"), str) or not f["extracto"].strip():
            continue
        dominios.add(dominio)

        manip = (f.get("manipulacion") or "ninguna").lower()
        if manip in ("enganosa", "desinformadora"):
            if f.get("coincide"):
                penal += 0.15
            continue
        cred = _PESO_CRED.get((f.get("credibilidad") or "").lower(), 0.25)
        if f.get("registro_curado") is not True:
            cred = min(cred, 0.6)
        if not f.get("coincide"):
            # Evidencia leída que no respalda el fallo reduce su solidez. No la
            # tratamos como una refutación total porque el contrato actual solo
            # distingue "respalda" de "matiza".
            contrapeso += cred * 0.12
            continue
        peso += cred
        t = (f.get("tendencia") or "").lower()
        if t:
            tendencias.add(t)
    contraste = bool(
        (tendencias & _IZQ and tendencias & _DER)
        or ("verificador" in tendencias and len(tendencias) > 1)
    )
    if contraste:
        peso *= 1.25
    conf = 95.0 * (1.0 - math.exp(-0.7 * peso))
    conf *= max(0.0, 1.0 - penal - contrapeso)
    return int(round(conf))


def resumir_evidencia(meta: dict) -> dict:
    """Resumen auditable de la evidencia usada por el cálculo de solidez."""
    fuentes_meta = meta.get("fuentes") or []
    leidas = [
        f for f in fuentes_meta
        if isinstance(f.get("extracto"), str) and f["extracto"].strip()
    ]
    citadas = [f for f in leidas if f.get("citada") is True]
    dominios = {_dominio_fuente(f.get("url") or "") for f in citadas}
    dominios.discard("")
    tendencias = {(f.get("tendencia") or "").lower() for f in citadas}
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
    extractos → confianza → re-serializar. Nunca lanza."""
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
    meta["confianza_modelo"] = meta.get("confianza", 0)
    meta["confianza"] = calcular_confianza(meta)
    meta["evidencia"] = resumir_evidencia(meta)
    if meta.get("veredicto") != "no_verificable" and meta["evidencia"]["leidas"] == 0:
        meta["veredicto_modelo"] = meta.get("veredicto")
        meta["veredicto"] = "sin_evidencia"
        meta["confianza"] = 0
        meta["resumen"] = "No se reunió evidencia verificable suficiente."
        prosa = (
            "No pude abrir y citar evidencia suficiente para sostener una conclusión. "
            "Prueba reformulando la afirmación con un nombre, fecha o país concreto."
        )
    return Procesado(reserializar(prosa, meta), prosa, meta)
