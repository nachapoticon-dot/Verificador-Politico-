"""Utilidades compartidas de los tests."""
from types import SimpleNamespace


def _chunk(content=None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def stream_de(content=None, tool_calls=None):
    """Iterador de chunks con la forma del stream de OpenAI/DeepSeek.

    ``tool_calls``: lista de tuplas ``(id, nombre, argumentos)``. Cada una se
    parte en dos chunks (cabecera con id+nombre, luego los argumentos), como
    hace la API real. ``content`` se trocea en fragmentos de 7 caracteres.
    """
    chunks = []
    for i, (id_, nombre, args) in enumerate(tool_calls or []):
        chunks.append(_chunk(tool_calls=[SimpleNamespace(
            index=i, id=id_, function=SimpleNamespace(name=nombre, arguments=""))]))
        chunks.append(_chunk(tool_calls=[SimpleNamespace(
            index=i, id=None, function=SimpleNamespace(name=None, arguments=args))]))
    if content:
        for j in range(0, len(content), 7):
            chunks.append(_chunk(content=content[j:j + 7]))
    return iter(chunks)
