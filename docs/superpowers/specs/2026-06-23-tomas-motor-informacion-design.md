# Tomás — motor de información: razonamiento, acceso ampliado, respuestas concisas y verificación de fuentes

- **Fecha:** 2026-06-23
- **Estado:** Aprobado el diseño; pendiente de revisión del spec antes de planificar.
- **Proyecto:** `verificador-politico` (agente Tomás, web + CLI sobre DeepSeek).

## Contexto y estado actual

Tomás es un agente de análisis factual: recibe una pregunta o afirmación y
devuelve un veredicto basado en hechos, contrastando medios de distintas
tendencias y citando fuentes. Hoy:

- **Bucle** (`verificador/agent.py`): tool-calling sobre DeepSeek; hasta 12 pasos
  (6 en modo rápido); emite progreso por `on_step(str)`.
- **Herramientas** (`verificador/search.py`): `buscar_web` (DuckDuckGo) y
  `leer_pagina` (httpx + trafilatura). No alcanzan sitios con mucho JS,
  bloqueados, ni vídeo.
- **Prompt** (`verificador/prompts.py`): impone una respuesta larga y estructurada
  (Veredicto / Qué encontré / Qué dicen las fuentes / Análisis / Fuentes) + un
  bloque JSON final con `veredicto`, `confianza`, `fuentes[]`.
- **Web** (`verificador/server.py`, `web/`): SSE con eventos `paso` (texto),
  `respuesta`, `moderacion`, `error`. Memoria de conversación por sesión en
  `_SESIONES[sid]`. El frontend dibuja sello, confianza y medidor de espectro
  desde el JSON.

## Objetivos

1. **Razonar mejor y más rápido**: plan breve, búsquedas en paralelo, ir antes a
   la fuente primaria, menos vueltas.
2. **Acceso a más información**: leer sitios con JS/bloqueados y leer el contenido
   de vídeos (YouTube/Shorts/TikTok) por su **transcripción/subtítulos/metadatos**.
3. **Respuestas concisas y adaptadas a la consulta**: veredicto en una línea +
   explicación breve, longitud proporcional a la pregunta.
4. **Verificación por el usuario**: citas inline numeradas y poder ver el extracto
   exacto del que Tomás sacó cada dato.
5. **Mejor animación de búsqueda**: traza viva por fuentes, no líneas planas.

## No objetivos / decisiones tomadas

- **IA descartable**: sin perfil de usuario ni personalización persistente entre
  sesiones. Se mantiene **solo la memoria de la conversación de la sesión actual**
  (ya existente en `_SESIONES`). "Adaptarse a la persona" = atender lo que pide
  ese mensaje/esa conversación, no recordar a nadie.
- **Visión de vídeo (analizar fotogramas) = Fase 2**, fuera de alcance. Ahora solo
  texto/transcripción.
- **Acceso a sitios difíciles = navegador headless local (Playwright/Chromium)**,
  no servicios de terceros. Se mitiga la latencia con ruta rápida primero +
  navegador persistente.
- Modelo: se mantiene **DeepSeek**. La velocidad se gana por pasos/paralelismo y
  concisión. Cambiar de modelo queda como palanca opcional futura, no en alcance.

## Diseño por componente

### 1. Razonamiento + velocidad — `agent.py`, `prompts.py`

- El prompt guía a Tomás a: (a) **planear** brevemente qué verificar; (b) lanzar
  **varias `buscar_web` en el mismo turno** (el bucle ya itera sobre múltiples
  `tool_calls`); (c) abrir solo las fuentes primarias necesarias; (d) sintetizar.
- Bajar el tope de pasos: `max_pasos` riguroso 12 → **8**; rápido 6 → **4**.
- `_ejecutar_tool` seguirá despachando; se añade la herramienta de vídeo (§2).
- **Sin cambios** en la estructura del bucle salvo: `on_step` pasa a recibir un
  **dict estructurado** en vez de un string (ver §4), y los resultados de lectura
  alimentan el mapa de extractos (ver §5).

### 2. Acceso ampliado — `search.py`

- **`leer_pagina` se vuelve enrutador** con dos niveles:
  1. **Ruta rápida**: httpx + trafilatura con timeout corto (~8 s).
  2. **Fallback**: si la ruta rápida falla, da texto vacío, o detecta muro de JS,
     usa **Playwright (Chromium)**: renderiza, espera red en reposo, extrae el
     texto principal (trafilatura sobre el HTML renderizado).
  - **Chromium persistente**: un único navegador lanzado de forma perezosa a
     nivel de módulo y reutilizado entre lecturas (no se arranca por llamada). Se
     cierra al apagar el proceso.
- **Nueva herramienta `ver_video(url)`** (expuesta al modelo por tool-schema):
  - **YouTube / Shorts**: extrae la **transcripción** vía
    `youtube-transcript-api` (rápido, sin navegador) + título/autor; si no hay
    transcripción, cae a metadatos.
  - **TikTok / otros**: Playwright extrae subtítulos visibles, descripción, autor
    y texto en pantalla disponible.
  - Devuelve texto plano (transcripción/resumen) que el modelo trata como una
    fuente más.
