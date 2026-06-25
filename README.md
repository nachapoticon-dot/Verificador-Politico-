# Verificador Político

Un agente de IA **sin tendencia política** que verifica hechos sobre la
actualidad política de **cualquier país**. Le haces una pregunta, busca en la
web, **contrasta medios de distintas tendencias** (derecha, izquierda, centro y
verificadores independientes) y responde con un veredicto basado en hechos,
citando siempre sus fuentes.

Sirve para preguntas como *"¿es verdad que el candidato X va a privatizar la
educación?"* o *"¿Milei eliminó el Banco Central?"*: separa lo que alguien
**dijo** de lo que le **atribuyen**, y explica si algo es siquiera posible
institucionalmente en ese país.

## Qué hace distinto

- **No toma partido.** Su única lealtad son los hechos. Nunca insinúa a quién votar.
- **Cualquier país.** Detecta la jurisdicción de la pregunta y adapta los medios
  y el análisis institucional a ese país. Puedes fijar uno con `--pais`.
- **Contrasta tendencias.** Busca cómo cubren el mismo hecho medios de derecha y
  de izquierda, y prioriza verificadores de la red IFCN (ColombiaCheck,
  Chequeado, Maldita, PolitiFact, AFP Factual…).
- **Recuerda la veracidad de cada sitio.** Lleva un registro curado con dos ejes
  por fuente: su **credibilidad** (qué tan precisa) y su **manipulación** (qué tan
  honesta: ninguna, sesgo, engañosa, desinformadora). Pondera lo que lee con
  ambos y nunca sostiene un veredicto sobre una fuente desinformadora.
- **Va a la fuente primaria.** Para declaraciones busca la cita completa, no el
  titular, y detecta lo sacado de contexto.
- **Evalúa lo que "va a pasar".** Explica si una promesa o un miedo de campaña es
  jurídica y constitucionalmente posible (casi ningún cargo legisla solo).
- **Etiqueta cada respuesta:** ✅ Verdadero · ❌ Falso · ⚠️ Engañoso ·
  🔀 Sacado de contexto · 🔮 Predicción / no comprobable · ❓ Sin evidencia.

## Cómo funciona

- **Modelo: DeepSeek** (`deepseek-chat`), vía API compatible con OpenAI.
- **Búsqueda propia:** como DeepSeek no tiene búsqueda web nativa, el agente usa
  herramientas propias por *function calling* — `buscar_web` (DuckDuckGo, sin
  API key) y `leer_pagina` (descarga y extrae el texto principal). Verás la
  traza de investigación en vivo (qué busca, qué lee).
- **Claves:** reutiliza tu `DEEPSEEK_API_KEY`. La busca en este orden: variable
  de entorno → `.env` local → `.env.local` del proyecto EdifcIA (son proyectos
  separados; este solo lee la clave, no toca EdifcIA).

## Instalación

Requiere Python 3.10+.

```bash
cd verificador-politico
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# La clave se toma de EdifcIA automáticamente; o ponla tú:
# export DEEPSEEK_API_KEY=sk-...
```

## Uso

Modo chat:

```bash
python main.py
```

Pregunta única (con país opcional para sesgar la búsqueda):

```bash
python main.py --pais AR "¿es verdad que Milei eliminó el Banco Central?"
python main.py "¿es verdad que el candidato X va a privatizar la educación?"
```

Cada pregunta es independiente (el agente no guarda memoria entre consultas).
Dentro del chat: `/pais XX` fija el país por defecto, `/pais off` lo quita,
`/salir` cierra.

### Interfaz web ("Tomás")

Además del CLI hay una interfaz web —**Tomás**, un agente de análisis: le das una
pregunta o una afirmación y devuelve una respuesta factual validada fuente por
fuente. Transmite la traza de validación en vivo (qué busca, qué lee) y dibuja el
veredicto, las fuentes contrastadas y un **aviso de honestidad** por fuente. Es
una app **React + Tailwind + shadcn** (en `frontend/`) que el servidor FastAPI
sirve ya construida.

```bash
# 1) construir el frontend (una vez, o tras cambiarlo)
cd frontend && npm install && npm run build && cd ..
# 2) levantar el servidor (sirve frontend/dist y la API en /api)
uvicorn verificador.server:app --reload
# abre http://127.0.0.1:8000
```

Para desarrollar el frontend con recarga en caliente: `cd frontend && npm run
dev` (Vite proxya `/api` al uvicorn del 8000). Eliges rigor (rápido / a fondo),
largo y detalle desde la propia página.

## Estructura

```
verificador-politico/
├── main.py                 # punto de entrada del CLI
├── verificador/
│   ├── agent.py            # bucle de tool-calling sobre DeepSeek (sin estado)
│   ├── search.py           # herramientas buscar_web / leer_pagina / ver_video
│   ├── prompts.py          # metodología, neutralidad, autenticidad
│   ├── config.py           # carga de la clave (incl. desde EdifcIA)
│   ├── fuentes.py          # registro de credibilidad/manipulación por fuente
│   ├── server.py           # servidor web (FastAPI + SSE), sirve frontend/dist
│   └── cli.py              # interfaz de terminal
├── frontend/               # interfaz "Tomás" (React + Tailwind + shadcn, Vite)
│   ├── src/                # componentes, hook de SSE, tema de Tomás
│   └── dist/               # build que sirve el servidor (npm run build)
├── requirements.txt
└── .env.example
```

## Límites honestos

- La IA puede equivocarse: úsalo como punto de partida. Por eso **siempre cita
  fuentes** — verifícalas tú también.
- Depende de lo que haya en la web (vía DuckDuckGo); si un tema es muy nuevo o
  nadie lo ha reportado, dirá "sin evidencia suficiente" en lugar de inventar.
- La clasificación de tendencia de cada medio es orientativa.
- DeepSeek no tiene búsqueda nativa; la calidad depende de los resultados de
  DuckDuckGo y de las páginas que se logren leer.
```
