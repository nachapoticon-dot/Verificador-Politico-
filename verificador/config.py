"""Carga de configuración y claves para el verificador (DeepSeek).

Resuelve la clave de DeepSeek de varias fuentes, en orden:
  1. La variable de entorno DEEPSEEK_API_KEY.
  2. Un archivo .env / .env.local en la raíz de este proyecto.
  3. El .env.local del proyecto EdifcIA (ruta configurable con EDIFICIA_DIR).

Así el verificador reutiliza la clave que ya tienes en EdifcIA sin duplicarla y
sin tocar ese proyecto: son cosas aparte. No usamos python-dotenv para no añadir
dependencias.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Ruta por defecto al proyecto EdifcIA (sobreescribible con EDIFICIA_DIR).
_DEFAULT_EDIFICIA_DIR = Path.home() / "Proyectos" / "EdifcIA"

# DeepSeek es compatible con la API de OpenAI.
DEFAULT_BASE_URL = "https://api.deepseek.com"
# Modelo público de DeepSeek que soporta function calling (búsqueda por tools).
DEFAULT_MODEL = "deepseek-chat"


@dataclass
class Config:
    api_key: str
    base_url: str
    model: str


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parsea un archivo .env simple (CLAVE=valor) ignorando comentarios."""
    valores: dict[str, str] = {}
    if not path.is_file():
        return valores
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valor = valor.strip().strip('"').strip("'")
        if clave.strip():
            valores[clave.strip()] = valor
    return valores


def _buscar_valor(clave: str) -> str | None:
    """Busca una variable en: entorno → .env local → .env.local de EdifcIA."""
    if os.environ.get(clave):
        return os.environ[clave]

    aqui = Path(__file__).resolve().parent.parent
    for nombre in (".env", ".env.local"):
        valores = _parse_env_file(aqui / nombre)
        if valores.get(clave):
            return valores[clave]

    edificia = Path(os.environ.get("EDIFICIA_DIR", _DEFAULT_EDIFICIA_DIR))
    valores = _parse_env_file(edificia / ".env.local")
    return valores.get(clave)


def cargar_config() -> Config | None:
    """Devuelve la Config de DeepSeek, o None si no hay clave en ningún lado."""
    api_key = _buscar_valor("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    base_url = _buscar_valor("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL
    model = _buscar_valor("DEEPSEEK_MODEL") or DEFAULT_MODEL
    return Config(api_key=api_key, base_url=base_url, model=model)
