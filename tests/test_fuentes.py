import json as _json
from unittest import mock
from io import StringIO
from pathlib import Path

from verificador.fuentes import (
    Fuente, dominio_registrable, clasificar, anotar,
    extraer_meta, capturar_propuestas,
)


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


def test_clasificar_incluye_manipulacion_default_ninguna():
    # Ninguna fuente del registro trae el campo todavía → cae a "ninguna".
    f = clasificar("https://reuters.com/a")
    assert f.manipulacion == "ninguna"


def test_anotar_incluye_eje_manipulacion():
    a = anotar("https://reuters.com/a")
    assert "manipulación NINGUNA" in a


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


def test_extraer_meta_lee_el_json_final():
    texto = 'Bla bla [1].\n\n```json\n{"veredicto":"informativo","fuentes":[]}\n```'
    meta = extraer_meta(texto)
    assert meta["veredicto"] == "informativo"
    assert extraer_meta("sin json") is None
    assert extraer_meta("```json\n{mal json\n```") is None


def test_capturar_propuestas_solo_desconocidas_y_dedupe(tmp_path):
    ruta = tmp_path / "propuestas.jsonl"
    meta = {"fuentes": [
        {"medio": "Reuters", "url": "https://reuters.com/a", "credibilidad": "alta", "tendencia": "centro"},
        {"medio": "Diario Raro", "url": "https://diario-raro-xyz.tld/n", "credibilidad": "media",
         "tendencia": "centro", "manipulacion": "enganosa"},
    ]}
    assert capturar_propuestas(meta, ruta) == 1  # reuters ya está en el registro
    # repetir el mismo dominio no añade otra línea
    assert capturar_propuestas(meta, ruta) == 0
    lineas = [l for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lineas) == 1
    fila = _json.loads(lineas[0])
    assert fila["dominio"] == "diario-raro-xyz.tld"
    assert fila["credibilidad"] == "media"
    assert fila["manipulacion"] == "enganosa"  # se captura el eje de honestidad


def test_capturar_propuestas_manipulacion_default_ninguna(tmp_path):
    ruta = tmp_path / "p.jsonl"
    meta = {"fuentes": [
        {"medio": "Otro", "url": "https://otro-dominio-xyz.tld/n",
         "credibilidad": "baja", "tendencia": "centro"},  # sin manipulacion
    ]}
    assert capturar_propuestas(meta, ruta) == 1
    fila = _json.loads(ruta.read_text(encoding="utf-8").splitlines()[0])
    assert fila["manipulacion"] == "ninguna"


def test_capturar_propuestas_meta_vacia_no_rompe(tmp_path):
    ruta = tmp_path / "p.jsonl"
    assert capturar_propuestas(None, ruta) == 0
    assert capturar_propuestas({}, ruta) == 0


def test_registro_incluye_fuentes_institucionales():
    for url in (
        "https://www.banrep.gov.co/es/el-banco",
        "https://www.registraduria.gov.co/",
        "https://www.boe.es/diario_boe/",
        "https://www.dane.gov.co/",
        "https://www.ine.es/",
    ):
        ficha = clasificar(url)
        assert ficha is not None, f"{url} debería estar registrada"
        assert ficha.tipo == "primaria_oficial"
        assert ficha.credibilidad == "alta"


def test_ningun_paraguas_de_gobierno_en_el_registro():
    """Una clave paraguas colaría cualquier subdominio como fuente oficial.

    `clasificar()` casa por sufijo, así que registrar `gob.mx` daría
    credibilidad alta y exención de tope a la oficina de prensa de cualquier
    gobierno. Entra la agencia que produce el dato, no el gobierno entero.

    Contar puntos no basta: `argentina.gob.ar` tiene dos y coló igual (caso
    real que pasó esta misma regla) porque es el portal agregado de TODO el
    Estado argentino, no la web de una agencia. Un dominio con dos puntos
    puede ser tan paraguas como uno con uno, así que además de la regla
    geométrica hace falta una lista cerrada de portales nacionales prohibidos.
    """
    import json
    from pathlib import Path
    import verificador.fuentes as fuentes_module
    registro = json.loads(
        (Path(fuentes_module.__file__).parent / "data" / "fuentes.json").read_text(encoding="utf-8")
    )
    # Excepciones: agencias internacionales y europeas bien conocidas con un solo punto.
    # Dominios de gobierno (gob.*, .gov.*) deben tener al menos 2 puntos.
    excepciones_un_punto = {"boe.es", "ine.es", "ine.mx", "congreso.es", "senado.es",
                            "bcentral.cl", "un.org", "worldbank.org", "imf.org"}
    for dominio, ficha in registro.items():
        if ficha.get("tipo") != "primaria_oficial":
            continue
        assert dominio.count(".") >= 2 or dominio in excepciones_un_punto, (
            f"{dominio} es demasiado amplio para ser una fuente primaria concreta"
        )
    # Portales-paraguas nacionales conocidos: prohibidos como clave del
    # registro sin importar cuántos puntos tengan ni qué `tipo` se les ponga.
    # Son el sitio de un gobierno entero, nunca la agencia que produce un dato.
    prohibidos = {
        "argentina.gob.ar", "gob.mx", "europa.eu", "gov.co",
        "gob.cl", "gob.pe", "gov.uk",
    }
    coladas = prohibidos & registro.keys()
    assert not coladas, (
        f"portal(es)-paraguas de gobierno en el registro: {sorted(coladas)} — "
        "entra la agencia que produce el dato, no el gobierno entero"
    )
