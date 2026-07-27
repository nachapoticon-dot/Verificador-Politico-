# Faro

Faro es un agente de verificación política sin memoria entre consultas. Busca
información actual, abre las fuentes, contrasta evidencia y devuelve una
conclusión con citas y una medida auditable de solidez.

Su objetivo es aplicar una metodología neutral y conservadora. No promete
infalibilidad ni sustituye la lectura directa de las fuentes.

## Capacidades

- Verificación política para cualquier país, con jurisdicción automática o fija.
- Afirmaciones, pero también preguntas y peticiones de explicación sobre
  asuntos públicos: no hace falta traer una afirmación para usarlo.
- Búsqueda web y lectura de artículos, páginas dinámicas y vídeos de YouTube.
- Contraste entre fuentes primarias, verificadores y medios de distintas líneas.
- Tres tipos de consulta: `afirmacion`, `pregunta` y `mecanismo`. El sello
  (verdadero, falso, engañoso, fuera de contexto, predicción, sin evidencia)
  solo se estampa en el primero: lo demás no lleva etiqueta porque no hay nada
  que juzgar.
- Solidez de la evidencia, calculada solo con fuentes abiertas, citadas y
  deduplicadas, con dos curvas: confirmaciones independientes para una
  afirmación en disputa, la mejor fuente disponible para una explicación.
- Registro curado de credibilidad, tendencia y manipulación por dominio.
- Streaming de la investigación y la respuesta mediante SSE.
- Protección contra URLs internas, entradas excesivas y consultas concurrentes.

## Arquitectura

```text
React + Vite
     │  POST /api/verificar
     ▼
FastAPI + SSE
     │
     ▼
Agente DeepSeek ──► DuckDuckGo / páginas / vídeos
     │
     ▼
Validación de citas, fuentes y solidez
```

Cada consulta es independiente. El frontend mantiene el hilo únicamente en
memoria durante la sesión del navegador; no construye perfiles ni entrena con
las preguntas del usuario.

## Instalación

Requiere Python 3.10+ y Node.js 22+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
cd frontend
npm install
npm run build
cd ..
```

Configura `DEEPSEEK_API_KEY` en `.env` o en el entorno. Por compatibilidad, la
aplicación también puede leerla desde `EDIFICIA_DIR/.env.local`.

El modelo por defecto es `deepseek-v4-flash`. DeepSeek retira nombres de modelo
con periodo de gracia corto —`deepseek-chat` y `deepseek-reasoner` dejaron de
existir el 2026-07-24 y toda consulta falló—, así que ante un error
`invalid_request_error` lo primero es comprobar qué modelos siguen vivos:

```bash
python scripts/humo.py
```

## Ejecución

Interfaz web:

```bash
uvicorn verificador.server:app --reload
```

Abre `http://127.0.0.1:8000`.

Desarrollo frontend con recarga automática:

```bash
cd frontend
npm run dev
```

CLI interactivo o consulta única:

```bash
python main.py
python main.py --pais AR "¿Milei eliminó el Banco Central?"
```

En el CLI, `/pais XX` fija el país, `/pais off` lo quita y `/salir` termina la
sesión.

## Verificación

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run check
```

Usa `python -m pytest`, no `.venv/bin/pytest`: los ejecutables del entorno
llevan la ruta absoluta incrustada en su shebang y dejan de funcionar si mueves
el proyecto de carpeta. `.venv/bin/python` sí sobrevive (es un enlace).

`npm run check` ejecuta las pruebas del contrato SSE, lint y build de producción.

## Estructura

```text
├── main.py                  Entrada del CLI
├── verificador/
│   ├── agent.py             Orquestación del modelo y herramientas
│   ├── search.py            Búsqueda, lectura web y vídeo
│   ├── veredicto.py         Contrato, citas y solidez
│   ├── fuentes.py           Registro de fuentes
│   ├── prompts.py           Metodología del agente
│   ├── server.py            API FastAPI y streaming SSE
│   └── cli.py               Interfaz de terminal
├── frontend/                Interfaz React + Vite + CSS
├── tests/                   Pruebas Python y contratos frontend
├── requirements.txt
└── .env.example
```

## Límites

- La calidad depende de las fuentes disponibles y de que puedan abrirse.
- Una clasificación editorial por dominio es orientativa, no una garantía sobre
  cada artículo.
- Una fuente leída puede contener errores; Faro muestra extractos y enlaces para
  que la evidencia pueda revisarse.
- Si no consigue evidencia trazable, la respuesta no se borra nunca: se conserva
  con la solidez a 0 y un aviso que distingue no haber encontrado nada
  (`nada_encontrado`) de no haber podido abrir lo que encontró (`sin_abrir`).
