from verificador import agent as agentmod
from verificador.agent import Verificador, _dominio
from verificador.search import Lectura

from tests.helpers import stream_de


def test_dominio():
    assert _dominio("https://www.elpais.com/x") == "elpais.com"
    assert _dominio("") == ""


def test_on_step_estructurado(monkeypatch):
    from verificador.config import Config
    a = Verificador(config=Config(api_key="x", base_url="http://l", model="m"))

    flujos = [
        stream_de(tool_calls=[("t1", "leer_pagina", '{"url": "https://www.elpais.com/n"}')]),
        stream_de(content="Veredicto final"),
    ]
    it = iter(flujos)
    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: next(it))
    monkeypatch.setattr(agentmod, "leer_pagina", lambda url, **k: Lectura("EXTRACTO LEGIBLE", True))

    eventos = []
    a.preguntar("¿es verdad X?", on_step=eventos.append)

    leyendo = [e for e in eventos if e.get("estado") == "leyendo"]
    ok = [e for e in eventos if e.get("estado") == "ok"]
    assert leyendo and leyendo[0]["tipo"] == "pagina"
    assert leyendo[0]["dominio"] == "elpais.com"
    assert ok and ok[0]["extracto"] == "EXTRACTO LEGIBLE"
    assert ok[0]["id"] == leyendo[0]["id"]


def test_on_step_fallo(monkeypatch):
    from verificador.config import Config
    a = Verificador(config=Config(api_key="x", base_url="http://l", model="m"))

    flujos = [
        stream_de(tool_calls=[("t1", "leer_pagina", '{"url": "https://www.elpais.com/n"}')]),
        stream_de(content="Veredicto final"),
    ]
    it = iter(flujos)
    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: next(it))
    monkeypatch.setattr(
        agentmod, "leer_pagina",
        lambda url, **k: Lectura(
            "[No pude abrir ni extraer texto de https://www.elpais.com/n.]", False
        ),
    )

    eventos = []
    a.preguntar("¿es verdad X?", on_step=eventos.append)

    leyendo = [e for e in eventos if e.get("estado") == "leyendo"]
    fallo = [e for e in eventos if e.get("estado") == "fallo"]
    assert leyendo and leyendo[0]["tipo"] == "pagina"
    assert fallo and fallo[0]["id"] == leyendo[0]["id"]
    # En fallo NUNCA se emite extracto (no debe llegar al visor de evidencias).
    assert "extracto" not in fallo[0]


def test_on_step_ver_video_no_youtube_es_fallo(monkeypatch):
    from verificador.config import Config
    a = Verificador(config=Config(api_key="x", base_url="http://l", model="m"))

    flujos = [
        stream_de(tool_calls=[("v1", "ver_video", '{"url": "https://www.tiktok.com/@x/video/1"}')]),
        stream_de(content="Veredicto final"),
    ]
    it = iter(flujos)
    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: next(it))
    # No mockeamos ver_video: el caso real no-YouTube debe dar ok=False.

    eventos = []
    a.preguntar("¿es verdad X?", on_step=eventos.append)

    leyendo = [e for e in eventos if e.get("estado") == "leyendo"]
    fallo = [e for e in eventos if e.get("estado") == "fallo"]
    assert leyendo and leyendo[0]["tipo"] == "video"
    assert fallo and fallo[0]["id"] == leyendo[0]["id"]
    assert "extracto" not in fallo[0]


def test_preguntar_captura_propuestas(monkeypatch, tmp_path):
    import verificador.agent as agentmod
    import verificador.fuentes as fuentes

    ruta = tmp_path / "propuestas.jsonl"
    monkeypatch.setattr(fuentes, "PROPUESTAS_PATH", ruta)

    ver = agentmod.Verificador()
    final = ('Respuesta [1].\n\n```json\n{"veredicto":"informativo","fuentes":'
             '[{"n":1,"medio":"Raro","url":"https://diario-raro-xyz.tld/n",'
             '"credibilidad":"media","tendencia":"centro"}]}\n```')
    monkeypatch.setattr(ver._client.chat.completions, "create",
                        lambda **k: stream_de(content=final))

    out = ver.preguntar("¿algo?")
    assert out.startswith("Respuesta [1].")
    assert '"veredicto": "informativo"' in out
    assert ruta.exists()
    assert "diario-raro-xyz.tld" in ruta.read_text(encoding="utf-8")


