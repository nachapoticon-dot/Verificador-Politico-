# tests/test_veredicto.py
from verificador.veredicto import partir, validar_meta, marcar_citas


def test_partir_separa_prosa_y_meta():
    texto = 'Es falso [1].\n\n```json\n{"veredicto": "falso", "fuentes": []}\n```'
    prosa, meta = partir(texto)
    assert prosa == "Es falso [1]."
    assert meta == {"veredicto": "falso", "fuentes": []}


def test_partir_sin_bloque_devuelve_meta_none():
    assert partir("solo prosa") == ("solo prosa", None)


def test_partir_json_invalido_devuelve_meta_none():
    prosa, meta = partir("prosa\n\n```json\n{mal\n```")
    assert prosa == "prosa"
    assert meta is None


def test_partir_json_que_no_es_dict_devuelve_none():
    assert partir('x\n\n```json\n[1, 2]\n```')[1] is None


def test_validar_meta_normaliza_campos():
    meta = validar_meta({
        "veredicto": " Falso ",
        "confianza": "85.4",
        "resumen": " La cifra es inventada. ",
        "pais": "CO",
        "fuentes": [
            {"n": "1", "medio": "Reuters", "url": "https://reuters.com/a",
             "credibilidad": "ALTA", "manipulacion": "Ninguna",
             "tendencia": "Centro", "coincide": True},
        ],
    })
    assert meta["veredicto"] == "falso"
    assert meta["confianza"] == 85
    assert meta["resumen"] == "La cifra es inventada."
    assert meta["pais"] == "CO"
    f = meta["fuentes"][0]
    assert f["n"] == 1 and f["coincide"] is True
    assert f["credibilidad"] == "alta" and f["manipulacion"] == "ninguna"
    assert f["tendencia"] == "centro"


def test_validar_meta_descarta_lo_invalido_campo_a_campo():
    meta = validar_meta({
        "veredicto": "veredicto-inventado",
        "confianza": "no-numero",
        "resumen": "",
        "fuentes": [
            {"n": "x", "url": "https://a.com"},          # n no numérico: fuera
            {"n": 2, "url": "javascript:alert(1)"},       # url no http: se quita la url
            "no-es-dict",
            {"n": 3, "credibilidad": "altisima"},          # cred fuera de vocabulario: fuera
        ],
    })
    assert "veredicto" not in meta
    assert meta["confianza"] == 0
    assert "resumen" not in meta
    ns = [f["n"] for f in meta["fuentes"]]
    assert ns == [2, 3]
    assert "url" not in meta["fuentes"][0]
    assert "credibilidad" not in meta["fuentes"][1]


def test_validar_meta_acota_confianza():
    assert validar_meta({"confianza": 250})["confianza"] == 100
    assert validar_meta({"confianza": -5})["confianza"] == 0


def test_validar_meta_no_dict_es_none():
    assert validar_meta(None) is None
    assert validar_meta([1]) is None
    assert validar_meta("x") is None


def test_marcar_citas_pone_citada_por_fuente():
    meta = {"fuentes": [{"n": 1}, {"n": 2}, {"n": 3}]}
    marcar_citas("Según [1] y también [3].", meta)
    assert [f["citada"] for f in meta["fuentes"]] == [True, False, True]


def test_marcar_citas_huerfanas_se_loguean_sin_romper(caplog):
    import logging
    meta = {"fuentes": [{"n": 1}]}
    with caplog.at_level(logging.WARNING, logger="verificador.veredicto"):
        marcar_citas("Dato [1] y dato [7].", meta)
    assert "7" in caplog.text
    assert meta["fuentes"][0]["citada"] is True


def test_marcar_citas_sin_fuentes_no_rompe():
    meta = {"fuentes": []}
    assert marcar_citas("Texto [1].", meta) == {"fuentes": []}
