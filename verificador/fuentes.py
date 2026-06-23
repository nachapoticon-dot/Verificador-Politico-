"""Registro curado de fuentes y su credibilidad.

Dos ejes independientes por fuente: tendencia política y credibilidad (alta,
media, baja, no_fiable). El registro vive en `data/fuentes.json` (curado a mano)
y se aplica por auto-anotación: cada fuente que el modelo ve va etiquetada con su
fiabilidad, para que pondere lo que lee. Las fuentes no registradas se proponen
para revisión humana (no se aplican solas).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
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


PROPUESTAS_PATH = _DATA_DIR / "propuestas.jsonl"

_JSON_RE = re.compile(r"```json\s*([\s\S]*?)```\s*$", re.IGNORECASE)


def extraer_meta(texto: str) -> dict | None:
    """Parsea el bloque ```json``` final de una respuesta. None si falta o es inválido."""
    m = _JSON_RE.search(texto or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1).strip())
    except Exception:  # noqa: BLE001 — JSON inválido: lo ignoramos
        return None


def _dominios_propuestos(ruta: Path) -> set[str]:
    if not ruta.exists():
        return set()
    try:
        text = ruta.read_text(encoding="utf-8")
    except OSError:
        return set()
    doms: set[str] = set()
    for linea in text.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            doms.add(json.loads(linea)["dominio"].lower())
        except Exception:  # noqa: BLE001
            continue
    return doms


def capturar_propuestas(meta: dict | None, ruta: Path | None = None) -> int:
    """Registra (append-only, deduplicado) los dominios de `meta.fuentes` que no
    están en el registro curado. Nunca lanza: si algo falla, devuelve lo escrito.
    """
    if ruta is None:
        ruta = PROPUESTAS_PATH
    if not meta:
        return 0
    fuentes = meta.get("fuentes") or []
    ya = {d.lower() for d in _REGISTRO} | _dominios_propuestos(ruta)
    nuevos = 0
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        for f in fuentes:
            url = (f or {}).get("url") or ""
            dom = dominio_registrable(url)
            if not dom or dom in ya or clasificar(url) is not None:
                continue
            fila = {
                "dominio": dom,
                "credibilidad": f.get("credibilidad"),
                "tendencia": f.get("tendencia"),
                "ejemplo_url": url,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            with ruta.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            ya.add(dom)
            nuevos += 1
    except Exception:  # noqa: BLE001 — la captura jamás rompe la respuesta
        return nuevos
    return nuevos


def _revisar() -> int:
    """Imprime las propuestas pendientes agrupadas por dominio (para curar a mano)."""
    propuestas = _dominios_propuestos(PROPUESTAS_PATH)
    if not propuestas:
        print("No hay propuestas pendientes.")
        return 0
    filas: dict[str, dict] = {}
    for linea in PROPUESTAS_PATH.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            d = json.loads(linea)
            filas[d["dominio"]] = d  # última valoración gana
        except Exception:  # noqa: BLE001
            continue
    print(f"{len(filas)} dominio(s) propuesto(s) (no en el registro curado):\n")
    for dom, d in sorted(filas.items()):
        print(f'  "{dom}": {{"credibilidad": "{d.get("credibilidad")}", '
              f'"tendencia": "{d.get("tendencia")}", "tipo": "?"}}'
              f'   # ej: {d.get("ejemplo_url")}')
    print("\nCopia las aprobadas a verificador/data/fuentes.json.")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "revisar":
        raise SystemExit(_revisar())
    print("Uso: python -m verificador.fuentes revisar")
    raise SystemExit(1)
