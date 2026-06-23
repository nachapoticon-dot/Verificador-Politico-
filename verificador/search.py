"""Herramientas de búsqueda y lectura web para el verificador.

DeepSeek no tiene búsqueda web nativa (a diferencia de Claude), así que se la
damos nosotros mediante function calling:

  - ``buscar_web``  → resultados de DuckDuckGo (sin necesidad de API key).
  - ``leer_pagina`` → descarga una URL y extrae su texto principal.

Estas funciones se exponen al modelo como "tools". El modelo decide cuándo
llamarlas para contrastar fuentes de distintas tendencias.
"""

from __future__ import annotations

import httpx
import re

# Mapa mínimo de país ISO-3166 → región de DuckDuckGo, para sesgar resultados.
_REGION = {
    "CO": "co-es", "MX": "mx-es", "AR": "ar-es", "ES": "es-es",
    "CL": "cl-es", "PE": "pe-es", "VE": "ve-es", "US": "us-en",
    "UY": "uy-es", "EC": "ec-es", "BO": "bo-es", "PY": "py-es",
    "CR": "cr-es", "GT": "gt-es", "BR": "br-pt", "FR": "fr-fr",
    "DE": "de-de", "IT": "it-it", "GB": "uk-en", "PT": "pt-pt",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

_YT_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def _id_youtube(url: str) -> str | None:
    m = _YT_RE.search(url or "")
    return m.group(1) if m else None


def _fetch_transcripcion(video_id: str) -> str | None:
    """Devuelve la transcripción unida, o None si no hay. Aísla la dependencia."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        tramos = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["es", "en", "pt", "fr"]
        )
    except Exception:  # noqa: BLE001 — sin transcripción disponible
        return None
    texto = " ".join(t.get("text", "") for t in tramos).strip()
    return texto or None


def ver_video(url: str, max_chars: int = 6000) -> str:
    """Lee el contenido de un vídeo por su transcripción (YouTube/Shorts).

    Verifica lo que se DICE en el vídeo, no la imagen. Para otras plataformas
    sin transcripción, devuelve un aviso (TikTok se cubre vía leer_pagina/navegador).
    """
    vid = _id_youtube(url)
    if vid:
        texto = _fetch_transcripcion(vid)
        if texto:
            if len(texto) > max_chars:
                texto = texto[:max_chars] + "\n…[transcripción truncada]"
            return f"[Transcripción de {url}]\n{texto}"
        return f"[{url}: sin transcripción disponible; no puedo leer su audio.]"
    return f"[{url}: no es un vídeo de YouTube con transcripción accesible.]"


def buscar_web(query: str, max_resultados: int = 6, pais: str | None = None) -> list[dict]:
    """Busca en DuckDuckGo y devuelve [{titulo, url, resumen}]."""
    from ddgs import DDGS  # import perezoso: acelera el arranque del CLI

    region = _REGION.get((pais or "").upper(), "wt-wt")
    resultados: list[dict] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, region=region, max_results=max_resultados):
                resultados.append(
                    {
                        "titulo": r.get("title", ""),
                        "url": r.get("href") or r.get("url", ""),
                        "resumen": r.get("body", ""),
                    }
                )
    except Exception as e:  # noqa: BLE001 — devolvemos el error al modelo
        return [{"error": f"Fallo la búsqueda: {e}"}]
    return resultados or [{"aviso": "Sin resultados para esa búsqueda."}]


def leer_pagina(url: str, max_chars: int = 6000) -> str:
    """Descarga una URL y devuelve su texto principal limpio (truncado)."""
    import trafilatura  # import perezoso

    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=20.0, follow_redirects=True)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        return f"[No pude abrir {url}: {e}]"

    texto = trafilatura.extract(
        resp.text, include_comments=False, include_tables=True, favor_recall=True
    )
    if not texto:
        return f"[No pude extraer texto legible de {url}]"
    if len(texto) > max_chars:
        texto = texto[:max_chars] + "\n…[texto truncado]"
    return texto


# Esquemas que se le pasan al modelo (formato de tools de OpenAI/DeepSeek).
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_web",
            "description": (
                "Busca en la web información actual. Úsala varias veces para "
                "contrastar cómo cubren un mismo hecho medios de distintas "
                "tendencias (derecha, izquierda, centro) y verificadores."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Términos de búsqueda, idealmente en el idioma del país.",
                    },
                    "max_resultados": {
                        "type": "integer",
                        "description": "Cuántos resultados traer (por defecto 6).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leer_pagina",
            "description": (
                "Abre una URL concreta y devuelve su texto. Úsala para leer la "
                "fuente primaria (la declaración completa, la ley, el artículo) "
                "cuando un titular o resumen no baste."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "La URL a leer."},
                },
                "required": ["url"],
            },
        },
    },
]
