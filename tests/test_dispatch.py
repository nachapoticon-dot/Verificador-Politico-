from verificador import agent as agentmod
from verificador import search
from verificador.search import Lectura

from tests.helpers import agente_de_prueba




def test_schema_incluye_ver_video():
    nombres = {s["function"]["name"] for s in search.TOOL_SCHEMAS}
    assert {"buscar_web", "leer_pagina", "ver_video"} <= nombres


def test_dispatch_ver_video(monkeypatch):
    # El dispatch usa el nombre importado directamente (agentmod.ver_video).
    monkeypatch.setattr(agentmod, "ver_video", lambda url, **k: Lectura(f"VID:{url}", True))
    a = agente_de_prueba()
    out = a._ejecutar_tool("ver_video", {"url": "https://youtu.be/abc123DEF45"})
    assert out.texto == "VID:https://youtu.be/abc123DEF45"
    assert out.ok is True


def _verificador_falso():
    """Verificador con config de mentira: no llega a llamar a la API."""
    return Verificador(config=Config(api_key="x", base_url="http://local",
                                     model="deepseek-v4-flash"))


def test_ejecutar_tool_tolera_max_resultados_no_numerico(monkeypatch):
    """El modelo puede mandar 'seis' en vez de 6; eso no puede tumbar la consulta."""
    monkeypatch.setattr(agentmod, "buscar_web", lambda **kw: [{"titulo": "x", "url": "https://a.com"}])
    v = _verificador_falso()
    out = v._ejecutar_tool("buscar_web", {"query": "x", "max_resultados": "seis"})
    assert out.ok is True


def test_ejecutar_tool_tolera_argumentos_que_no_son_objeto():
    """json.loads puede devolver una lista; args.get reventaría."""
    v = _verificador_falso()
    out = v._ejecutar_tool("buscar_web", ["query", "x"])
    assert out.ok is False
    assert "argumentos" in out.texto.lower()


def test_ejecutar_tool_tolera_argumentos_none():
    v = _verificador_falso()
    out = v._ejecutar_tool("leer_pagina", None)
    assert out.ok is False
