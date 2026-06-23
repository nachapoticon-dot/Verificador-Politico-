from fastapi.testclient import TestClient
from verificador import server


def test_sse_emite_traza_y_respuesta(monkeypatch):
    # Falsea el agente: emite un paso de traza y una respuesta.
    class _FakeAgente:
        country = None
        rigor = "riguroso"
        messages = [{"role": "assistant", "content": "RESPUESTA FINAL"}]
        def preguntar(self, pregunta, on_step=None):
            on_step({"id": "s1", "tipo": "busqueda", "estado": "buscando",
                     "titulo": "x", "url": None, "dominio": None})

    monkeypatch.setattr(server, "_sesion",
                        lambda sid, c, r: {"agente": _FakeAgente(), "strikes": 0})
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar",
                       json={"pregunta": "¿es verdad?", "sid": "t"}) as r:
        cuerpo = "".join(chunk for chunk in r.iter_text())
    assert "event: traza" in cuerpo
    assert "event: respuesta" in cuerpo
    assert "RESPUESTA FINAL" in cuerpo
