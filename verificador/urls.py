"""Normalización canónica de URLs.

Una misma página llega con variantes (con/sin ``www.``, con parámetros de
tracking, con barra final). Esta clave canónica sirve para casar extractos de
la traza con las fuentes citadas y como clave de la caché de lecturas.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit

_TRACKING = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid"}


def normalizar_url(url: str) -> str:
    """Clave canónica: sin esquema, sin ``www.``, sin tracking, sin ``/`` final
    ni fragmento. Devuelve ``""`` si no hay URL."""
    if not url or not url.strip():
        return ""
    u = url.strip()
    try:
        p = urlsplit(u if "://" in u else "http://" + u)
    except ValueError:
        return u.lower()
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    ruta = p.path.rstrip("/")
    pares = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING
    ]
    query = urlencode(pares)
    return host + ruta + ("?" + query if query else "")
