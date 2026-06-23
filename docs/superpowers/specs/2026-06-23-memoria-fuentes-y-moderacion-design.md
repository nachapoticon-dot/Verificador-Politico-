# Memoria de fuentes, veredicto honesto, lista ponderada y respeto endurecido

> Diseño aprobado en brainstorming el 2026-06-23. Evoluciona *cómo Tomás juzga
> y presenta las fuentes y las afirmaciones*, y endurece la moderación de respeto.

## Objetivo

Cuatro objetivos acoplados (que se reparten en seis piezas de implementación, ver
abajo), surgidos de probar la app:

1. **Memoria de fuentes con credibilidad.** Hoy la tendencia de cada fuente la
   inventa el modelo al vuelo y no existe noción de fiabilidad. Wikipedia
   (editable por cualquiera) pesa igual que una agencia. Se añade un registro
   curado de fuentes con credibilidad para que el agente pondere lo que lee.
2. **Veredicto honesto.** Una consulta tipo pregunta/tema ("presidente actual de
   Colombia 2026") recibe hoy un ❌/✅. Si no hay afirmación verificable, no debe
   haber veredicto verdadero/falso.
3. **Lista ponderada de fuentes.** Se sustituye el medidor de espectro abstracto
   por una lista legible que muestra tendencia **y** credibilidad por fuente.
4. **Respeto endurecido.** La moderación actual es blanda y nunca cierra. Pasa a:
   un aviso firme y, si se repite, cierre de la conversación.

## Restricciones heredadas (del proyecto)

- **IA descartable**: solo memoria de la conversación de la sesión (`_SESIONES[sid]`);
  sin perfil de usuario ni persistencia entre sesiones. El registro de fuentes y
  el log de propuestas son **metadatos de fuentes**, no datos de usuario → no
  violan esta restricción.
- Modelo fijo **DeepSeek** (`deepseek-chat`).
- Ruta rápida httpx siempre primero; Playwright como fallback en su hilo propietario.
- Citas `[n]` del prose deben coincidir con `fuentes[].n` del JSON.
- Degradación elegante: nada nuevo debe romper la ruta básica.

---

## Pieza 1 — Registro de fuentes (curado, estático, versionado)

### Modelo de datos

Dos ejes **independientes** por fuente:

- **tendencia** (ya existe): `izquierda | centro-izquierda | centro | centro-derecha | derecha | verificador | internacional`.
- **credibilidad** (nuevo), 4 niveles:
  - `alta` — verificadores IFCN, agencias (Reuters/AP/AFP/EFE), fuentes oficiales/primarias.
  - `media` — prensa de referencia con línea editorial.
  - `baja` — enciclopedias editables (Wikipedia), blogs, prensa muy partidista.
  - `no_fiable` — redes sociales como *prueba* de un hecho, sitios de desinformación, sátira.

### Archivo

`verificador/data/fuentes.json` — mapa *dominio registrable → ficha*:

```json
{
  "wikipedia.org":      {"credibilidad": "baja",      "tendencia": "centro",        "tipo": "enciclopedia_editable", "nota": "cualquiera edita; punto de partida, no prueba"},
  "reuters.com":        {"credibilidad": "alta",      "tendencia": "centro",        "tipo": "agencia"},
  "apnews.com":         {"credibilidad": "alta",      "tendencia": "centro",        "tipo": "agencia"},
  "afp.com":            {"credibilidad": "alta",      "tendencia": "internacional", "tipo": "agencia"},
  "colombiacheck.com":  {"credibilidad": "alta",      "tendencia": "verificador",   "tipo": "verificador_ifcn"},
  "chequeado.com":      {"credibilidad": "alta",      "tendencia": "verificador",   "tipo": "verificador_ifcn"},
  "maldita.es":         {"credibilidad": "alta",      "tendencia": "verificador",   "tipo": "verificador_ifcn"},
  "newtral.es":         {"credibilidad": "alta",      "tendencia": "verificador",   "tipo": "verificador_ifcn"},
  "elpais.com":         {"credibilidad": "media",     "tendencia": "centro-izquierda", "tipo": "medio"},
  "elmundo.es":         {"credibilidad": "media",     "tendencia": "centro-derecha",   "tipo": "medio"},
  "infobae.com":        {"credibilidad": "media",     "tendencia": "centro-derecha",   "tipo": "medio"},
  "eltiempo.com":       {"credibilidad": "media",     "tendencia": "centro",        "tipo": "medio"},
  "x.com":              {"credibilidad": "no_fiable", "tendencia": "internacional", "tipo": "red_social", "nota": "no es prueba de un hecho; sí fuente primaria de qué dijo alguien"},
  "facebook.com":       {"credibilidad": "no_fiable", "tendencia": "internacional", "tipo": "red_social"}
}
```

- **Semilla inicial** (≈30–50 entradas): verificadores IFCN regionales
  (ColombiaCheck, La Silla Vacía/Detector, Chequeado, Animal Político, Verificado,
  PolitiFact, FactCheck.org, AFP Factual, Reuters/AP Fact Check, Full Fact),
  agencias (Reuters, AP, AFP, EFE), prensa de referencia por región con su
  tendencia (El País, El Mundo, ABC, elDiario.es, El Tiempo, El Espectador, Semana,
  RCN, Infobae, NYT, WSJ, Fox News…), baja (`wikipedia.org`, `*.blogspot.com`,
  `medium.com`, `*.wordpress.com`), no_fiable (`x.com`/`twitter.com`, `facebook.com`,
  `tiktok.com`, `instagram.com`).
- **Matiz redes sociales**: marcadas `no_fiable` *como prueba de un hecho*, pero el
  prompt aclara que sí valen como **fuente primaria de qué dijo alguien**.

### Módulo `verificador/fuentes.py`

```python
class Fuente(NamedTuple):
    dominio: str
    credibilidad: str      # alta|media|baja|no_fiable
    tendencia: str
    tipo: str
    nota: str | None

def dominio_registrable(url: str) -> str   # baja a minúsculas, quita esquema, www y subdominios → "wikipedia.org"
def clasificar(url: str) -> Fuente | None  # busca por dominio registrable; None si no está en el registro
```

- Patrones comodín (`*.blogspot.com`) se resuelven por sufijo de dominio.
- El registro se carga una vez (módulo) desde el JSON.

---

## Pieza 2 — Consumo por auto-anotación

El registro se aplica **antes** de que el modelo vea cada fuente, en la capa de
salida de las tools (el modelo no puede olvidarse de comprobar).

- `buscar_web`: cada dict de resultado gana una clave `"fiabilidad"` con la
  etiqueta (junto a `titulo`/`url`/`resumen`), de modo que el modelo la ve en el
  mismo objeto.
- `leer_pagina` / `ver_video`: el `texto` devuelto al modelo se antepone con la
  etiqueta de la fuente.

Formato de la etiqueta:

- **Conocida**: `[fuente: Wikipedia · fiabilidad BAJA (enciclopedia editable; punto de partida, no prueba) · tendencia centro]`
- **Desconocida**: `[fuente: dominio no registrado — clasifícala tú en el JSON de cierre; quedará como propuesta de revisión]`

La anotación es una función pura `anotar(url) -> str` en `fuentes.py`, llamada
desde `search.py`. No cambia el contrato `Lectura(texto, ok)`: la etiqueta se
antepone a `texto` solo cuando `ok` es True (en fallo no se añade nada, para no
ensuciar el aviso ni el visor).

---

## Pieza 3 — Capa híbrida de propuestas

El modelo ya emite tendencia/credibilidad por fuente en el JSON de cierre. Para
los dominios **no** registrados, se capturan como propuestas (no se aplican solas).

- **Captura**: el bloque ```json``` final de la respuesta se parsea en el backend
  con un helper `extraer_meta(texto) -> dict | None` (en `fuentes.py`; misma lógica
  que `partirRespuesta` del frontend, pero en Python). `agent.py`, tras producir el
  mensaje final en `preguntar`, llama a `fuentes.capturar_propuestas(meta_fuentes)`.
  Por cada fuente cuyo dominio no esté en el registro, escribe una línea en
  `verificador/data/propuestas.jsonl` (append-only), deduplicada por dominio:
  `{"dominio": "...", "credibilidad": "...", "tendencia": "...", "ejemplo_url": "...", "ts": "ISO-8601"}`.
  La captura nunca debe romper la respuesta: si el JSON falta o es inválido, se
  ignora en silencio.
- **Revisión**: subcomando CLI `python -m verificador.fuentes revisar` que lista
  las propuestas pendientes agrupadas por dominio (con la valoración del modelo y
  un ejemplo de url) para que un humano las apruebe copiándolas a `fuentes.json`.
  El JSON también es editable a mano. No hay promoción automática.
- La dedupe lee las propuestas ya escritas + el registro curado para no repetir.

---

## Pieza 4 — Veredicto honesto (pregunta vs afirmación)

### Prompt

Nueva instrucción de clasificación de la entrada al principio del método:

- Si la consulta **contiene una afirmación verificable** (algo que puede ser
  verdadero o falso), procede como hoy: investiga y emite veredicto.
- Si es una **pregunta informativa / tema / pedido de datos** sin afirmación que
  contrastar, responde igual (con búsqueda y citas) pero con
  `veredicto: "informativo"` y **sin** etiqueta de verdad/falso.

Además, ponderación por credibilidad (regla de honestidad nueva):
> Nunca sostengas un veredicto solo sobre una fuente de credibilidad `baja` o
> `no_fiable`. Corrobora con fuentes `alta`/`media`. Wikipedia y similares son
> punto de partida, no prueba. Las redes sirven como prueba de *qué dijo alguien*,
> no de que un hecho sea cierto.

### Contrato JSON (cambios)

- `veredicto` gana el valor `informativo`:
  `"verdadero|falso|enganoso|fuera_de_contexto|prediccion|sin_evidencia|informativo"`.
- Cada entrada de `fuentes[]` gana `"credibilidad": "alta|media|baja|no_fiable"`.

```json
{
  "veredicto": "informativo",
  "confianza": 0,
  "resumen": "una frase",
  "pais": "CO",
  "fuentes": [
    {"n": 1, "medio": "El Tiempo", "tendencia": "centro", "credibilidad": "media", "url": "https://...", "coincide": true}
  ]
}
```

- Para `informativo`, `confianza` no se interpreta como veracidad (la UI no
  muestra barra de confianza en ese caso).

---

## Pieza 5 — Frontend: lista ponderada (opción C)

Se **elimina** `pintarEspectro` (el medidor izquierda/centro/derecha). Se
**fusiona** con la lista de fuentes clicables que ya añadió la Task 9, en una sola
lista donde cada fila es:

`[chip de tendencia]  [medio (enlace)]  [✓ respalda | · matiza]  [insignia de credibilidad]  ▸ ver de dónde salió`

- Chip de tendencia: color por bloque (izquierda cálido / centro neutro / derecha
  azulado; verificador e internacional con su propio matiz).
- Insignia de credibilidad: píldora con color (alta verde, media teal, baja ámbar,
  no_fiable rojo) y texto.
- Se conserva el desplegable `<details>` "ver de dónde salió" por fuente (de la
  Task 9), con su construcción XSS-segura (`urlSegura`, `.textContent`).
- `EXTRACTOS` sigue alimentándose desde la traza igual que hoy.

### Sello neutro `informativo`

Nuevo sello **ℹ️ INFORMACIÓN** con color apagado/teal. Cuando
`veredicto === "informativo"`:
- Se muestra el sello neutro en vez de ✅/❌/⚠️.
- **No** se muestra la barra de "confianza" (no aplica como veracidad).
- El resto (prosa con citas, lista de fuentes) igual.

`SELLOS` en `app.js` gana la entrada `informativo`. El `data-v` correspondiente
recibe un color neutro en `style.css`.

---

## Pieza 6 — Respeto endurecido

### `moderation.py`

- `mensaje_limite` se reescribe a una secuencia de **dos** estados:
  - 1.er insulto → aviso **firme y seco** (sin "en buena onda"; sin devolver
    grosería, pero tajante: no se toleran faltas de respeto).
  - repetición → mensaje de **cierre** (Tomás se despide; la conversación queda
    cerrada; para volver hay que empezar de nuevo).
- Se elimina el decremento de strikes ("recuperar margen") en `server.py`.

### `server.py`

- La sesión gana estado `cerrada: bool` en `_SESIONES[sid]`.
- Flujo en `/api/verificar`:
  - Si `sesion["cerrada"]` ya es True → responde solo evento `cerrada` con el
    mensaje final, sin procesar nada.
  - Si `es_irrespetuoso(pregunta)`: incrementa `strikes`.
    - `strikes == 1` → evento `moderacion` con el aviso firme.
    - `strikes >= 2` → marca `sesion["cerrada"] = True`, emite evento `cerrada`
      con el mensaje de despedida.
- (Se mantiene la lógica de no llamar al modelo ante una falta de respeto.)

### Frontend (`app.js` / `style.css`)

- Nuevo manejo del evento `cerrada`: pinta el mensaje final de cierre (estilo
  límite), **bloquea el composer** de forma permanente (no como el `enCurso`
  temporal) y muestra un aviso de que la conversación se cerró y hay que recargar
  para empezar de nuevo.
- El evento `moderacion` sigue como hoy (aviso, sin cerrar).

---

## Componentes y límites

| Unidad | Responsabilidad | Depende de |
|---|---|---|
| `verificador/data/fuentes.json` | Registro curado (datos) | — |
| `verificador/data/propuestas.jsonl` | Log append-only de propuestas | — |
| `verificador/fuentes.py` | Cargar registro, `dominio_registrable`, `clasificar`, `anotar`, captura/dedupe de propuestas, CLI `revisar` | `fuentes.json`, `propuestas.jsonl` |
| `verificador/search.py` | Inyectar anotación en `buscar_web`/`leer_pagina`/`ver_video` | `fuentes.anotar` |
| `verificador/prompts.py` | Clasificación pregunta/afirmación; ponderación por credibilidad; contrato JSON (`informativo`, `credibilidad`) | — |
| `verificador/agent.py` | Capturar propuestas de `meta.fuentes` no registradas | `fuentes` |
| `verificador/moderation.py` | Secuencia aviso firme → cierre | — |
| `verificador/server.py` | Estado `cerrada`, eventos `moderacion`/`cerrada`, sin decremento | `moderation` |
| `web/app.js` | Lista ponderada (fusiona espectro+lista), sello `informativo`, evento `cerrada` | — |
| `web/style.css` | Chips tendencia, insignias credibilidad, sello neutro, aviso de cierre | — |

## Plan de pruebas

- `tests/test_fuentes.py` — `dominio_registrable` (www/subdominios/comodines),
  `clasificar` (conocida/desconocida), `anotar` (formato conocida vs desconocida),
  captura+dedupe de propuestas (escribe/relee `propuestas.jsonl` en tmp).
- `tests/test_lectura.py` / `test_video.py` — la anotación se antepone al `texto`
  solo cuando `ok`; en fallo no se añade.
- `tests/test_prompt.py` — el prompt incluye `informativo`, `credibilidad`, la
  clasificación pregunta/afirmación y la regla de ponderación; el JSON de ejemplo
  trae `"credibilidad"`.
- `tests/test_moderation.py` — `mensaje_limite` da aviso firme en el 1.er strike y
  mensaje de cierre en el 2.º; sin decremento.
- `tests/test_server.py` — 2.º insulto emite evento `cerrada` y marca la sesión;
  una petición a una sesión ya cerrada responde `cerrada` sin llamar al modelo.
- Frontend — `node --check web/app.js`; `tests/test_citas.mjs` sigue verde; (si
  se extrae alguna función pura de render, un test node para ella).
- No romper los 17 tests actuales.

## Fuera de alcance

- Visión de vídeo por fotogramas (sigue fuera).
- Promoción automática de propuestas al registro (siempre revisión humana).
- Aprendizaje/persistencia de perfil de usuario (prohibido por diseño).
- Puntaje numérico de credibilidad (se eligieron 4 niveles).
