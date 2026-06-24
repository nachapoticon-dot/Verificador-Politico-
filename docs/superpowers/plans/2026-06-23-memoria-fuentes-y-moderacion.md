# Memoria de fuentes, veredicto honesto, lista ponderada y moderación — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar a Tomás un registro curado de fuentes con credibilidad que pondere lo que lee, dejar de estampar veredicto a preguntas sin afirmación, mostrar una lista ponderada de fuentes y endurecer la moderación de respeto hasta cerrar la conversación.

**Architecture:** Un módulo nuevo `verificador/fuentes.py` carga un registro JSON curado (dominio → credibilidad/tendencia/tipo) y anota cada resultado de búsqueda/lectura antes de que el modelo lo vea. El prompt clasifica pregunta vs afirmación y pondera por credibilidad. El frontend sustituye el medidor de espectro por una lista ponderada. La moderación pasa de avisos blandos a un aviso firme y cierre de sesión.

**Tech Stack:** Python 3.10+ (stdlib `json`, `urllib.parse`, `re`, `datetime`), pytest; FastAPI + SSE; JS/CSS sin build; `node --check` para sintaxis.

## Global Constraints

- **IA descartable**: solo memoria de la conversación de la sesión (`_SESIONES[sid]`); sin perfil de usuario ni persistencia entre sesiones. `fuentes.json` y `propuestas.jsonl` son metadatos de fuentes, no datos de usuario.
- Modelo fijo **DeepSeek** (`deepseek-chat`). No cambiar de modelo.
- Ruta rápida httpx siempre primero; Playwright solo fallback, en su hilo propietario (no tocar esa lógica).
- Citas `[n]` del prose deben coincidir con `fuentes[].n` del JSON.
- Credibilidad: 4 niveles exactos `alta | media | baja | no_fiable`.
- Tendencia (valores exactos): `izquierda | centro-izquierda | centro | centro-derecha | derecha | verificador | internacional`.
- Veredicto (valores exactos): `verdadero | falso | enganoso | fuera_de_contexto | prediccion | sin_evidencia | informativo`.
- Degradación elegante: nada nuevo debe romper la respuesta. La captura de propuestas y la anotación nunca lanzan hacia el usuario.
- No romper los 17 tests actuales.
- Usar el venv: `.venv/bin/pytest`, `.venv/bin/python`.

---

### Task 1: Módulo `fuentes.py` — registro, clasificación y anotación

**Files:**
- Create: `verificador/data/fuentes.json`
- Create: `verificador/fuentes.py`
- Test: `tests/test_fuentes.py`

**Interfaces:**
- Produces:
  - `class Fuente(NamedTuple)`: `dominio: str, credibilidad: str, tendencia: str, tipo: str, nota: str | None`
  - `dominio_registrable(url: str) -> str` — host en minúsculas, sin esquema, sin `www.`, sin puerto. `""` si no hay host.
  - `clasificar(url: str) -> Fuente | None` — match por igualdad de host o sufijo (`es.wikipedia.org` → `wikipedia.org`). `None` si no está en el registro.
  - `anotar(url: str) -> str` — etiqueta para el modelo (conocida vs desconocida).
  - `_REGISTRO: dict[str, dict]` — registro cargado (lo consume Task 2).

- [ ] **Step 1: Crear el registro semilla `verificador/data/fuentes.json`**

```json
{
  "reuters.com":       {"credibilidad": "alta", "tendencia": "centro", "tipo": "agencia"},
  "apnews.com":        {"credibilidad": "alta", "tendencia": "centro", "tipo": "agencia"},
  "afp.com":           {"credibilidad": "alta", "tendencia": "internacional", "tipo": "agencia"},
  "efe.com":           {"credibilidad": "alta", "tendencia": "centro", "tipo": "agencia"},
  "colombiacheck.com": {"credibilidad": "alta", "tendencia": "verificador", "tipo": "verificador_ifcn"},
  "lasillavacia.com":  {"credibilidad": "alta", "tendencia": "verificador", "tipo": "verificador_ifcn"},
  "chequeado.com":     {"credibilidad": "alta", "tendencia": "verificador", "tipo": "verificador_ifcn"},
  "animalpolitico.com":{"credibilidad": "alta", "tendencia": "verificador", "tipo": "verificador_ifcn"},
  "maldita.es":        {"credibilidad": "alta", "tendencia": "verificador", "tipo": "verificador_ifcn"},
  "newtral.es":        {"credibilidad": "alta", "tendencia": "verificador", "tipo": "verificador_ifcn"},
  "politifact.com":    {"credibilidad": "alta", "tendencia": "verificador", "tipo": "verificador_ifcn"},
  "factcheck.org":     {"credibilidad": "alta", "tendencia": "verificador", "tipo": "verificador_ifcn"},
  "fullfact.org":      {"credibilidad": "alta", "tendencia": "verificador", "tipo": "verificador_ifcn"},
  "elpais.com":        {"credibilidad": "media", "tendencia": "centro-izquierda", "tipo": "medio"},
  "eldiario.es":       {"credibilidad": "media", "tendencia": "izquierda", "tipo": "medio"},
  "elmundo.es":        {"credibilidad": "media", "tendencia": "centro-derecha", "tipo": "medio"},
  "abc.es":            {"credibilidad": "media", "tendencia": "derecha", "tipo": "medio"},
  "eltiempo.com":      {"credibilidad": "media", "tendencia": "centro", "tipo": "medio"},
  "elespectador.com":  {"credibilidad": "media", "tendencia": "centro-izquierda", "tipo": "medio"},
  "semana.com":        {"credibilidad": "media", "tendencia": "centro-derecha", "tipo": "medio"},
  "infobae.com":       {"credibilidad": "media", "tendencia": "centro-derecha", "tipo": "medio"},
  "nytimes.com":       {"credibilidad": "media", "tendencia": "centro-izquierda", "tipo": "medio"},
  "wsj.com":           {"credibilidad": "media", "tendencia": "centro-derecha", "tipo": "medio"},
  "foxnews.com":       {"credibilidad": "media", "tendencia": "derecha", "tipo": "medio"},
  "wikipedia.org":     {"credibilidad": "baja", "tendencia": "centro", "tipo": "enciclopedia_editable", "nota": "cualquiera edita; punto de partida, no prueba"},
  "blogspot.com":      {"credibilidad": "baja", "tendencia": "centro", "tipo": "blog"},
  "wordpress.com":     {"credibilidad": "baja", "tendencia": "centro", "tipo": "blog"},
  "medium.com":        {"credibilidad": "baja", "tendencia": "centro", "tipo": "blog"},
  "x.com":             {"credibilidad": "no_fiable", "tendencia": "internacional", "tipo": "red_social", "nota": "no es prueba de un hecho; sí fuente primaria de qué dijo alguien"},
  "twitter.com":       {"credibilidad": "no_fiable", "tendencia": "internacional", "tipo": "red_social", "nota": "no es prueba de un hecho; sí fuente primaria de qué dijo alguien"},
  "facebook.com":      {"credibilidad": "no_fiable", "tendencia": "internacional", "tipo": "red_social"},
  "tiktok.com":        {"credibilidad": "no_fiable", "tendencia": "internacional", "tipo": "red_social"},
  "instagram.com":     {"credibilidad": "no_fiable", "tendencia": "internacional", "tipo": "red_social"}
}
```

