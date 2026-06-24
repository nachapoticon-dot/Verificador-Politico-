# Modos de respuesta (largo + detalle) y formato limpio — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar a Tomás un modo de respuesta ajustable desde la interfaz (largo: corta/normal/detallada · detalle: simple/técnico) con un predeterminado corta+simple, y arreglar de raíz que el markdown de encabezados (`###`) nunca se muestre crudo.

**Architecture:** El modo viaja por request como `largo`/`detalle` (igual que `país`/`rigor`): la UI lo manda en el POST, el server lo valida y lo pasa al `Verificador`, y `preguntar()` antepone una instrucción de modo (de `prompts.instruccion_modo`) como un mensaje `system` efímero por turno —el `SYSTEM_PROMPT` base no se reconstruye, así el caché del prompt se mantiene. El front limpia cualquier encabezado markdown al renderizar.

**Tech Stack:** Python 3.10+ (stdlib), pytest; FastAPI + SSE; JS/CSS sin build (`node --check`). Modelo fijo DeepSeek.

## Global Constraints

- IA descartable: el modo se lee por request; sin perfil de usuario ni persistencia entre sesiones; se resetea al recargar.
- Modelo fijo DeepSeek (`deepseek-chat`). No cambiar de modelo.
- No romper el caché del prompt: el `SYSTEM_PROMPT` base (primer mensaje `system`) no se modifica por request; el modo se inyecta como mensaje aparte.
- `rigor` (rápido/a fondo) NO cambia: controla cuánto investiga, no cómo redacta. El modo de respuesta es independiente.
- Largo (valores exactos): `corta | normal | detallada`. Detalle (valores exactos): `simple | tecnico`. Predeterminado: `corta` + `simple`.
- Citas `[n]` del prose deben seguir coincidiendo con `fuentes[].n` del JSON.
- Degradación elegante: `largo`/`detalle` ausentes o inválidos caen al default sin romper la respuesta.
- No romper los 38 tests actuales.
- Usar el venv: `.venv/bin/pytest`, `.venv/bin/python`. Front: `node --check web/app.js`.

---

### Task 1: `instruccion_modo` + reglas de prompt (formato y modo)

**Files:**
- Modify: `verificador/prompts.py`
- Test: `tests/test_prompt.py`

**Interfaces:**
- Produces:
  - `instruccion_modo(largo: str, detalle: str) -> str` — línea de modo que arranca con `"[Modo de respuesta] "`; tolera valores fuera de vocab cayendo a `corta`/`simple`. La consume Task 2.
  - `SYSTEM_PROMPT` actualizado: prohíbe encabezados markdown y delega el largo/detalle al modo.

- [ ] **Step 1: Escribir los tests que fallan (añadir a `tests/test_prompt.py`)**

```python
def test_instruccion_modo_textos_por_eje():
    from verificador.prompts import instruccion_modo
    corta = instruccion_modo("corta", "simple")
    assert corta.startswith("[Modo de respuesta] ")
    assert "1-2 frases" in corta
    assert "lenguaje llano" in corta.lower()
    det = instruccion_modo("detallada", "tecnico")
    assert "varios párrafos" in det
    assert "metodología" in det.lower()


def test_instruccion_modo_cae_al_default_si_invalido():
    from verificador.prompts import instruccion_modo
    assert instruccion_modo("xxx", "yyy") == instruccion_modo("corta", "simple")


def test_prompt_prohibe_encabezados_markdown():
    from verificador.prompts import SYSTEM_PROMPT
    pl = SYSTEM_PROMPT.lower()
    assert "encabezados markdown" in pl
    assert "###" in SYSTEM_PROMPT
    # el largo ya no se hardcodea: se delega al modo de cada consulta
    assert "modo de respuesta" in pl
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_prompt.py -k "modo or encabezados" -v`
Expected: FAIL — `ImportError: cannot import name 'instruccion_modo'`.

- [ ] **Step 3: Añadir `instruccion_modo` al final de `verificador/prompts.py`**

