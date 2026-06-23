"""Herramientas de búsqueda y lectura web para el verificador.

DeepSeek no tiene búsqueda web nativa (a diferencia de Claude), así que se la
damos nosotros mediante function calling:

  - ``buscar_web``  → resultados de DuckDuckGo (sin necesidad de API key).
  - ``leer_pagina`` → descarga una URL y extrae su texto principal.

Estas funciones se exponen al modelo como "tools". El modelo decide cuándo
llamarlas para contrastar fuentes de distintas tendencias.
"""

from __future__ import annotations

import atexit
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


_navegador_singleton = None  # (playwright, browser) reutilizados entre lecturas


def _extraer(html: str) -> str | None:
    import trafilatura

    return trafilatura.extract(
        html, include_comments=False, include_tables=True, favor_recall=True
    )


def _leer_rapido(url: str) -> str | None:
    """Ruta rápida: httpx + trafilatura. None si falla o sale vacío."""
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=8.0, follow_redirects=True)
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        return None
    texto = _extraer(resp.text)
    return texto or None


def _navegador():
    """Lanza Chromium una sola vez y lo reutiliza (coste de arranque amortizado)."""
    global _navegador_singleton
    if _navegador_singleton is None:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(headless=True)
        except Exception:
            pw.stop()
            raise
        _navegador_singleton = (pw, browser)
    return _navegador_singleton[1]


def _leer_navegador(url: str) -> str | None:
    """Fallback: renderiza con Chromium y extrae el texto principal."""
    try:
        browser = _navegador()
        page = browser.new_page(user_agent=_HEADERS["User-Agent"])
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
            html = page.content()
        finally:
            page.close()
    except Exception:  # noqa: BLE001 — degradación elegante (p.ej. Chromium ausente)
        return None
    return _extraer(html)


def cerrar_navegador() -> None:
    """Cierra el navegador persistente, si se abrió."""
    global _navegador_singleton
    if _navegador_singleton is not None:
        pw, browser = _navegador_singleton
        try:
            browser.close()
            pw.stop()
        except Exception:  # noqa: BLE001
            pass
        _navegador_singleton = None


atexit.register(cerrar_navegador)


def leer_pagina(url: str, max_chars: int = 6000) -> str:
    """Descarga una URL y devuelve su texto principal (rápido → navegador)."""
    texto = _leer_rapido(url) or _leer_navegador(url)
    if not texto:
        return f"[No pude abrir ni extraer texto de {url}.]"
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
    {
        "type": "function",
        "function": {
            "name": "ver_video",
            "description": (
                "Lee el CONTENIDO de un vídeo (YouTube, Shorts) por su "
                "transcripción para verificar lo que se dice en él. Úsala cuando "
                "la fuente sea un vídeo. No analiza la imagen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "La URL del vídeo."},
                },
                "required": ["url"],
            },
        },
    },
]
