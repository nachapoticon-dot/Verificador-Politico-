# tests/test_veredicto.py
from verificador.veredicto import partir, validar_meta, marcar_citas, adjuntar_extractos, aplicar_registro, calcular_confianza, Procesado, procesar


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


def test_aplicar_registro_sobreescribe_dominios_curados():
    # reuters.com está en el registro con credibilidad alta (ver test_fuentes).
    meta = {"fuentes": [
        {"n": 1, "url": "https://www.reuters.com/a", "credibilidad": "baja",
         "manipulacion": "sesgo", "tendencia": "derecha"},
        {"n": 2, "url": "https://dominio-no-registrado-xyz.tld/n",
         "credibilidad": "media"},
    ]}
    aplicar_registro(meta)
    f1, f2 = meta["fuentes"]
    assert f1["credibilidad"] == "alta"          # manda el registro curado
    assert f1["manipulacion"] == "ninguna"
    assert f2["credibilidad"] == "media"          # no registrado: queda el del modelo


def test_adjuntar_extractos_casa_por_url_normalizada():
    meta = {"fuentes": [
        {"n": 1, "url": "https://elpais.com/nota?utm_source=tw"},
        {"n": 2, "url": "https://otro.com/x"},
    ]}
    extractos = {"https://www.elpais.com/nota/": "TEXTO LEÍDO"}
    adjuntar_extractos(meta, extractos)
    assert meta["fuentes"][0]["extracto"] == "TEXTO LEÍDO"
    assert "extracto" not in meta["fuentes"][1]


def test_adjuntar_extractos_sin_datos_no_rompe():
    meta = {"fuentes": [{"n": 1}]}
    adjuntar_extractos(meta, None)
    adjuntar_extractos(meta, {})
    assert "extracto" not in meta["fuentes"][0]


def test_confianza_cero_sin_fuentes_que_coincidan():
    assert calcular_confianza({"fuentes": []}) == 0
    assert calcular_confianza({"fuentes": [
        {"n": 1, "coincide": False, "credibilidad": "alta"},
    ]}) == 0


def test_confianza_una_fuente_alta_es_media():
    c = calcular_confianza({"fuentes": [
        {"n": 1, "coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"},
    ]})
    assert 40 <= c <= 55


def test_confianza_contraste_izq_der_sube():
    base = {"coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"}
    sin_contraste = calcular_confianza({"fuentes": [
        {"n": 1, "tendencia": "izquierda", **base},
        {"n": 2, "tendencia": "centro-izquierda", **base},
    ]})
    con_contraste = calcular_confianza({"fuentes": [
        {"n": 1, "tendencia": "izquierda", **base},
        {"n": 2, "tendencia": "derecha", **base},
    ]})
    assert con_contraste > sin_contraste


def test_confianza_tres_buenas_contrastadas_ronda_90_y_nunca_100():
    base = {"coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"}
    c = calcular_confianza({"fuentes": [
        {"n": 1, "tendencia": "izquierda", **base},
        {"n": 2, "tendencia": "derecha", **base},
        {"n": 3, "tendencia": "verificador", **base},
    ]})
    assert 85 <= c < 100


def test_fuentes_deshonestas_no_suman_y_penalizan():
    solo_desinfo = calcular_confianza({"fuentes": [
        {"n": 1, "coincide": True, "credibilidad": "alta",
         "manipulacion": "desinformadora"},
    ]})
    assert solo_desinfo == 0
    limpia = calcular_confianza({"fuentes": [
        {"n": 1, "coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"},
    ]})
    con_lastre = calcular_confianza({"fuentes": [
        {"n": 1, "coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"},
        {"n": 2, "coincide": True, "credibilidad": "alta", "manipulacion": "enganosa"},
    ]})
    assert con_lastre < limpia


def test_sin_tendencia_no_cuenta_como_contraste():
    """Una fuente sin tendencia no es "otra tendencia": no dispara el bono."""
    base = {"coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"}
    sin_tendencia = calcular_confianza({"fuentes": [
        {"n": 1, "tendencia": "verificador", **base},
        {"n": 2, **base},
    ]})
    dos_reales = calcular_confianza({"fuentes": [
        {"n": 1, "tendencia": "verificador", **base},
        {"n": 2, "tendencia": "centro", **base},
    ]})
    assert dos_reales > sin_tendencia


def test_procesar_pipeline_completo():
    texto = ('Es falso [1].\n\n```json\n'
             '{"veredicto": "falso", "confianza": 90, "resumen": "Inventado.",'
             ' "pais": "CO", "fuentes": [{"n": 1, "medio": "Reuters",'
             ' "url": "https://www.reuters.com/a?utm_source=x",'
             ' "credibilidad": "baja", "tendencia": "derecha", "coincide": true}]}'
             '\n```')
    p = procesar(texto, extractos={"https://reuters.com/a": "LO QUE LEYÓ"})
    assert isinstance(p, Procesado)
    assert p.prosa == "Es falso [1]."
    f = p.meta["fuentes"][0]
    assert f["credibilidad"] == "alta"        # registro curado manda
    assert f["extracto"] == "LO QUE LEYÓ"     # casó por URL normalizada
    assert f["citada"] is True
    assert p.meta["confianza_modelo"] == 90
    assert p.meta["confianza"] != 90           # recalculada (1 fuente alta ≈ 48)
    assert p.texto.startswith("Es falso [1].")
    assert '"confianza_modelo": 90' in p.texto


def test_procesar_repara_una_vez_si_falta_el_json():
    llamadas = []

    def reparar(prosa):
        llamadas.append(prosa)
        return '```json\n{"veredicto": "informativo", "fuentes": []}\n```'

    p = procesar("Solo prosa sin bloque.", reparar=reparar)
    assert llamadas == ["Solo prosa sin bloque."]
    assert p.meta["veredicto"] == "informativo"


def test_procesar_acepta_reparacion_con_json_pelado():
    p = procesar("Prosa.", reparar=lambda _: '{"veredicto": "falso", "fuentes": []}')
    assert p.meta["veredicto"] == "falso"


def test_procesar_degrada_si_la_reparacion_falla():
    p = procesar("Prosa.", reparar=lambda _: None)
    assert p.meta is None
    assert p.texto == "Prosa."
    p2 = procesar("Prosa.", reparar=lambda _: (_ for _ in ()).throw(RuntimeError()))
    assert p2.meta is None


def test_procesar_sin_reparador_devuelve_prosa():
    p = procesar("Prosa sin json.")
    assert p == Procesado("Prosa sin json.", "Prosa sin json.", None)