- [ ] **Step 2: Escribir el test que falla `tests/test_fuentes.py`**

```python
from verificador.fuentes import Fuente, dominio_registrable, clasificar, anotar


def test_dominio_registrable_normaliza():
    assert dominio_registrable("https://www.Reuters.com/article/x?y=1") == "reuters.com"
    assert dominio_registrable("http://es.wikipedia.org/wiki/Colombia") == "es.wikipedia.org"
    assert dominio_registrable("reuters.com/sin-esquema") == "reuters.com"
    assert dominio_registrable("") == ""


def test_clasificar_conocida_exacta_y_por_sufijo():
    f = clasificar("https://es.wikipedia.org/wiki/X")
    assert isinstance(f, Fuente)
    assert f.dominio == "wikipedia.org"
    assert f.credibilidad == "baja"
    assert clasificar("https://reuters.com/a").credibilidad == "alta"
    assert clasificar("https://blog.miblog.blogspot.com/post").credibilidad == "baja"


def test_clasificar_desconocida_es_none():
    assert clasificar("https://un-dominio-rarisimo-xyz.tld/nota") is None
    # un sufijo que NO es separador de dominio no debe colar como match:
    assert clasificar("https://notwikipedia.org/x") is None


def test_anotar_conocida_incluye_credibilidad_y_tendencia():
    a = anotar("https://es.wikipedia.org/wiki/X")
    assert "fiabilidad BAJA" in a
    assert "tendencia centro" in a
    assert "wikipedia.org" in a


def test_anotar_desconocida_pide_clasificar():
    a = anotar("https://un-dominio-rarisimo-xyz.tld/nota")
    assert "no registrado" in a
    assert "propuesta" in a
```

