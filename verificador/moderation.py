"""Moderación de respeto.

El agente pone límites cuando una persona es irrespetuosa: no responde a la
grosería con grosería ni continúa la verificación, sino que pide respeto con
amabilidad y firmeza, escalando si la conducta se repite.

Es una comprobación léxica determinista (rápida y sin coste de modelo). No
pretende ser perfecta; atrapa los insultos directos más comunes. La calidez del
límite la pone el mensaje, no el castigo.
"""

from __future__ import annotations

import re
import unicodedata

# Raíces de insulto frecuentes (ES, varias regiones). Se comparan sin tildes y
# en minúsculas. Son raíces para cubrir variantes (idiota/idiotas, etc.).
_INSULTOS = [
    "idiota", "imbecil", "estupid", "tarad", "pendej", "gilipoll", "subnormal",
    "retrasad", "inutil", "cretin", "mequetref", "payaso", "ignorante de mierda",
    "mierda", "puta", "puto", "cabron", "cabrona", "malparid", "hijueputa",
    "hijo de puta", "hdp", "gonorrea", "careverga", "huevon", "boludo",
    "pelotudo", "forro ", "sorete", "mogolic", "tarup", "baboso",
    "callate", "jodete", "vete a la mierda", "andate a la mierda",
    "no servis", "no sirves", "sos basura", "eres basura", "sos un inutil",
    "eres un inutil", "estupida maquina", "maldita maquina",
]

# Frases que parecen insulto pero son uso legítimo (evita falsos positivos).
_EXCEPCIONES = [
    "esa noticia es una mierda",  # crítica a un contenido, no a la persona/agente
]


def _normalizar(texto: str) -> str:
    texto = texto.lower()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return texto


def es_irrespetuoso(texto: str) -> bool:
    norm = _normalizar(texto)
    for exc in _EXCEPCIONES:
        if _normalizar(exc) in norm:
            return False
    for raiz in _INSULTOS:
        # \b al inicio para no marcar "tarado" dentro de otra palabra inocua.
        if re.search(rf"\b{re.escape(_normalizar(raiz))}", norm):
            return True
    return False


def mensaje_limite(strikes: int) -> str:
    """Aviso firme al primer insulto; mensaje de cierre si se repite."""
    if strikes <= 1:
        return (
            "Aquí no se falta el respeto. No voy a responder a un insulto. "
            "Si quieres que verifique algo, pídemelo con respeto y lo hago."
        )
    return (
        "Esto se termina aquí: ya te pedí respeto y seguiste. Cierro la "
        "conversación. Si quieres retomar, empieza de nuevo y con buen trato."
    )
