# tests/test_veredicto.py
from verificador.veredicto import partir, validar_meta, marcar_citas, adjuntar_extractos, aplicar_registro, calcular_solidez, Procesado, procesar


def _evidencia(n, dominio, **extra):
    base = {
        "n": n,
        "url": f"https://{dominio}/nota-{n}",
        "citada": True,
        "extracto": "Texto efectivamente leído",
        "registro_curado": True,
        "coincide": True,
        "credibilidad": "alta",
        "manipulacion": "ninguna",
    }
    return {**base, **extra}


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


def test_validar_meta_no_coacciona_strings_a_booleanos_y_deduplica_n():
    meta = validar_meta({"fuentes": [
        {"n": 1, "coincide": "false", "url": "https://a.com"},
        {"n": 1, "coincide": True, "url": "https://b.com"},
    ]})
    assert len(meta["fuentes"]) == 1
    assert meta["fuentes"][0]["coincide"] is False


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


def test_solidez_cero_sin_fuentes_que_coincidan():
    assert calcular_solidez({"tipo": "afirmacion", "fuentes": []}) == 0
    assert calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com", coincide=False),
    ]}) == 0


def test_solidez_una_fuente_alta_es_media():
    c = calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com"),
    ]})
    assert 40 <= c <= 55


def test_solidez_contraste_izq_der_sube():
    sin_contraste = calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com", tendencia="izquierda"),
        _evidencia(2, "b.com", tendencia="centro-izquierda"),
    ]})
    con_contraste = calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com", tendencia="izquierda"),
        _evidencia(2, "b.com", tendencia="derecha"),
    ]})
    assert con_contraste > sin_contraste


def test_solidez_tres_buenas_contrastadas_ronda_90_y_nunca_100():
    c = calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com", tendencia="izquierda"),
        _evidencia(2, "b.com", tendencia="derecha"),
        _evidencia(3, "c.com", tendencia="verificador"),
    ]})
    assert 85 <= c < 100


def test_fuentes_deshonestas_no_suman_y_penalizan():
    solo_desinfo = calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com", manipulacion="desinformadora"),
    ]})
    assert solo_desinfo == 0
    limpia = calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com"),
    ]})
    con_lastre = calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com"),
        _evidencia(2, "b.com", manipulacion="enganosa"),
    ]})
    assert con_lastre < limpia


def test_sin_tendencia_no_cuenta_como_contraste():
    """Una fuente sin tendencia no es "otra tendencia": no dispara el bono."""
    sin_tendencia = calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com", tendencia="verificador"),
        _evidencia(2, "b.com"),
    ]})
    dos_reales = calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com", tendencia="verificador"),
        _evidencia(2, "b.com", tendencia="centro"),
    ]})
    assert dos_reales > sin_tendencia


def test_solidez_ignora_no_leidas_no_citadas_y_dominios_duplicados():
    valida = _evidencia(1, "a.com")
    no_leida = _evidencia(2, "b.com", extracto="")
    no_citada = _evidencia(3, "c.com", citada=False)
    duplicada = _evidencia(4, "a.com")
    assert calcular_solidez({"tipo": "afirmacion", "fuentes": [valida, no_leida, no_citada, duplicada]}) == calcular_solidez({"tipo": "afirmacion", "fuentes": [valida]})


def test_evidencia_que_matiza_reduce_solidez():
    limpia = calcular_solidez({"tipo": "afirmacion", "fuentes": [_evidencia(1, "a.com")]})
    matizada = calcular_solidez({"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com"),
        _evidencia(2, "b.com", coincide=False),
    ]})
    assert matizada < limpia


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
    assert p.meta["solidez_modelo"] == 90
    assert p.meta["solidez"] != 90             # recalculada (1 fuente alta ≈ 48)
    assert p.meta["evidencia"]["leidas"] == 1
    assert p.texto.startswith("Es falso [1].")
    assert '"solidez_modelo": 90' in p.texto


def test_procesar_repara_una_vez_si_falta_el_json():
    llamadas = []

    def reparar(prosa):
        llamadas.append(prosa)
        return '```json\n{"tipo": "pregunta", "fuentes": []}\n```'

    p = procesar("Solo prosa sin bloque.", reparar=reparar)
    assert llamadas == ["Solo prosa sin bloque."]
    assert p.meta["tipo"] == "pregunta"


