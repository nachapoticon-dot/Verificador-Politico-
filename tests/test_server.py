from fastapi.testclient import TestClient
from verificador import server


def test_sse_emite_traza_y_respuesta(monkeypatch):
    # Falsea el agente: emite un paso de traza y devuelve una respuesta.
    class _FakeAgente:
        def preguntar(self, pregunta, *, country=None, rigor="riguroso",
                      largo="corta", detalle="simple", on_step=None):
            on_step({"id": "s1", "tipo": "busqueda", "estado": "buscando",
                     "titulo": "x", "url": None, "dominio": None})
            return "RESPUESTA FINAL"

    monkeypatch.setattr(server, "_agente", lambda: _FakeAgente())
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar",
                       json={"pregunta": "¿es verdad?"}) as r:
        cuerpo = "".join(chunk for chunk in r.iter_text())
    assert "event: traza" in cuerpo
    assert "event: respuesta" in cuerpo
    assert "RESPUESTA FINAL" in cuerpo


def test_pregunta_vacia_no_llama_al_agente(monkeypatch):
    llamado = {"v": False}

    class _A:
        def preguntar(self, *a, **k):
            llamado["v"] = True
            return "x"

    monkeypatch.setattr(server, "_agente", lambda: _A())
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar", json={"pregunta": "   "}) as r:
        cuerpo = "".join(chunk for chunk in r.iter_text())
    assert "event: error" in cuerpo
    assert llamado["v"] is False


def test_endpoint_valida_largo_detalle_pais_rigor(monkeypatch):
    capturado = {}

    class _FakeAgente:
        def preguntar(self, pregunta, *, country=None, rigor="riguroso",
                      largo="corta", detalle="simple", on_step=None):
            capturado.update(country=country, rigor=rigor,
                             largo=largo, detalle=detalle)
            return "ok"

    monkeypatch.setattr(server, "_agente", lambda: _FakeAgente())
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar",
                       json={"pregunta": "x", "largo": "zzz", "detalle": "tecnico",
                             "pais": "ar", "rigor": "rapido"}) as r:
        "".join(chunk for chunk in r.iter_text())

    assert capturado["largo"] == "corta"      # inválido → default
    assert capturado["detalle"] == "tecnico"  # válido → respetado
    assert capturado["country"] == "AR"       # normalizado a mayúsculas
    assert capturado["rigor"] == "rapido"
