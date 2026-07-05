from verificador import search


def setup_function(_f):
    search._cache.clear()


def test_id_youtube_formas():
    assert search._id_youtube("https://www.youtube.com/watch?v=abc123DEF45") == "abc123DEF45"
    assert search._id_youtube("https://youtu.be/abc123DEF45") == "abc123DEF45"
    assert search._id_youtube("https://www.youtube.com/shorts/abc123DEF45") == "abc123DEF45"
    assert search._id_youtube("https://elpais.com/algo") is None


def test_ver_video_youtube_usa_transcripcion(monkeypatch):
    # Simula la API de transcripción para no depender de la red.
    monkeypatch.setattr(search, "_fetch_transcripcion", lambda vid: "Hola soy un vídeo")
    out = search.ver_video("https://youtu.be/abc123DEF45")
    assert "Hola soy un vídeo" in out.texto
    assert "youtu.be/abc123DEF45" in out.texto
    assert out.ok is True


def test_ver_video_sin_transcripcion(monkeypatch):
    monkeypatch.setattr(search, "_fetch_transcripcion", lambda vid: None)
    out = search.ver_video("https://youtu.be/abc123DEF45")
    assert "sin transcripción" in out.texto.lower()
    assert out.ok is False


def test_ver_video_no_youtube_es_fallo():
    # Sin transcripción accesible (no es YouTube) → ok=False.
    out = search.ver_video("https://www.tiktok.com/@x/video/123")
    assert out.ok is False
    assert "no es un vídeo de youtube" in out.texto.lower()


def test_ver_video_ok_antepone_anotacion(monkeypatch):
    monkeypatch.setattr(search, "_id_youtube", lambda url: "abc12345678")
    monkeypatch.setattr(search, "_fetch_transcripcion", lambda vid: "hola mundo")
    out = search.ver_video("https://youtube.com/watch?v=abc12345678")
    assert out.ok is True
    assert out.texto.startswith("[fuente:")          # anotación antepuesta
    assert "hola mundo" in out.texto


def test_ver_video_fallo_no_antepone_anotacion(monkeypatch):
    import verificador.search as s
    out = s.ver_video("https://vimeo.com/123")        # no es YouTube → fallo
    assert out.ok is False
    assert not out.texto.startswith("[fuente:")