```python
_MODO_LARGO = {
    "corta": "Responde en 1-2 frases: el veredicto y solo el dato esencial con su cita; sin contexto extra.",
    "normal": "Responde en un párrafo breve: veredicto y explicación directa con los datos clave citados.",
    "detallada": "Desarrolla con el detalle que el tema exija (varios párrafos si hace falta): contexto, matices y las fuentes que corroboran o discrepan.",
}
_MODO_DETALLE = {
    "simple": "Usa lenguaje llano para cualquiera; evita la jerga; si das una cifra, explícala en palabras simples.",
    "tecnico": "Incluye cifras precisas, unidades y metodología cuando aporten (p. ej. variación interanual, fuente del dato).",
}


def instruccion_modo(largo: str, detalle: str) -> str:
    """Línea de modo que se antepone a cada consulta.

    Combina el eje de largo y el de detalle. Tolera valores fuera de
    vocabulario cayendo al modo predeterminado (corta + simple).
    """
    l = _MODO_LARGO.get(largo, _MODO_LARGO["corta"])
    d = _MODO_DETALLE.get(detalle, _MODO_DETALLE["simple"])
    return f"[Modo de respuesta] {l} {d}"
```

- [ ] **Step 4: Editar la sección `# Cómo respondes` del `SYSTEM_PROMPT`**

**4a.** Localizar la frase que hardcodea el largo:

```
La longitud es PROPORCIONAL a \
la pregunta: si es simple, responde en 1-3 frases; amplía solo si la persona pide \
detalle o el matiz lo exige.
```

y reemplazarla por:

```
El largo y el nivel de detalle te los marca el modo de respuesta que se indica \
al inicio de cada consulta (entre corchetes, "[Modo de respuesta] ..."): respétalo.
```

**4b.** Localizar el párrafo que termina la sección:

```
No incluyas una lista de "Fuentes" en el texto: las fuentes van en el bloque JSON \
final y la interfaz las muestra. Nunca afirmes un dato sin su cita.
```

y añadir justo después un párrafo nuevo:

```
No uses encabezados markdown (#, ##, ###) ni tablas: solo prosa y, como mucho, \
**negrita** para destacar. Para enumerar, usa viñetas que empiecen con "- ".
```

