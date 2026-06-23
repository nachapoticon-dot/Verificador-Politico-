"""Interfaz de línea de comandos interactiva para el verificador."""

from __future__ import annotations

import sys

import openai

from .agent import Verificador
from .config import cargar_config

BANNER = """\
╔══════════════════════════════════════════════════════════════╗
║   Verificador Político                                       ║
║   Agente de IA sin tendencia que verifica hechos (cualquier  ║
║   país) · funciona con DeepSeek                              ║
╚══════════════════════════════════════════════════════════════╝

Hazme una pregunta sobre política de cualquier país y buscaré en la
web, contrastaré medios de distintas tendencias y te diré qué es
verdad, qué es falso y qué está sacado de contexto.

Comandos:
  /pais XX   fija un país (código ISO, p. ej. AR, MX, ES) para sesgar
             la búsqueda  ·  /pais off  para quitarlo
  /nuevo     olvidar la conversación
  /salir
"""

# Códigos de color ANSI.
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

# Icono por tipo de paso de la traza de investigación.
_ICONOS = {"busqueda": "🔎", "pagina": "📄", "video": "🎬"}


def _formatear_paso(ev: dict) -> str:
    """Convierte un evento de traza (dict estructurado) en una línea legible.

    Robusto ante claves ausentes: cae a lo que haya (titulo → dominio → url).
    """
    if not isinstance(ev, dict):  # defensivo: contrato antiguo (str)
        return str(ev)
    icono = _ICONOS.get(ev.get("tipo") or "", "•")
    estado = ev.get("estado") or ""
    etiqueta = ev.get("titulo") or ev.get("dominio") or ev.get("url") or ""
    partes = [p for p in (icono, estado, etiqueta) if p]
    return " ".join(partes)


def _leer_pregunta() -> str | None:
    try:
        return input(f"\n{_BOLD}Tú ›{_RESET} ").strip()
    except (EOFError, KeyboardInterrupt):
        return None


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])

    # Permite "--pais XX" en cualquier posición.
    country: str | None = None
    if "--pais" in argv:
        i = argv.index("--pais")
        if i + 1 < len(argv):
            country = argv[i + 1]
            del argv[i : i + 2]

    if cargar_config() is None:
        print(
            "No encontré DEEPSEEK_API_KEY. Opciones:\n"
            "  · export DEEPSEEK_API_KEY=...\n"
            "  · crea un .env en este proyecto con la clave\n"
            "  · o déjala en el .env.local de EdifcIA (se lee automáticamente)",
            file=sys.stderr,
        )
        return 1

    agente = Verificador(country=country)

    # Modo pregunta única: verificador "¿es verdad que...?"
    if argv:
        return _responder(agente, " ".join(argv))

    # Modo interactivo
    print(BANNER)
    if country:
        print(f"{_DIM}País fijado: {country}{_RESET}")
    while True:
        pregunta = _leer_pregunta()
        if pregunta is None or pregunta in {"/salir", "/exit", "/quit"}:
            print("\nHasta luego.")
            return 0
        if not pregunta:
            continue
        if pregunta in {"/nuevo", "/new", "/reset"}:
            agente.reiniciar()
            print("Conversación reiniciada.")
            continue
        if pregunta.startswith("/pais"):
            partes = pregunta.split()
            if len(partes) < 2:
                actual = agente.country or "ninguno (global)"
                print(f"País actual: {actual}. Uso: /pais XX  ·  /pais off")
            elif partes[1].lower() in {"off", "global", "none"}:
                agente.country = None
                print("País quitado: búsqueda global.")
            else:
                agente.country = partes[1].upper()
                print(f"País fijado: {agente.country}.")
            continue
        _responder(agente, pregunta)
    return 0


def _responder(agente: Verificador, pregunta: str) -> int:
    def on_step(ev: dict) -> None:
        print(f"{_DIM}  {_formatear_paso(ev)}{_RESET}", flush=True)

    print(f"\n{_BOLD}Verificador ›{_RESET} {_DIM}(investigando…){_RESET}")
    try:
        respuesta = agente.preguntar(pregunta, on_step=on_step)
    except openai.AuthenticationError:
        print("\n[Clave de DeepSeek inválida o sin permisos.]", file=sys.stderr)
        return 1
    except openai.RateLimitError:
        print(
            "\n[Límite de DeepSeek alcanzado (o sin saldo). Espera e intenta de nuevo.]",
            file=sys.stderr,
        )
        return 1
    except openai.APIError as e:
        print(f"\n[Error de la API de DeepSeek: {e}]", file=sys.stderr)
        return 1
    print()
    print(respuesta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
