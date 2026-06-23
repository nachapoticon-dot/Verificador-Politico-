"""Núcleo del agente verificador, sobre DeepSeek.

DeepSeek es compatible con la API de OpenAI, así que usamos el SDK de OpenAI
apuntando a su base_url (mismo patrón que el cerebro de EdifcIA, pero este es un
proyecto aparte). Como DeepSeek no tiene búsqueda web nativa, le damos nuestras
propias herramientas (verificador/search.py) vía function calling y orquestamos
el bucle aquí.
"""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse

from openai import OpenAI

from .config import Config, cargar_config
from .prompts import SYSTEM_PROMPT
from . import search
from .search import TOOL_SCHEMAS, buscar_web, leer_pagina, ver_video


@dataclass
class Verificador:
    """Mantiene una conversación con memoria sobre política (cualquier país)."""

    config: Config = field(default_factory=lambda: _require_config())
    messages: list[dict] = field(default_factory=list)
    max_pasos: int = 8
    # Código de país ISO-3166 (p. ej. "AR") para sesgar la búsqueda, o None.
    country: str | None = None
    # Nivel de exigencia: "rapido" (menos fuentes, más veloz) o "riguroso".
    rigor: str = "riguroso"
    _client: OpenAI = field(init=False)

    def __post_init__(self) -> None:
        self._client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)
        self._reset_system()

    def _reset_system(self) -> None:
        fecha = _dt.date.today().isoformat()
        contexto_pais = (
            f"\nPaís de contexto fijado por el usuario: {self.country}. "
            "Da por hecho que la pregunta trata de ese país salvo que sea evidente lo contrario."
            if self.country
            else ""
        )
        self.messages = [
            {
                "role": "system",
                "content": f"{SYSTEM_PROMPT}\n\nFecha de hoy: {fecha}.{contexto_pais}",
            }
        ]

    def _ejecutar_tool(self, nombre: str, args: dict) -> str:
        """Despacha una llamada de herramienta y devuelve el resultado serializado."""
        if nombre == "buscar_web":
            tope = 4 if self.rigor == "rapido" else 8
            pedido = int(args.get("max_resultados", 6))
            res = buscar_web(
                query=args.get("query", ""),
                max_resultados=max(1, min(pedido, tope)),
                pais=self.country,
            )
            return json.dumps(res, ensure_ascii=False)
        if nombre == "leer_pagina":
            return leer_pagina(url=args.get("url", ""))
        if nombre == "ver_video":
            return search.ver_video(url=args.get("url", ""))
        return f"[Herramienta desconocida: {nombre}]"

    def preguntar(self, pregunta: str, on_step: Callable[[dict], None] | None = None) -> str:
        """Procesa una pregunta y devuelve la respuesta final.

        ``on_step`` (opcional) recibe un dict estructurado por cada herramienta
        (evento de inicio con tipo y estado; evento de fin con estado y extracto)
        para mostrar la traza de investigación en vivo.
        """
        self.messages.append({"role": "user", "content": pregunta})

        pasos = 4 if self.rigor == "rapido" else self.max_pasos
        for _ in range(pasos):
            resp = self._client.chat.completions.create(
                model=self.config.model,
                messages=self.messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.2,
            )
            msg = resp.choices[0].message

            assistant: dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            self.messages.append(assistant)

            # Sin llamadas a herramientas → es la respuesta final.
            if not msg.tool_calls:
                return msg.content or ""

            # Ejecutar cada herramienta y devolver su resultado al modelo.
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                ev = _evento_inicio(tc.id, tc.function.name, args)
                if on_step:
                    on_step(ev)
                resultado = self._ejecutar_tool(tc.function.name, args)
                if on_step:
                    fin = {"id": ev["id"], "tipo": ev["tipo"], "estado": "ok",
                           "titulo": ev["titulo"], "url": ev["url"], "dominio": ev["dominio"]}
                    if ev["tipo"] in ("pagina", "video"):
                        r = resultado or ""
                        fin["extracto"] = r[:1500]
                        if r.startswith("[No pude") or "sin transcripción" in r.lower():
                            fin["estado"] = "fallo"
                    on_step(fin)
                self.messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": resultado}
                )

        return (
            "[Alcancé el límite de pasos de investigación sin concluir. "
            "Intenta reformular la pregunta de forma más específica.]"
        )

    def reiniciar(self) -> None:
        """Borra la memoria de la conversación (conserva el prompt de sistema)."""
        self._reset_system()


def _dominio(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return ""
    return host[4:] if host.startswith("www.") else host


def _evento_inicio(_id: str, nombre: str, args: dict) -> dict:
    if nombre == "buscar_web":
        return {"id": _id, "tipo": "busqueda", "estado": "buscando",
                "titulo": args.get("query", ""), "url": None, "dominio": None}
    tipo = "video" if nombre == "ver_video" else "pagina"
    url = args.get("url", "")
    dom = _dominio(url)
    return {"id": _id, "tipo": tipo, "estado": "leyendo",
            "titulo": dom or url, "url": url, "dominio": dom}


def _require_config() -> Config:
    cfg = cargar_config()
    if cfg is None:
        raise RuntimeError(
            "No encontré DEEPSEEK_API_KEY (ni en el entorno, ni en .env, ni en "
            "el .env.local de EdifcIA)."
        )
    return cfg