(Conservar el estilo de continuación con `\` del archivo.)

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_prompt.py -v`
Expected: PASS (incluidos los nuevos y el test de concisión/citas existente).

- [ ] **Step 6: Commit**

```bash
git add verificador/prompts.py tests/test_prompt.py
git commit -m "feat: instruccion_modo + prompt prohíbe encabezados y delega largo/detalle"
```

---

### Task 2: `Verificador` lee el modo e inyecta la instrucción

**Files:**
- Modify: `verificador/agent.py`
- Test: `tests/test_traza.py`

**Interfaces:**
- Consumes: `prompts.instruccion_modo` (Task 1).
- Produces: `Verificador` con atributos `largo: str = "corta"`, `detalle: str = "simple"`; `preguntar` antepone un mensaje `system` con la instrucción de modo antes del turno del usuario, sin tocar `messages[0]` (el system base).

- [ ] **Step 1: Escribir el test que falla (añadir a `tests/test_traza.py`)**

```python
def test_preguntar_inyecta_instruccion_de_modo(monkeypatch):
    from types import SimpleNamespace
    import verificador.agent as agentmod

    ver = agentmod.Verificador()
    ver.largo = "detallada"
    ver.detalle = "tecnico"
    base_system = ver.messages[0]["content"]  # system base, no debe cambiar

    final = 'Respuesta [1].\n\n```json\n{"veredicto":"informativo","fuentes":[]}\n```'
    fake = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=final, tool_calls=None))]
    )
    monkeypatch.setattr(ver._client.chat.completions, "create", lambda **k: fake)

    ver.preguntar("¿algo?")

    # El system base (primer mensaje) queda intacto → caché del prompt a salvo.
    assert ver.messages[0]["content"] == base_system
    # Se inyectó un mensaje de modo (system) con el texto del modo elegido.
    modos = [m for m in ver.messages
             if m["role"] == "system" and "[Modo de respuesta]" in m["content"]]
    assert modos, "no se inyectó la instrucción de modo"
    assert "varios párrafos" in modos[-1]["content"]
    # Va antes del turno del usuario.
    idx_modo = ver.messages.index(modos[-1])
    idx_user = next(i for i, m in enumerate(ver.messages) if m["role"] == "user")
    assert idx_modo < idx_user
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_traza.py -k modo -v`
Expected: FAIL — `AttributeError: 'Verificador' object has no attribute 'largo'` (o no se inyecta el mensaje de modo).

- [ ] **Step 3: Añadir los atributos en `verificador/agent.py`**

Tras la línea `rigor: str = "riguroso"` (agent.py:36), añadir:

```python
    # Modo de redacción de la respuesta (no afecta cuánto investiga; eso es rigor).
    largo: str = "corta"      # corta | normal | detallada
    detalle: str = "simple"   # simple | tecnico
```

- [ ] **Step 4: Importar `instruccion_modo` e inyectarla en `preguntar`**

Cambiar el import (agent.py:21):

```python
from .prompts import SYSTEM_PROMPT, instruccion_modo
```

En `preguntar`, justo ANTES de `self.messages.append({"role": "user", "content": pregunta})` (agent.py:87), insertar:

```python
        # Instrucción de modo: mensaje system efímero por turno. No toca el system
        # base (messages[0]), así el prefijo cacheado del prompt no cambia.
        self.messages.append(
            {"role": "system", "content": instruccion_modo(self.largo, self.detalle)}
        )
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_traza.py -v`
Expected: PASS (incluido el nuevo; los de traza/propuestas siguen verdes).

- [ ] **Step 6: Commit**

```bash
git add verificador/agent.py tests/test_traza.py
git commit -m "feat: Verificador inyecta instruccion de modo por consulta"
```

---

### Task 3: Server lee y valida `largo`/`detalle`

**Files:**
- Modify: `verificador/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `Verificador.largo`, `Verificador.detalle` (Task 2).
- Produces: `_sesion(sid, country, rigor, largo, detalle)`; el endpoint lee `largo`/`detalle` del body, los valida (default `corta`/`simple`) y los aplica al agente sobre la marcha.

- [ ] **Step 1: Actualizar los monkeypatches existentes de `_sesion` (firma nueva) y añadir el test que falla, en `tests/test_server.py`**

En los tres `monkeypatch.setattr(server, "_sesion", lambda sid, c, r: ...)` existentes (en `test_sse_emite_traza_y_respuesta`, `test_segundo_insulto_cierra_la_sesion`, `test_sesion_cerrada_rechaza_sin_llamar_al_modelo`), cambiar la firma del lambda a cinco parámetros:

```python
lambda sid, c, r, largo, detalle: ...
```

(es decir: `lambda sid, c, r, largo, detalle: {"agente": _FakeAgente(), "strikes": 0}` y `lambda sid, c, r, largo, detalle: sesion` en los otros dos.)

Añadir el test nuevo:

```python
def test_endpoint_valida_largo_y_detalle(monkeypatch):
    from fastapi.testclient import TestClient
    from verificador import server

    capturado = {}

    class _FakeAgente:
        messages = []
        def preguntar(self, *a, **k):
            return "ok"

    def fake_sesion(sid, country, rigor, largo, detalle):
        capturado["largo"] = largo
        capturado["detalle"] = detalle
        return {"agente": _FakeAgente(), "strikes": 0, "cerrada": False}

    monkeypatch.setattr(server, "_sesion", fake_sesion)
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar",
                       json={"pregunta": "x", "sid": "t",
                             "largo": "zzz", "detalle": "tecnico"}) as r:
        "".join(chunk for chunk in r.iter_text())

    assert capturado["largo"] == "corta"      # inválido → default
    assert capturado["detalle"] == "tecnico"  # válido → respetado
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_server.py -k "largo or detalle" -v`
Expected: FAIL — `TypeError: _sesion() takes 3 positional arguments but 5 were given` (la firma aún no se amplió).

- [ ] **Step 3: Ampliar `_sesion` en `verificador/server.py`**

Cambiar la firma y la creación/actualización (server.py:37-44):

```python
def _sesion(sid: str, country: str | None, rigor: str,
            largo: str, detalle: str) -> dict:
    s = _SESIONES.get(sid)
    if s is None:
        s = {"agente": Verificador(country=country, rigor=rigor,
                                   largo=largo, detalle=detalle),
             "strikes": 0, "cerrada": False}
        _SESIONES[sid] = s
    # Permite cambiar país/rigor/modo sobre la marcha sin perder la conversación.
    s["agente"].country = country
    s["agente"].rigor = rigor
    s["agente"].largo = largo
    s["agente"].detalle = detalle
    return s
