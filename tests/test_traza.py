from verificador import agent as agentmod
from verificador.agent import Verificador, _dominio
from verificador.search import Lectura


class _FakeMsg:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeTC:
    def __init__(self, _id, name, args):
        self.id = _id
        self.type = "function"
        self.function = type("F", (), {"name": name, "arguments": args})()


def test_dominio():
    assert _dominio("https://www.elpais.com/x") == "elpais.com"
    assert _dominio("") == ""


def test_on_step_estructurado(monkeypatch):
    from verificador.config import Config
    a = Verificador(config=Config(api_key="x", base_url="http://l", model="m"))

    # Primera respuesta: pide leer_pagina; segunda: responde sin tools.
    respuestas = [
        _FakeMsg("", [_FakeTC("t1", "leer_pagina", '{"url": "https://www.elpais.com/n"}')]),
        _FakeMsg("Veredicto final"),
    ]

    class _Choices:
        def __init__(self, m): self.choices = [type("C", (), {"message": m})()]

    it = iter(respuestas)
    monkeypatch.setattr(
        a._client.chat.completions, "create", lambda **k: _Choices(next(it))
    )
    monkeypatch.setattr(agentmod, "leer_pagina", lambda url, **k: Lectura("EXTRACTO LEGIBLE", True))

    eventos = []
    a.preguntar("¿es verdad X?", on_step=eventos.append)

    leyendo = [e for e in eventos if e["estado"] == "leyendo"]
    ok = [e for e in eventos if e["estado"] == "ok"]
    assert leyendo and leyendo[0]["tipo"] == "pagina"
    assert leyendo[0]["dominio"] == "elpais.com"
    assert ok and ok[0]["extracto"] == "EXTRACTO LEGIBLE"
    assert ok[0]["id"] == leyendo[0]["id"]


def test_on_step_fallo(monkeypatch):
    from verificador.config import Config
    a = Verificador(config=Config(api_key="x", base_url="http://l", model="m"))

    # Primera respuesta: pide leer_pagina; segunda: responde sin tools.
    respuestas = [
        _FakeMsg("", [_FakeTC("t1", "leer_pagina", '{"url": "https://www.elpais.com/n"}')]),
        _FakeMsg("Veredicto final"),
    ]

    class _Choices:
        def __init__(self, m): self.choices = [type("C", (), {"message": m})()]

    it = iter(respuestas)
    monkeypatch.setattr(
        a._client.chat.completions, "create", lambda **k: _Choices(next(it))
    )
    monkeypatch.setattr(
        agentmod, "leer_pagina",
        lambda url, **k: Lectura(
            "[No pude abrir ni extraer texto de https://www.elpais.com/n.]", False
        ),
    )

    eventos = []
    a.preguntar("¿es verdad X?", on_step=eventos.append)

    leyendo = [e for e in eventos if e["estado"] == "leyendo"]
    fallo = [e for e in eventos if e["estado"] == "fallo"]
    assert leyendo and leyendo[0]["tipo"] == "pagina"
    assert fallo and fallo[0]["id"] == leyendo[0]["id"]
    # En fallo NUNCA se emite extracto (no debe llegar al visor de evidencias).
    assert "extracto" not in fallo[0]


def test_on_step_ver_video_no_youtube_es_fallo(monkeypatch):
    from verificador.config import Config
    a = Verificador(config=Config(api_key="x", base_url="http://l", model="m"))

    respuestas = [
        _FakeMsg("", [_FakeTC("v1", "ver_video", '{"url": "https://www.tiktok.com/@x/video/1"}')]),
        _FakeMsg("Veredicto final"),
    ]

    class _Choices:
        def __init__(self, m): self.choices = [type("C", (), {"message": m})()]

    it = iter(respuestas)
    monkeypatch.setattr(
        a._client.chat.completions, "create", lambda **k: _Choices(next(it))
    )
    # No mockeamos ver_video: el caso real no-YouTube debe dar ok=False.

    eventos = []
    a.preguntar("¿es verdad X?", on_step=eventos.append)

    leyendo = [e for e in eventos if e["estado"] == "leyendo"]
    fallo = [e for e in eventos if e["estado"] == "fallo"]
    assert leyendo and leyendo[0]["tipo"] == "video"
    assert fallo and fallo[0]["id"] == leyendo[0]["id"]
    assert "extracto" not in fallo[0]


def test_preguntar_captura_propuestas(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import verificador.agent as agentmod
    import verificador.fuentes as fuentes

    ruta = tmp_path / "propuestas.jsonl"
    monkeypatch.setattr(fuentes, "PROPUESTAS_PATH", ruta)

    ver = agentmod.Verificador()
    final = ('Respuesta [1].\n\n```json\n{"veredicto":"informativo","fuentes":'
             '[{"n":1,"medio":"Raro","url":"https://diario-raro-xyz.tld/n",'
             '"credibilidad":"media","tendencia":"centro"}]}\n```')
    fake = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=final, tool_calls=None))]
    )
    monkeypatch.setattr(ver._client.chat.completions, "create", lambda **k: fake)

    out = ver.preguntar("¿algo?")
    assert out == final
    assert ruta.exists()
    assert "diario-raro-xyz.tld" in ruta.read_text(encoding="utf-8")
