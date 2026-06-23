"""Registro curado de fuentes y su credibilidad.

Dos ejes independientes por fuente: tendencia política y credibilidad (alta,
media, baja, no_fiable). El registro vive en `data/fuentes.json` (curado a mano)
y se aplica por auto-anotación: cada fuente que el modelo ve va etiquetada con su
fiabilidad, para que pondere lo que lee. Las fuentes no registradas se proponen
para revisión humana (no se aplican solas).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

_DATA_DIR = Path(__file__).resolve().parent / "data"
_FUENTES_PATH = _DATA_DIR / "fuentes.json"


class Fuente(NamedTuple):
    dominio: str
    credibilidad: str  # alta | media | baja | no_fiable
    tendencia: str
    tipo: str
    nota: str | None


def _cargar_registro() -> dict[str, dict]:
    try:
        with _FUENTES_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 — sin registro, degradamos a {}
        return {}


_REGISTRO: dict[str, dict] = _cargar_registro()

_ETIQ_CRED = {"alta": "ALTA", "media": "MEDIA", "baja": "BAJA", "no_fiable": "NO FIABLE"}


def dominio_registrable(url: str) -> str:
    """Host en minúsculas, sin esquema, sin `www.`, sin puerto. '' si no hay."""
    if not url:
        return ""
    host = urlparse(url if "://" in url else "http://" + url).hostname or ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def clasificar(url: str) -> Fuente | None:
    """Devuelve la ficha de la fuente, o None si su dominio no está registrado.

    Empareja por igualdad de host o por sufijo de dominio (`es.wikipedia.org`
    casa con la clave `wikipedia.org`; `notwikipedia.org` NO, por el punto guía).
    """
    host = dominio_registrable(url)
    if not host:
        return None
    for dom, ficha in _REGISTRO.items():
        if host == dom or host.endswith("." + dom):
            return Fuente(dom, ficha["credibilidad"], ficha["tendencia"],
                          ficha["tipo"], ficha.get("nota"))
    return None


def anotar(url: str) -> str:
    """Etiqueta que se antepone a lo que el modelo ve de esta fuente."""
    f = clasificar(url)
    if f is None:
        return ("[fuente: dominio no registrado — clasifícala tú en el JSON de "
                "cierre; quedará como propuesta de revisión]")
    nota = f" ({f.nota})" if f.nota else ""
    return (f"[fuente: {f.dominio} · fiabilidad "
            f"{_ETIQ_CRED.get(f.credibilidad, f.credibilidad.upper())}"
            f"{nota} · tendencia {f.tendencia}]")
