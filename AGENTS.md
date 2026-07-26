# Faro — guía para agentes

Verificador de hechos sobre política. Backend Python (FastAPI + SSE), frontend
React + Vite. Un solo desarrollador. El README explica qué es y cómo instalarlo;
esto explica cómo trabajar en él sin pisar minas.

## Comandos

```bash
.venv/bin/python -m pytest -q        # backend (herméticas, sin red)
cd frontend && npm run check         # contratos SSE + oxlint + build
.venv/bin/python scripts/humo.py     # contrato contra la API real (gasta tokens)
uvicorn verificador.server:app --reload
```

**Usa `python -m pytest`, nunca `.venv/bin/pytest`.** Los ejecutables del
entorno llevan la ruta absoluta en su shebang y este proyecto ya se movió de
carpeta una vez: están rotos. `.venv/bin/python` es un enlace y sí funciona.

## Estado conocido

`tests/test_lectura.py::test_navegador_reutilizado_entre_hilos` **falla, y es
preexistente.** Usa una URL `file://` y el guardia SSRF (`search.py:_url_publica`)
rechaza todo lo que no sea http/s hacia una IP global, así que nunca llega a
Playwright. No lo arregles debilitando el guardia: hay que hacerlo inyectable.
Mientras tanto, 104 de 105 en verde es el estado esperado.

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

El diseño del siguiente nivel está en
`docs/superpowers/specs/2026-07-26-faro-siguiente-nivel-design.md`: pipeline de
razonamiento en cuatro etapas, contrato nuevo de veredicto (`tipo` separado de
`veredicto`, `solidez` en vez de `confianza`) y rediseño del control de esfuerzo.
Léelo antes de tocar `veredicto.py`, `prompts.py` o `agent.py`.
