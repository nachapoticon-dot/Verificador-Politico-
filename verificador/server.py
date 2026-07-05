"""Servidor web del Verificador.

Sirve la interfaz (carpeta web/) y expone un endpoint que transmite, en vivo y
por SSE, la traza de investigación y la respuesta final.

El servidor no guarda estado de sesión: cada petición es independiente y el
agente se comparte (es seguro entre hilos porque los parámetros de la consulta
viajan por llamada).

Levantar:  uvicorn verificador.server:app --reload
"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent import Verificador
from .config import cargar_config

# El frontend es una app React (Vite) que se construye a frontend/dist. El
# servidor sirve ese build; en desarrollo se usa `npm run dev` (proxy a /api).
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
ASSETS_DIR = DIST_DIR / "assets"

app = FastAPI(title="Verificador Político")

# Agente compartido, creado de forma perezosa la primera vez que se usa (así el
# import del módulo no exige la clave). Sin estado entre consultas.
_AGENTE: Verificador | None = None
_AGENTE_LOCK = threading.Lock()


def _agente() -> Verificador:
    global _AGENTE
    if _AGENTE is None:
        with _AGENTE_LOCK:
            if _AGENTE is None:
                _AGENTE = Verificador()
    return _AGENTE


def _sse(evento: str, dato) -> str:
    return f"event: {evento}\ndata: {json.dumps(dato, ensure_ascii=False)}\n\n"


def _evento_cola(ev: dict) -> tuple[str, dict]:
    """Mapea un evento de on_step a su evento SSE (delta, delta_reset o traza)."""
    tipo = ev.get("tipo")
    if tipo == "delta":
        return "delta", {"texto": ev.get("texto", "")}
    if tipo == "delta_reset":
        return "delta_reset", {}
    return "traza", ev


@app.get("/")
def index():
    idx = DIST_DIR / "index.html"
    if idx.is_file():
        return FileResponse(idx)
    return HTMLResponse(
        "<h1>Falta construir el frontend</h1>"
        "<p>Corre <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code> "
        "y recarga.</p>",
        status_code=503,
    )


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "config": cargar_config() is not None}


@app.post("/api/verificar")
async def verificar(request: Request) -> StreamingResponse:
    body = await request.json()
    pregunta = (body.get("pregunta") or "").strip()
    country = (body.get("pais") or "").strip().upper() or None
    rigor = "rapido" if body.get("rigor") == "rapido" else "riguroso"
    largo = body.get("largo")
    largo = largo if largo in ("corta", "normal", "detallada") else "corta"
    detalle = body.get("detalle")
    detalle = detalle if detalle in ("simple", "tecnico") else "simple"

    def gen():
        if not pregunta:
            yield _sse("error", {"mensaje": "Escribe una pregunta."})
            return

        # Verificación con traza en vivo. El agente bloquea, así que lo corremos
        # en un hilo y pasamos los eventos por una cola.
        cola: queue.Queue = queue.Queue()

        def trabajar():
            try:
                final = _agente().preguntar(
                    pregunta,
                    country=country,
                    rigor=rigor,
                    largo=largo,
                    detalle=detalle,
                    on_step=lambda ev: cola.put(_evento_cola(ev)),
                )
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


# Activos del build (JS/CSS con hash). Solo si el frontend ya está construido.
if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
