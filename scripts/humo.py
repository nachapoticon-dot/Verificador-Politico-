#!/usr/bin/env python3
"""Prueba de humo contra la API real: ¿sigue existiendo el contrato que Faro usa?

La suite de pytest es hermética (no toca la red), así que no puede ver que el
proveedor retire un modelo o cambie el formato de las respuestas. Esto sí. El
2026-07-24 DeepSeek retiró `deepseek-chat` y Faro empezó a fallar en todas las
consultas sin que ningún test se enterara.

Comprueba, en orden y parando en el primer fallo:

  1. Hay clave y configuración.
  2. El modelo configurado está entre los que la API ofrece hoy.
  3. Responde a una llamada simple.
  4. Sabe pedir herramientas con el esquema de `verificador/search.py`.
  5. Streaming y tool calls conviven.

Uso:
    python scripts/humo.py              # comprueba el modelo configurado
    python scripts/humo.py --modelo X   # comprueba otro

Sale con 0 si todo pasa, 1 si algo falla. Consume unos pocos céntimos de
tokens: es una llamada real, no un mock.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verificador.config import cargar_config  # noqa: E402
from verificador.search import TOOL_SCHEMAS  # noqa: E402

OK, FALLO = "  ✓", "  ✗"


def _salir(mensaje: str) -> None:
    print(f"{FALLO} {mensaje}")
    raise SystemExit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modelo", help="modelo a probar (por defecto, el configurado)")
    args = ap.parse_args()

    print("Prueba de humo de Faro contra la API real\n")

    # 1. Configuración
    cfg = cargar_config()
    if cfg is None:
        _salir(
            "No hay DEEPSEEK_API_KEY (ni en el entorno, ni en .env, ni en el "
            ".env.local de EdifcIA). Copia .env.example a .env y pon tu clave."
        )
    modelo = args.modelo or cfg.model
    print(f"  base_url: {cfg.base_url}")
    print(f"  modelo:   {modelo}")
    print(f"{OK} configuración cargada\n")

    from openai import OpenAI

    cliente = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)

    # 2. ¿El modelo sigue existiendo? Esta es la comprobación que faltaba.
    try:
        disponibles = sorted(m.id for m in cliente.models.list().data)
    except Exception as e:  # noqa: BLE001
        _salir(f"no pude listar modelos: {type(e).__name__}: {str(e)[:200]}")
    print(f"  la API ofrece: {', '.join(disponibles)}")
    if modelo not in disponibles:
        _salir(
            f"'{modelo}' NO está disponible. Actualiza DEFAULT_MODEL en "
            f"verificador/config.py o la variable DEEPSEEK_MODEL."
        )
    print(f"{OK} '{modelo}' sigue disponible\n")

    # 3. Llamada simple
    try:
        r = cliente.chat.completions.create(
            model=modelo,
            messages=[{"role": "user", "content": "Responde solo: ok"}],
            max_tokens=400,
            temperature=0.0,
        )
    except Exception as e:  # noqa: BLE001
        _salir(f"la llamada simple falló: {type(e).__name__}: {str(e)[:200]}")
    if not (r.choices[0].message.content or "").strip():
        _salir("la llamada simple devolvió contenido vacío")
    print(f"{OK} responde a una llamada simple\n")

    # 4. Function calling con NUESTRO esquema real
    try:
        r = cliente.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": "Busca siempre antes de responder."},
                {"role": "user", "content": "¿Quién preside Colombia ahora mismo?"},
            ],
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.0,
        )
    except Exception as e:  # noqa: BLE001
        _salir(f"function calling falló: {type(e).__name__}: {str(e)[:200]}")
    llamadas = r.choices[0].message.tool_calls or []
    if not llamadas:
        _salir(
            "el modelo NO pidió ninguna herramienta ante una pregunta de "
            "actualidad. Faro depende de que las pida: revisa TOOL_SCHEMAS."
        )
    print(f"  pidió: {', '.join(t.function.name for t in llamadas)}")
    print(f"{OK} function calling con el esquema de Faro\n")

    # 5. Streaming + tools, y si trae razonamiento visible
    try:
        stream = cliente.chat.completions.create(
            model=modelo,
            messages=[{"role": "user", "content": "En una frase: ¿qué es un banco central?"}],
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            stream=True,
            max_tokens=600,
        )
        n_txt = n_raz = 0
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            d = chunk.choices[0].delta
            if getattr(d, "content", None):
                n_txt += 1
            if getattr(d, "reasoning_content", None):
                n_raz += 1
    except Exception as e:  # noqa: BLE001
        _salir(f"el streaming falló: {type(e).__name__}: {str(e)[:200]}")
    if n_txt == 0 and n_raz == 0:
        _salir("el streaming no entregó ningún delta")
    print(f"  deltas de contenido: {n_txt} · de razonamiento: {n_raz}")
    print(f"{OK} streaming y herramientas conviven\n")

    if n_raz:
        print("  Nota: este modelo expone razonamiento en vivo "
              "(`reasoning_content`), que Faro puede mostrar en la traza.")
    else:
        print("  Nota: este modelo NO expuso razonamiento por deltas; la traza "
              "solo podrá mostrar los artefactos de cada etapa.")

    print("\nTodo en orden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
