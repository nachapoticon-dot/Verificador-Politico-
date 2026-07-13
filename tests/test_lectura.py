import threading
import time

import pytest

from verificador import search


def setup_function(_f):
    search._cache.clear()


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


def test_ddgs_se_serializa_entre_hilos(monkeypatch):
    estado = {"activas": 0, "maximas": 0}
    estado_lock = threading.Lock()

    class _DDGS:
        def __enter__(self): return self
        def __exit__(self, *_a): return False
        def text(self, *_a, **_k):
            with estado_lock:
                estado["activas"] += 1
                estado["maximas"] = max(estado["maximas"], estado["activas"])
            time.sleep(0.03)
            with estado_lock:
                estado["activas"] -= 1
            return []

    monkeypatch.setattr("ddgs.DDGS", _DDGS)
    hilos = [
        threading.Thread(target=search._ddgs_texto, args=(f"q{i}", "wt-wt", 2))
        for i in range(2)
    ]
    for hilo in hilos: hilo.start()
    for hilo in hilos: hilo.join()
    assert estado["maximas"] == 1


def test_url_publica_bloquea_redes_internas_y_credenciales(monkeypatch):
    def resolver(host, _port):
        ip = "93.184.216.34" if host == "publica.example" else "10.0.0.8"
        return [(None, None, None, None, (ip, 0))]

    monkeypatch.setattr(search.socket, "getaddrinfo", resolver)
    assert search._url_publica("https://publica.example/nota") is True
    assert search._url_publica("http://interna.example/admin") is False
    assert search._url_publica("http://localhost:8000") is False
    assert search._url_publica("file:///etc/passwd") is False
    assert search._url_publica("https://usuario:clave@publica.example") is False


def test_ruta_rapida_valida_cada_redireccion(monkeypatch):
    import httpx

    llamadas = []
    monkeypatch.setattr(search, "_url_publica", lambda url: "127.0.0.1" not in url)

    def get(url, **_kwargs):
        llamadas.append(url)
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1:8000/privado"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(search.httpx, "get", get)
    assert search._leer_rapido("https://publica.example/nota") is None
    assert llamadas == ["https://publica.example/nota"]
