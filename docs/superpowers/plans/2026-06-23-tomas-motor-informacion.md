# Tomás — motor de información: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ampliar a Tomás con acceso a sitios JS/bloqueados y vídeo (transcripción), razonamiento más rápido, respuestas concisas con citas verificables, y una traza de búsqueda viva.

**Architecture:** El backend Python (agente DeepSeek + tools) gana un enrutador de lectura (httpx rápido → Playwright fallback persistente) y una tool de vídeo (transcripción). El prompt produce prosa corta con citas `[n]` y un bloque JSON con `fuentes[].n`. El agente emite eventos de traza estructurados (dict) que el server retransmite por SSE; el frontend los pinta como tarjetas vivas y, en la respuesta, enlaza las citas y deja ver el extracto leído por fuente.

**Tech Stack:** Python 3.10+, openai SDK (DeepSeek), httpx, trafilatura, **playwright (chromium)**, **youtube-transcript-api**, FastAPI + SSE, JS/CSS sin build, pytest.

## Global Constraints

- Sin dependencias de terceros para alcanzar sitios: **navegador headless local (Playwright/Chromium)**; nunca un servicio externo de scraping.
- **IA descartable**: solo memoria de la conversación de la sesión (`_SESIONES[sid]`); sin perfil de usuario ni persistencia entre sesiones.
- **Visión de vídeo (fotogramas) = fuera de alcance**; vídeo se trata por transcripción/subtítulos/metadatos (texto).
- Modelo fijo: **DeepSeek** (`deepseek-chat`). No cambiar de modelo.
- Ruta rápida (httpx) **siempre primero**; Playwright solo como fallback, con **un Chromium persistente reutilizado** (no arrancar por llamada).
- Citas inline `[n]` del prose **deben** coincidir con `fuentes[].n` del JSON, numeradas por orden de aparición.
- Extracto enviado al cliente truncado a **~1500 caracteres**.
- Degradación elegante: si Playwright/Chromium no está, la ruta rápida sigue funcionando.

---

### Task 1: Setup — dependencias, test scaffolding, git

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nada.
- Produces: entorno con `playwright`, `youtube-transcript-api`, `pytest` instalados; Chromium descargado; `pytest` ejecutable desde la raíz.

- [ ] **Step 1: Añadir dependencias a `requirements.txt`**

Añadir al final:
```
# Acceso a sitios con JS/bloqueados (navegador headless local) y vídeo.
playwright>=1.44
youtube-transcript-api>=0.6
# Pruebas
pytest>=8.0
```

- [ ] **Step 2: Instalar dependencias y Chromium**

Run:
```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```
Expected: instala paquetes y descarga Chromium (~150–300 MB) sin error.

- [ ] **Step 3: Crear scaffolding de tests**

Crear `tests/__init__.py` (vacío) y `tests/conftest.py`:
```python
"""Configuración común de pytest: asegura que la raíz del proyecto está en sys.path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 4: Asegurar git y .gitignore**

Run:
```bash
git -C /Users/nachapoticon/Personal/verificador-politico rev-parse --git-dir 2>/dev/null || git -C /Users/nachapoticon/Personal/verificador-politico init
```
Añadir a `.gitignore` (si no están):
```
.venv
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 5: Verificar pytest**

Run: `.venv/bin/pytest -q`
Expected: "no tests ran" (sin errores de colección).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tests/__init__.py tests/conftest.py .gitignore
git commit -m "chore: add playwright, transcript and pytest deps + test scaffold"
```

---

### Task 2: Tool `ver_video` — transcripción de YouTube/Shorts

**Files:**
- Modify: `verificador/search.py`
- Test: `tests/test_video.py`

**Interfaces:**
- Consumes: nada de tareas previas.
- Produces:
  - `ver_video(url: str, max_chars: int = 6000) -> str` — devuelve texto plano (transcripción + cabecera con la URL) o un aviso `[...]` si no hay transcripción.
  - `_id_youtube(url: str) -> str | None` — extrae el id de vídeo de URLs de YouTube/Shorts/youtu.be.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_video.py`:
```python
from verificador import search


def test_id_youtube_formas():
    assert search._id_youtube("https://www.youtube.com/watch?v=abc123DEF45") == "abc123DEF45"
    assert search._id_youtube("https://youtu.be/abc123DEF45") == "abc123DEF45"
    assert search._id_youtube("https://www.youtube.com/shorts/abc123DEF45") == "abc123DEF45"
    assert search._id_youtube("https://elpais.com/algo") is None


def test_ver_video_youtube_usa_transcripcion(monkeypatch):
    # Simula la API de transcripción para no depender de la red.
    def fake_get(video_id, languages=None):
        assert video_id == "abc123DEF45"
        return [{"text": "Hola"}, {"text": "soy un vídeo"}]

    monkeypatch.setattr(search, "_fetch_transcripcion", lambda vid: "Hola soy un vídeo")
    out = search.ver_video("https://youtu.be/abc123DEF45")
    assert "Hola soy un vídeo" in out
    assert "youtu.be/abc123DEF45" in out


def test_ver_video_sin_transcripcion(monkeypatch):
    monkeypatch.setattr(search, "_fetch_transcripcion", lambda vid: None)
    out = search.ver_video("https://youtu.be/abc123DEF45")
    assert "sin transcripción" in out.lower()
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_video.py -v`
Expected: FAIL (`_id_youtube`/`ver_video` no existen).

- [ ] **Step 3: Implementar en `verificador/search.py`**

Añadir al inicio (imports) y nuevas funciones:
```python
import re

_YT_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def _id_youtube(url: str) -> str | None:
    m = _YT_RE.search(url or "")
    return m.group(1) if m else None


def _fetch_transcripcion(video_id: str) -> str | None:
    """Devuelve la transcripción unida, o None si no hay. Aísla la dependencia."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        tramos = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["es", "en", "pt", "fr"]
        )
    except Exception:  # noqa: BLE001 — sin transcripción disponible
        return None
    texto = " ".join(t.get("text", "") for t in tramos).strip()
    return texto or None


def ver_video(url: str, max_chars: int = 6000) -> str:
    """Lee el contenido de un vídeo por su transcripción (YouTube/Shorts).

    Verifica lo que se DICE en el vídeo, no la imagen. Para otras plataformas
    sin transcripción, devuelve un aviso (TikTok se cubre vía leer_pagina/navegador).
    """
    vid = _id_youtube(url)
    if vid:
        texto = _fetch_transcripcion(vid)
        if texto:
            if len(texto) > max_chars:
                texto = texto[:max_chars] + "\n…[transcripción truncada]"
            return f"[Transcripción de {url}]\n{texto}"
        return f"[{url}: sin transcripción disponible; no puedo leer su audio.]"
    return f"[{url}: no es un vídeo de YouTube con transcripción accesible.]"
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_video.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add verificador/search.py tests/test_video.py
git commit -m "feat: ver_video tool reads YouTube/Shorts transcripts"
```

---

### Task 3: Enrutador de `leer_pagina` con fallback de navegador persistente

**Files:**
- Modify: `verificador/search.py`
- Test: `tests/test_lectura.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `leer_pagina(url: str, max_chars: int = 6000) -> str` — enrutador: rápido → navegador.
  - `_leer_rapido(url: str) -> str | None` — httpx+trafilatura; None si falla/vacío.
  - `_leer_navegador(url: str) -> str | None` — Playwright; None si falla.
  - `_navegador()` — singleton perezoso del Chromium persistente.
  - `cerrar_navegador() -> None` — cierre limpio.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_lectura.py`:
