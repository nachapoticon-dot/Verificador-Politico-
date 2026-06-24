# Modos de respuesta (largo + detalle) y formato limpio — Diseño

## Problema

Dos cosas hoy:

1. **Markdown crudo en pantalla.** El modelo emite encabezados markdown (`###`)
   que la interfaz no renderiza: `formatear()` en `web/app.js` maneja párrafos,
   `**negrita**`, enlaces y URLs sueltas, pero no encabezados, así que se muestran
   literalmente como `### Lo que sí es verificable…`. Se ve feo.
2. **No hay forma de personalizar cómo responde Tomás.** El prompt fija un largo
   "proporcional a la pregunta" (1-3 frases) y un nivel de detalle implícito, pero
   el usuario no puede elegir respuestas más cortas/largas ni más simples/técnicas.

## Objetivo

Dar un **modo de respuesta** ajustable desde la interfaz, con dos ejes ortogonales
y un modo **predeterminado**, y arreglar de raíz el render de encabezados para que
nunca más aparezca markdown crudo.

- **Largo:** `corta` | `normal` | `detallada`
- **Detalle:** `simple` | `tecnico`
- **Predeterminado al cargar:** `corta` + `simple`

`rigor` (rápido/a fondo) **no cambia**: controla cuánto investiga (número de
búsquedas y pasos), no cómo redacta. El modo de respuesta es independiente y solo
afecta la redacción final.

## Restricciones (heredadas del proyecto)

- IA descartable: el modo se lee por request (como país/rigor); sin perfil de
  usuario ni persistencia entre sesiones. Se resetea al recargar la página.
- Modelo fijo DeepSeek (`deepseek-chat`).
- No romper el caché del prompt: el `SYSTEM_PROMPT` base no se reconstruye por
  request; el modo se inyecta como instrucción breve por consulta.
- Citas `[n]` del prose siguen coincidiendo con `fuentes[].n` del JSON de cierre.
- Degradación elegante: valores de modo inválidos o ausentes caen al default sin
  romper la respuesta.
- No romper los tests actuales (38 verdes).
- Usar el venv: `.venv/bin/pytest`, `.venv/bin/python`. Front sin build:
  `node --check web/app.js`.

## Enfoque elegido

**Instrucción de modo por consulta.** El `SYSTEM_PROMPT` base queda intacto
(voz, reglas, contrato JSON). En cada pregunta se antepone una línea corta que
describe el largo y el detalle pedidos. Ventajas: no rompe el caché del prompt,
permite cambiar el modo a mitad de conversación, y mantiene la lógica aislada en
una sola función. Espeja cómo ya fluye `rigor`.

Alternativa descartada: incrustar el texto del modo dentro del `SYSTEM_PROMPT` y
reconstruirlo por request — rompe el caché y mezcla responsabilidades.

## Arquitectura y flujo de datos

```
UI (index.html: 2 segmentados)
  │  largo ∈ {corta,normal,detallada}   detalle ∈ {simple,tecnico}
  ▼
app.js  ──POST /api/verificar { pregunta, sid, pais, rigor, largo, detalle }──►
  ▼
server.py  valida largo/detalle (default corta/simple) → setea agente.largo/detalle
  ▼
agent.Verificador.preguntar()
  │  inyecta prompts.instruccion_modo(largo, detalle) como mensaje breve
  │  (NO dentro del system base → caché intacto)
  ▼
DeepSeek → prosa (sin encabezados) + JSON de cierre
  ▼
app.js: formatear() renderiza prosa; defensivo ante # sueltos
```

### Componentes

**1. UI — `web/index.html`, `web/app.js`, `web/style.css`**

Dos controles segmentados nuevos, mismo estilo `.seg-opt`/`.is-on` que el de rigor:

```
Respuesta:  [ Corta ✓ ] [ Normal ] [ Detallada ]
Detalle:    [ Simple ✓ ] [ Técnico ]
```

- Botones con `data-largo` / `data-detalle`. Default marcado: `corta` y `simple`.
- En `app.js`: variables `let largo = "corta";` y `let detalle = "simple";`,
  actualizadas por listeners igual que `rigor`. Se añaden al cuerpo del POST
  (`largo`, `detalle`).
- Se resetean al recargar (no se persisten), como rigor hoy.

**2. Server — `verificador/server.py`**

- Leer del body: `largo` validado contra `{"corta","normal","detallada"}`
  (default `"corta"` si falta/ inválido) y `detalle` contra `{"simple","tecnico"}`
  (default `"simple"`).
