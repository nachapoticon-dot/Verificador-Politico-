# Faro: del buscador al razonamiento

Diseño aprobado el 2026-07-26.

## Problema

Faro reúne fuentes, las clasifica y las resume. No razona. Recopila.

Tres síntomas, con su causa localizada en el código:

**El selector de esfuerzo no cambia el esfuerzo.** Los tres presets de
`frontend/src/App.tsx:17-36` fijan los tres `rigor: "riguroso"`. Solo varían
`largo` y `detalle`: cuánto escribe, no cuánto investiga. La profundidad real
(`max_pasos = 8`, topes de resultados) es idéntica en los tres. El control que
dice "a fondo" solo alarga la prosa.

**Faro rechaza preguntas legítimas.** Tres puertas encadenadas:

- `prompts.py:196-198` obliga a que la primera línea sea uno de seis sellos, y
  `informativo` no está en la lista. Una respuesta educativa correcta se ve
  forzada a estampar el único sello neutro disponible: ❓ SIN EVIDENCIA.
- `veredicto.py:279` descarta **la prosa ya escrita** cuando
  `evidencia.leidas == 0` y la sustituye por un texto fijo que pide "reformular
  la afirmación". Como el streaming ya envió esa prosa al navegador, el usuario
  ve borrarse una buena respuesta delante de él.
- `prompts.py:134-145` clasifica como `no_verificable` cualquier "encargo ajeno
  a verificar" — categoría en la que un modelo puede meter "explícame la
  reforma pensional".

**No hay etapa de pensamiento.** `agent.py:203` es un bucle ReAct plano:
modelo → herramientas → modelo, hasta 8 vueltas. No descompone, no forma
hipótesis, no busca lo que lo refutaría, no separa síntesis de recolección.

### Evidencia de una corrida real

Consulta: *"El Banco de la República es el banco central de Colombia"*.
Trivialmente cierta, verificada contra la web del propio banco.

- Solidez resultante: **33 / 100**.
- El extracto guardado de `banrep.gov.co` era su **página de CAPTCHA**
  ("su actividad nos hace pensar que usted es un Bot"). `leer_pagina` devolvió
  `ok=True` porque trafilatura extrajo texto — el del portero, no el del
  artículo. Ese muro se pasó al modelo como evidencia, se marcó `citada` y fue
  **la única fuente que sumó**.
- `banrep.gov.co`, `registraduria.gov.co` y `boe.es` no están en el registro
  curado (33 dominios, **cero institucionales**), así que `veredicto.py:185`
  les capa la credibilidad a 0.6: por debajo de un periódico curado.
- Con `evidencia.leidas == 1`, si ese CAPTCHA no hubiera extraído texto, la
  puerta de `veredicto.py:279` habría borrado la respuesta entera.

## Objetivo

Que cualquiera pueda educarse con un simple mensaje, sin que Faro deje de ser
Faro.

**Alcance**: se ensancha la FORMA, no el dominio. Faro sigue siendo cívico
—política, economía, instituciones, leyes, datos oficiales— pero deja de exigir
una afirmación. Entran preguntas, conceptos y mecanismos sobre esos temas.
"¿Cómo funciona el sistema electoral de Colombia?" sí; "¿qué es la
fotosíntesis?" no.

**Razonamiento**: cuatro conductas, todas garantizadas, ninguna emergente.
Descomponer, dudar de sí mismo, explicar el mecanismo, y que se le vea pensar.

**Esfuerzo**: el selector compra profundidad real y tiempo real.
~20 s / ~60 s / ~180 s.

## Motor

`deepseek-v4-flash`, con `deepseek-v4-pro` en las etapas de juicio.

DeepSeek retiró los alias `deepseek-chat` y `deepseek-reasoner` el 2026-07-24
15:59 UTC; toda consulta fallaba. Corregido en el commit `83bfa30`.

Razones, todas verificadas contra la API con una llamada real:

- **Pesos abiertos MIT**, sin restricciones. Cumple el requisito de open source.
- `reasoning_content` **sale en español y es coherente**: *"El usuario pregunta
  quién es el presidente actual de Colombia. Esto es un hecho verificable.
  Antes de responder, debo buscar información actualizada."*
