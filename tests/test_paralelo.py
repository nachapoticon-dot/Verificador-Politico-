import threading

from verificador import agent as agentmod
from verificador.agent import Verificador
from verificador.config import Config
from verificador.search import Lectura

from tests.helpers import stream_de


def _agente():
    return Verificador(config=Config(api_key="x", base_url="http://l", model="m"))


def test_dos_lecturas_corren_a_la_vez(monkeypatch):
    """Una barrera de 2: solo se cruza si ambas lecturas corren en paralelo."""
    a = _agente()
    barrera = threading.Barrier(2, timeout=5)

    def lp(url, **k):
        barrera.wait()
        return Lectura(f"X:{url}", True)

    monkeypatch.setattr(agentmod, "leer_pagina", lp)
    flujos = [
        stream_de(tool_calls=[
            ("t1", "leer_pagina", '{"url": "https://a.com/1"}'),
            ("t2", "leer_pagina", '{"url": "https://b.com/2"}'),
        ]),
        stream_de(content="fin"),
    ]
    it = iter(flujos)
    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: next(it))
    out = a.preguntar("x")
    assert "fin" in out


def test_mensajes_tool_conservan_el_orden(monkeypatch):
    a = _agente()
    capturas = []

    def fake_create(**k):
        capturas.append(k["messages"])
        if len(capturas) == 1:
            return stream_de(tool_calls=[
                ("t1", "leer_pagina", '{"url": "https://a.com/1"}'),
                ("t2", "leer_pagina", '{"url": "https://b.com/2"}'),
            ])
        return stream_de(content="fin")

    monkeypatch.setattr(a._client.chat.completions, "create", fake_create)
    monkeypatch.setattr(agentmod, "leer_pagina",
                        lambda url, **k: Lectura(f"X:{url}", True))
    a.preguntar("x")
    tools = [m for m in capturas[1] if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tools] == ["t1", "t2"]
