from verificador.prompts import SYSTEM_PROMPT


def test_prompt_pide_concision_citas_y_n():
    p = SYSTEM_PROMPT.lower()
    assert "concis" in p or "breve" in p
    assert "[1]" in SYSTEM_PROMPT  # ejemplo de cita inline
    assert '"n"' in SYSTEM_PROMPT   # campo n en el JSON
    assert "no guard" in p or "sin memoria" in p or "no construyas" in p
    # Ya NO debe imponer las secciones largas fijas:
    assert "Qué dicen las fuentes:" not in SYSTEM_PROMPT