```

(Conservar la lógica real de obtención/creación que ya tenga `_sesion`; lo único que cambia es la firma, los dos parámetros nuevos al construir `Verificador`, y las dos asignaciones `largo`/`detalle`.)

- [ ] **Step 4: Leer y validar `largo`/`detalle` en el handler**

Donde se leen `country` y `rigor` del body (server.py:63-64), añadir debajo:

```python
    largo = body.get("largo")
    largo = largo if largo in ("corta", "normal", "detallada") else "corta"
    detalle = body.get("detalle")
    detalle = detalle if detalle in ("simple", "tecnico") else "simple"
```

y cambiar la llamada (server.py:66):

```python
    sesion = _sesion(sid, country, rigor, largo, detalle)
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_server.py -v`
Expected: PASS (el nuevo y los tres existentes con la firma actualizada).

- [ ] **Step 6: Commit**

```bash
git add verificador/server.py tests/test_server.py
git commit -m "feat: server lee y valida largo/detalle y los pasa al agente"
```

---

### Task 4: UI — controles de modo y envío en el POST

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`
- Modify: `web/style.css`

**Interfaces:**
- Consumes: el endpoint que ya acepta `largo`/`detalle` (Task 3).
- Produces: dos controles segmentados (`data-largo`, `data-detalle`) con default `corta`/`simple`; `app.js` manda `largo`/`detalle` en el cuerpo del POST.

- [ ] **Step 1: Añadir los controles en `web/index.html`**

Dentro de `<div class="controls">`, tras el bloque `.ctrl` de "Profundidad" (index.html:46), añadir:

```html
      <div class="ctrl">
        <span class="ctrl-lbl">Respuesta</span>
        <div class="seg" role="group" aria-label="Largo de la respuesta">
          <button type="button" data-largo="corta" class="seg-opt is-on" title="1-2 frases.">Corta</button>
          <button type="button" data-largo="normal" class="seg-opt" title="Un párrafo.">Normal</button>
          <button type="button" data-largo="detallada" class="seg-opt" title="Con contexto y matices.">Detallada</button>
        </div>
      </div>
      <div class="ctrl">
        <span class="ctrl-lbl">Detalle</span>
        <div class="seg" role="group" aria-label="Nivel de detalle">
          <button type="button" data-detalle="simple" class="seg-opt is-on" title="Lenguaje llano.">Simple</button>
          <button type="button" data-detalle="tecnico" class="seg-opt" title="Cifras y metodología.">Técnico</button>
        </div>
      </div>
```

- [ ] **Step 2: Estado y listeners en `web/app.js`**

Tras `let rigor = "riguroso";` (app.js:18), añadir:

```javascript
let largo = "corta";
let detalle = "simple";
```

Reemplazar el listener de profundidad (app.js:76-83) por uno acotado a cada grupo `.seg` (evita que un grupo borre el `is-on` de los otros):

```javascript
/* ---------- Toggles segmentados (profundidad, largo, detalle) ---------- */
document.querySelectorAll(".seg").forEach((grupo) => {
  grupo.querySelectorAll(".seg-opt").forEach((btn) => {
    btn.addEventListener("click", () => {
      grupo.querySelectorAll(".seg-opt").forEach((b) => b.classList.remove("is-on"));
      btn.classList.add("is-on");
      if (btn.dataset.rigor) rigor = btn.dataset.rigor;
      else if (btn.dataset.largo) largo = btn.dataset.largo;
      else if (btn.dataset.detalle) detalle = btn.dataset.detalle;
    });
  });
});
```

- [ ] **Step 3: Mandar `largo`/`detalle` en el POST**

En el cuerpo del `fetch` (app.js:147-148, junto a `pais` y `rigor`), añadir:

```javascript
      largo,
      detalle,
```

- [ ] **Step 4: Asegurar que la barra de controles envuelve (en `web/style.css`)**

Para que cuatro controles quepan en pantallas angostas, garantizar el wrap. Localizar la regla `.controls { ... }` y añadirle (si no la tuviera ya) `flex-wrap: wrap;`. Si la regla no existe, añadir:

```css
.controls { flex-wrap: wrap; }
```

(Los estilos `.seg`, `.seg-opt`, `.is-on`, `.ctrl`, `.ctrl-lbl` ya existen y se reutilizan tal cual.)