```python
from verificador import search


def test_leer_pagina_usa_ruta_rapida(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "Texto rápido legible")
    # Si la rápida funciona, NO debe tocar el navegador.
    def boom(url):
        raise AssertionError("no debería usar el navegador")
    monkeypatch.setattr(search, "_leer_navegador", boom)
    assert search.leer_pagina("https://x.com") == "Texto rápido legible"


def test_leer_pagina_cae_al_navegador(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: None)
    monkeypatch.setattr(search, "_leer_navegador", lambda url: "Texto del navegador")
    assert search.leer_pagina("https://js-pesado.com") == "Texto del navegador"


def test_leer_pagina_trunca(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "A" * 9000)
    monkeypatch.setattr(search, "_leer_navegador", lambda url: None)
    out = search.leer_pagina("https://x.com", max_chars=100)
    assert out.endswith("…[texto truncado]")
    assert len(out) < 200


def test_leer_pagina_falla_todo(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: None)
    monkeypatch.setattr(search, "_leer_navegador", lambda url: None)
    out = search.leer_pagina("https://imposible.com")
    assert "no pude" in out.lower()
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_lectura.py -v`
Expected: FAIL (las funciones internas aún no existen con esta forma).

- [ ] **Step 3: Reescribir la lectura en `verificador/search.py`**

Reemplazar la función `leer_pagina` existente por el enrutador y sus auxiliares:
```python
_navegador_singleton = None  # (playwright, browser) reutilizados entre lecturas


def _extraer(html: str) -> str | None:
    import trafilatura

    return trafilatura.extract(
        html, include_comments=False, include_tables=True, favor_recall=True
    )


def _leer_rapido(url: str) -> str | None:
    """Ruta rápida: httpx + trafilatura. None si falla o sale vacío."""
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=8.0, follow_redirects=True)
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        return None
    texto = _extraer(resp.text)
    return texto or None


def _navegador():
    """Lanza Chromium una sola vez y lo reutiliza (coste de arranque amortizado)."""
    global _navegador_singleton
    if _navegador_singleton is None:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        _navegador_singleton = (pw, browser)
    return _navegador_singleton[1]


def _leer_navegador(url: str) -> str | None:
    """Fallback: renderiza con Chromium y extrae el texto principal."""
    try:
        browser = _navegador()
        page = browser.new_page(user_agent=_HEADERS["User-Agent"])
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
            html = page.content()
        finally:
            page.close()
    except Exception:  # noqa: BLE001 — degradación elegante (p.ej. Chromium ausente)
        return None
    return _extraer(html)


def cerrar_navegador() -> None:
    """Cierra el navegador persistente, si se abrió."""
    global _navegador_singleton
    if _navegador_singleton is not None:
        pw, browser = _navegador_singleton
        try:
            browser.close()
            pw.stop()
        except Exception:  # noqa: BLE001
            pass
        _navegador_singleton = None


def leer_pagina(url: str, max_chars: int = 6000) -> str:
    """Descarga una URL y devuelve su texto principal (rápido → navegador)."""
    texto = _leer_rapido(url) or _leer_navegador(url)
    if not texto:
        return f"[No pude abrir ni extraer texto de {url}.]"
    if len(texto) > max_chars:
        texto = texto[:max_chars] + "\n…[texto truncado]"
    return texto
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_lectura.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add verificador/search.py tests/test_lectura.py
git commit -m "feat: leer_pagina router with persistent Playwright fallback"
```

---

### Task 4: Exponer `ver_video` al modelo y dispatch en el agente

**Files:**
- Modify: `verificador/search.py` (TOOL_SCHEMAS)
- Modify: `verificador/agent.py` (`_ejecutar_tool`, `max_pasos`)
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `ver_video`, `leer_pagina`, `buscar_web` de tareas previas.
- Produces: el agente sabe ejecutar `ver_video`; `TOOL_SCHEMAS` incluye su esquema.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_dispatch.py`:
```python
from verificador import search
from verificador.agent import Verificador
from verificador.config import Config


def _agente():
    cfg = Config(api_key="x", base_url="http://local", model="deepseek-chat")
    return Verificador(config=cfg)


def test_schema_incluye_ver_video():
    nombres = {s["function"]["name"] for s in search.TOOL_SCHEMAS}
    assert {"buscar_web", "leer_pagina", "ver_video"} <= nombres


