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
import queue
import threading
from typing import NamedTuple

import httpx
import re


class Lectura(NamedTuple):
    """Resultado de una herramienta de lectura.

    `texto` es lo que se le devuelve al modelo (contrato de cara al modelo:
    siempre un string). `ok` indica si la lectura tuvo éxito y es lo que decide
    el `estado` de la traza (ok → ✓; False → fallo). En fallo, `texto` es un
    aviso para el modelo que NUNCA debe llegar al visor de evidencias.
    """

    texto: str
    ok: bool

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


def ver_video(url: str, max_chars: int = 6000) -> Lectura:
    """Lee el contenido de un vídeo por su transcripción (YouTube/Shorts).

    Verifica lo que se DICE en el vídeo, no la imagen. Para otras plataformas
    sin transcripción, devuelve un aviso (TikTok se cubre vía leer_pagina/navegador).
    Devuelve ``Lectura(texto, ok)``: ``ok`` es False si no hay transcripción
    accesible (no es YouTube, o no la hay).
    """
    vid = _id_youtube(url)
    if vid:
        texto = _fetch_transcripcion(vid)
        if texto:
            if len(texto) > max_chars:
                texto = texto[:max_chars] + "\n…[transcripción truncada]"
            return Lectura(f"[Transcripción de {url}]\n{texto}", True)
        return Lectura(
            f"[{url}: sin transcripción disponible; no puedo leer su audio.]", False
        )
    return Lectura(
        f"[{url}: no es un vídeo de YouTube con transcripción accesible.]", False
    )


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


# --- Playwright en un único hilo propietario de larga vida -------------------
#
# Los objetos de la API síncrona de Playwright tienen AFINIDAD DE HILO: solo se
# pueden usar desde el hilo que los creó. Como el servidor corre cada petición
# en un hilo daemon nuevo, un singleton creado perezosamente en el hilo de una
# petición revienta cuando otra petición (otro hilo) lo reutiliza.
#
# Solución: un solo hilo propietario arranca y posee `sync_playwright()` + el
# Chromium lanzado. Los llamadores envían un trabajo (la url) a una cola y
# bloquean esperando su resultado. TODAS las llamadas de Playwright (launch,
# new_page, goto, content, close) ocurren EN ese hilo. El apagado se señaliza
# con un centinela para que el cierre también ocurra en el hilo propietario.

_CENTINELA = object()  # señal de apagado para el hilo propietario
_navegador_lock = threading.Lock()
_navegador_hilo: threading.Thread | None = None
_navegador_jobs: "queue.Queue | None" = None


def _bucle_navegador(jobs: "queue.Queue") -> None:
    """Cuerpo del hilo propietario: posee Playwright y atiende trabajos.

    Si Chromium no está disponible (no instalado o el launch falla), el hilo
    se marca inutilizable y responde None a cada trabajo (degradación elegante).
    """
    from playwright.sync_api import sync_playwright

    pw = None
    browser = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
    except Exception:  # noqa: BLE001 — Chromium ausente o launch fallido
        if pw is not None:
            try:
                pw.stop()
            except Exception:  # noqa: BLE001
                pass
        # Drena trabajos devolviendo None hasta recibir el centinela.
        while True:
            job = jobs.get()
            if job is _CENTINELA:
                return
            _url, result_q = job
            result_q.put(None)

    try:
        while True:
            job = jobs.get()
            if job is _CENTINELA:
                break
            url, result_q = job
            try:
                result_q.put(_leer_en_pagina(browser, url))
            except Exception:  # noqa: BLE001 — nunca dejes a un llamador colgado
                result_q.put(None)
    finally:
        try:
            browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            pw.stop()
        except Exception:  # noqa: BLE001
            pass


def _arrancar_navegador() -> "queue.Queue":
    """Arranca el hilo propietario una sola vez (idempotente) y devuelve su cola."""
    global _navegador_hilo, _navegador_jobs
    with _navegador_lock:
        if _navegador_hilo is None or not _navegador_hilo.is_alive():
            _navegador_jobs = queue.Queue()
            _navegador_hilo = threading.Thread(
                target=_bucle_navegador,
                args=(_navegador_jobs,),
                name="playwright-owner",
                daemon=True,
            )
            _navegador_hilo.start()
        return _navegador_jobs


def _leer_en_pagina(browser, url: str) -> str | None:
    """Renderiza una url en el navegador y extrae su texto. Corre en el hilo propietario."""
    page = browser.new_page(user_agent=_HEADERS["User-Agent"])
    try:
        page.goto(url, wait_until="networkidle", timeout=20000)
        html = page.content()
    finally:
        page.close()
    return _extraer(html)


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


def _leer_navegador(url: str, timeout: float = 30.0) -> str | None:
    """Fallback: envía la url al hilo propietario de Chromium y espera su texto.

    Bloquea hasta `timeout` segundos. Devuelve None ante cualquier fallo o si
    Chromium no está disponible (el hilo propietario degrada a None), de modo
    que `_leer_rapido(url) or _leer_navegador(url)` siga respondiendo.
    """
    jobs = _arrancar_navegador()
    result_q: "queue.Queue" = queue.Queue(maxsize=1)
    jobs.put((url, result_q))
    try:
        return result_q.get(timeout=timeout)
    except queue.Empty:
        return None


def cerrar_navegador() -> None:
    """Apaga el hilo propietario: señaliza el centinela y espera su cierre.

    El navegador y Playwright se cierran EN el hilo propietario (nunca desde
    otro hilo), respetando la afinidad de hilo de la API síncrona.
    """
    global _navegador_hilo, _navegador_jobs
    with _navegador_lock:
        hilo = _navegador_hilo
        jobs = _navegador_jobs
        _navegador_hilo = None
        _navegador_jobs = None
    if hilo is not None and jobs is not None:
        jobs.put(_CENTINELA)
        hilo.join(timeout=10)


atexit.register(cerrar_navegador)


def leer_pagina(url: str, max_chars: int = 6000) -> Lectura:
    """Descarga una URL y devuelve su texto principal (rápido → navegador).

    Devuelve ``Lectura(texto, ok)``: ``ok`` es False si no se pudo abrir ni
    extraer texto (el aviso no debe llegar al visor de evidencias).
    """
    texto = _leer_rapido(url) or _leer_navegador(url)
    if not texto:
        return Lectura(f"[No pude abrir ni extraer texto de {url}.]", False)
    if len(texto) > max_chars:
        texto = texto[:max_chars] + "\n…[texto truncado]"
    return Lectura(texto, True)


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
