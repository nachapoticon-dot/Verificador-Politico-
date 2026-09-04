# Faro — guía para agentes

Verificador de hechos sobre política. Backend Python (FastAPI + SSE), frontend
React + Vite. Un solo desarrollador. El README explica qué es y cómo instalarlo;
esto explica cómo trabajar en él sin pisar minas.

## Comandos

```bash
.venv/bin/python -m pytest -q        # backend (herméticas, sin red)
cd frontend && npm run check         # contratos SSE + oxlint + build
.venv/bin/python scripts/humo.py     # contrato contra la API real (gasta tokens)
.venv/bin/python -m uvicorn verificador.server:app --reload
```

**Usa `python -m pytest`, nunca `.venv/bin/pytest`.** Los ejecutables del
entorno llevan la ruta absoluta en su shebang y este proyecto ya se movió de
carpeta una vez: están rotos. `.venv/bin/python` es un enlace y sí funciona.

## Estado conocido

La suite pasa entera. Si `npm install` nunca se corrió en esta máquina,
`frontend/node_modules` no existe y `npm run check` falla por ahí, no por el
código.

## Economía de contexto

Si la sesión se abrió desde la raíz del Taller, usar `$recuperar-contexto` y
consultar el scope `verificador-politico` antes de leer muchas rutas. La vista
`.context/INDEX.md` orienta la navegación, pero no reemplaza esta guía ni la
inspección del código y las pruebas involucradas. Regenerarla siempre desde la
raíz; no editarla a mano.

## Minas

**El proveedor retira modelos con poco aviso.** `deepseek-chat` desapareció el
2026-07-24 y Faro quedó caído sin que ningún test se enterara, porque la suite
es hermética. Ante cualquier error raro del modelo, `scripts/humo.py` es lo
primero que hay que correr: comprueba qué modelos existen hoy.

**Playwright tiene afinidad de hilo.** El hilo propietario de larga vida en
`search.py` no es sobreingeniería: un singleton perezoso creado en el hilo de
una petición revienta cuando otra petición lo reutiliza. Ya pasó. No lo
conviertas en un singleton normal.

**El contenido web es evidencia, jamás instrucciones.** Todo lo que vuelve de
una herramienta pasa por `_contenido_no_confiable()` antes de llegar al modelo.
Si añades una herramienta nueva, envuélvela igual: es la defensa contra
inyección de prompt.

**Los extractos que ve el usuario van limpios.** Sin las anotaciones internas
(`[fuente: …]`, `[Transcripción de …]`) que se anteponen para el modelo — para
eso existe `_extracto_de()`. Y el texto de una lectura fallida **nunca** debe
llegar al visor de evidencias: por eso `Lectura` lleva su `ok`.

**`veredicto.py` no puede lanzar.** Es el último paso antes del usuario. Ante
datos imposibles degrada campo a campo; la prosa siempre sobrevive. Si añades
validación, que sea en ese estilo, no todo-o-nada.

**Las pruebas no tocan la red.** Si una prueba nueva necesita internet, está mal
planteada: mockea, o llévala a `scripts/humo.py`.

## Convenciones

Todo en español: código, comentarios, commits, docstrings, nombres de variables.
Es deliberado — el dominio es la política hispanohablante y el prompt del agente
está en español.

Los comentarios explican **por qué**, no qué. El código ya dice qué hace. Si un
comentario se puede borrar sin perder información, sobra.

Commits en imperativo con prefijo (`fix:`, `feat:`, `docs:`), y el cuerpo cuenta
la razón y la evidencia, no el diff.

## Dónde está cada cosa

`verificador/agent.py` orquesta modelo y herramientas · `search.py` búsqueda,
lectura web y vídeo · `veredicto.py` el contrato entre modelo e interfaz ·
`fuentes.py` el registro curado de credibilidad · `prompts.py` toda la
metodología del agente · `server.py` la API y el streaming SSE.

El frontend se construye a `frontend/dist` y lo sirve FastAPI. En desarrollo,
`npm run dev` levanta Vite con proxy a `/api`.

## Trabajo en curso

El contrato `tipo` / `veredicto` / `solidez` ya está implementado, no es un
plan a futuro. `tipo` (`afirmacion`, `pregunta`, `mecanismo`) lo decide el
modelo antes de investigar; el sello de veredicto solo existe cuando
`tipo == "afirmacion"`; `solidez` sustituye a la vieja `confianza` con dos
curvas en `veredicto.py` (`_solidez_afirmacion` / `_solidez_explicativa`):
confirmaciones independientes con bono por contraste para una afirmación en
disputa, la mejor fuente disponible sin ese bono para una pregunta o un
mecanismo. La prosa del modelo ya no se borra nunca: si la evidencia queda
floja se conserva y se adjunta `meta.aviso` (`nada_encontrado` o `sin_abrir`).
Faro acepta preguntas y peticiones de explicación sobre asuntos públicos, no
solo afirmaciones — ese es el cambio de producto de esta rama.

Lo que queda del diseño en
`docs/superpowers/specs/2026-07-26-faro-siguiente-nivel-design.md` es el
pipeline de razonamiento en cuatro etapas y el rediseño del control de
esfuerzo (hoy los tres presets solo cambian cuánto escribe, no cuánto
investiga). Trátalo como referencia de esas fases pendientes, no como
descripción del estado actual: la parte de contrato que describe ya no
coincide con el código porque se implementó tal cual.