- [ ] **Step 3: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_fuentes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'verificador.fuentes'`.

- [ ] **Step 4: Implementar `verificador/fuentes.py` (parte 1)**

```python
"""Registro curado de fuentes y su credibilidad.

Dos ejes independientes por fuente: tendencia política y credibilidad (alta,
media, baja, no_fiable). El registro vive en `data/fuentes.json` (curado a mano)
y se aplica por auto-anotación: cada fuente que el modelo ve va etiquetada con su
fiabilidad, para que pondere lo que lee. Las fuentes no registradas se proponen
para revisión humana (no se aplican solas).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlparse

_DATA_DIR = Path(__file__).resolve().parent / "data"
_FUENTES_PATH = _DATA_DIR / "fuentes.json"


class Fuente(NamedTuple):
    dominio: str
    credibilidad: str  # alta | media | baja | no_fiable
    tendencia: str
    tipo: str
    nota: str | None


def _cargar_registro() -> dict[str, dict]:
    try:
        with _FUENTES_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 — sin registro, degradamos a {}
        return {}


_REGISTRO: dict[str, dict] = _cargar_registro()

_ETIQ_CRED = {"alta": "ALTA", "media": "MEDIA", "baja": "BAJA", "no_fiable": "NO FIABLE"}


def dominio_registrable(url: str) -> str:
    """Host en minúsculas, sin esquema, sin `www.`, sin puerto. '' si no hay."""
    if not url:
        return ""
    host = urlparse(url if "://" in url else "http://" + url).hostname or ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def clasificar(url: str) -> Fuente | None:
    """Devuelve la ficha de la fuente, o None si su dominio no está registrado.

    Empareja por igualdad de host o por sufijo de dominio (`es.wikipedia.org`
    casa con la clave `wikipedia.org`; `notwikipedia.org` NO, por el punto guía).
    """
    host = dominio_registrable(url)
    if not host:
        return None
    for dom, ficha in _REGISTRO.items():
        if host == dom or host.endswith("." + dom):
            return Fuente(dom, ficha["credibilidad"], ficha["tendencia"],
                          ficha["tipo"], ficha.get("nota"))
    return None


def anotar(url: str) -> str:
    """Etiqueta que se antepone a lo que el modelo ve de esta fuente."""
    f = clasificar(url)
    if f is None:
        return ("[fuente: dominio no registrado — clasifícala tú en el JSON de "
                "cierre; quedará como propuesta de revisión]")
    nota = f" ({f.nota})" if f.nota else ""
    return (f"[fuente: {f.dominio} · fiabilidad {_ETIQ_CRED[f.credibilidad]}"
            f"{nota} · tendencia {f.tendencia}]")
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_fuentes.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add verificador/data/fuentes.json verificador/fuentes.py tests/test_fuentes.py
git commit -m "feat: registro curado de fuentes con credibilidad + clasificar/anotar"
```

---

### Task 2: Propuestas de fuentes — captura, dedupe y CLI de revisión

**Files:**
- Modify: `verificador/fuentes.py`
- Modify: `.gitignore`
- Test: `tests/test_fuentes.py`

**Interfaces:**
- Consumes: `_REGISTRO`, `clasificar`, `dominio_registrable` (Task 1).
- Produces:
  - `extraer_meta(texto: str) -> dict | None` — parsea el bloque ```json``` final de una respuesta.
  - `capturar_propuestas(meta: dict | None, ruta: Path | None = None) -> int` — registra dominios no conocidos; devuelve cuántos nuevos escribió.
  - CLI: `python -m verificador.fuentes revisar` lista propuestas pendientes.
  - `PROPUESTAS_PATH: Path`.

- [ ] **Step 1: Escribir los tests que fallan (añadir a `tests/test_fuentes.py`)**

```python
import json as _json
from pathlib import Path
from verificador.fuentes import extraer_meta, capturar_propuestas


def test_extraer_meta_lee_el_json_final():
    texto = 'Bla bla [1].\n\n```json\n{"veredicto":"informativo","fuentes":[]}\n```'
    meta = extraer_meta(texto)
    assert meta["veredicto"] == "informativo"
    assert extraer_meta("sin json") is None
    assert extraer_meta("```json\n{mal json\n```") is None


def test_capturar_propuestas_solo_desconocidas_y_dedupe(tmp_path):
    ruta = tmp_path / "propuestas.jsonl"
    meta = {"fuentes": [
        {"medio": "Reuters", "url": "https://reuters.com/a", "credibilidad": "alta", "tendencia": "centro"},
        {"medio": "Diario Raro", "url": "https://diario-raro-xyz.tld/n", "credibilidad": "media", "tendencia": "centro"},
    ]}
    assert capturar_propuestas(meta, ruta) == 1  # reuters ya está en el registro
    # repetir el mismo dominio no añade otra línea
    assert capturar_propuestas(meta, ruta) == 0
    lineas = [l for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lineas) == 1
    fila = _json.loads(lineas[0])
    assert fila["dominio"] == "diario-raro-xyz.tld"
    assert fila["credibilidad"] == "media"


def test_capturar_propuestas_meta_vacia_no_rompe(tmp_path):
    ruta = tmp_path / "p.jsonl"
    assert capturar_propuestas(None, ruta) == 0
    assert capturar_propuestas({}, ruta) == 0
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_fuentes.py -k "meta or propuestas" -v`
Expected: FAIL — `ImportError: cannot import name 'extraer_meta'`.

- [ ] **Step 3: Implementar en `verificador/fuentes.py` (parte 2)**

Añadir los imports al principio del módulo (junto a los existentes):

```python
import re
from datetime import datetime, timezone
```

Y al final del módulo:

```python
PROPUESTAS_PATH = _DATA_DIR / "propuestas.jsonl"

_JSON_RE = re.compile(r"```json\s*([\s\S]*?)```\s*$", re.IGNORECASE)


def extraer_meta(texto: str) -> dict | None:
    """Parsea el bloque ```json``` final de una respuesta. None si falta o es inválido."""
    m = _JSON_RE.search(texto or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1).strip())
    except Exception:  # noqa: BLE001 — JSON inválido: lo ignoramos
        return None


def _dominios_propuestos(ruta: Path) -> set[str]:
    if not ruta.exists():
        return set()
    doms: set[str] = set()
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            doms.add(json.loads(linea)["dominio"])
        except Exception:  # noqa: BLE001
            continue
    return doms


def capturar_propuestas(meta: dict | None, ruta: Path | None = None) -> int:
    """Registra (append-only, deduplicado) los dominios de `meta.fuentes` que no
    están en el registro curado. Nunca lanza: si algo falla, devuelve lo escrito.
    """
    if ruta is None:
        ruta = PROPUESTAS_PATH
    if not meta:
        return 0
    fuentes = meta.get("fuentes") or []
    ya = {d.lower() for d in _REGISTRO} | _dominios_propuestos(ruta)
    nuevos = 0
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        for f in fuentes:
            url = (f or {}).get("url") or ""
            dom = dominio_registrable(url)
            if not dom or dom in ya or clasificar(url) is not None:
                continue
            fila = {
                "dominio": dom,
                "credibilidad": f.get("credibilidad"),
                "tendencia": f.get("tendencia"),
                "ejemplo_url": url,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            with ruta.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            ya.add(dom)
            nuevos += 1
    except Exception:  # noqa: BLE001 — la captura jamás rompe la respuesta
        return nuevos
    return nuevos


def _revisar() -> int:
    """Imprime las propuestas pendientes agrupadas por dominio (para curar a mano)."""
    propuestas = _dominios_propuestos(PROPUESTAS_PATH)
    if not propuestas:
        print("No hay propuestas pendientes.")
        return 0
    filas: dict[str, dict] = {}
    for linea in PROPUESTAS_PATH.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            d = json.loads(linea)
        except Exception:  # noqa: BLE001
            continue
        filas[d["dominio"]] = d  # última valoración gana
    print(f"{len(filas)} dominio(s) propuesto(s) (no en el registro curado):\n")
    for dom, d in sorted(filas.items()):
        print(f'  "{dom}": {{"credibilidad": "{d.get("credibilidad")}", '
              f'"tendencia": "{d.get("tendencia")}", "tipo": "?"}}'
              f'   # ej: {d.get("ejemplo_url")}')
    print("\nCopia las aprobadas a verificador/data/fuentes.json.")
    return 0


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "revisar":
        raise SystemExit(_revisar())
    print("Uso: python -m verificador.fuentes revisar")
    raise SystemExit(1)
```

- [ ] **Step 4: Ignorar el log de propuestas en git (añadir a `.gitignore`)**

Añadir la línea:

```
verificador/data/propuestas.jsonl
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_fuentes.py -v`
Expected: PASS (todos, incluidos los 3 nuevos).

- [ ] **Step 6: Commit**

```bash
git add verificador/fuentes.py tests/test_fuentes.py .gitignore
git commit -m "feat: captura de propuestas de fuentes + CLI revisar"
```

---

### Task 3: Auto-anotación en `search.py`

**Files:**
- Modify: `verificador/search.py`
- Test: `tests/test_lectura.py`, `tests/test_video.py`

**Interfaces:**
- Consumes: `fuentes.anotar(url)` (Task 1).
- Produces: `buscar_web` añade clave `"fiabilidad"` a cada resultado; `leer_pagina`/`ver_video` anteponen la etiqueta al `texto` cuando `ok` es True.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir a `tests/test_video.py`:

```python
def test_ver_video_ok_antepone_anotacion(monkeypatch):
    import verificador.search as s
    monkeypatch.setattr(s, "_id_youtube", lambda url: "abc12345678")
    monkeypatch.setattr(s, "_fetch_transcripcion", lambda vid: "hola mundo")
    out = s.ver_video("https://youtube.com/watch?v=abc12345678")
    assert out.ok is True
    assert out.texto.startswith("[fuente:")          # anotación antepuesta
    assert "hola mundo" in out.texto


def test_ver_video_fallo_no_antepone_anotacion(monkeypatch):
    import verificador.search as s
    out = s.ver_video("https://vimeo.com/123")        # no es YouTube → fallo
    assert out.ok is False
    assert not out.texto.startswith("[fuente:")
```

Añadir a `tests/test_lectura.py`:

```python
def test_leer_pagina_ok_antepone_anotacion(monkeypatch):
    import verificador.search as s
    monkeypatch.setattr(s, "_leer_rapido", lambda url: "contenido leído")
    out = s.leer_pagina("https://reuters.com/articulo")
    assert out.ok is True
    assert out.texto.startswith("[fuente:")
    assert "fiabilidad ALTA" in out.texto
    assert "contenido leído" in out.texto


def test_buscar_web_anota_cada_resultado(monkeypatch):
    import verificador.search as s

    class _DDGS:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def text(self, *a, **k):
            return [{"title": "t", "href": "https://es.wikipedia.org/wiki/X", "body": "b"}]

    monkeypatch.setattr("ddgs.DDGS", _DDGS)
    res = s.buscar_web("colombia")
    assert "fiabilidad BAJA" in res[0]["fiabilidad"]
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_video.py tests/test_lectura.py -k "anota or anotacion" -v`
Expected: FAIL (la anotación aún no se antepone; `KeyError: 'fiabilidad'`).

- [ ] **Step 3: Implementar en `verificador/search.py`**

Añadir el import (junto a los otros del módulo):

```python
from . import fuentes
```

En `ver_video`, en la rama de éxito, anteponer la anotación tras truncar:

```python
        texto = _fetch_transcripcion(vid)
        if texto:
            if len(texto) > max_chars:
                texto = texto[:max_chars] + "\n…[transcripción truncada]"
            return Lectura(f"{fuentes.anotar(url)}\n[Transcripción de {url}]\n{texto}", True)
```

En `leer_pagina`, anteponer la anotación tras truncar:

```python
    texto = _leer_rapido(url) or _leer_navegador(url)
    if not texto:
        return Lectura(f"[No pude abrir ni extraer texto de {url}.]", False)
    if len(texto) > max_chars:
        texto = texto[:max_chars] + "\n…[texto truncado]"
    return Lectura(f"{fuentes.anotar(url)}\n{texto}", True)
```

En `buscar_web`, dentro del bucle `for r in ddgs.text(...)`, extraer `url` a una variable y añadir la clave `fiabilidad` a cada resultado (mantener la llamada `ddgs.text(query, region=region, max_results=max_resultados)` igual que estaba):

```python
            for r in ddgs.text(query, region=region, max_results=max_resultados):
                url = r.get("href") or r.get("url", "")
                resultados.append(
                    {
                        "titulo": r.get("title", ""),
                        "url": url,
                        "resumen": r.get("body", ""),
                        "fiabilidad": fuentes.anotar(url),
                    }
                )
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_video.py tests/test_lectura.py -v`
Expected: PASS (incluidos los nuevos; los existentes siguen verdes — los mocks de `_leer_rapido`/`_fetch_transcripcion` no cambian el contrato `Lectura`).

- [ ] **Step 5: Commit**

```bash
git add verificador/search.py tests/test_lectura.py tests/test_video.py
git commit -m "feat: auto-anotación de credibilidad en buscar_web/leer_pagina/ver_video"
```

---

### Task 4: Captura de propuestas en `agent.py`

**Files:**
- Modify: `verificador/agent.py`
- Test: `tests/test_traza.py` (o nuevo bloque)

**Interfaces:**
- Consumes: `fuentes.extraer_meta`, `fuentes.capturar_propuestas` (Task 2).
- Produces: tras producir la respuesta final, `preguntar` registra las propuestas de fuentes no conocidas (sin romper nada).

- [ ] **Step 1: Escribir el test que falla (añadir a `tests/test_traza.py`)**

El test falsea el cliente de DeepSeek para que `preguntar` devuelva una respuesta final (sin tool_calls) con un JSON de cierre que cita un dominio no registrado:

```python
def test_preguntar_captura_propuestas(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import verificador.agent as agentmod
    import verificador.fuentes as fuentes

    ruta = tmp_path / "propuestas.jsonl"
    monkeypatch.setattr(fuentes, "PROPUESTAS_PATH", ruta)

    ver = agentmod.Verificador()
    final = ('Respuesta [1].\n\n```json\n{"veredicto":"informativo","fuentes":'
             '[{"n":1,"medio":"Raro","url":"https://diario-raro-xyz.tld/n",'
             '"credibilidad":"media","tendencia":"centro"}]}\n```')
    fake = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=final, tool_calls=None))]
    )
    monkeypatch.setattr(ver._client.chat.completions, "create", lambda **k: fake)

    out = ver.preguntar("¿algo?")
    assert out == final
    assert ruta.exists()
    assert "diario-raro-xyz.tld" in ruta.read_text(encoding="utf-8")
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_traza.py -k propuestas -v`
Expected: FAIL (no se capturan propuestas todavía).

- [ ] **Step 3: Implementar en `verificador/agent.py`**

Añadir el import:

```python
from . import fuentes
```

En `preguntar`, el retorno de la respuesta final es `return msg.content or ""` (cuando `msg.tool_calls` es falsy, agent.py:116). Reemplazar esa línea por la captura previa + retorno:

```python
            # Sin llamadas a herramientas → es la respuesta final.
            if not msg.tool_calls:
                final = msg.content or ""
                # Propone para revisión las fuentes citadas cuyo dominio no esté
                # en el registro curado. Nunca debe romper la respuesta.
                try:
                    fuentes.capturar_propuestas(fuentes.extraer_meta(final))
                except Exception:  # noqa: BLE001
                    pass
                return final
```

(No hace falta capturar en el retorno del límite de pasos, agent.py:141, porque ahí no hay JSON de cierre.)

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_traza.py -v`
Expected: PASS (incluido el nuevo; los demás de traza siguen verdes).

- [ ] **Step 5: Commit**

```bash
git add verificador/agent.py tests/test_traza.py
git commit -m "feat: agent propone fuentes no registradas tras responder"
```

---

### Task 5: Prompt — veredicto `informativo`, credibilidad y ponderación

**Files:**
- Modify: `verificador/prompts.py`
- Test: `tests/test_prompt.py`

**Interfaces:**
- Produces: `SYSTEM_PROMPT` con clasificación pregunta/afirmación, ponderación por credibilidad y contrato JSON con `informativo` + `credibilidad`.

- [ ] **Step 1: Escribir el test que falla (añadir a `tests/test_prompt.py`)**

```python
def test_prompt_clasifica_pregunta_y_pondera_credibilidad():
    from verificador.prompts import SYSTEM_PROMPT
    p = SYSTEM_PROMPT
    pl = p.lower()
    # veredicto informativo para preguntas sin afirmación:
    assert "informativo" in p
    assert "afirmaci" in pl  # menciona afirmación vs pregunta
    # ponderación por credibilidad y trato de baja/no fiable:
    assert "credibilidad" in pl
    assert "no_fiable" in p
    assert "wikipedia" in pl  # punto de partida, no prueba
    # el JSON de cierre incluye el campo credibilidad por fuente:
    assert '"credibilidad"' in p
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_prompt.py -v`
Expected: FAIL (`informativo`/`credibilidad` aún no están en el prompt).

- [ ] **Step 3: Editar `verificador/prompts.py`**

**3a.** Tras la sección `# Cómo trabajas` (antes de `# Tu voz`), insertar una sección nueva:

```text
# Antes de verificar: ¿hay una afirmación que contrastar?

Distingue qué te piden:
- Si la consulta contiene una AFIRMACIÓN verificable (algo que puede ser
  verdadero o falso), investígala y emite veredicto.
- Si es una PREGUNTA informativa o un tema, sin afirmación que contrastar
  (p. ej. "presidente actual de Colombia 2026"), respóndela igual de bien (con
  búsqueda y citas) pero NO la marques como verdadera o falsa: usa el veredicto
  `informativo`. No inventes una afirmación para poder estampar un sello.

# Pondera por credibilidad de la fuente

Cada fuente que leas viene etiquetada con su fiabilidad (alta, media, baja,
no_fiable) y su tendencia. Úsalas:
- Nunca sostengas un veredicto solo sobre una fuente de credibilidad `baja` o
  `no_fiable`. Corrobóralo con fuentes `alta`/`media`.
- Wikipedia y similares son punto de partida, no prueba.
- Las redes sociales valen como prueba de QUÉ DIJO alguien (fuente primaria),
  no de que un hecho sea cierto.
- Si una fuente no viene etiquetada (dominio no registrado), clasifícala tú en
  el JSON de cierre con tu mejor juicio; quedará registrada como propuesta.
```

**3b.** En la sección `# Pie técnico`, cambiar el enum de `veredicto` y añadir `credibilidad` al objeto de `fuentes`:

```text
  "veredicto": "verdadero|falso|enganoso|fuera_de_contexto|prediccion|sin_evidencia|informativo",
```

```text
  "fuentes": [
    {"n": 1, "medio": "nombre", "tendencia": "izquierda|centro-izquierda|centro|centro-derecha|derecha|verificador|internacional", "credibilidad": "alta|media|baja|no_fiable", "url": "https://...", "coincide": true}
  ]
```

**3c.** Añadir, tras la explicación del JSON, esta frase:

```text
`credibilidad` refleja la fiabilidad de la fuente (usa la etiqueta que viene con
cada fuente; si no venía etiquetada, tu mejor juicio). Para `veredicto` =
`informativo`, `confianza` no es veracidad: déjala en 0 o como solidez de la
información.
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_prompt.py -v`
Expected: PASS (incluido el test existente de concisión/citas).

- [ ] **Step 5: Commit**

```bash
git add verificador/prompts.py tests/test_prompt.py
git commit -m "feat: prompt clasifica pregunta/afirmación y pondera credibilidad"
```

---

### Task 6: Moderación — aviso firme y cierre

**Files:**
- Modify: `verificador/moderation.py`
- Test: `tests/test_moderation.py`

**Interfaces:**
- Produces: `mensaje_limite(strikes: int) -> str` con dos estados: `strikes <= 1` → aviso firme; `strikes >= 2` → mensaje de cierre. `es_irrespetuoso` no cambia.

- [ ] **Step 1: Escribir el test que falla `tests/test_moderation.py`**

```python
from verificador.moderation import es_irrespetuoso, mensaje_limite


def test_detecta_insulto_y_respeta_excepcion():
    assert es_irrespetuoso("eres estupido") is True
    assert es_irrespetuoso("esa noticia es una mierda") is False
    assert es_irrespetuoso("¿es verdad que bajó el paro?") is False


def test_primer_aviso_es_firme_no_blando():
    m = mensaje_limite(1)
    assert "buena onda" not in m.lower()      # ya no es blando
    assert "respeto" in m.lower()


def test_repeticion_cierra_la_conversacion():
    m = mensaje_limite(2)
    ml = m.lower()
    assert "cierr" in ml or "cerrad" in ml or "termin" in ml
    # y se mantiene firme también para strikes mayores
    assert mensaje_limite(3) == m
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_moderation.py -v`
Expected: FAIL (el mensaje actual de strike 1 dice "en buena onda"; no hay mensaje de cierre).

- [ ] **Step 3: Reescribir `mensaje_limite` en `verificador/moderation.py`**

Sustituir la función `mensaje_limite` por:

```python
def mensaje_limite(strikes: int) -> str:
    """Aviso firme al primer insulto; mensaje de cierre si se repite."""
    if strikes <= 1:
        return (
            "Aquí no se falta el respeto. No voy a responder a un insulto. "
            "Si quieres que verifique algo, pídemelo con respeto y lo hago."
        )
    return (
        "Esto se termina aquí: ya te pedí respeto y seguiste. Cierro la "
        "conversación. Si quieres retomar, empieza de nuevo y con buen trato."
    )
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_moderation.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add verificador/moderation.py tests/test_moderation.py
git commit -m "feat: moderación firme con cierre de conversación al reincidir"
```

---

### Task 7: Server — estado `cerrada` y eventos

**Files:**
- Modify: `verificador/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `es_irrespetuoso`, `mensaje_limite` (Task 6).
- Produces: SSE emite evento `cerrada` al reincidir y ante sesiones ya cerradas; la sesión gana `cerrada: bool`; se elimina el decremento de strikes.

- [ ] **Step 1: Escribir los tests que fallan (añadir a `tests/test_server.py`)**

```python
def test_segundo_insulto_cierra_la_sesion(monkeypatch):
    from fastapi.testclient import TestClient
    from verificador import server

    sesion = {"agente": None, "strikes": 0, "cerrada": False}
    monkeypatch.setattr(server, "_sesion", lambda sid, c, r: sesion)
    client = TestClient(server.app)

    def pedir(texto):
        with client.stream("POST", "/api/verificar",
                           json={"pregunta": texto, "sid": "t"}) as r:
            return "".join(chunk for chunk in r.iter_text())

    c1 = pedir("eres estupido")
    assert "event: moderacion" in c1
    c2 = pedir("idiota")
    assert "event: cerrada" in c2
    assert sesion["cerrada"] is True


def test_sesion_cerrada_rechaza_sin_llamar_al_modelo(monkeypatch):
    from fastapi.testclient import TestClient
    from verificador import server

    class _Boom:
        def preguntar(self, *a, **k):
            raise AssertionError("no debe llamar al modelo en sesión cerrada")
        messages = []
    sesion = {"agente": _Boom(), "strikes": 2, "cerrada": True}
    monkeypatch.setattr(server, "_sesion", lambda sid, c, r: sesion)
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar",
                       json={"pregunta": "¿es verdad?", "sid": "t"}) as r:
        cuerpo = "".join(chunk for chunk in r.iter_text())
    assert "event: cerrada" in cuerpo
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `.venv/bin/pytest tests/test_server.py -k "cerrada or cierra" -v`
Expected: FAIL (no existe el evento `cerrada` ni el estado).

- [ ] **Step 3: Editar `verificador/server.py`**

**3a.** En `_sesion`, inicializar `cerrada` al crear la sesión:

```python
        s = {"agente": Verificador(country=country, rigor=rigor), "strikes": 0, "cerrada": False}
```

**3b.** En `gen()`, sustituir el bloque de moderación (entre el chequeo de `pregunta` vacía y la verificación) por:

```python
        # 0) Sesión ya cerrada por faltas de respeto: no se procesa nada más.
        if sesion.get("cerrada"):
            yield _sse("cerrada", {"mensaje": mensaje_limite(2)})
            return

        # 1) Moderación: límite firme y cierre si se reincide, sin llamar al modelo.
        if es_irrespetuoso(pregunta):
            sesion["strikes"] += 1
            if sesion["strikes"] >= 2:
                sesion["cerrada"] = True
                yield _sse("cerrada", {"mensaje": mensaje_limite(sesion["strikes"])})
            else:
                yield _sse("moderacion", {"mensaje": mensaje_limite(sesion["strikes"])})
            return
```

Eliminar el bloque que decrementaba strikes ("Buen trato: la persona puede ir recuperando margen").

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `.venv/bin/pytest tests/test_server.py -v`
Expected: PASS (incluidos los nuevos; el test de SSE `traza`/`respuesta` sigue verde).

- [ ] **Step 5: Commit**

```bash
git add verificador/server.py tests/test_server.py
git commit -m "feat: server cierra la sesión al reincidir en faltas de respeto"
```

---

### Task 8: Frontend — lista ponderada de fuentes + sello `informativo`

**Files:**
- Modify: `web/app.js`
- Modify: `web/style.css`

**Interfaces:**
- Consumes: `meta.fuentes[]` con `tendencia`, `credibilidad`, `url`, `n`, `coincide`, `medio`; `EXTRACTOS` (de la traza); `urlSegura` (Task 9 previa).
- Produces: una sola lista ponderada (sustituye `pintarEspectro` + la lista de la Task 9 anterior); sello `informativo`.

- [ ] **Step 1: Añadir el sello `informativo` y un mapa de etiquetas de credibilidad (en `web/app.js`)**

En el objeto `SELLOS`, añadir la entrada:

```javascript
  informativo:        { etiqueta: "Información", v: "info", emoji: "ℹ️" },
```

Cerca de los `const` de arriba, añadir:

```javascript
// Etiquetas legibles de credibilidad (clave del JSON → texto + clase de color).
const CREDIBILIDAD = {
  alta:      { txt: "alta",      clase: "b-alta" },
  media:     { txt: "media",     clase: "b-media" },
  baja:      { txt: "baja",      clase: "b-baja" },
  no_fiable: { txt: "no fiable", clase: "b-no" },
};
// Bloque de color por tendencia.
const TEND_CLASE = {
  "izquierda": "t-izq", "centro-izquierda": "t-izq", "centro": "t-cen",
  "centro-derecha": "t-der", "derecha": "t-der",
  "verificador": "t-ver", "internacional": "t-int",
};
```

- [ ] **Step 2: Reemplazar el render de fuentes en `pintarRespuesta` por la lista ponderada**

En `pintarRespuesta`, **eliminar** la llamada a `pintarEspectro`:

```javascript
  if (meta && Array.isArray(meta.fuentes) && meta.fuentes.length) {
    cont.appendChild(pintarEspectro(meta.fuentes));
  }
```

y la construcción de la `fuentes-lista` anterior (la de la Task 9), sustituyéndolas por una sola llamada:

```javascript
  const fuentesMeta = (meta && Array.isArray(meta.fuentes)) ? meta.fuentes : [];
  if (fuentesMeta.length) {
    cont.appendChild(pintarFuentes(fuentesMeta));
  }
```

Reemplazar la función `pintarEspectro` entera por `pintarFuentes` (construcción XSS-segura por DOM):

```javascript
// Lista ponderada de fuentes: tendencia + medio + respalda/matiza + credibilidad
// + "ver de dónde salió". Reemplaza al medidor de espectro.
function pintarFuentes(fuentes) {
  const box = document.createElement("div");
  box.className = "fuentes-bloque";
  const cab = document.createElement("div");
  cab.className = "fuentes-cab";
  cab.textContent = "fuentes contrastadas";
  box.appendChild(cab);

  const lista = document.createElement("ul");
  lista.className = "fuentes-lista";
  fuentes.forEach((f) => {
    const li = document.createElement("li");

    const tend = document.createElement("span");
    const tkey = (f.tendencia || "").toLowerCase();
    tend.className = "chip-t " + (TEND_CLASE[tkey] || "t-cen");
    tend.textContent = tkey || "—";
    li.appendChild(tend);

    const a = document.createElement("a");
    a.href = urlSegura(f.url);
    a.target = "_blank";
    a.rel = "noopener";
    a.className = "fuente-medio";
    a.textContent = "[" + f.n + "] " + (f.medio || f.url || "fuente");
    li.appendChild(a);

    const rel = document.createElement("span");
    rel.className = "fuente-rel";
    rel.textContent = f.coincide ? "✓ respalda" : "· matiza";
    li.appendChild(rel);

    const cred = CREDIBILIDAD[(f.credibilidad || "").toLowerCase()];
    if (cred) {
      const badge = document.createElement("span");
      badge.className = "badge-c " + cred.clase;
      badge.textContent = cred.txt;
      li.appendChild(badge);
    }

    const ex = EXTRACTOS[f.url];
    if (ex) {
      const det = document.createElement("details");
      det.className = "prueba";
      const sum = document.createElement("summary");
      sum.textContent = "ver de dónde salió";
      const bq = document.createElement("blockquote");
      bq.textContent = ex.extracto;
      det.appendChild(sum);
      det.appendChild(bq);
      li.appendChild(det);
    }

    lista.appendChild(li);
  });
  box.appendChild(lista);
  return box;
}
```

- [ ] **Step 3: Saltar la barra de confianza cuando el veredicto es `informativo`**

En `pintarRespuesta`, donde se pinta la confianza dentro de `if (sello)`, condicionar a que el veredicto NO sea informativo. Sustituir la condición:

```javascript
    if (meta && Number.isFinite(meta.confianza)) {
```

por:

```javascript
    if (meta && meta.veredicto !== "informativo" && Number.isFinite(meta.confianza)) {
```

- [ ] **Step 4: Verificar sintaxis**

Run: `node --check web/app.js`
Expected: sin errores.

- [ ] **Step 5: Estilos en `web/style.css`**

Añadir (y eliminar las reglas `.espectro*` y la `.fuentes-lista` antigua si quedaran):

```css
.fuentes-bloque { margin-top: 1.3rem; }
.fuentes-cab { font-family: var(--mono); font-size: 0.6rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.6rem; }
.fuentes-lista { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 0.5rem; }
.fuentes-lista > li { display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem; font-family: var(--mono); font-size: 0.8rem; }
.chip-t { font-size: 0.62rem; padding: 0.12rem 0.45rem; border-radius: 5px; letter-spacing: 0.06em; text-transform: uppercase; border: 1px solid; }
.t-izq { color: #b5562a; border-color: #e3c3ad; background: #fbf1e9; }
.t-cen { color: var(--ink-2); border-color: #ddd4c4; background: #f4efe5; }
.t-der { color: #3a5a8a; border-color: #b9c8df; background: #eef2f8; }
.t-ver { color: var(--true); border-color: #b9dcc6; background: #e8f3ec; }
.t-int { color: var(--tomas); border-color: #b9cdd6; background: #e9f0f3; }
.fuente-medio { flex: 1; min-width: 8rem; color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--line); }
.fuente-medio:hover { border-color: var(--tomas); }
.fuente-rel { color: var(--muted); font-size: 0.72rem; }
.badge-c { font-size: 0.62rem; padding: 0.12rem 0.5rem; border-radius: 999px; letter-spacing: 0.04em; text-transform: uppercase; font-weight: bold; }
.b-alta { color: var(--true); background: #e8f3ec; }
.b-media { color: var(--tomas); background: #e9f0f3; }
.b-baja { color: #9a7416; background: #f7efd9; }
.b-no { color: var(--false); background: #fbeae8; }
.prueba { flex-basis: 100%; margin-top: 0.2rem; }
.prueba summary { cursor: pointer; color: var(--muted); font-size: 0.72rem; letter-spacing: 0.04em; }
.prueba blockquote { margin: 0.4rem 0 0; padding: 0.55rem 0.75rem; border-left: 2px solid var(--tomas); background: var(--card); font-family: var(--serif); font-style: italic; font-size: 0.9rem; color: var(--ink-2); white-space: pre-wrap; }
.pill[data-v="info"] { color: var(--tomas); }
```

- [ ] **Step 6: Commit**

```bash
git add web/app.js web/style.css
git commit -m "feat: lista ponderada de fuentes con credibilidad y sello informativo"
```

---

### Task 9: Frontend — cierre de conversación

**Files:**
- Modify: `web/app.js`
- Modify: `web/style.css`

**Interfaces:**
- Consumes: evento SSE `cerrada` (Task 7).
- Produces: bloqueo permanente del composer y mensaje de cierre.

- [ ] **Step 1: Manejar el evento `cerrada` en `manejarEvento` (en `web/app.js`)**

En `manejarEvento`, añadir una rama tras `moderacion`:

```javascript
  } else if (evento === "cerrada") {
    cerrarTraza(traza, true);
    pintarAviso(dato.mensaje || "Conversación cerrada.", true);
    cerrarConversacion();
  } else if (evento === "error") {
```

- [ ] **Step 2: Añadir `cerrarConversacion` (en `web/app.js`)**

Cerca de `setEnCurso`, añadir:

```javascript
// Cierre permanente por faltas de respeto: bloquea el composer para esta sesión.
function cerrarConversacion() {
  enviar.disabled = true;
  entrada.readOnly = true;
  entrada.placeholder = "Conversación cerrada. Recarga la página para empezar de nuevo.";
  if (form) form.classList.add("cerrada");
}
```

- [ ] **Step 3: Verificar sintaxis**

Run: `node --check web/app.js`
Expected: sin errores.

- [ ] **Step 4: Estilo del composer cerrado (en `web/style.css`)**

```css
.composer.cerrada { opacity: 0.55; pointer-events: none; }
```

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/style.css
git commit -m "feat: frontend cierra el composer cuando la sesión se cierra"
```

---

## Self-review (cobertura del spec)

- Pieza 1 (registro + clasificación) → Task 1. ✓
- Pieza 2 (auto-anotación) → Task 3. ✓
- Pieza 3 (propuestas híbridas + CLI) → Task 2 (funciones+CLI) + Task 4 (captura en agente). ✓
- Pieza 4 (veredicto honesto: `informativo` + ponderación) → Task 5. ✓
- Pieza 5 (lista ponderada + sello neutro) → Task 8. ✓
- Pieza 6 (respeto endurecido) → Task 6 (mensajes) + Task 7 (server) + Task 9 (frontend cierre). ✓
- Contrato JSON (`informativo`, `credibilidad`) → Task 5 (prompt) consumido por Task 8 (frontend). ✓
- Degradación elegante (captura/anotación no rompen) → Task 2/4 (try/except), Task 3 (solo cuando ok). ✓
- No persistencia de usuario → solo se persisten metadatos de fuentes (`propuestas.jsonl`, gitignored). ✓
```
