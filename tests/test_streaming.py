from verificador.agent import Verificador
from verificador.config import Config

from tests.helpers import stream_de


def _agente():
    return Verificador(config=Config(api_key="x", base_url="http://l", model="m"))


def test_completar_pide_stream_y_junta_el_contenido(monkeypatch):
    a = _agente()
    capturado = {}

    def fake_create(**k):
        capturado.update(k)
        return stream_de(content="Hola mundo verificado")

    monkeypatch.setattr(a._client.chat.completions, "create", fake_create)
    eventos = []
    content, tcs = a._completar([], eventos.append)
    assert capturado["stream"] is True
    assert content == "Hola mundo verificado"
    assert tcs == []
    deltas = [e for e in eventos if e["tipo"] == "delta"]
    assert "".join(d["texto"] for d in deltas) == "Hola mundo verificado"


def test_completar_reconstruye_tool_calls_sin_emitir_deltas(monkeypatch):
    a = _agente()
    monkeypatch.setattr(
        a._client.chat.completions, "create",
        lambda **k: stream_de(tool_calls=[("t1", "buscar_web", '{"query": "x"}')]))
    eventos = []
    content, tcs = a._completar([], eventos.append)
    assert tcs == [{"id": "t1", "name": "buscar_web", "arguments": '{"query": "x"}'}]
    assert not [e for e in eventos if e["tipo"] == "delta"]


def test_completar_resetea_si_llegan_tools_tras_texto(monkeypatch):
    a = _agente()

    def flujo(**k):
        yield from stream_de(content="pensando…")
        yield from stream_de(tool_calls=[("t1", "buscar_web", '{"query": "x"}')])

    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: flujo())
    eventos = []
    _content, tcs = a._completar([], eventos.append)
    assert [e for e in eventos if e["tipo"] == "delta_reset"]
    assert tcs and tcs[0]["name"] == "buscar_web"


def test_completar_sin_on_step_no_rompe(monkeypatch):
    a = _agente()
    monkeypatch.setattr(a._client.chat.completions, "create",
                        lambda **k: stream_de(content="Texto"))
    content, tcs = a._completar([], None)
    assert content == "Texto"
