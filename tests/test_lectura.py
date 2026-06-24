import threading

import pytest

from verificador import search


def _chromium_disponible() -> bool:
    """Sonda barata: ¿podemos importar Playwright y lanzar Chromium?"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        return False
    try:
        with sync_playwright() as pw:
            navegador = pw.chromium.launch(headless=True)
            navegador.close()
    except Exception:  # noqa: BLE001
        return False
    return True


@pytest.mark.skipif(
    not _chromium_disponible(), reason="Playwright/Chromium no disponible en este entorno"
)
def test_navegador_reutilizado_entre_hilos(tmp_path):
    """Dos hilos distintos leen vía Chromium y ambos obtienen el texto.

    Real (no mockeado) y hermético (file://, sin red). Falla con el diseño de
    singleton-por-llamada (afinidad de hilo de Playwright); pasa con el hilo
    propietario único.
    """
    pagina = tmp_path / "pagina.html"
    pagina.write_text(
        "<html><body><article><h1>Titular de prueba</h1>"
        "<p>Este es un párrafo de prueba con texto suficiente para que "
        "trafilatura lo extraiga sin problemas en este test hermético sin red.</p>"
        "</article></body></html>",
        encoding="utf-8",
    )
    url = pagina.as_uri()

    resultados: dict[int, str | None] = {}

    def correr(k: int) -> None:
        resultados[k] = search._leer_navegador(url)

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=60)
    search.cerrar_navegador()

    assert resultados.get(0) and "párrafo de prueba" in resultados[0]
    assert resultados.get(1) and "párrafo de prueba" in resultados[1]


def test_leer_pagina_usa_ruta_rapida(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "Texto rápido legible")
    # Si la rápida funciona, NO debe tocar el navegador.
    def boom(url):
        raise AssertionError("no debería usar el navegador")
    monkeypatch.setattr(search, "_leer_navegador", boom)
    out = search.leer_pagina("https://x.com")
    assert "[fuente:" in out.texto
    assert "Texto rápido legible" in out.texto
    assert out.ok is True


def test_leer_pagina_cae_al_navegador(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: None)
    monkeypatch.setattr(search, "_leer_navegador", lambda url: "Texto del navegador")
    out = search.leer_pagina("https://js-pesado.com")
    assert "[fuente:" in out.texto
    assert "Texto del navegador" in out.texto
    assert out.ok is True


def test_leer_pagina_trunca(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "A" * 9000)
    monkeypatch.setattr(search, "_leer_navegador", lambda url: None)
    out = search.leer_pagina("https://x.com", max_chars=100)
    assert out.texto.endswith("…[texto truncado]")
    assert len(out.texto) < 300  # anotación más 100 chars más truncado
    assert out.ok is True


def test_leer_pagina_falla_todo(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: None)
    monkeypatch.setattr(search, "_leer_navegador", lambda url: None)
    out = search.leer_pagina("https://imposible.com")
    assert "no pude" in out.texto.lower()
    assert out.ok is False


def test_leer_pagina_ok_antepone_anotacion(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "contenido leído")
    out = search.leer_pagina("https://reuters.com/articulo")
    assert out.ok is True
    assert out.texto.startswith("[fuente:")
    assert "fiabilidad ALTA" in out.texto
    assert "contenido leído" in out.texto


def test_buscar_web_anota_cada_resultado(monkeypatch):
    import verificador.search as s

    class _DDGS:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def text(self, *a, **k):
            return [{"title": "t", "href": "https://es.wikipedia.org/wiki/X", "body": "b"}]

    monkeypatch.setattr("ddgs.DDGS", _DDGS)
    res = s.buscar_web("colombia")
    assert "fiabilidad BAJA" in res[0]["fiabilidad"]
