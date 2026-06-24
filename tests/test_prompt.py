from verificador.prompts import SYSTEM_PROMPT


def test_prompt_clasifica_pregunta_y_pondera_credibilidad():
    p = SYSTEM_PROMPT
    pl = p.lower()
    # veredicto informativo para preguntas sin afirmación:
    assert "informativo" in p
    assert "afirmaci" in pl  # menciona afirmación vs pregunta
    # ponderación por credibilidad y trato de baja/no fiable:
    assert "credibilidad" in pl
    assert "no_fiable" in p
    assert "wikipedia" in pl  # punto de partida, no prueba
    # el JSON de cierre incluye el campo credibilidad por fuente:
    assert '"credibilidad"' in p


def test_prompt_pide_concision_citas_y_n():
    p = SYSTEM_PROMPT.lower()
    assert "concis" in p or "breve" in p
    assert "[1]" in SYSTEM_PROMPT  # ejemplo de cita inline
    assert '"n"' in SYSTEM_PROMPT   # campo n en el JSON
    assert "no guard" in p or "sin memoria" in p or "no construyas" in p
    # Ya NO debe imponer las secciones largas fijas:
    assert "Qué dicen las fuentes:" not in SYSTEM_PROMPT


def test_instruccion_modo_textos_por_eje():
    from verificador.prompts import instruccion_modo
    corta = instruccion_modo("corta", "simple")
    assert corta.startswith("[Modo de respuesta] ")
    assert "1-2 frases" in corta
    assert "lenguaje llano" in corta.lower()
    det = instruccion_modo("detallada", "tecnico")
    assert "varios párrafos" in det
    assert "metodología" in det.lower()


def test_instruccion_modo_cae_al_default_si_invalido():
    from verificador.prompts import instruccion_modo
    assert instruccion_modo("xxx", "yyy") == instruccion_modo("corta", "simple")


def test_prompt_prohibe_encabezados_markdown():
    from verificador.prompts import SYSTEM_PROMPT
    pl = SYSTEM_PROMPT.lower()
    assert "encabezados markdown" in pl
    assert "###" in SYSTEM_PROMPT
    # el largo ya no se hardcodea: se delega al modo de cada consulta
    assert "modo de respuesta" in pl
