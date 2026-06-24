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
                        lambda sid, c, r, largo, detalle: {"agente": _FakeAgente(), "strikes": 0})
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar",
                       json={"pregunta": "¿es verdad?", "sid": "t"}) as r:
        cuerpo = "".join(chunk for chunk in r.iter_text())
    assert "event: traza" in cuerpo
    assert "event: respuesta" in cuerpo
    assert "RESPUESTA FINAL" in cuerpo


def test_segundo_insulto_cierra_la_sesion(monkeypatch):
    sesion = {"agente": None, "strikes": 0, "cerrada": False}
    monkeypatch.setattr(server, "_sesion", lambda sid, c, r, largo, detalle: sesion)
    client = TestClient(server.app)

    def pedir(texto):
        with client.stream("POST", "/api/verificar",
                           json={"pregunta": texto, "sid": "t"}) as r:
            return "".join(chunk for chunk in r.iter_text())

    c1 = pedir("eres estupido")
    assert "event: moderacion" in c1
    c2 = pedir("idiota")
    assert "event: cerrada" in c2
    assert sesion["cerrada"] is True


def test_sesion_cerrada_rechaza_sin_llamar_al_modelo(monkeypatch):
    class _Boom:
        def preguntar(self, *a, **k):
            raise AssertionError("no debe llamar al modelo en sesión cerrada")
        messages = []
    sesion = {"agente": _Boom(), "strikes": 2, "cerrada": True}
    monkeypatch.setattr(server, "_sesion", lambda sid, c, r, largo, detalle: sesion)
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar",
                       json={"pregunta": "¿es verdad?", "sid": "t"}) as r:
        cuerpo = "".join(chunk for chunk in r.iter_text())
    assert "event: cerrada" in cuerpo


def test_endpoint_valida_largo_y_detalle(monkeypatch):
    from fastapi.testclient import TestClient
    from verificador import server

    capturado = {}

    class _FakeAgente:
        messages = []
        def preguntar(self, *a, **k):
            return "ok"

    def fake_sesion(sid, country, rigor, largo, detalle):
        capturado["largo"] = largo
        capturado["detalle"] = detalle
        return {"agente": _FakeAgente(), "strikes": 0, "cerrada": False}

    monkeypatch.setattr(server, "_sesion", fake_sesion)
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar",
                       json={"pregunta": "x", "sid": "t",
                             "largo": "zzz", "detalle": "tecnico"}) as r:
        "".join(chunk for chunk in r.iter_text())

    assert capturado["largo"] == "corta"      # inválido → default
    assert capturado["detalle"] == "tecnico"  # válido → respetado
