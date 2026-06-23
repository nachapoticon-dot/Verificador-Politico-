from verificador import agent as agentmod
from verificador import search
from verificador.agent import Verificador
from verificador.config import Config
from verificador.search import Lectura


def _agente():
    cfg = Config(api_key="x", base_url="http://local", model="deepseek-chat")
    return Verificador(config=cfg)


def test_schema_incluye_ver_video():
    nombres = {s["function"]["name"] for s in search.TOOL_SCHEMAS}
    assert {"buscar_web", "leer_pagina", "ver_video"} <= nombres


def test_dispatch_ver_video(monkeypatch):
    # El dispatch usa el nombre importado directamente (agentmod.ver_video).
    monkeypatch.setattr(agentmod, "ver_video", lambda url, **k: Lectura(f"VID:{url}", True))
    a = _agente()
    out = a._ejecutar_tool("ver_video", {"url": "https://youtu.be/abc123DEF45"})
    assert out.texto == "VID:https://youtu.be/abc123DEF45"
    assert out.ok is True