- **Se transmite por deltas** junto con tool calls y streaming (61 deltas de
  razonamiento medidos en la prueba).
- **`thinking` es un dial**: `disabled` (0 chars, 46 tokens de salida),
  `enabled/low` (364 chars, 156 tokens), por defecto (~470 chars, ~165 tokens).
  `reasoning_effort` acepta `low`, `medium`, `high`, `max`, `xhigh`.
- **No exige devolver `reasoning_content`** en multi-turno con herramientas: la
  segunda vuelta pasa sin error 400. El bucle actual no se rompe por ahí.
- $0.14 / $0.28 por millón: entre 6 y 17 veces más barato que las alternativas,
  y un pipeline de 4 etapas multiplica el consumo.
- Migración nula: misma clave, misma `base_url`.

Descartados: **GLM-5.2** por estar centrado en chino-inglés, riesgo de primer
orden para un verificador en español; **Kimi K3** por ~190 s hasta el primer
token y $15/M de salida, incompatibles con 4 etapas con streaming.

No existe ningún benchmark público de calidad en español para estos modelos.
Se resuelve con evaluación propia (ver Fase 5), no con literatura.

## Arquitectura

`agent.py` deja de ser un bucle y pasa a ser una fachada fina.

```
verificador/
  razonamiento/
    contrato.py        Encuadre, SubPregunta, Hallazgo, Refutacion
    encuadre.py        1. clasificar + descomponer
    investigacion.py   2. bucle de herramientas por sub-pregunta
    refutacion.py      3. pase adversarial
    sintesis.py        4. pesar, resolver contradicciones, escribir
    __init__.py        orquestador: encadena etapas y emite eventos
  esfuerzo.py          preset -> presupuesto (fuente única de verdad)
  modelo.py            una llamada: streaming, thinking, reasoning_effort
  prompts/             base + un prompt por etapa
```

Cada etapa es una unidad con contrato explícito de entrada y salida: se entiende,
se testea y se cambia sin leer las demás. El bucle de herramientas actual no se
tira — se reubica dentro de `investigacion.py`.

### El dial de esfuerzo

Una tabla, un archivo. Mata de paso los tres defaults contradictorios de `largo`
(`prompts.py:263` y `agent.py:186` dan `corta`; `server.py:55` da `normal`).

| | Esencial | Normal | A fondo |
|---|---|---|---|
| Etapas | encuadre ligero → investigar → sintetizar | las 4 | las 4 |
| `reasoning_effort` | `low` | `medium` | `high` |
| Sub-preguntas | 1 (no descompone) | hasta 3 | hasta 6 |
| Pasos de herramienta | 4 | 8 | 16 |
| Refutación | — | 1 pase | 1 pase + 2ª vuelta si encuentra algo |
| Modelo | v4-flash | v4-flash | v4-flash; v4-pro en refutar y sintetizar |
| Objetivo | ~20 s | ~60 s | ~180 s |

Tres diales que escalan juntos: qué etapas corren, cuánto razona el modelo en
cada una, y cuánto puede investigar.

### Dos decisiones de fondo

**Cuando la refutación corre, se muestra encuentre o no.** Si busca lo que la
desmentiría y no aparece nada, se dice. Es información valiosa y es la prueba
visible de que dudó de sí mismo. Mostrarla solo cuando encuentra algo volvería
invisible la conducta. (En `Esencial` no corre; la interfaz lo indica en vez de
callarlo, para que la ausencia no se confunda con "no encontró nada".)

**El pensamiento visible tiene dos capas.** Los artefactos limpios
(sub-preguntas, contradicciones, cómo pesó cada fuente) son la estructura y lo
que se lee. El `reasoning_content` nativo, transmitido en vivo dentro de cada
etapa, es la textura de que está pensando ahora. Plegable: es ruidoso.

## Contrato del veredicto

El frontend **ya sabe pintar `informativo`** (`maps.ts:19`, sello ℹ️) y
`no_verificable` (💬). La interfaz estaba lista; lo mata el backend. Esto es
desatascar, no construir.