- [ ] **Step 5: Verificar sintaxis**

Run: `node --check web/app.js`
Expected: sin errores.

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/app.js web/style.css
git commit -m "feat: controles de modo de respuesta (largo/detalle) en la UI"
```

---

### Task 5: Frontend — render limpio de encabezados y viñetas

**Files:**
- Modify: `web/app.js`
- Test: manual (`node --check`; sin harness JS)

**Interfaces:**
- Consumes: `escapar`, `negrita`, `enlazar` (existentes en app.js).
- Produces: `formatear` renderiza párrafos, convierte cualquier encabezado markdown (`#`..`######`) en **negrita** (nunca crudo) y agrupa viñetas `- `/`* ` en `<ul>`.

- [ ] **Step 1: Reemplazar `formatear` en `web/app.js`**

Sustituir la función `formatear` actual (app.js:423-426) por:

```javascript
// Formateo ligero y XSS-seguro: párrafos, **negrita**, enlaces, viñetas, y
// encabezados markdown degradados a negrita (nunca se muestran "###" crudos).
function formatear(texto) {
  const bloques = texto.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  return bloques.map(formatearBloque).join("");
}

function formatearBloque(bloque) {
  const lineas = bloque.split("\n").filter((l) => l.trim());
  const esVinieta = (l) => /^[-*]\s+/.test(l.trim());
  if (lineas.length && lineas.every(esVinieta)) {
    const items = lineas
      .map((l) => "<li>" + enLinea(l.trim().replace(/^[-*]\s+/, "")) + "</li>")
      .join("");
    return "<ul class='resp-lista'>" + items + "</ul>";
  }
  const html = lineas
    .map((l) => {
      const h = l.match(/^#{1,6}\s*(.+)$/);
      return h ? "<strong>" + enLinea(h[1]) + "</strong>" : enLinea(l);
    })
    .join("<br>");
  return "<p>" + html + "</p>";
}

// Transformaciones inline, siempre escapando primero (XSS).
function enLinea(s) {
  return enlazar(negrita(escapar(s)));
}
```

(`escapar`, `negrita` y `enlazar` quedan igual. `enlazarCitas` se sigue aplicando fuera, en `pintarRespuesta`, sobre el resultado de `formatear`.)

- [ ] **Step 2: Verificar sintaxis**

Run: `node --check web/app.js`
Expected: sin errores.

- [ ] **Step 3: Verificación manual del render**

Con el server corriendo (`.venv/bin/uvicorn verificador.server:app`), abrir http://127.0.0.1:8000 y hacer una consulta cuya respuesta antes mostraba `###`. Confirmar que:
- ningún `#` de encabezado aparece crudo (se ve en negrita);
- una respuesta con líneas `- ...` se ve como lista con viñetas;
- las citas `[n]` siguen siendo enlaces clicables.

(Si no hay clave/datos para una consulta real, basta `node --check` + revisión del código; anotarlo así en el reporte.)

- [ ] **Step 4: Commit**

```bash
git add web/app.js
git commit -m "fix: formatear degrada encabezados markdown a negrita y renderiza viñetas"
```

---

## Self-review (cobertura del spec)

- Eje largo + eje detalle, default corta+simple → Task 1 (textos+función), Task 2 (atributos+inyección), Task 3 (validación server), Task 4 (UI). ✓
- Control en UI (segmentados estilo rigor) → Task 4. ✓
- Modo por request, sin persistencia, reseteo al recargar → Task 3 (lee body) + Task 4 (variables JS por sesión). ✓
- No romper el caché del prompt (system base intacto) → Task 2 (mensaje system aparte; test lo verifica). ✓
- `rigor` separado del modo → no se toca `rigor`; atributos nuevos independientes. ✓
- Degradación ante valores inválidos → Task 1 (`instruccion_modo` cae al default) + Task 3 (validación server). ✓
- Arreglo `###` baseline (prompt + front) → Task 1 (regla en prompt) + Task 5 (formatear defensivo). ✓
- Citas `[n]` intactas → `enlazarCitas` se sigue aplicando en `pintarRespuesta`; Task 5 no lo toca. ✓
- Tests existentes no se rompen → Task 3 actualiza los 3 monkeypatches de `_sesion`. ✓
