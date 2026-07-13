"""Servidor web del Verificador.

Sirve la interfaz construida en ``frontend/dist`` y expone un endpoint que
transmite por SSE la investigación y la respuesta final.

El servidor no guarda estado de sesión: cada petición es independiente y el
agente se comparte (es seguro entre hilos porque los parámetros de la consulta
viajan por llamada).

Levantar:  uvicorn verificador.server:app --reload
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import queue
import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .agent import ConsultaCancelada, Verificador
from .config import cargar_config

# El frontend es una app React (Vite) que se construye a frontend/dist. El
# servidor sirve ese build; en desarrollo se usa `npm run dev` (proxy a /api).
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
ASSETS_DIR = DIST_DIR / "assets"

app = FastAPI(title="Verificador Político")
_log = logging.getLogger(__name__)

# Agente compartido, creado de forma perezosa la primera vez que se usa (así el
# import del módulo no exige la clave). Sin estado entre consultas.
_AGENTE: Verificador | None = None
_AGENTE_LOCK = threading.Lock()
_CONSULTAS = threading.BoundedSemaphore(value=4)
_CONSULTA_TIMEOUT = 120.0


class VerificarEntrada(BaseModel):
    """Contrato público y acotado del endpoint de verificación."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    pregunta: str = Field(default="", max_length=4000)
    pais: str | None = Field(default=None, max_length=2)
    rigor: str = "riguroso"
    largo: str = "normal"
    detalle: str = "simple"

    @field_validator("pais")
    @classmethod
    def validar_pais(cls, valor: str | None) -> str | None:
        if not valor:
            return None
        if len(valor) != 2 or not valor.isalpha():
            raise ValueError("pais debe ser un código ISO de dos letras")
        return valor.upper()


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


@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    icono = DIST_DIR / "favicon.svg"
    if icono.is_file():
        return FileResponse(icono, media_type="image/svg+xml")
    return HTMLResponse("", status_code=404)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "config": cargar_config() is not None}


@app.post("/api/verificar")
async def verificar(body: VerificarEntrada, request: Request) -> StreamingResponse:
    pregunta = body.pregunta
    country = body.pais
    rigor = "rapido" if body.rigor == "rapido" else "riguroso"
    largo = body.largo
    largo = largo if largo in ("corta", "normal", "detallada") else "corta"
    detalle = body.detalle
    detalle = detalle if detalle in ("simple", "tecnico") else "simple"

    async def gen():
        if not pregunta:
            yield _sse("error", {"mensaje": "Escribe una pregunta."})
            return

        cola: queue.Queue = queue.Queue(maxsize=256)
        cancel_event = threading.Event()
        timeout_event = threading.Event()

        def emitir(evento: str | None, dato) -> None:
            if cancel_event.is_set() and evento is not None:
                return
            try:
                cola.put_nowait((evento, dato))
            except queue.Full:
                # Los deltas siguientes o la respuesta final reconciliarán el
                # estado; nunca bloqueamos un hilo abandonado por el cliente.
                pass

        def emitir_terminal(evento: str | None, dato) -> None:
            """Entrega respuesta/error/fin aunque haya cancelación o cola llena."""
            try:
                cola.put_nowait((evento, dato))
                return
            except queue.Full:
                pass
            try:
                cola.get_nowait()
                cola.put_nowait((evento, dato))
            except (queue.Empty, queue.Full):
                pass

        def agotar_tiempo() -> None:
            timeout_event.set()
            cancel_event.set()

        temporizador = threading.Timer(_CONSULTA_TIMEOUT, agotar_tiempo)
        temporizador.daemon = True
        temporizador.start()

        def trabajar():
            adquirido = _CONSULTAS.acquire(blocking=False)
            if not adquirido:
                emitir("error", {"mensaje": "Hay varias verificaciones en curso. Intenta de nuevo en un momento."})
                emitir(None, None)
                return
            try:
                agente = _agente()
                kwargs = {
                    "country": country,
                    "rigor": rigor,
                    "largo": largo,
                    "detalle": detalle,
                    "on_step": lambda ev: emitir(*_evento_cola(ev)),
                }
                if "cancel_event" in inspect.signature(agente.preguntar).parameters:
                    kwargs["cancel_event"] = cancel_event
                final = agente.preguntar(pregunta, **kwargs)
                emitir_terminal("respuesta", {"texto": final})
            except ConsultaCancelada:
                if timeout_event.is_set():
                    emitir_terminal(
                        "error", {"mensaje": "La verificación superó el tiempo máximo."}
                    )
            except Exception as e:  # noqa: BLE001
                _log.exception("falló una verificación", exc_info=e)
                emitir_terminal(
                    "error", {"mensaje": "No se pudo completar la verificación."}
                )
            finally:
                _CONSULTAS.release()
                emitir_terminal(None, None)

        threading.Thread(target=trabajar, daemon=True).start()
        try:
            while True:
                try:
                    evento, dato = await asyncio.to_thread(cola.get, True, 0.25)
                except queue.Empty:
                    if await request.is_disconnected():
                        cancel_event.set()
                        break
                    continue
                if evento is None:
                    break
                yield _sse(evento, dato)
        finally:
            cancel_event.set()
            temporizador.cancel()

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


# Activos del build (JS/CSS con hash). Solo si el frontend ya está construido.
if ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
