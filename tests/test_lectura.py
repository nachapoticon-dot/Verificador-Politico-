from verificador import search


def test_leer_pagina_usa_ruta_rapida(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "Texto rápido legible")
    # Si la rápida funciona, NO debe tocar el navegador.
    def boom(url):
        raise AssertionError("no debería usar el navegador")
    monkeypatch.setattr(search, "_leer_navegador", boom)
    assert search.leer_pagina("https://x.com") == "Texto rápido legible"


def test_leer_pagina_cae_al_navegador(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: None)
    monkeypatch.setattr(search, "_leer_navegador", lambda url: "Texto del navegador")
    assert search.leer_pagina("https://js-pesado.com") == "Texto del navegador"


def test_leer_pagina_trunca(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "A" * 9000)
    monkeypatch.setattr(search, "_leer_navegador", lambda url: None)
    out = search.leer_pagina("https://x.com", max_chars=100)
    assert out.endswith("…[texto truncado]")
    assert len(out) < 200


def test_leer_pagina_falla_todo(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: None)
    monkeypatch.setattr(search, "_leer_navegador", lambda url: None)
    out = search.leer_pagina("https://imposible.com")
    assert "no pude" in out.lower()
