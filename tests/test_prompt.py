from verificador.prompts import SYSTEM_PROMPT


def test_prompt_clasifica_pregunta_y_pondera_credibilidad():
    from verificador.prompts import SYSTEM_PROMPT
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