- El modelo decide cuándo llamar a `ver_video` (cuando la URL es de vídeo) vs
  `leer_pagina`.

### 3. Respuesta concisa y adaptada — `prompts.py`

- **Nuevo formato de salida**:
  - **Una línea de veredicto** (con su emoji/etiqueta).
  - **Explicación breve y directa**, cuya extensión es **proporcional a la
    complejidad de la pregunta**. Preguntas simples → respuesta de 1–3 frases.
    Solo se amplía cuando la consulta lo pide o el matiz lo exige.
  - **Citas inline numeradas** `[1]`, `[2]` en el punto donde se usa cada dato.
  - **Se eliminan del prose** las secciones fijas largas y la lista "Fuentes":
    las fuentes viven en el JSON y las pinta la UI.
- **Adaptación sin memoria**: el prompt instruye inferir, del propio mensaje y de
  la conversación de la sesión, el tono/profundidad/ángulo que necesita esa
  persona. No se construye ni guarda perfil.
- **Contrato JSON** (ampliado, sigue siendo el último bloque ```json):
  ```json
  {
    "veredicto": "verdadero|falso|enganoso|fuera_de_contexto|prediccion|sin_evidencia",
    "confianza": 0,
    "resumen": "una frase",
    "pais": "ISO o nombre",
    "fuentes": [
      {"n": 1, "medio": "...", "tendencia": "izquierda|centro-izquierda|centro|centro-derecha|derecha|verificador|internacional", "url": "https://...", "coincide": true}
    ]
  }
  ```
  - `n` numera la fuente y **debe coincidir** con las citas `[n]` del texto.
  - El orden de `fuentes` sigue el de aparición de las citas.

### 4. Animación de búsqueda — SSE + frontend

- `on_step(dict)` y el server emiten un evento SSE **`traza`** con forma:
  ```json
  {"id": "s3", "tipo": "busqueda|pagina|video", "estado": "buscando|leyendo|ok|fallo",
   "titulo": "…", "url": "https://…", "dominio": "elpais.com"}
  ```
- El frontend renderiza cada fuente como una **tarjeta viva**: dominio (+favicon
  `https://www.google.com/s2/favicons?domain=…`), título, y estado animado
  (buscando → leyendo → ✓/✗) con barra/pulso. Sustituye a las líneas de texto.
- Compatibilidad: se conserva un texto legible por accesibilidad.

### 5. Verificación de fuentes — server + frontend

- Cada lectura emite su **extracto exacto** dentro del propio evento `traza` con
  estado `ok` (campo `extracto`, lo que ya produce `leer_pagina`/`ver_video`,
  truncado a ~1500 caracteres para el cliente). El frontend **acumula un mapa
  `url → {extracto, titulo}`** a medida que llegan; no hay un evento aparte.
- En la respuesta final, el frontend:
  - convierte cada `[n]` del texto en un **enlace clicable** a la fuente `n`;
  - junto a cada fuente, un control **"ver de dónde salió"** que despliega el
    extracto leído (match por URL);
  - mantiene el medidor de espectro y los árbitros ya existentes.

## Flujo de datos (resumen)

```
usuario → POST /api/verificar (sid, pregunta, pais, rigor)
  server → Verificador.preguntar(on_step=dict)
    agent → buscar_web (paralelo) ──emite traza{busqueda}
          → leer_pagina/ver_video ──emite traza{pagina|video, ok, extracto}
          → respuesta (prose con [n]) + bloque JSON
  server → SSE: traza* (cada lectura ok lleva su extracto) … respuesta
  cliente → tarjetas vivas (acumula url→extracto) → sello+confianza+citas[n] enlazadas → espectro → "ver de dónde salió"
```

## Dependencias nuevas

- `playwright` (+ `playwright install chromium`, ~300 MB).
- `youtube-transcript-api`.
- Añadir a `requirements.txt` y nota de instalación de Chromium en el README.

## Rendimiento

- Ruta rápida primero; Playwright solo como fallback.
- Chromium **persistente** y reutilizado (sin coste de arranque por lectura).
- Búsquedas en paralelo y menos pasos.
- Respuesta más corta = menos tokens de salida = menos latencia.

## Manejo de errores

- Playwright no instalado / Chromium ausente → mensaje claro al modelo y a la UI;
  la ruta rápida sigue funcionando (degradación elegante).
- Vídeo sin transcripción → se reporta "sin transcripción disponible", no se
  inventa.
- Timeouts de fallback acotados para no colgar la respuesta.

## Pruebas

- **Unidad**: enrutador de `leer_pagina` (rápida vs fallback con HTML simulado);
  `ver_video` con un vídeo de transcripción conocida; parseo del nuevo formato
  (prose conciso + `[n]` + JSON con `n`).
- **Integración**: una verificación real end-to-end emite eventos `traza`
  estructurados y un `respuesta` con citas que casan con `fuentes[].n`.
- **Frontend**: manual — tarjetas vivas, citas clicables, "ver de dónde salió".

## Palancas futuras (fuera de alcance)

- Fase 2: comprensión visual de vídeo (modelo multimodal).
- Cambio de modelo por velocidad.
