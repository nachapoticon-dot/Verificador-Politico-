"""Servidor web del Verificador.

Sirve la interfaz (carpeta web/) y expone un endpoint que transmite, en vivo y
por SSE, la traza de investigación y la respuesta final. Incluye la capa de
moderación de respeto antes de gastar una llamada al modelo.

Levantar:  uvicorn verificador.server:app --reload
"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent import Verificador
from .config import cargar_config
from .moderation import es_irrespetuoso, mensaje_limite

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Verificador Político")

# Estado por sesión en memoria: { sid: {"agente": Verificador, "strikes": int} }
_SESIONES: dict[str, dict] = {}


def _sse(evento: str, dato) -> str:
    return f"event: {evento}\ndata: {json.dumps(dato, ensure_ascii=False)}\n\n"


def _sesion(sid: str, country: str | None, rigor: str) -> dict:
    s = _SESIONES.get(sid)
    if s is None:
        s = {"agente": Verificador(country=country, rigor=rigor), "strikes": 0, "cerrada": False}
        _SESIONES[sid] = s
    # Permite cambiar país/rigor sobre la marcha sin perder la conversación.
    s["agente"].country = country
    s["agente"].rigor = rigor
    return s


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "config": cargar_config() is not None}


@app.post("/api/verificar")
async def verificar(request: Request) -> StreamingResponse:
    body = await request.json()
    pregunta = (body.get("pregunta") or "").strip()
    sid = body.get("sid") or "anon"
    country = (body.get("pais") or "").strip().upper() or None
    rigor = "rapido" if body.get("rigor") == "rapido" else "riguroso"

    sesion = _sesion(sid, country, rigor)

    def gen():
        if not pregunta:
            yield _sse("error", {"mensaje": "Escribe una pregunta."})
            return

        # 0) Sesión ya cerrada por faltas de respeto: no se procesa nada más.
        if sesion.get("cerrada"):
            yield _sse("cerrada", {"mensaje": mensaje_limite(sesion.get("strikes", 2))})
            return

        # 1) Moderación: límite firme y cierre si se reincide, sin llamar al modelo.
        if es_irrespetuoso(pregunta):
            sesion["strikes"] += 1
            if sesion["strikes"] >= 2:
                sesion["cerrada"] = True
                yield _sse("cerrada", {"mensaje": mensaje_limite(sesion["strikes"])})
            else:
                yield _sse("moderacion", {"mensaje": mensaje_limite(sesion["strikes"])})
            return

        # 2) Verificación con traza en vivo (el agente bloquea; lo corremos en
        #    un hilo y pasamos los eventos por una cola).
        cola: queue.Queue = queue.Queue()

        def trabajar():
            try:
                agente: Verificador = sesion["agente"]
                agente.preguntar(
                    pregunta, on_step=lambda ev: cola.put(("traza", ev))
                )
                # La respuesta final ya está en el último mensaje del agente.
                final = agente.messages[-1].get("content", "")
                cola.put(("respuesta", {"texto": final}))
            except Exception as e:  # noqa: BLE001
                cola.put(("error", {"mensaje": str(e)}))
            finally:
                cola.put((None, None))

        threading.Thread(target=trabajar, daemon=True).start()
        while True:
            evento, dato = cola.get()
            if evento is None:
                break
            yield _sse(evento, dato)

    return StreamingResponse(gen(), media_type="text/event-stream")


# Archivos estáticos (style.css, app.js, fuentes locales si las hubiera).
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
