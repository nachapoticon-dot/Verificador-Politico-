from unittest import mock
from io import StringIO

from verificador.fuentes import Fuente, dominio_registrable, clasificar, anotar


def test_dominio_registrable_normaliza():
    assert dominio_registrable("https://www.Reuters.com/article/x?y=1") == "reuters.com"
    assert dominio_registrable("http://es.wikipedia.org/wiki/Colombia") == "es.wikipedia.org"
    assert dominio_registrable("reuters.com/sin-esquema") == "reuters.com"
    assert dominio_registrable("") == ""


def test_clasificar_conocida_exacta_y_por_sufijo():
    f = clasificar("https://es.wikipedia.org/wiki/X")
    assert isinstance(f, Fuente)
    assert f.dominio == "wikipedia.org"
    assert f.credibilidad == "baja"
    assert clasificar("https://reuters.com/a").credibilidad == "alta"
    assert clasificar("https://blog.miblog.blogspot.com/post").credibilidad == "baja"


def test_clasificar_desconocida_es_none():
    assert clasificar("https://un-dominio-rarisimo-xyz.tld/nota") is None
    # un sufijo que NO es separador de dominio no debe colar como match:
    assert clasificar("https://notwikipedia.org/x") is None


def test_anotar_conocida_incluye_credibilidad_y_tendencia():
    a = anotar("https://es.wikipedia.org/wiki/X")
    assert "fiabilidad BAJA" in a
    assert "tendencia centro" in a
    assert "wikipedia.org" in a


def test_anotar_desconocida_pide_clasificar():
    a = anotar("https://un-dominio-rarisimo-xyz.tld/nota")
    assert "no registrado" in a
    assert "propuesta" in a


def test_registro_degrada_a_dict_vacio_si_falta_json():
    import verificador.fuentes as m
    # Path instances tienen atributos de solo-lectura (Py3.14), así que
    # parcheamos Path.open a nivel de clase: mismo efecto, no crashea.
    with mock.patch("pathlib.Path.open", side_effect=FileNotFoundError):
        assert m._cargar_registro() == {}


def test_registro_degrada_a_dict_vacio_si_json_invalido():
    import verificador.fuentes as m
    with mock.patch("pathlib.Path.open", return_value=StringIO("not-json")):
        assert m._cargar_registro() == {}