def test_preguntar_inyecta_instruccion_de_modo(monkeypatch):
    import verificador.agent as agentmod

    ver = agentmod.Verificador()
    final = 'Respuesta [1].\n\n```json\n{"veredicto":"informativo","fuentes":[]}\n```'
    capturado = {}

    def fake_create(**k):
        capturado["messages"] = k["messages"]
        return stream_de(content=final)

    monkeypatch.setattr(ver._client.chat.completions, "create", fake_create)

    ver.preguntar("¿algo?", largo="detallada", detalle="tecnico")

    msgs = capturado["messages"]
    # El system base va primero y no es la instrucción de modo.
    assert msgs[0]["role"] == "system"
    assert not msgs[0]["content"].startswith("[Modo de respuesta]")
    # Se inyectó un mensaje de modo (system) con el texto del modo elegido.
    modos = [m for m in msgs
             if m["role"] == "system" and m["content"].startswith("[Modo de respuesta]")]
    assert modos, "no se inyectó la instrucción de modo"
    assert "varios párrafos" in modos[-1]["content"]
    # Va antes del turno del usuario.
    idx_modo = msgs.index(modos[-1])
    idx_user = next(i for i, m in enumerate(msgs) if m["role"] == "user")
    assert idx_modo < idx_user


def test_cada_consulta_es_independiente(monkeypatch):
    """Sin estado: cada preguntar() arranca de cero, sin arrastrar la anterior."""
    import verificador.agent as agentmod

    ver = agentmod.Verificador()
    final = 'Respuesta [1].\n\n```json\n{"veredicto":"informativo","fuentes":[]}\n```'
    capturas = []

    def fake_create(**k):
        capturas.append(k["messages"])
        return stream_de(content=final)

    monkeypatch.setattr(ver._client.chat.completions, "create", fake_create)

    ver.preguntar("primera")
    ver.preguntar("segunda")

    assert len(capturas) == 2
    for msgs in capturas:
        modos = [m for m in msgs
                 if m["role"] == "system" and m["content"].startswith("[Modo de respuesta]")]
        assert len(modos) == 1  # exactamente una, no se acumulan
        usuarios = [m for m in msgs if m["role"] == "user"]
        assert len(usuarios) == 1
    # La segunda consulta no contiene rastro de la primera.
    assert all(m.get("content") != "primera" for m in capturas[1])
    assert any(m.get("content") == "segunda" for m in capturas[1])


def test_preguntar_enriquece_meta(monkeypatch):
    """El texto devuelto lleva el meta validado: registro curado, extracto
    casado por URL normalizada y confianza recalculada."""
    from verificador import veredicto
    from verificador.config import Config

    a = Verificador(config=Config(api_key="x", base_url="http://l", model="m"))
    final = ('Es falso [1].\n\n```json\n'
             '{"veredicto": "falso", "confianza": 90, "fuentes":'
             ' [{"n": 1, "medio": "Reuters",'
             ' "url": "https://reuters.com/a?utm_source=x",'
             ' "credibilidad": "baja", "tendencia": "derecha", "coincide": true}]}'
             '\n```')

    flujos = [
        stream_de(tool_calls=[("t1", "leer_pagina", '{"url": "https://www.reuters.com/a"}')]),
        stream_de(content=final),
    ]
    it = iter(flujos)
    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: next(it))
    monkeypatch.setattr(
        agentmod,
        "leer_pagina",
        lambda url, **k: Lectura(
            "[fuente: reuters.com · fiabilidad ALTA · manipulación NINGUNA · "
            "tendencia centro]\nLO QUE LEYÓ",
            True,
        ),
    )

    out = a.preguntar("¿es verdad X?")
    _, meta = veredicto.partir(out)
    f = meta["fuentes"][0]
    assert f["credibilidad"] == "alta"         # registro curado manda
    assert f["extracto"] == "LO QUE LEYÓ"      # www./utm no impiden el casado
    assert not f["extracto"].startswith("[fuente:")  # sin la anotación interna
    assert meta["confianza_modelo"] == 90
    assert 40 <= meta["confianza"] <= 55        # recalculada: 1 fuente alta