def test_dispatch_ver_video(monkeypatch):
    monkeypatch.setattr(search, "ver_video", lambda url, **k: f"VID:{url}")
    a = _agente()
    out = a._ejecutar_tool("ver_video", {"url": "https://youtu.be/abc123DEF45"})
    assert out == "VID:https://youtu.be/abc123DEF45"
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_dispatch.py -v`
Expected: FAIL (no existe el schema de `ver_video` ni el dispatch).

- [ ] **Step 3: Añadir el schema en `verificador/search.py`**

Añadir al final de la lista `TOOL_SCHEMAS`:
```python
    {
        "type": "function",
        "function": {
            "name": "ver_video",
            "description": (
                "Lee el CONTENIDO de un vídeo (YouTube, Shorts) por su "
                "transcripción para verificar lo que se dice en él. Úsala cuando "
                "la fuente sea un vídeo. No analiza la imagen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "La URL del vídeo."},
                },
                "required": ["url"],
            },
        },
    },
```

- [ ] **Step 4: Dispatch y menos pasos en `verificador/agent.py`**

En `_ejecutar_tool`, antes del `return "[Herramienta desconocida...]"`, añadir:
```python
        if nombre == "ver_video":
            return ver_video(url=args.get("url", ""))
```
Y actualizar el import:
```python
from .search import TOOL_SCHEMAS, buscar_web, leer_pagina, ver_video
```
Bajar el tope de pasos: `max_pasos: int = 12` → `max_pasos: int = 8`, y en `preguntar`:
`pasos = 6 if self.rigor == "rapido" else self.max_pasos` → `pasos = 4 if self.rigor == "rapido" else self.max_pasos`.

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_dispatch.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add verificador/search.py verificador/agent.py tests/test_dispatch.py
git commit -m "feat: expose ver_video to model, fewer steps"
```

---

### Task 5: Eventos de traza estructurados + captura de extractos

**Files:**
- Modify: `verificador/agent.py`
- Test: `tests/test_traza.py`

**Interfaces:**
- Consumes: bucle `preguntar`, tools.
- Produces: `preguntar(pregunta, on_step=None)` donde `on_step` recibe **dict**:
  - antes de ejecutar: `{"id": str, "tipo": "busqueda"|"pagina"|"video", "estado": "buscando"|"leyendo", "titulo": str, "url": str|None, "dominio": str|None}`
  - después: el mismo `id` con `"estado": "ok"|"fallo"` y, para `pagina`/`video`, `"extracto": str` (≤1500).
  - helper `_dominio(url) -> str`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_traza.py`:
```python
from verificador import agent as agentmod
from verificador.agent import Verificador, _dominio


class _FakeMsg:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeTC:
    def __init__(self, _id, name, args):
        self.id = _id
        self.type = "function"
        self.function = type("F", (), {"name": name, "arguments": args})()


def test_dominio():
    assert _dominio("https://www.elpais.com/x") == "elpais.com"
    assert _dominio("") == ""


def test_on_step_estructurado(monkeypatch):
    from verificador.config import Config
    a = Verificador(config=Config(api_key="x", base_url="http://l", model="m"))

    # Primera respuesta: pide leer_pagina; segunda: responde sin tools.
    respuestas = [
        _FakeMsg("", [_FakeTC("t1", "leer_pagina", '{"url": "https://www.elpais.com/n"}')]),
        _FakeMsg("Veredicto final"),
    ]

    class _Choices:
        def __init__(self, m): self.choices = [type("C", (), {"message": m})()]

    it = iter(respuestas)
    monkeypatch.setattr(
        a._client.chat.completions, "create", lambda **k: _Choices(next(it))
    )
    monkeypatch.setattr(agentmod, "leer_pagina", lambda url, **k: "EXTRACTO LEGIBLE")

    eventos = []
    a.preguntar("¿es verdad X?", on_step=eventos.append)

    leyendo = [e for e in eventos if e["estado"] == "leyendo"]
    ok = [e for e in eventos if e["estado"] == "ok"]
    assert leyendo and leyendo[0]["tipo"] == "pagina"
    assert leyendo[0]["dominio"] == "elpais.com"
    assert ok and ok[0]["extracto"] == "EXTRACTO LEGIBLE"
    assert ok[0]["id"] == leyendo[0]["id"]
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_traza.py -v`
Expected: FAIL (`_dominio` no existe; `on_step` aún recibe strings).

- [ ] **Step 3: Implementar en `verificador/agent.py`**

Añadir helper y reescribir el envío de pasos. Sustituir `_describir_paso` por:
```python
from urllib.parse import urlparse