- Pasar al agente sobre la marcha, junto a país/rigor:
  `s["agente"].largo = largo; s["agente"].detalle = detalle`.
- `_sesion(...)` y la construcción de `Verificador(...)` aceptan los nuevos
  parámetros con defaults.

**3. Agente + prompt — `verificador/agent.py`, `verificador/prompts.py`**

- `Verificador` gana atributos `largo: str = "corta"` y `detalle: str = "simple"`
  (como `rigor`).
- Nueva función pura en `prompts.py`:
  `instruccion_modo(largo: str, detalle: str) -> str` — devuelve una línea breve
  combinando el eje de largo y el de detalle. Tolera valores fuera de vocab
  cayendo al default.
- En `preguntar()`, en cada turno, añadir un mensaje de rol `system` con la
  instrucción de modo **inmediatamente antes** del mensaje `user` de la pregunta.
  El primer mensaje de la lista (el `SYSTEM_PROMPT` base) no se modifica nunca, así
  que el prefijo cacheado se mantiene. La instrucción de modo es un mensaje aparte
  (no se concatena al contenido del usuario), para no ensuciar el turno del usuario.
- Generalizar la sección `# Cómo respondes` del `SYSTEM_PROMPT`: en vez de
  hardcodear "1-3 frases", indicar que "el largo y el nivel de detalle te los
  marca el modo de respuesta de cada consulta".

Textos de `instruccion_modo` (combinación de dos ejes en una línea):

- Largo:
  - `corta`: "Responde en 1-2 frases: el veredicto y solo el dato esencial con su
    cita; sin contexto extra."
  - `normal`: "Responde en un párrafo breve: veredicto y explicación directa con
    los datos clave citados."
  - `detallada`: "Desarrolla con el detalle que el tema exija (varios párrafos si
    hace falta): contexto, matices y las fuentes que corroboran o discrepan."
- Detalle:
  - `simple`: "Lenguaje llano para cualquiera; evita jerga; si das una cifra,
    explícala en palabras simples."
  - `tecnico`: "Incluye cifras precisas, unidades y metodología cuando aporten
    (p. ej. variación interanual, fuente del dato)."

El prefijo de la línea es algo como:
`[Modo de respuesta] {texto_largo} {texto_detalle}`

**4. Formato limpio (baseline, no es un modo) — `prompts.py` + `web/app.js`**

Doble red para que `###` nunca se vea crudo:

- *Prompt:* regla nueva en `# Cómo respondes`: "No uses encabezados markdown
  (`#`, `##`, `###`) ni tablas; solo prosa y, como mucho, `**negrita**` para
  destacar. Para enumerar, usá viñetas con `- `."
- *Front `formatear()`:* defensivo —
  - una línea que empiece con `#{1,6}\s*` se renderiza quitando los `#` y poniendo
    el texto en `**negrita**` (nunca markdown crudo);
  - soporte de viñetas: líneas que empiecen con `- ` se agrupan en una `<ul><li>`.
  - Se mantiene el escapado XSS actual (`escapar` antes de cualquier transformación).

## Manejo de errores / degradación

- `largo`/`detalle` inválidos o ausentes → default `corta`/`simple` en el server
  y también en `instruccion_modo` (defensa en profundidad).
- Si el modelo igualmente emite `###`, el front los limpia: el usuario nunca ve
  markdown crudo.
- Ningún cambio toca la captura de propuestas ni la anotación de fuentes.

## Testing

- `tests/test_prompt.py`:
  - `instruccion_modo` devuelve el texto esperado para cada largo y cada detalle,
    y cae al default ante valores fuera de vocab.
  - `SYSTEM_PROMPT` contiene la prohibición de encabezados markdown.
- `tests/test_traza.py` (o agente): `preguntar` inserta la instrucción de modo en
  la lista de mensajes (verificable con un cliente falso), y el system base no se
  altera.
- `tests/test_server.py`: el endpoint lee `largo`/`detalle` del body y tolera
  valores inválidos cayendo al default (sin llamar de más al modelo).
- Front: `node --check web/app.js`. El stripping de `#` y las viñetas se verifican
  manualmente (no hay harness JS); idealmente con un par de respuestas de ejemplo.

## Fuera de alcance (YAGNI)

- Ejes de tono y de formato visual (el usuario los descartó). El formato limpio se
  aplica como baseline único, no como opción.
- Persistencia del modo entre sesiones / perfil de usuario.
- Que "Detallada" fuerce más investigación (eso es `rigor`, se mantiene aparte).