def test_procesar_acepta_reparacion_con_json_pelado():
    p = procesar("Prosa.", reparar=lambda _: '{"veredicto": "falso", "fuentes": []}')
    # El veredicto reparado sobrevive intacto: ya no se sobrescribe con
    # "sin_evidencia" solo por no haber evidencia leída (esa era la puerta
    # destructiva que esta tarea elimina).
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


def test_aplicar_registro_expone_el_tipo_de_fuente():
    meta = {"fuentes": [{"n": 1, "url": "https://www.banrep.gov.co/es/el-banco"}]}
    aplicar_registro(meta)
    assert meta["fuentes"][0]["tipo_fuente"] == "primaria_oficial"


def test_primaria_oficial_no_sufre_el_tope_de_no_curada():
    """El tope de 0.6 castiga lo no revisado; una institucional no lo necesita.

    Ojo: `_evidencia` pone `registro_curado: True` por defecto, y con eso el
    tope no se aplica a NADIE y el test pasaría sin probar nada. Hay que
    forzarlo a False en los dos lados para que la comparación signifique algo.
    """
    oficial = _evidencia(1, "banrep.gov.co", registro_curado=False,
                         tipo_fuente="primaria_oficial")
    medio = _evidencia(1, "cualquiermedio.com", registro_curado=False,
                       tipo_fuente="medio")
    curada = _evidencia(1, "reuters.com", registro_curado=True)
    assert (calcular_solidez({"tipo": "afirmacion", "fuentes": [oficial]})
            > calcular_solidez({"tipo": "afirmacion", "fuentes": [medio]}))
    # Y pesa exactamente igual que una curada de credibilidad alta.
    assert (calcular_solidez({"tipo": "afirmacion", "fuentes": [oficial]})
            == calcular_solidez({"tipo": "afirmacion", "fuentes": [curada]}))


def test_validar_meta_acepta_tipo():
    m = validar_meta({"tipo": "mecanismo", "fuentes": []})
    assert m["tipo"] == "mecanismo"
    assert "veredicto" not in m


def test_tipo_invalido_cae_a_afirmacion():
    assert validar_meta({"tipo": "cualquier-cosa", "fuentes": []})["tipo"] == "afirmacion"
    assert validar_meta({"fuentes": []})["tipo"] == "afirmacion"


def test_una_pregunta_no_arrastra_veredicto():
    """Aunque el modelo mande un veredicto en una pregunta, se descarta."""
    m = validar_meta({"tipo": "pregunta", "veredicto": "verdadero", "fuentes": []})
    assert m["tipo"] == "pregunta"
    assert "veredicto" not in m


def test_afirmacion_conserva_su_veredicto():
    m = validar_meta({"tipo": "afirmacion", "veredicto": "falso", "fuentes": []})
    assert m["veredicto"] == "falso"


def test_informativo_ya_no_es_veredicto_valido():
    m = validar_meta({"tipo": "afirmacion", "veredicto": "informativo", "fuentes": []})
    assert "veredicto" not in m


def test_mecanismo_con_una_primaria_oficial_da_solidez_alta():
    """El criterio de aceptación del diseño: esto ya no puede dar 33."""
    meta = {"tipo": "mecanismo", "fuentes": [
        _evidencia(1, "banrep.gov.co", tipo_fuente="primaria_oficial", tendencia="centro"),
    ]}
    assert calcular_solidez(meta) >= 75


def test_afirmacion_con_una_sola_fuente_no_da_solidez_alta():
    """En disputa, una sola fuente nunca basta, por buena que sea."""
    meta = {"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "banrep.gov.co", tipo_fuente="primaria_oficial"),
    ]}
    assert calcular_solidez(meta) < 60


def test_mecanismo_solo_con_wikipedia_no_da_solidez_alta():
    meta = {"tipo": "mecanismo", "fuentes": [
        _evidencia(1, "wikipedia.org", credibilidad="baja", tipo_fuente="enciclopedia_editable"),
    ]}
    # El valor real es 18; un margen de 32 puntos (< 50) no detectaría una
    # regresión que subiera la curva. < 25 sigue dejando holgura sin ser ciego.
    assert calcular_solidez(meta) < 25


def test_afirmacion_contrastada_sigue_subiendo():
    meta = {"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com", tendencia="izquierda"),
        _evidencia(2, "b.com", tendencia="derecha"),
        _evidencia(3, "c.com", tendencia="verificador"),
    ]}
    assert 85 <= calcular_solidez(meta) < 100


