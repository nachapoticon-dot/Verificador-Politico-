import verificador.search as search
from verificador.search import buscar_web, leer_pagina


def setup_function(_f):
    search._cache.clear()


def test_leer_pagina_cachea_por_url_normalizada(monkeypatch):
    llamadas = []

    def rapido(url):
        llamadas.append(url)
        return "TEXTO LARGO"

    monkeypatch.setattr(search, "_leer_rapido", rapido)
    monkeypatch.setattr(search, "_leer_navegador", lambda url, **k: None)
    a = leer_pagina("https://www.ejemplo.com/nota?utm_source=x")
    b = leer_pagina("https://ejemplo.com/nota/")
    assert a.ok and b.ok
    assert len(llamadas) == 1          # la segunda salió de la caché
    assert b.texto == a.texto


def test_fallos_no_se_cachean(monkeypatch):
    intentos = {"n": 0}

    def rapido(url):
        intentos["n"] += 1
        return None if intentos["n"] == 1 else "YA FUNCIONA"

    monkeypatch.setattr(search, "_leer_rapido", rapido)
    monkeypatch.setattr(search, "_leer_navegador", lambda url, **k: None)
    assert leer_pagina("https://ejemplo.com/x").ok is False
    assert leer_pagina("https://ejemplo.com/x").ok is True


def test_cache_expira(monkeypatch):
    reloj = {"t": 1000.0}
    monkeypatch.setattr(search.time, "monotonic", lambda: reloj["t"])
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "TEXTO")
    monkeypatch.setattr(search, "_leer_navegador", lambda url, **k: None)
    leer_pagina("https://ejemplo.com/x")
    reloj["t"] += search._CACHE_TTL + 1
    llamadas = []

    def rapido2(url):
        llamadas.append(url)
        return "TEXTO2"

    monkeypatch.setattr(search, "_leer_rapido", rapido2)
    leer_pagina("https://ejemplo.com/x")
    assert llamadas                     # expiró: volvió a leer


def test_cache_respeta_el_tope(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "T")
    monkeypatch.setattr(search, "_leer_navegador", lambda url, **k: None)
    for i in range(search._CACHE_MAX + 5):
        leer_pagina(f"https://ejemplo.com/{i}")
    assert len(search._cache) <= search._CACHE_MAX


def test_buscar_web_reintenta_y_recupera(monkeypatch):
    intentos = {"n": 0}

    def ddgs_texto(query, region, max_resultados):
        intentos["n"] += 1
        if intentos["n"] < 3:
            raise RuntimeError("ratelimit")
        return [{"title": "T", "href": "https://reuters.com/a", "body": "B"}]

    monkeypatch.setattr(search, "_ddgs_texto", ddgs_texto)
    monkeypatch.setattr(search.time, "sleep", lambda s: None)
    res = buscar_web("x")
    assert intentos["n"] == 3
    assert res[0]["titulo"] == "T"


def test_buscar_web_agota_reintentos_y_devuelve_error(monkeypatch):
    def revienta(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(search, "_ddgs_texto", revienta)
    monkeypatch.setattr(search.time, "sleep", lambda s: None)
    res = buscar_web("x")
    assert "error" in res[0]
