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
    for f in meta.get("fuentes") or []:
        if not isinstance(f, dict):
            continue
        try:
            n = int(f.get("n"))
        except (TypeError, ValueError):
            continue
        fu: dict = {"n": n, "coincide": bool(f.get("coincide"))}
        url = f.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            fu["url"] = url
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
            continue
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