def _dominio(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return ""
    return host[4:] if host.startswith("www.") else host


def _evento_inicio(_id: str, nombre: str, args: dict) -> dict:
    if nombre == "buscar_web":
        return {"id": _id, "tipo": "busqueda", "estado": "buscando",
                "titulo": args.get("query", ""), "url": None, "dominio": None}
    tipo = "video" if nombre == "ver_video" else "pagina"
    url = args.get("url", "")
    return {"id": _id, "tipo": tipo, "estado": "leyendo",
            "titulo": _dominio(url) or url, "url": url, "dominio": _dominio(url)}
```
En `preguntar`, dentro del bucle de `tool_calls`, reemplazar el bloque que llamaba a `on_step`/`_describir_paso` por:
```python
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                ev = _evento_inicio(tc.id, tc.function.name, args)
                if on_step:
                    on_step(ev)
                resultado = self._ejecutar_tool(tc.function.name, args)
                if on_step:
                    fin = {"id": ev["id"], "tipo": ev["tipo"], "estado": "ok",
                           "titulo": ev["titulo"], "url": ev["url"], "dominio": ev["dominio"]}
                    if ev["tipo"] in ("pagina", "video"):
                        fin["extracto"] = (resultado or "")[:1500]
                        if resultado.startswith("[No pude") or "sin transcripción" in resultado.lower():
                            fin["estado"] = "fallo"
                    on_step(fin)
                self.messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": resultado}
                )
```
Actualizar el tipo del parámetro: `on_step: Callable[[dict], None] | None = None`.

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_traza.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add verificador/agent.py tests/test_traza.py
git commit -m "feat: structured trace events with per-source excerpts"
```

---

### Task 6: Prompt conciso, citas [n] y adaptación sin memoria

**Files:**
- Modify: `verificador/prompts.py`
- Test: `tests/test_prompt.py`

**Interfaces:**
- Consumes: nada de código (texto del prompt).
- Produces: `SYSTEM_PROMPT` con el nuevo contrato (prosa corta + `[n]` + JSON con `n`).

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_prompt.py`:
```python
from verificador.prompts import SYSTEM_PROMPT


def test_prompt_pide_concision_citas_y_n():
    p = SYSTEM_PROMPT.lower()
    assert "concis" in p or "breve" in p
    assert "[1]" in SYSTEM_PROMPT  # ejemplo de cita inline
    assert '"n"' in SYSTEM_PROMPT   # campo n en el JSON
    assert "no guard" in p or "sin memoria" in p or "no construyas" in p
    # Ya NO debe imponer las secciones largas fijas:
    assert "Qué dicen las fuentes:" not in SYSTEM_PROMPT
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_prompt.py -v`
Expected: FAIL.

- [ ] **Step 3: Reescribir las secciones de formato en `verificador/prompts.py`**

Sustituir la sección `# Formato de respuesta` (y la lista "Fuentes" del prose) por:
```text
# Cómo respondes: conciso y a medida

Responde a la consulta concreta, sin plantillas. La longitud es PROPORCIONAL a
la pregunta: si es simple, responde en 1-3 frases; amplía solo si la persona pide
detalle o el matiz lo exige. Adáptate al tono y al nivel de quien pregunta a
partir de su propio mensaje y de la conversación de esta sesión. No construyas ni
guardes un perfil de la persona; no recuerdas a nadie entre sesiones.

Estructura mínima:
1) Primera línea: el veredicto con su etiqueta (✅ VERDADERO, ❌ FALSO,
   ⚠️ ENGAÑOSO, 🔀 SACADO DE CONTEXTO, 🔮 PREDICCIÓN, ❓ SIN EVIDENCIA).
2) Después, una explicación breve y directa. Cuando uses un dato, cítalo inline
   con un número entre corchetes: "...el paro bajó al 7% [1] aunque otro informe
   lo matiza [2]". Numera las citas por orden de aparición, empezando en [1].

No incluyas una lista de "Fuentes" en el texto: las fuentes van en el bloque JSON
final y la interfaz las muestra. Nunca afirmes un dato sin su cita.
```
Y actualizar el bloque JSON del "Pie técnico" para incluir `"n"`:
```text
  "fuentes": [
    {"n": 1, "medio": "nombre", "tendencia": "izquierda|centro-izquierda|centro|centro-derecha|derecha|verificador|internacional", "url": "https://...", "coincide": true}
  ]
```
Añadir esta frase tras el JSON: «`n` numera la fuente y DEBE coincidir con la cita `[n]` del texto; el orden sigue el de aparición de las citas.»

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_prompt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add verificador/prompts.py tests/test_prompt.py
git commit -m "feat: concise, need-adaptive prompt with inline [n] citations"
```

---

### Task 7: Server retransmite traza estructurada por SSE

**Files:**
- Modify: `verificador/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `Verificador.preguntar(on_step=dict)` (Task 5).
- Produces: el endpoint emite eventos SSE `traza` (dict tal cual) además de `respuesta`/`moderacion`/`error`.