def test_solidez_sin_fuentes_es_cero_en_los_tres_tipos():
    for t in ("afirmacion", "pregunta", "mecanismo"):
        assert calcular_solidez({"tipo": t, "fuentes": []}) == 0


def test_un_muro_no_leido_no_da_solidez():
    meta = {"tipo": "mecanismo", "fuentes": [
        _evidencia(1, "banrep.gov.co", tipo_fuente="primaria_oficial", extracto=""),
    ]}
    assert calcular_solidez(meta) == 0


def test_calcular_solidez_aguanta_tipos_inesperados():
    """Los campos vienen de un modelo de lenguaje: pueden ser cualquier cosa.

    veredicto.py es el último paso antes del usuario y no puede lanzar nunca.
    """
    basura = [1, None, [], {}, True, 3.5, object()]
    for valor in basura:
        for campo in ("credibilidad", "manipulacion", "tendencia", "url",
                      "extracto", "coincide", "tipo_fuente"):
            meta = {"tipo": "mecanismo", "fuentes": [_evidencia(1, "a.com", **{campo: valor})]}
            calcular_solidez(meta)          # no debe lanzar
    for forma in (["x"], [None], 1, "texto", {"a": 1}, None):
        calcular_solidez({"tipo": "afirmacion", "fuentes": forma})
    for m in (None, 1, "x", []):
        calcular_solidez(m)


def test_desinformadoras_no_corroboran_en_la_curva_explicativa():
    """Contarlas por cabezas llevaba la respuesta al techo del sistema."""
    sola = {"tipo": "mecanismo", "fuentes": [_evidencia(1, "a.com")]}
    con_basura = {"tipo": "mecanismo", "fuentes": [
        _evidencia(1, "a.com"),
        _evidencia(2, "b.com", manipulacion="desinformadora"),
        _evidencia(3, "c.com", manipulacion="desinformadora"),
    ]}
    assert calcular_solidez(con_basura) == calcular_solidez(sola)


def test_lo_que_contradice_resta_tambien_en_la_curva_explicativa():
    limpia = {"tipo": "mecanismo", "fuentes": [_evidencia(1, "a.com")]}
    contradicha = {"tipo": "mecanismo", "fuentes": [
        _evidencia(1, "a.com"),
        _evidencia(2, "b.com", coincide=False),
    ]}
    assert calcular_solidez(contradicha) < calcular_solidez(limpia)


def test_la_prosa_sobrevive_sin_evidencia_abierta():
    """Lo que el modelo escribió no se destruye jamás: se anota."""
    texto = ('El Banco de la República es el banco central [1].\n\n```json\n'
             '{"tipo": "mecanismo", "confianza": 90, "fuentes": '
             '[{"n": 1, "url": "https://banrep.gov.co/x", "coincide": true}]}\n```')
    p = procesar(texto)
    assert "banco central" in p.prosa
    assert "reformul" not in p.prosa.lower()
    assert p.meta["aviso"]["codigo"] == "sin_abrir"
    assert p.meta["solidez"] == 0


def test_aviso_distingue_no_encontrar_de_no_poder_abrir():
    sin_nada = procesar('Texto.\n\n```json\n{"tipo": "pregunta", "fuentes": []}\n```')
    assert sin_nada.meta["aviso"]["codigo"] == "nada_encontrado"


def test_sin_aviso_cuando_hay_evidencia_abierta():
    texto = ('Es falso [1].\n\n```json\n'
             '{"tipo": "afirmacion", "veredicto": "falso", "fuentes": '
             '[{"n": 1, "url": "https://reuters.com/x", "coincide": true}]}\n```')
    p = procesar(texto, extractos={"https://reuters.com/x": "Texto leído de verdad"})
    assert "aviso" not in p.meta
    assert p.meta["solidez"] > 0


def test_validar_meta_aguanta_fuentes_que_no_son_lista():
    """El bloque JSON lo escribe un modelo: `fuentes` puede llegar como
    número, booleano o texto, e iterar sobre eso lanzaría."""
    for basura in (42, True, "texto", {"a": 1}, 3.5, None):
        m = validar_meta({"tipo": "afirmacion", "fuentes": basura})
        assert m["fuentes"] == []


def test_procesar_aguanta_fuentes_que_no_son_lista():
    """Y el pipeline entero tampoco puede romperse por eso: la prosa sobrevive."""
    p = procesar('Una respuesta.\n\n```json\n{"tipo": "pregunta", "fuentes": 42}\n```')
    assert p.prosa == "Una respuesta."
