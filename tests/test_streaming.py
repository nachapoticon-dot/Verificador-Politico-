import threading

import pytest

from verificador.agent import ConsultaCancelada

from tests.helpers import agente_de_prueba, stream_de


def test_completar_pide_stream_y_junta_el_contenido(monkeypatch):
    a = agente_de_prueba()
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
    a = agente_de_prueba()
    monkeypatch.setattr(
        a._client.chat.completions, "create",
        lambda **k: stream_de(tool_calls=[("t1", "buscar_web", '{"query": "x"}')]))
    eventos = []
    content, tcs = a._completar([], eventos.append)
    assert tcs == [{"id": "t1", "name": "buscar_web", "arguments": '{"query": "x"}'}]
    assert not [e for e in eventos if e["tipo"] == "delta"]


def test_completar_resetea_si_llegan_tools_tras_texto(monkeypatch):
    a = agente_de_prueba()

    def flujo(**k):
        yield from stream_de(content="pensando…")
        yield from stream_de(tool_calls=[("t1", "buscar_web", '{"query": "x"}')])

    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: flujo())
    eventos = []
    _content, tcs = a._completar([], eventos.append)
    assert [e for e in eventos if e["tipo"] == "delta_reset"]
    assert tcs and tcs[0]["name"] == "buscar_web"


def test_completar_sin_on_step_no_rompe(monkeypatch):
    a = agente_de_prueba()
    monkeypatch.setattr(a._client.chat.completions, "create",
                        lambda **k: stream_de(content="Texto"))
    content, tcs = a._completar([], None)
    assert content == "Texto"


def test_preguntar_cancelada_no_llama_al_modelo(monkeypatch):
    a = agente_de_prueba()
    llamado = {"valor": False}
    monkeypatch.setattr(
        a._client.chat.completions,
        "create",
        lambda **_k: llamado.update(valor=True),
    )
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ConsultaCancelada):
        a.preguntar("consulta", cancel_event=cancel)
    assert llamado["valor"] is False