### Separar qué te preguntaron de qué se concluyó

- **`tipo`** — `afirmacion` · `pregunta` · `mecanismo`. Lo decide la etapa de
  **encuadre**, antes de investigar.
- **`veredicto`** — solo existe cuando `tipo == "afirmacion"`. Los seis sellos.

Los dos veredictos rotos desaparecen por construcción:

- `informativo` deja de ser veredicto y pasa a ser `tipo: pregunta`. Nunca fue
  un veredicto: ese era el bug. Sin sello obligatorio, el modelo deja de verse
  forzado a estampar ❓ SIN EVIDENCIA en respuestas correctas.
- `no_verificable` deja de ser un tipo: es un **rechazo**, resuelto en encuadre
  sin gastar una investigación, y mucho más estrecho — solo opiniones puras,
  gustos personales y encargos creativos.

### `solidez` sustituye a `confianza`, con dos curvas

"Confianza en el veredicto" no significa nada al explicar una institución. "Qué
tan bien respaldado está esto" siempre significa algo.

- **Fuentes institucionales al registro**, con tipo `primaria_oficial`:
  `banrep.gov.co`, `registraduria.gov.co`, `boe.es`, `dane.gov.co`,
  `inegi.org.mx`, `ine.es`, `indec.gob.ar`, congresos, senados, boletines
  oficiales. El tope de 0.6 de `veredicto.py:186-187` **no se les aplica**.
- **Dos curvas según el tipo.** Para una afirmación en disputa, la curva actual
  es correcta: lo que da solidez son confirmaciones independientes con bono por
  contraste. Para una pregunta o un mecanismo ese modelo es absurdo — nadie
  necesita que un medio de izquierda y uno de derecha coincidan en qué hace un
  banco central. Ahí manda la mejor fuente disponible, sin bono por contraste:
  una primaria oficial, abierta y citada, basta para solidez alta.

  La calibración exacta de ambas curvas se fija en implementación, contra una
  batería de casos con solidez esperada anotada a mano. El criterio de
  aceptación es concreto: el caso del Banco de la República, leído de verdad,
  no puede dar 33.
- **Un muro anti-bot deja de contar como lectura.** `leer_pagina` detecta
  CAPTCHAs, Cloudflare y paywalls y devuelve `ok=False`.

### La prosa no se borra nunca

`veredicto.py:279` se elimina. Regla nueva: **degradar informando, jamás
borrando.** Si la evidencia es floja, la prosa sobrevive, la solidez baja y se
adjunta un `aviso` que la interfaz pinta como banda. Y distingue dos fracasos
hoy indistinguibles: "no encontré nada" y "encontré pero no pude abrirlo".

Aplicado al caso real de arriba: descartado el CAPTCHA, esa consulta tendría
cero fuentes abiertas. No se inventa un número — se dice que el Banco de la
República bloquea la lectura automática y que la respuesta se apoya solo en
Wikipedia. Es honesto y además accionable.

### Nuevos campos

- `subpreguntas: [{id, texto, resuelta, hallazgo, fuentes: [n]}]`
- `refutacion: {se_busco, encontro, resumen, fuentes: [n]}`

## Interfaz

La estética no se toca: `--canvas #f5efe5`, `--brand #315f5d`, Geist + Georgia,
el cristal, y el Faro dibujado a mano con su parpadeo y su ceja.

**El esfuerzo sube de rango, el país baja.** El país es un ajuste de sesión que
cambias rara vez: deja la barra del composer y pasa a la cabecera, junto a la
marca, como control compacto persistente — visible siempre, pero fuera del
camino de escribir. El esfuerzo, que ahora compra etapas y minutos, ocupa el
sitio que deja libre y se presenta con su precio visible.

Dos formas según el momento:

- **Estado inicial** (donde hoy vive el retrato y sobra espacio): las tres
  opciones completas, con nombre, **tiempo estimado** y una línea de qué hace
  cada una.
- **Conversación empezada**: píldora compacta con el modo actual, que se
  expande al tocarla.

Enseña la primera vez y se aparta después. Disuelve además el problema de móvil:
la forma expandida solo existe donde hay sitio, nunca como fila fija sobre el
teclado (`faro.css:231`).

