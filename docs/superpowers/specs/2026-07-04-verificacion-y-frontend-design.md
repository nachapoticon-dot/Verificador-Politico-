# Mejoras del sistema de verificación y del frontend de Faro

Fecha: 2026-07-04 · Estado: aprobado por el usuario

## Contexto

Faro es un verificador de hechos políticos: agente DeepSeek con tool-calling
(`buscar_web` / `leer_pagina` / `ver_video`), servidor FastAPI con SSE y
frontend React + Tailwind (estética editorial papel manila). La auditoría
detectó que el contrato del veredicto (bloque ```json final) es frágil y sin
validación, la confianza es un número que el modelo se inventa, la respuesta
final no llega en streaming, la búsqueda no tiene caché ni paralelismo, y en el
frontend las opciones de respuesta viven lejos del composer, el `resumen` del
JSON nunca se muestra y la lista de fuentes es una sopa de chips ilegible.

Alcance frontend limitado por el usuario a: opciones de respuesta del agente,
aspecto visual de las respuestas y muestra de los sitios verificados. El resto
de la interfaz (hero, avatar, marca) no se toca.

## Parte A — Sistema de verificación (backend)

### A1. Contrato robusto + citas válidas

Nuevo módulo `verificador/veredicto.py` con la lógica de post-proceso de la
respuesta final:

- **Validación del meta**: parsea el bloque ```json final (reutilizando
  `fuentes.extraer_meta`) y valida esquema y tipos: `veredicto` dentro del
  vocabulario, `confianza` numérica 0-100, `fuentes` lista de objetos con `n`
  entero y `url` string. Los campos inválidos se normalizan o descartan campo a
  campo (no todo-o-nada).
- **Reparación (una sola vez)**: si el bloque JSON falta o no parsea, se hace
  UNA llamada extra al modelo con la respuesta y la instrucción "emite solo el
  bloque JSON con este esquema". Si también falla, la respuesta viaja sin meta
  (la UI ya degrada a detectar el sello por emoji).
- **Consistencia de citas**: comprueba que cada `[n]` de la prosa exista en
  `fuentes` y viceversa. Las citas huérfanas se registran (log) y las fuentes
  jamás citadas se conservan pero se marcan (`citada: false`) para que la UI
  pueda distinguirlas.
- **Normalización de URLs compartida**: función única (host sin `www.`, sin
  parámetros de tracking `utm_*`/`fbclid`/`gclid`, sin `/` final, sin
  fragmento) usada por: el emparejado extracto↔fuente, la caché de páginas
  (A4) y el frontend (misma regla portada a `lib/format.ts`). El servidor
  adjunta a cada fuente del meta su extracto de la traza ya emparejado
  (`extracto`), para que el frontend no tenga que casar URLs.

El pipeline queda: respuesta cruda del modelo → `veredicto.procesar()` →
`{prosa, meta validado y enriquecido}` → SSE. El CLI usa el mismo módulo.

### A2. Confianza fundamentada

`veredicto.py` recalcula la confianza a partir de las fuentes del meta:

- Base: suma de fuentes con `coincide: true`, ponderadas por credibilidad
  (alta=1.0, media=0.6, baja=0.25, no_fiable=0).
- Bono si entre las que coinciden hay tendencias opuestas (izquierda/derecha o
  cualquiera + verificador): el contraste real sube la confianza.
- Penalización si el apoyo depende de fuentes con `manipulacion` engañosa o
  desinformadora (estas nunca suman; solo restan solidez global).
- Se reescala a 0-100 con techo asintótico (3-4 fuentes buenas y contrastadas ≈
  90; nunca 100).
- La credibilidad/manipulación usada es la del **registro curado**
  (`fuentes.clasificar`) cuando el dominio está registrado; la autoevaluación
  del modelo solo se usa para dominios no registrados.

El número mostrado es el calculado. El del modelo se conserva en el meta como
`confianza_modelo` (diagnóstico). Veredictos `informativo` y `no_verificable`
siguen sin mostrar confianza.

### A3. Streaming de la respuesta final

- `agent.preguntar()` pasa a llamar la API con `stream=True` en todas las
  vueltas. Los fragmentos de contenido se reenvían vía `on_step` como eventos
  `{"tipo": "delta", "texto": ...}` SOLO mientras no aparezcan tool_calls en el
  stream (si aparecen, los deltas de esa vuelta se descartan y se ejecutan las
  herramientas como hasta ahora).
- `server.py` emite eventos SSE `delta` con cada fragmento y al final el evento
  `respuesta` completo actual (con el meta ya validado por A1/A2), que
  sobreescribe lo acumulado — así el frontend viejo o el CLI siguen
  funcionando sin cambios.
- Frontend: `useVerificador` acumula deltas en `turno.respuesta` con estado
  nuevo `"respondiendo"`; `format.ts` oculta todo desde "```json" aunque el
  bloque esté incompleto. El sello y las fuentes solo se pintan al llegar
  `respuesta`.

### A4. Búsqueda más sólida

- **Caché de páginas**: en `search.py`, caché en memoria con TTL (~15 min) y
  tope de entradas, keyed por URL normalizada (A1), para `leer_pagina` y
  `ver_video`. Evita re-descargar lo mismo dentro de una consulta "a fondo" y
  entre consultas cercanas.
- **Reintentos**: `buscar_web` reintenta hasta 2 veces con backoff corto ante
  excepción de `ddgs`; `_leer_rapido` reintenta 1 vez ante error de red (no
  ante 4xx).
- **Herramientas en paralelo**: cuando el modelo pide varias tool_calls en el
  mismo turno, `agent.py` las ejecuta con `ThreadPoolExecutor` (máx. 4). Los
  eventos de traza de inicio se emiten todos antes de lanzar, y los de fin al
  completar cada una. `buscar_web` y `leer_pagina` ya son thread-safe; el
  navegador Playwright ya serializa por su cola de hilo propietario.

## Parte B — Frontend (alcance acotado)

Identidad intacta: papel manila, Fraunces/Newsreader/Space Mono, color fuerte
solo en el veredicto. El elemento firma del rediseño es la **ficha de fuentes
tipo periódico** (B3).

### B1. Opciones de respuesta → al composer, un solo eje

- El masthead queda solo con la marca (se elimina `CONTROLES` de la cabecera).
- En el composer, bajo el textarea, un segmentado único de 3 presets que mapean
  a los parámetros existentes de la API (sin cambio de backend):

  | Preset | rigor | largo | detalle |
  |---|---|---|---|
  | Esencial | rapido | corta | simple |
  | Normal (defecto) | riguroso | normal | simple |
  | A fondo | riguroso | detallada | tecnico |

- Microtexto en `title` por opción: Esencial "menos fuentes, respuesta en
  segundos"; Normal "contraste completo, un párrafo"; A fondo "contexto,
  matices y cifras".
- El preset elegido persiste durante la sesión (estado en `App`).

### B2. Aspecto visual de las respuestas

- **Titular**: `meta.resumen` se muestra como titular de la respuesta en
  Fraunces (tamaño ~1.5rem), entre el sello y la prosa. Si falta, no se
  reserva hueco.
- **Sello como fallo editorial**: banda única con filete superior grueso
  (3px) del color del veredicto; dentro, etiqueta del veredicto (mono,
  mayúsculas) + confianza integrada a la derecha ("confianza 82" + barra
  fina). Sustituye a pill + barrita sueltas.
- **Citas visibles**: `[n]` deja de ser superíndice: enlace con recuadro
  sutil (borde 1px, radio pequeño, color faro), `title` = nombre del medio.
- **País junto a la firma**: "Faro verifica · Colombia" usando `meta.pais`
  (mapeado a nombre si es código ISO conocido; si no, tal cual). Sin país, la
  firma queda como hoy.

### B3. Sitios verificados → tabla editorial compacta (elemento firma)

Sustituye la lista de chips por una ficha tipo periódico con filetes finos:

- Cabecera: "FUENTES CONTRASTADAS · N" (mono, tracking ancho).
- Una fila por fuente, columnas: `[n]` (mono) · favicon + medio (enlace) ·
  tendencia abreviada (c-izq, c-der, verif., int., —) · relación ("✓ respalda"
  en verde tinta / "· matiza" en gris) · control de expandir (⌄) si hay
  extracto.
- **Solo se anuncia lo anómalo**: credibilidad `baja`/`no_fiable` y cualquier
  `manipulacion` distinta de `ninguna` aparecen como aviso rojo/ámbar en la
  fila; credibilidad alta/media y manipulación ninguna no pintan nada.
- Fuentes con `citada: false` (A1) se muestran atenuadas al final.
- Fila expandida: el extracto como cita en Newsreader itálica, con enlace
  "abrir ↗". Sin `<details>` nativo: expansión controlada para animarla.
- Favicons: mismo servicio actual (Google s2) — mejora futura, fuera de
  alcance.
- Móvil (≤600px): cada fila colapsa a dos líneas (medio + relación arriba,
  tendencia y avisos abajo).

## Orden de ejecución y pruebas

1. **A1** contrato + normalización de URLs (base de todo) — pytest para
   validación, reparación, consistencia de citas y normalización.
2. **A2** confianza calculada — pytest con casos de contraste/eco/manipulación.
3. **A3** streaming y **A4** búsqueda, independientes entre sí.
4. **B1 → B2 → B3** frontend (B2/B3 consumen el meta enriquecido de A1/A2).

Cada fase pasa la suite existente (`pytest`, `node tests/test_citas.mjs`) más
sus tests nuevos, y el frontend se verifica con `npm run build` y revisión
visual en el navegador.

## Fuera de alcance

Cancelación al desconectar el cliente, timeout global por consulta, ampliación
del registro de fuentes y tooling de curación, favicons propios, cambios en
hero/marca/avatar. Quedan anotados como mejoras futuras.
