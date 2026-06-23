#!/usr/bin/env python3
"""Punto de entrada del Verificador Político (cualquier país).

Uso:
    python main.py                          # modo interactivo (chat)
    python main.py "¿es verdad que ...?"     # pregunta única
    python main.py --pais AR "¿es verdad ...?"  # sesga la búsqueda a un país
"""

from verificador.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