- [ ] **Step 1: Escribir el test que falla**

Crear `tests/test_server.py`:
```python
import json
from fastapi.testclient import TestClient
from verificador import server


def test_sse_emite_traza_y_respuesta(monkeypatch):
    # Falsea el agente: emite un paso de traza y una respuesta.
    class _FakeAgente:
        country = None
        rigor = "riguroso"
        messages = [{"role": "assistant", "content": "RESPUESTA FINAL"}]
        def preguntar(self, pregunta, on_step=None):
            on_step({"id": "s1", "tipo": "busqueda", "estado": "buscando",
                     "titulo": "x", "url": None, "dominio": None})

    monkeypatch.setattr(server, "_sesion",
                        lambda sid, c, r: {"agente": _FakeAgente(), "strikes": 0})
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar",
                       json={"pregunta": "¿es verdad?", "sid": "t"}) as r:
        cuerpo = "".join(chunk for chunk in r.iter_text())
    assert "event: traza" in cuerpo
    assert "event: respuesta" in cuerpo
    assert "RESPUESTA FINAL" in cuerpo
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_server.py -v`
Expected: FAIL (hoy emite `paso`, no `traza`).

- [ ] **Step 3: Implementar en `verificador/server.py`**

En `trabajar()`, cambiar el `on_step` para emitir el dict tal cual como evento `traza`:
```python
                agente.preguntar(
                    pregunta, on_step=lambda ev: cola.put(("traza", ev))
                )
```
(El resto de `gen()` ya retransmite `evento, dato` con `_sse(evento, dato)`, así que `traza` se serializa solo.)

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add verificador/server.py tests/test_server.py
git commit -m "feat: stream structured 'traza' events over SSE"
```

---

### Task 8: Frontend — tarjetas vivas de búsqueda

**Files:**
- Modify: `web/app.js`
- Modify: `web/style.css`

**Interfaces:**
- Consumes: eventos SSE `traza` (dict con `id`, `tipo`, `estado`, `titulo`, `url`, `dominio`, `extracto?`).
- Produces:
  - en `app.js`, manejo del evento `traza` que crea/actualiza tarjetas por `id` y acumula `window`-scope `extractos[url] = {extracto, titulo}` (variable de módulo `EXTRACTOS`).
  - función `tarjetaFuente(ev)` y `actualizarTarjeta(ev)`.

- [ ] **Step 1: Reemplazar el manejo de `paso` por `traza` en `app.js`**

En `manejarEvento`, sustituir la rama `if (evento === "paso")` por:
```javascript
  if (evento === "traza") {
    pintarTrazaEvento(traza, dato);
  } else if (evento === "respuesta") {
```
Y añadir el mapa de extractos cerca de los `const` de arriba:
```javascript
const EXTRACTOS = {}; // url -> { extracto, titulo } acumulado de la traza
```

- [ ] **Step 2: Implementar `pintarTrazaEvento` en `app.js`**

Reemplazar `pintarPaso` por:
```javascript
function pintarTrazaEvento(traza, ev) {
  if (ev.url && ev.extracto) EXTRACTOS[ev.url] = { extracto: ev.extracto, titulo: ev.titulo };
  let card = traza.querySelector('[data-id="' + ev.id + '"]');
  if (!card) {
    card = document.createElement("div");
    card.className = "fuente-card";
    card.dataset.id = ev.id;
    const icono = ev.tipo === "busqueda" ? "🔎" : ev.tipo === "video" ? "▶" : "📄";
    const dom = ev.dominio
      ? '<img class="fav" alt="" src="https://www.google.com/s2/favicons?domain=' + ev.dominio + '&sz=32" />'
      : '<span class="fav fav--q">' + icono + "</span>";
    card.innerHTML = dom +
      '<span class="fuente-tit"></span>' +
      '<span class="fuente-estado"></span>';
    card.querySelector(".fuente-tit").textContent = ev.titulo || ev.dominio || "";
    traza.appendChild(card);
  }
  const est = card.querySelector(".fuente-estado");
  const etiquetas = { buscando: "buscando…", leyendo: "leyendo…", ok: "✓", fallo: "✗" };
  est.textContent = etiquetas[ev.estado] || "";
  card.dataset.estado = ev.estado;
}
```

- [ ] **Step 2b: Verificar sintaxis**

Run: `node --check web/app.js`
Expected: sin errores.

- [ ] **Step 3: Estilos de tarjeta en `web/style.css`**

Añadir (sección de traza):
```css
.fuente-card { display: flex; align-items: center; gap: 0.55rem; padding: 0.4rem 0; font-family: var(--mono); font-size: 0.78rem; color: var(--ink-2); animation: surgir 0.3s ease both; }
.fuente-card .fav { width: 18px; height: 18px; border-radius: 4px; flex: none; display: grid; place-items: center; }
.fuente-card .fuente-tit { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fuente-card .fuente-estado { color: var(--muted); }
.fuente-card[data-estado="buscando"] .fuente-estado,
.fuente-card[data-estado="leyendo"] .fuente-estado { color: var(--tomas); animation: latido 1.1s ease-in-out infinite; }
.fuente-card[data-estado="ok"] .fuente-estado { color: var(--true); }
.fuente-card[data-estado="fallo"] { opacity: 0.55; }
.fuente-card[data-estado="fallo"] .fuente-estado { color: var(--false); }
```

- [ ] **Step 4: Verificación manual**

Run: `.venv/bin/uvicorn verificador.server:app --port 8000` y abrir `http://127.0.0.1:8000`.
Hacer una pregunta. Expected: aparecen tarjetas con favicon/dominio que pasan de "buscando…/leyendo…" a "✓".

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/style.css
git commit -m "feat: live source cards in the search trace"
```

---

### Task 9: Frontend — citas clicables y "ver de dónde salió"

**Files:**
- Modify: `web/app.js`
- Modify: `web/style.css`

**Interfaces:**
- Consumes: `EXTRACTOS` (Task 8), `partirRespuesta`/`pintarEspectro` existentes, `meta.fuentes[].n/url`.
- Produces:
  - `enlazarCitas(html, fuentes)` — convierte `[n]` en enlaces a la fuente n.
  - render de fuentes con detalle desplegable del extracto.

- [ ] **Step 1: Escribir test de la función pura (node)**

Crear `tests/test_citas.mjs`:
```javascript
import assert from "node:assert";

// Copia mínima de la función a probar (sin DOM).
function enlazarCitas(texto, fuentes) {
  const porN = {};
  (fuentes || []).forEach((f) => { porN[f.n] = f; });
  return texto.replace(/\[(\d+)\]/g, (m, n) => {
    const f = porN[n];
    if (!f) return m;
    return '<a class="cita" href="' + f.url + '" target="_blank" rel="noopener">[' + n + "]</a>";
  });
}

const out = enlazarCitas("el paro bajó [1] pero [2] lo matiza", [
  { n: 1, url: "https://a.com" }, { n: 2, url: "https://b.com" },
]);
assert.ok(out.includes('href="https://a.com"'));
assert.ok(out.includes('>[2]</a>'));
assert.ok(enlazarCitas("sin [9] fuente", []).includes("[9]")); // sin enlace si no existe
console.log("ok");
```

- [ ] **Step 2: Ejecutar y ver que pasa**

Run: `node tests/test_citas.mjs`
Expected: imprime `ok`.

- [ ] **Step 3: Añadir `enlazarCitas` y usarla en `app.js`**

Añadir la función (idéntica a la del test, sin el `assert`) y, en `pintarRespuesta`, tras construir el cuerpo, enlazar las citas antes de inyectar el HTML:
```javascript
  const fuentes = (meta && meta.fuentes) || [];
  body.innerHTML = enlazarCitas(formatear(prosa), fuentes);
```

- [ ] **Step 4: "Ver de dónde salió" en `pintarEspectro`/fuentes**

En el render de fuentes (dentro de `pintarRespuesta`, donde se listan `meta.fuentes`), por cada fuente con extracto en `EXTRACTOS[f.url]`, añadir un `<details>`:
```javascript
  if (fuentes.length) {
    const lista = document.createElement("ul");
    lista.className = "fuentes-lista";
    fuentes.forEach((f) => {
      const li = document.createElement("li");
      const ex = EXTRACTOS[f.url];
      li.innerHTML =
        '<a href="' + f.url + '" target="_blank" rel="noopener">[' + f.n + "] " +
        (f.medio || f.url) + "</a>" +
        (ex ? '<details class="prueba"><summary>ver de dónde salió</summary>' +
              '<blockquote></blockquote></details>' : "");
      if (ex) li.querySelector("blockquote").textContent = ex.extracto;
      lista.appendChild(li);
    });
    cont.appendChild(lista);
  }
```

- [ ] **Step 4b: Verificar sintaxis**

Run: `node --check web/app.js`
Expected: sin errores.

- [ ] **Step 5: Estilos en `web/style.css`**

```css
.cita { font-size: 0.82em; vertical-align: super; color: var(--tomas); text-decoration: none; padding: 0 1px; }
.cita:hover { text-decoration: underline; }
.fuentes-lista { list-style: none; padding: 0; margin: 1.2rem 0 0; display: flex; flex-direction: column; gap: 0.6rem; }
.fuentes-lista > li { font-family: var(--mono); font-size: 0.82rem; }
.fuentes-lista a { color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--line); }
.fuentes-lista a:hover { border-color: var(--tomas); }
.prueba { margin-top: 0.3rem; }
.prueba summary { cursor: pointer; color: var(--muted); font-size: 0.74rem; letter-spacing: 0.04em; }
.prueba blockquote { margin: 0.5rem 0 0; padding: 0.6rem 0.8rem; border-left: 2px solid var(--tomas); background: var(--card); font-family: var(--serif); font-style: italic; font-size: 0.92rem; color: var(--ink-2); white-space: pre-wrap; }
```

- [ ] **Step 6: Verificación manual end-to-end**

Run: servidor en marcha; hacer una pregunta real. Expected: la respuesta es corta, con `[n]` clicables; bajo ella, la lista de fuentes con "ver de dónde salió" que despliega el extracto leído.

- [ ] **Step 7: Commit**

```bash
git add web/app.js web/style.css tests/test_citas.mjs
git commit -m "feat: clickable [n] citations and per-source evidence viewer"
```

---

## Self-review (cobertura del spec)

- §1 Razonamiento+velocidad → Task 4 (menos pasos), Task 6 (prompt: plan, paralelo, concisión). ✓
- §2 Acceso ampliado → Task 2 (vídeo), Task 3 (router+Playwright), Task 4 (expone tool). ✓
- §3 Concisión + citas + sin memoria → Task 6. ✓
- §4 Animación de búsqueda → Task 5 (eventos), Task 7 (SSE), Task 8 (tarjetas). ✓
- §5 Verificación de fuentes → Task 5 (extractos), Task 8 (acumula), Task 9 (citas + "ver de dónde salió"). ✓
- Memoria de sesión → sin cambios (se conserva `_SESIONES`). ✓
- Degradación si no hay Chromium → Task 3 (`_leer_navegador` devuelve None). ✓
