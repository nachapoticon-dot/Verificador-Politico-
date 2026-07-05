from verificador.urls import normalizar_url


def test_quita_esquema_www_y_barra_final():
    assert normalizar_url("https://www.elpais.com/nota/") == "elpais.com/nota"
    assert normalizar_url("http://elpais.com/nota") == "elpais.com/nota"


def test_quita_tracking_pero_conserva_query_real():
    assert normalizar_url("https://x.com/a?utm_source=tw&fbclid=1&id=7") == "x.com/a?id=7"
    assert normalizar_url("https://x.com/a?gclid=9") == "x.com/a"


def test_quita_fragmento_y_normaliza_mayusculas_de_host():
    assert normalizar_url("https://X.com/A#seccion") == "x.com/A"


def test_sin_esquema_tambien_funciona():
    assert normalizar_url("www.reuters.com/a") == "reuters.com/a"


def test_vacia_o_solo_espacios_da_vacio():
    assert normalizar_url("") == ""
    assert normalizar_url("   ") == ""


def test_equivalencias_que_deben_casar():
    a = normalizar_url("https://www.semana.com/n/?utm_campaign=x")
    b = normalizar_url("http://semana.com/n")
    assert a == b
