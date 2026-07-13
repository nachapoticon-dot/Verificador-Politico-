# Faro

Faro es un agente de verificación política sin memoria entre consultas. Busca
información actual, abre las fuentes, contrasta evidencia y devuelve una
conclusión con citas y una medida auditable de solidez.

Su objetivo es aplicar una metodología neutral y conservadora. No promete
infalibilidad ni sustituye la lectura directa de las fuentes.

## Capacidades

- Verificación política para cualquier país, con jurisdicción automática o fija.
- Búsqueda web y lectura de artículos, páginas dinámicas y vídeos de YouTube.
- Contraste entre fuentes primarias, verificadores y medios de distintas líneas.
- Veredictos: verdadero, falso, engañoso, fuera de contexto, predicción y sin evidencia.
- Confianza calculada solo con fuentes abiertas, citadas y deduplicadas.
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
.venv/bin/pytest -q
cd frontend && npm run check
```

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
- Si no consigue evidencia trazable, degrada la respuesta a `sin_evidencia`.