**La traza pasa de log a relato.** Las etapas son la narración: el encuadre
lista las sub-preguntas y su estado; la refutación dice qué buscó; la síntesis,
que escribe. Debajo, plegable, el `reasoning_content` en vivo.

**El salto de layout se arregla solo.** Hoy la banda del sello y el titular se
insertan encima de la prosa ya leída (`Answer.tsx:95,111`) porque hasta el final
nadie sabía el veredicto. Con el pipeline, `tipo` se conoce al terminar el
encuadre: la interfaz reserva el marco desde el principio y lo rellena después.

**Detalle y accesibilidad.** `.seg-opt` vuelve a 44px (hoy 36, `faro.css:170`,
los targets más pequeños de la app). El texto del trade-off sale del
`aria-label` y pasa a ser visible — hoy `aria-label` *sustituye* el nombre
accesible, así que un usuario vidente nunca lee la explicación
(`App.tsx:21,27,33`). `--muted-text` se oscurece hasta pasar 4.5:1 sobre el
cristal. Las abreviaturas tipo "c-der" dejan de depender de un `title` en hover,
inútil en táctil. Las filas de fuentes abandonan el grid de 7 columnas fijas con
parches de `grid-column` por breakpoint. El textarea se deshabilita durante
`enCurso` diciendo por qué.

## Pruebas

Cada etapa se testea aislada con un cliente falso; `test_dispatch.py` ya tiene
el patrón. La tabla de esfuerzo se testea como tabla: cada preset produce el
presupuesto documentado. La detección anti-bot, con HTML real de CAPTCHAs. Los
eventos SSE nuevos, con el patrón de `test_sse.mjs`.

**Se restaura el test de afinidad de hilo.**
`test_lectura.py::test_navegador_reutilizado_entre_hilos` lleva tiempo fallando:
usa una URL `file://` y el guardia SSRF (`search.py:107`) rechaza todo lo que no
sea http/s hacia una IP global, así que `_leer_navegador` devuelve `None` sin
llegar a tocar Playwright. No puede pasar tal como está escrito, y por tanto la
propiedad que protegía —la afinidad de hilo de Playwright, que fue un bug real y
caro— lleva tiempo sin cobertura. Se arregla haciendo inyectable el guardia.

### Coste

El contrato es incompatible hacia atrás: **29 tests en `test_veredicto.py` y 8
en `test_traza.py`** se reescriben, más 37 asserts que mencionan `confianza`.
`test_traza.py:101-102` **consagra el bug** —afirma como correcto que
`informativo` se convierta en `sin_evidencia`— y se borra en lugar de adaptarse.

## Orden de trabajo

Ordenado por valor entregado y riesgo, no por dependencia técnica.

Son **dos planes de implementación distintos**, no uno: las fases 1-2 son
saneamiento del backend actual y se pueden ejecutar y cerrar enteras antes de
tocar la arquitectura; las fases 3-5 son la construcción nueva. Cada bloque
merece su propio plan y su propia rama.

1. **El suelo.** Anti-bot, registro institucional, unificar los defaults de
   `largo`, el crash de `agent.py:99` (`int(args.get("max_resultados", 6))`
   lanza `ValueError` con `"seis"`, y `args.get` lanza `AttributeError` si
   `json.loads` devolvió una lista), y el test de afinidad. No dependen de la
   arquitectura nueva y mejoran Faro hoy.
2. **El contrato.** `tipo`/`veredicto`/`solidez` y matar la puerta que borra
   prosa. Aquí desaparece "solo responde afirmaciones políticas".
3. **El pipeline.** Las cuatro etapas, `esfuerzo.py`, `modelo.py`.
4. **La interfaz.** Control de esfuerzo, traza-relato, salto de layout,
   accesibilidad.
5. **Evaluación en español.** 20-30 afirmaciones reales por cada motor,
   comparadas a mano, para decidir qué modelo va en qué etapa. Ningún benchmark
   público lo resuelve.

Tras la fase 1 se nota la mejora; tras la 2 desaparece la frustración principal;
3 y 4 son el salto de nivel.
