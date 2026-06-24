from verificador.moderation import es_irrespetuoso, mensaje_limite


def test_detecta_insulto_y_respeta_excepcion():
    assert es_irrespetuoso("eres estupido") is True
    assert es_irrespetuoso("esa noticia es una mierda") is False
    assert es_irrespetuoso("¿es verdad que bajó el paro?") is False


def test_primer_aviso_es_firme_no_blando():
    m = mensaje_limite(1)
    assert "buena onda" not in m.lower()      # ya no es blando
    assert "respeto" in m.lower()


def test_repeticion_cierra_la_conversacion():
    m = mensaje_limite(2)
    ml = m.lower()
    assert "cierr" in ml or "cerrad" in ml or "termin" in ml
    # y se mantiene firme también para strikes mayores
    assert mensaje_limite(3) == m
