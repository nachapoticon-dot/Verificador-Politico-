# Mejoras de verificación y frontend — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Robustecer el contrato del veredicto (validación + reparación + citas + extractos), fundamentar la confianza, transmitir la respuesta en streaming, endurecer la búsqueda, y rediseñar en el frontend las opciones de respuesta, el aspecto de la respuesta y la ficha de fuentes.

**Architecture:** Un nuevo módulo `verificador/veredicto.py` post-procesa toda respuesta final del modelo (validar → reparar → citas → registro → extractos → confianza → re-serializar); el agente lo invoca antes de devolver, así CLI, servidor y frontend reciben el mismo texto enriquecido sin cambiar el contrato `respuesta.texto`. El streaming añade eventos SSE `delta`/`delta_reset` sin romper clientes viejos (el evento `respuesta` final sigue llegando completo). El frontend mueve las opciones al composer como presets, muestra el `resumen` como titular y sustituye la lista de fuentes por una ficha editorial.

**Tech Stack:** Python 3.14 (venv en `.venv`), FastAPI + SSE, SDK de OpenAI apuntando a DeepSeek, pytest; React 19 + Vite + Tailwind (build a `frontend/dist`), asserts de Node para lógica portada.

**Spec:** `docs/superpowers/specs/2026-07-04-verificacion-y-frontend-design.md`

## Global Constraints

- Identificadores, comentarios, docstrings y mensajes de commit **en español**, siguiendo el estilo del repo (`feat:`, `fix:`, `docs:` en minúscula).
- Python se corre con el venv del proyecto: `.venv/bin/python -m pytest tests/ -q` desde la raíz.
- Tests de Node: `node tests/test_citas.mjs` — su salida esperada es `ok`. Ese archivo prueba **copias** de las funciones de `frontend/src/lib/format.ts`; si cambias la lógica en TS, actualiza la copia.
- Build del frontend: `cd frontend && npm run build` (sale a `frontend/dist`, que sirve FastAPI). En desarrollo: `npm run dev` con uvicorn en el 8000.
- **Cero dependencias nuevas** (ni pip ni npm).
- El post-proceso del veredicto **nunca lanza**: ante meta inválido degrada campo a campo; la prosa siempre sobrevive.
- Los textos de error de herramientas jamás llegan al visor de evidencias (solo lecturas con `ok=True` producen `extracto`).
- El evento SSE `respuesta` final siempre lleva el texto completo (los clientes que ignoren `delta` siguen funcionando).

---

### Task 1: `urls.py` — normalización canónica de URLs

**Files:**
- Create: `verificador/urls.py`
- Test: `tests/test_urls.py`

**Interfaces:**
- Consumes: nada.
- Produces: `normalizar_url(url: str) -> str` — clave canónica: sin esquema, sin `www.`, sin parámetros de tracking (`utm_*`, `fbclid`, `gclid`, `igshid`, `mc_cid`, `mc_eid`), sin barra final ni fragmento; `""` si no hay URL. La usan `veredicto.py` (Task 4) y `search.py` (Task 9); su port TS llega en Task 12.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_urls.py
from verificador.urls import normalizar_url


def test_quita_esquema_www_y_barra_final():
    assert normalizar_url("https://www.elpais.com/nota/") == "elpais.com/nota"
    assert normalizar_url("http://elpais.com/nota") == "elpais.com/nota"


def test_quita_tracking_pero_conserva_query_real():
    assert normalizar_url("https://x.com/a?utm_source=tw&fbclid=1&id=7") == "x.com/a?id=7"
    assert normalizar_url("https://x.com/a?gclid=9") == "x.com/a"


def test_quita_fragmento_y_normaliza_mayusculas_de_host():
    assert normalizar_url("https://X.com/A#seccion") == "x.com/A"


def test_sin_esquema_tambien_funciona():
    assert normalizar_url("www.reuters.com/a") == "reuters.com/a"


def test_vacia_o_solo_espacios_da_vacio():
    assert normalizar_url("") == ""
    assert normalizar_url("   ") == ""


def test_equivalencias_que_deben_casar():
    a = normalizar_url("https://www.semana.com/n/?utm_campaign=x")
    b = normalizar_url("http://semana.com/n")
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_urls.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'verificador.urls'`

- [ ] **Step 3: Write minimal implementation**

```python
# verificador/urls.py
"""Normalización canónica de URLs.

Una misma página llega con variantes (con/sin ``www.``, con parámetros de
tracking, con barra final). Esta clave canónica sirve para casar extractos de
la traza con las fuentes citadas y como clave de la caché de lecturas.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit

_TRACKING = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid"}


def normalizar_url(url: str) -> str:
    """Clave canónica: sin esquema, sin ``www.``, sin tracking, sin ``/`` final
    ni fragmento. Devuelve ``""`` si no hay URL."""
    if not url or not url.strip():
        return ""
    u = url.strip()
    try:
        p = urlsplit(u if "://" in u else "http://" + u)
    except ValueError:
        return u.lower()
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    ruta = p.path.rstrip("/")
    pares = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING
    ]
    query = urlencode(pares)
    return host + ruta + ("?" + query if query else "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_urls.py -q`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add verificador/urls.py tests/test_urls.py
git commit -m "feat: normalización canónica de URLs (base de extractos y caché)"
```

---

### Task 2: `veredicto.py` — partir la respuesta y validar el meta

**Files:**
- Create: `verificador/veredicto.py`
- Test: `tests/test_veredicto.py`

**Interfaces:**
- Consumes: nada (módulo nuevo).
- Produces: `partir(texto: str) -> tuple[str, dict | None]` (prosa, meta bruto) y `validar_meta(meta) -> dict | None`. El meta validado garantiza: `veredicto` (opcional, dentro del vocabulario), `confianza: int` 0-100 (siempre presente), `resumen`/`pais` (opcionales, str no vacío), `fuentes: list[dict]` (siempre presente) donde cada fuente tiene `n: int`, `coincide: bool` y opcionalmente `url` (solo http/https), `medio`, `credibilidad`, `manipulacion`, `tendencia` (en minúsculas, vocabulario cerrado para cred/manip).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_veredicto.py
from verificador.veredicto import partir, validar_meta


def test_partir_separa_prosa_y_meta():
    texto = 'Es falso [1].\n\n```json\n{"veredicto": "falso", "fuentes": []}\n```'
    prosa, meta = partir(texto)
    assert prosa == "Es falso [1]."
    assert meta == {"veredicto": "falso", "fuentes": []}


def test_partir_sin_bloque_devuelve_meta_none():
    assert partir("solo prosa") == ("solo prosa", None)


def test_partir_json_invalido_devuelve_meta_none():
    prosa, meta = partir("prosa\n\n```json\n{mal\n```")
    assert prosa == "prosa"
    assert meta is None


def test_partir_json_que_no_es_dict_devuelve_none():
    assert partir('x\n\n```json\n[1, 2]\n```')[1] is None


def test_validar_meta_normaliza_campos():
    meta = validar_meta({
        "veredicto": " Falso ",
        "confianza": "85.4",
        "resumen": " La cifra es inventada. ",
        "pais": "CO",
        "fuentes": [
            {"n": "1", "medio": "Reuters", "url": "https://reuters.com/a",
             "credibilidad": "ALTA", "manipulacion": "Ninguna",
             "tendencia": "Centro", "coincide": True},
        ],
    })
    assert meta["veredicto"] == "falso"
    assert meta["confianza"] == 85
    assert meta["resumen"] == "La cifra es inventada."
    assert meta["pais"] == "CO"
    f = meta["fuentes"][0]
    assert f["n"] == 1 and f["coincide"] is True
    assert f["credibilidad"] == "alta" and f["manipulacion"] == "ninguna"
    assert f["tendencia"] == "centro"


def test_validar_meta_descarta_lo_invalido_campo_a_campo():
    meta = validar_meta({
        "veredicto": "veredicto-inventado",
        "confianza": "no-numero",
        "resumen": "",
        "fuentes": [
            {"n": "x", "url": "https://a.com"},          # n no numérico: fuera
            {"n": 2, "url": "javascript:alert(1)"},       # url no http: se quita la url
            "no-es-dict",
            {"n": 3, "credibilidad": "altisima"},          # cred fuera de vocabulario: fuera
        ],
    })
    assert "veredicto" not in meta
    assert meta["confianza"] == 0
    assert "resumen" not in meta
    ns = [f["n"] for f in meta["fuentes"]]
    assert ns == [2, 3]
    assert "url" not in meta["fuentes"][0]
    assert "credibilidad" not in meta["fuentes"][1]


def test_validar_meta_acota_confianza():
    assert validar_meta({"confianza": 250})["confianza"] == 100
    assert validar_meta({"confianza": -5})["confianza"] == 0


def test_validar_meta_no_dict_es_none():
    assert validar_meta(None) is None
    assert validar_meta([1]) is None
    assert validar_meta("x") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'verificador.veredicto'`

- [ ] **Step 3: Write minimal implementation**

```python
# verificador/veredicto.py
"""Post-proceso del veredicto: el contrato entre el modelo y la interfaz.

Toda respuesta final del modelo pasa por aquí antes de llegar al usuario:
se valida el bloque ```json de cierre (y se repara si falta), se comprueba la
consistencia de las citas [n], se aplican las etiquetas del registro curado,
se adjuntan los extractos de la traza y se recalcula la confianza a partir de
las fuentes reales. Nunca lanza: ante datos imposibles degrada campo a campo;
la prosa siempre sobrevive.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable
from typing import NamedTuple

from . import fuentes
from .urls import normalizar_url

_log = logging.getLogger(__name__)

VEREDICTOS = {
    "verdadero", "falso", "enganoso", "fuera_de_contexto",
    "prediccion", "sin_evidencia", "informativo", "no_verificable",
}
CREDIBILIDADES = {"alta", "media", "baja", "no_fiable"}
MANIPULACIONES = {"ninguna", "sesgo", "enganosa", "desinformadora"}

_JSON_RE = re.compile(r"```json\s*([\s\S]*?)```\s*$", re.IGNORECASE)


def partir(texto: str) -> tuple[str, dict | None]:
    """Separa la prosa del bloque ```json final. Meta ``None`` si falta o no parsea."""
    m = _JSON_RE.search(texto or "")
    if not m:
        return (texto or "").strip(), None
    prosa = texto[: m.start()].strip()
    try:
        meta = json.loads(m.group(1).strip())
    except Exception:  # noqa: BLE001 — JSON inválido: se tratará como ausente
        meta = None
    return prosa, meta if isinstance(meta, dict) else None


def validar_meta(meta) -> dict | None:
    """Meta validado campo a campo (lo inválido se descarta, no todo-o-nada)."""
    if not isinstance(meta, dict):
        return None
    out: dict = {}
    v = meta.get("veredicto")
    if isinstance(v, str) and v.lower().strip() in VEREDICTOS:
        out["veredicto"] = v.lower().strip()
    try:
        c = float(meta.get("confianza"))
        out["confianza"] = int(round(min(100.0, max(0.0, c))))
    except (TypeError, ValueError):
        out["confianza"] = 0
    for campo in ("resumen", "pais"):
        val = meta.get(campo)
        if isinstance(val, str) and val.strip():
            out[campo] = val.strip()
    out["fuentes"] = []
    for f in meta.get("fuentes") or []:
        if not isinstance(f, dict):
            continue
        try:
            n = int(f.get("n"))
        except (TypeError, ValueError):
            continue
        fu: dict = {"n": n, "coincide": bool(f.get("coincide"))}
        url = f.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            fu["url"] = url
        medio = f.get("medio")
        if isinstance(medio, str) and medio.strip():
            fu["medio"] = medio.strip()
        for campo, validos in (("credibilidad", CREDIBILIDADES),
                               ("manipulacion", MANIPULACIONES)):
            val = f.get(campo)
            if isinstance(val, str) and val.lower().strip() in validos:
                fu[campo] = val.lower().strip()
        t = f.get("tendencia")
        if isinstance(t, str) and t.strip():
            fu["tendencia"] = t.lower().strip()
        out["fuentes"].append(fu)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add verificador/veredicto.py tests/test_veredicto.py
git commit -m "feat: veredicto.py valida el bloque JSON campo a campo"
```

---

### Task 3: `veredicto.py` — consistencia de citas

**Files:**
- Modify: `verificador/veredicto.py`
- Test: `tests/test_veredicto.py`

**Interfaces:**
- Consumes: meta validado de `validar_meta` (Task 2).
- Produces: `marcar_citas(prosa: str, meta: dict) -> dict` — añade `citada: bool` a cada fuente según aparezca `[n]` en la prosa; registra en log las citas huérfanas (números citados sin fuente). Muta y devuelve el mismo dict.

- [ ] **Step 1: Write the failing test** (añadir a `tests/test_veredicto.py`)

```python
from verificador.veredicto import marcar_citas


def test_marcar_citas_pone_citada_por_fuente():
    meta = {"fuentes": [{"n": 1}, {"n": 2}, {"n": 3}]}
    marcar_citas("Según [1] y también [3].", meta)
    assert [f["citada"] for f in meta["fuentes"]] == [True, False, True]


def test_marcar_citas_huerfanas_se_loguean_sin_romper(caplog):
    import logging
    meta = {"fuentes": [{"n": 1}]}
    with caplog.at_level(logging.WARNING, logger="verificador.veredicto"):
        marcar_citas("Dato [1] y dato [7].", meta)
    assert "7" in caplog.text
    assert meta["fuentes"][0]["citada"] is True


def test_marcar_citas_sin_fuentes_no_rompe():
    meta = {"fuentes": []}
    assert marcar_citas("Texto [1].", meta) == {"fuentes": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`
Expected: FAIL — `ImportError: cannot import name 'marcar_citas'`

- [ ] **Step 3: Write minimal implementation** (añadir a `verificador/veredicto.py`)

```python
_CITA_RE = re.compile(r"\[(\d+)\]")


def marcar_citas(prosa: str, meta: dict) -> dict:
    """Marca cada fuente con ``citada`` y avisa (log) de citas sin fuente."""
    citadas = {int(n) for n in _CITA_RE.findall(prosa or "")}
    enumeradas = {f["n"] for f in meta.get("fuentes") or []}
    huerfanas = citadas - enumeradas
    if huerfanas:
        _log.warning("citas sin fuente en el JSON de cierre: %s", sorted(huerfanas))
    for f in meta.get("fuentes") or []:
        f["citada"] = f["n"] in citadas
    return meta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add verificador/veredicto.py tests/test_veredicto.py
git commit -m "feat: consistencia de citas [n] ↔ fuentes del veredicto"
```

---

### Task 4: `veredicto.py` — registro curado y extractos

**Files:**
- Modify: `verificador/veredicto.py`
- Test: `tests/test_veredicto.py`

**Interfaces:**
- Consumes: `fuentes.clasificar(url)` (existente), `normalizar_url` (Task 1).
- Produces: `aplicar_registro(meta: dict) -> dict` — para fuentes con dominio en el registro curado, sobreescribe `credibilidad`, `manipulacion` y `tendencia` con la ficha curada (la autoevaluación del modelo solo queda para dominios no registrados). `adjuntar_extractos(meta: dict, extractos: dict[str, str] | None) -> dict` — añade `extracto` a cada fuente cuya URL normalizada case con una lectura de la traza.

- [ ] **Step 1: Write the failing test** (añadir a `tests/test_veredicto.py`)

```python
from verificador.veredicto import adjuntar_extractos, aplicar_registro


def test_aplicar_registro_sobreescribe_dominios_curados():
    # reuters.com está en el registro con credibilidad alta (ver test_fuentes).
    meta = {"fuentes": [
        {"n": 1, "url": "https://www.reuters.com/a", "credibilidad": "baja",
         "manipulacion": "sesgo", "tendencia": "derecha"},
        {"n": 2, "url": "https://dominio-no-registrado-xyz.tld/n",
         "credibilidad": "media"},
    ]}
    aplicar_registro(meta)
    f1, f2 = meta["fuentes"]
    assert f1["credibilidad"] == "alta"          # manda el registro curado
    assert f1["manipulacion"] == "ninguna"
    assert f2["credibilidad"] == "media"          # no registrado: queda el del modelo


def test_adjuntar_extractos_casa_por_url_normalizada():
    meta = {"fuentes": [
        {"n": 1, "url": "https://elpais.com/nota?utm_source=tw"},
        {"n": 2, "url": "https://otro.com/x"},
    ]}
    extractos = {"https://www.elpais.com/nota/": "TEXTO LEÍDO"}
    adjuntar_extractos(meta, extractos)
    assert meta["fuentes"][0]["extracto"] == "TEXTO LEÍDO"
    assert "extracto" not in meta["fuentes"][1]


def test_adjuntar_extractos_sin_datos_no_rompe():
    meta = {"fuentes": [{"n": 1}]}
    adjuntar_extractos(meta, None)
    adjuntar_extractos(meta, {})
    assert "extracto" not in meta["fuentes"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`
Expected: FAIL — `ImportError: cannot import name 'adjuntar_extractos'`

- [ ] **Step 3: Write minimal implementation** (añadir a `verificador/veredicto.py`)

```python
def aplicar_registro(meta: dict) -> dict:
    """Para dominios curados, la etiqueta del registro manda sobre la del modelo."""
    for f in meta.get("fuentes") or []:
        ficha = fuentes.clasificar(f.get("url") or "")
        if ficha is None:
            continue
        f["credibilidad"] = ficha.credibilidad
        f["manipulacion"] = ficha.manipulacion
        f["tendencia"] = ficha.tendencia
    return meta


def adjuntar_extractos(meta: dict, extractos: dict[str, str] | None) -> dict:
    """Adjunta a cada fuente el extracto leído en la traza (casado por URL canónica)."""
    if not extractos:
        return meta
    por_url = {normalizar_url(u): x for u, x in extractos.items() if u and x}
    for f in meta.get("fuentes") or []:
        x = por_url.get(normalizar_url(f.get("url") or ""))
        if x:
            f["extracto"] = x
    return meta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add verificador/veredicto.py tests/test_veredicto.py
git commit -m "feat: registro curado manda y los extractos casan por URL canónica"
```

---

### Task 5: `veredicto.py` — confianza fundamentada

**Files:**
- Modify: `verificador/veredicto.py`
- Test: `tests/test_veredicto.py`

**Interfaces:**
- Consumes: meta con fuentes ya pasadas por `aplicar_registro` (Task 4).
- Produces: `calcular_confianza(meta: dict) -> int` — 0-100 a partir de las fuentes: suma de las que `coincide=True` ponderadas por credibilidad (alta 1.0, media 0.6, baja 0.25, no_fiable 0); las `enganosa`/`desinformadora` nunca suman y si "coinciden" penalizan; bono ×1.25 si hay contraste real (izquierda+derecha, o verificador + otra tendencia); techo asintótico `95·(1−e^(−0.7·peso))` — nunca 100.

- [ ] **Step 1: Write the failing test** (añadir a `tests/test_veredicto.py`)

```python
from verificador.veredicto import calcular_confianza


def test_confianza_cero_sin_fuentes_que_coincidan():
    assert calcular_confianza({"fuentes": []}) == 0
    assert calcular_confianza({"fuentes": [
        {"n": 1, "coincide": False, "credibilidad": "alta"},
    ]}) == 0


def test_confianza_una_fuente_alta_es_media():
    c = calcular_confianza({"fuentes": [
        {"n": 1, "coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"},
    ]})
    assert 40 <= c <= 55


def test_confianza_contraste_izq_der_sube():
    base = {"coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"}
    sin_contraste = calcular_confianza({"fuentes": [
        {"n": 1, "tendencia": "izquierda", **base},
        {"n": 2, "tendencia": "centro-izquierda", **base},
    ]})
    con_contraste = calcular_confianza({"fuentes": [
        {"n": 1, "tendencia": "izquierda", **base},
        {"n": 2, "tendencia": "derecha", **base},
    ]})
    assert con_contraste > sin_contraste


def test_confianza_tres_buenas_contrastadas_ronda_90_y_nunca_100():
    base = {"coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"}
    c = calcular_confianza({"fuentes": [
        {"n": 1, "tendencia": "izquierda", **base},
        {"n": 2, "tendencia": "derecha", **base},
        {"n": 3, "tendencia": "verificador", **base},
    ]})
    assert 85 <= c < 100


def test_fuentes_deshonestas_no_suman_y_penalizan():
    solo_desinfo = calcular_confianza({"fuentes": [
        {"n": 1, "coincide": True, "credibilidad": "alta",
         "manipulacion": "desinformadora"},
    ]})
    assert solo_desinfo == 0
    limpia = calcular_confianza({"fuentes": [
        {"n": 1, "coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"},
    ]})
    con_lastre = calcular_confianza({"fuentes": [
        {"n": 1, "coincide": True, "credibilidad": "alta", "manipulacion": "ninguna"},
        {"n": 2, "coincide": True, "credibilidad": "alta", "manipulacion": "enganosa"},
    ]})
    assert con_lastre < limpia
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`
Expected: FAIL — `ImportError: cannot import name 'calcular_confianza'`

- [ ] **Step 3: Write minimal implementation** (añadir a `verificador/veredicto.py`)

```python
_PESO_CRED = {"alta": 1.0, "media": 0.6, "baja": 0.25, "no_fiable": 0.0}
_IZQ = {"izquierda", "centro-izquierda"}
_DER = {"derecha", "centro-derecha"}


def calcular_confianza(meta: dict) -> int:
    """Confianza 0-100 calculada de las fuentes reales, no autodeclarada.

    Suman las fuentes que coinciden, ponderadas por credibilidad; el contraste
    real (tendencias opuestas o verificador + otra) da un bono; las fuentes
    deshonestas nunca suman y, si "apoyan", restan solidez. Techo asintótico:
    ni un aluvión de fuentes llega a 100.
    """
    peso = 0.0
    penal = 0.0
    tendencias: set[str] = set()
    for f in meta.get("fuentes") or []:
        manip = (f.get("manipulacion") or "ninguna").lower()
        if manip in ("enganosa", "desinformadora"):
            if f.get("coincide"):
                penal += 0.15
            continue
        if not f.get("coincide"):
            continue
        peso += _PESO_CRED.get((f.get("credibilidad") or "").lower(), 0.25)
        tendencias.add((f.get("tendencia") or "").lower())
    contraste = bool(
        (tendencias & _IZQ and tendencias & _DER)
        or ("verificador" in tendencias and len(tendencias) > 1)
    )
    if contraste:
        peso *= 1.25
    conf = 95.0 * (1.0 - math.exp(-0.7 * peso))
    conf *= max(0.0, 1.0 - penal)
    return int(round(conf))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add verificador/veredicto.py tests/test_veredicto.py
git commit -m "feat: confianza calculada de las fuentes (contraste suma, deshonestidad resta)"
```

---

### Task 6: `veredicto.py` — `procesar()` orquestador

**Files:**
- Modify: `verificador/veredicto.py`
- Test: `tests/test_veredicto.py`

**Interfaces:**
- Consumes: todo lo anterior de `veredicto.py`.
- Produces: `Procesado(texto: str, prosa: str, meta: dict | None)` (NamedTuple) y `procesar(texto: str, extractos: dict[str, str] | None = None, reparar: Callable[[str], str | None] | None = None) -> Procesado`. Si el JSON falta/no parsea y hay `reparar`, se llama UNA vez con la prosa y se acepta tanto un bloque vallado como JSON pelado. El meta final lleva `confianza` (calculada) y `confianza_modelo` (la original). `texto` es la prosa + bloque re-serializado (o solo la prosa si no hay meta). Es lo que consumen el agente (Task 7), el servidor y el frontend.

- [ ] **Step 1: Write the failing test** (añadir a `tests/test_veredicto.py`)

```python
from verificador.veredicto import Procesado, procesar


def test_procesar_pipeline_completo():
    texto = ('Es falso [1].\n\n```json\n'
             '{"veredicto": "falso", "confianza": 90, "resumen": "Inventado.",'
             ' "pais": "CO", "fuentes": [{"n": 1, "medio": "Reuters",'
             ' "url": "https://www.reuters.com/a?utm_source=x",'
             ' "credibilidad": "baja", "tendencia": "derecha", "coincide": true}]}'
             '\n```')
    p = procesar(texto, extractos={"https://reuters.com/a": "LO QUE LEYÓ"})
    assert isinstance(p, Procesado)
    assert p.prosa == "Es falso [1]."
    f = p.meta["fuentes"][0]
    assert f["credibilidad"] == "alta"        # registro curado manda
    assert f["extracto"] == "LO QUE LEYÓ"     # casó por URL normalizada
    assert f["citada"] is True
    assert p.meta["confianza_modelo"] == 90
    assert p.meta["confianza"] != 90           # recalculada (1 fuente alta ≈ 48)
    assert p.texto.startswith("Es falso [1].")
    assert '"confianza_modelo": 90' in p.texto


def test_procesar_repara_una_vez_si_falta_el_json():
    llamadas = []

    def reparar(prosa):
        llamadas.append(prosa)
        return '```json\n{"veredicto": "informativo", "fuentes": []}\n```'

    p = procesar("Solo prosa sin bloque.", reparar=reparar)
    assert llamadas == ["Solo prosa sin bloque."]
    assert p.meta["veredicto"] == "informativo"


def test_procesar_acepta_reparacion_con_json_pelado():
    p = procesar("Prosa.", reparar=lambda _: '{"veredicto": "falso", "fuentes": []}')
    assert p.meta["veredicto"] == "falso"


def test_procesar_degrada_si_la_reparacion_falla():
    p = procesar("Prosa.", reparar=lambda _: None)
    assert p.meta is None
    assert p.texto == "Prosa."
    p2 = procesar("Prosa.", reparar=lambda _: (_ for _ in ()).throw(RuntimeError()))
    assert p2.meta is None


def test_procesar_sin_reparador_devuelve_prosa():
    p = procesar("Prosa sin json.")
    assert p == Procesado("Prosa sin json.", "Prosa sin json.", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`
Expected: FAIL — `ImportError: cannot import name 'procesar'`

- [ ] **Step 3: Write minimal implementation** (añadir a `verificador/veredicto.py`)

```python
class Procesado(NamedTuple):
    """Resultado del post-proceso: texto re-serializado, prosa y meta validado."""

    texto: str
    prosa: str
    meta: dict | None


def reserializar(prosa: str, meta: dict | None) -> str:
    """Vuelve a unir prosa + bloque ```json (o la prosa sola si no hay meta)."""
    if meta is None:
        return prosa
    bloque = json.dumps(meta, ensure_ascii=False, indent=2)
    return f"{prosa}\n\n```json\n{bloque}\n```"


def procesar(
    texto: str,
    extractos: dict[str, str] | None = None,
    reparar: Callable[[str], str | None] | None = None,
) -> Procesado:
    """Pipeline completo: partir → (reparar) → validar → citas → registro →
    extractos → confianza → re-serializar. Nunca lanza."""
    prosa, bruto = partir(texto)
    if bruto is None and reparar is not None:
        try:
            arreglo = reparar(prosa)
        except Exception:  # noqa: BLE001 — la reparación jamás rompe la respuesta
            arreglo = None
        if arreglo:
            _, bruto = partir(arreglo)
            if bruto is None:
                # A veces el modelo devuelve el JSON pelado, sin la valla.
                try:
                    cand = json.loads(arreglo.strip())
                    bruto = cand if isinstance(cand, dict) else None
                except Exception:  # noqa: BLE001
                    bruto = None
    meta = validar_meta(bruto)
    if meta is None:
        return Procesado(prosa, prosa, None)
    marcar_citas(prosa, meta)
    aplicar_registro(meta)
    adjuntar_extractos(meta, extractos)
    meta["confianza_modelo"] = meta.get("confianza", 0)
    meta["confianza"] = calcular_confianza(meta)
    return Procesado(reserializar(prosa, meta), prosa, meta)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`
Expected: PASS. Después corre la suite completa: `.venv/bin/python -m pytest tests/ -q` — Expected: PASS (nada existente toca aún este módulo).

- [ ] **Step 5: Commit**

```bash
git add verificador/veredicto.py tests/test_veredicto.py
git commit -m "feat: procesar() orquesta el post-proceso completo del veredicto"
```

---

### Task 7: el agente integra `procesar` + reparación

**Files:**
- Modify: `verificador/prompts.py` (añadir `PROMPT_REPARACION` al final)
- Modify: `verificador/agent.py`
- Test: `tests/test_traza.py` (dos tests actualizados, uno nuevo)

**Interfaces:**
- Consumes: `veredicto.procesar` (Task 6).
- Produces: `Verificador.preguntar()` sigue devolviendo `str`, pero ahora es el texto **enriquecido** (`Procesado.texto`); `Verificador._reparar_json(prosa: str) -> str | None` hace la llamada de reparación (sin tools, temperature 0). El agente acumula `extractos: dict[url, str]` de las lecturas ok y se los pasa a `procesar`.

- [ ] **Step 1: Write the failing test**

En `tests/test_traza.py`, **actualizar** `test_preguntar_captura_propuestas` (el texto devuelto ya no es idéntico al del modelo) y **añadir** un test de enriquecimiento. Reemplazar la línea `assert out == final` por las dos líneas indicadas, y añadir el test nuevo al final del archivo:

```python
# en test_preguntar_captura_propuestas, sustituir `assert out == final` por:
    assert out.startswith("Respuesta [1].")
    assert '"veredicto": "informativo"' in out


def test_preguntar_enriquece_meta(monkeypatch):
    """El texto devuelto lleva el meta validado: registro curado, extracto
    casado por URL normalizada y confianza recalculada."""
    from types import SimpleNamespace
    from verificador import veredicto
    from verificador.config import Config

    a = Verificador(config=Config(api_key="x", base_url="http://l", model="m"))
    final = ('Es falso [1].\n\n```json\n'
             '{"veredicto": "falso", "confianza": 90, "fuentes":'
             ' [{"n": 1, "medio": "Reuters",'
             ' "url": "https://reuters.com/a?utm_source=x",'
             ' "credibilidad": "baja", "tendencia": "derecha", "coincide": true}]}'
             '\n```')

    class _FakeMsg:
        def __init__(self, content, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

    class _FakeTC:
        def __init__(self, _id, name, args):
            self.id = _id
            self.type = "function"
            self.function = type("F", (), {"name": name, "arguments": args})()

    class _Choices:
        def __init__(self, m): self.choices = [type("C", (), {"message": m})()]

    respuestas = [
        _FakeMsg("", [_FakeTC("t1", "leer_pagina", '{"url": "https://www.reuters.com/a"}')]),
        _FakeMsg(final),
    ]
    it = iter(respuestas)
    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: _Choices(next(it)))
    monkeypatch.setattr(agentmod, "leer_pagina", lambda url, **k: Lectura("LO QUE LEYÓ", True))

    out = a.preguntar("¿es verdad X?")
    _, meta = veredicto.partir(out)
    f = meta["fuentes"][0]
    assert f["credibilidad"] == "alta"         # registro curado manda
    assert f["extracto"] == "LO QUE LEYÓ"      # www./utm no impiden el casado
    assert meta["confianza_modelo"] == 90
    assert 40 <= meta["confianza"] <= 55        # recalculada: 1 fuente alta
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_traza.py -q`
Expected: FAIL — en `test_preguntar_captura_propuestas` (`out` sí es igual a `final` todavía) y en `test_preguntar_enriquece_meta` (sin `extracto` ni `confianza_modelo`).

- [ ] **Step 3: Write minimal implementation**

3a. Al final de `verificador/prompts.py` añadir:

```python
# Se usa cuando una respuesta llegó sin su bloque JSON de cierre: se pide SOLO
# el bloque, deducido de la propia respuesta (una única llamada de reparación).
PROMPT_REPARACION = """\
La siguiente respuesta de un verificador de hechos llegó sin su bloque JSON de
cierre. Emite SOLO ese bloque (```json ... ```), sin prosa alguna, deducido de
la propia respuesta, con esta estructura exacta:

```json
{
  "veredicto": "verdadero|falso|enganoso|fuera_de_contexto|prediccion|sin_evidencia|informativo|no_verificable",
  "confianza": 0,
  "resumen": "una sola frase con la conclusión",
  "pais": "código ISO o nombre del país",
  "fuentes": [
    {"n": 1, "medio": "nombre", "tendencia": "izquierda|centro-izquierda|centro|centro-derecha|derecha|verificador|internacional", "credibilidad": "alta|media|baja|no_fiable", "manipulacion": "ninguna|sesgo|enganosa|desinformadora", "url": "https://...", "coincide": true}
  ]
}
```

Cada [n] citado en la respuesta debe tener su fuente con ese n. Si un campo no
se puede deducir, usa el valor más conservador."""
```

3b. En `verificador/agent.py`:

- Cambiar el import de prompts: `from .prompts import PROMPT_REPARACION, SYSTEM_PROMPT, instruccion_modo` y añadir `from . import veredicto` junto a `from . import fuentes`.
- Añadir el método a `Verificador` (después de `_ejecutar_tool`):

```python
    def _reparar_json(self, prosa: str) -> str | None:
        """Pide al modelo SOLO el bloque JSON de cierre para una respuesta que
        llegó sin él (una única llamada; si falla, se degrada sin meta)."""
        try:
            resp = self._client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": PROMPT_REPARACION},
                    {"role": "user", "content": prosa},
                ],
                temperature=0.0,
            )
            return resp.choices[0].message.content or None
        except Exception:  # noqa: BLE001 — la reparación jamás rompe la respuesta
            return None
```

- En `preguntar()`, justo después de `messages.append({"role": "user", ...})`, añadir `extractos: dict[str, str] = {}`.
- Reemplazar el bloque "Sin llamadas a herramientas → es la respuesta final" por:

```python
            # Sin llamadas a herramientas → es la respuesta final. Se valida y
            # enriquece el meta (citas, registro, extractos, confianza) antes
            # de devolverla; nada de esto puede romper la respuesta.
            if not msg.tool_calls:
                procesado = veredicto.procesar(
                    msg.content or "", extractos=extractos, reparar=self._reparar_json
                )
                try:
                    fuentes.capturar_propuestas(procesado.meta)
                except Exception:  # noqa: BLE001
                    pass
                return procesado.texto
```

- En el bucle de herramientas, reemplazar desde `lectura = self._ejecutar_tool(...)` hasta el `on_step(fin)` por:

```python
                lectura = self._ejecutar_tool(tc.function.name, args,
                                              country=country, rigor=rigor)
                con_extracto = ev["tipo"] in ("pagina", "video") and lectura.ok
                if con_extracto and ev["url"]:
                    extractos[ev["url"]] = lectura.texto[:1500]
                if on_step:
                    fin = {"id": ev["id"], "tipo": ev["tipo"],
                           "estado": "ok" if lectura.ok else "fallo",
                           "titulo": ev["titulo"], "url": ev["url"], "dominio": ev["dominio"]}
                    # Solo en éxito guardamos el extracto: el texto de error
                    # nunca debe llegar al visor "ver de dónde salió".
                    if con_extracto:
                        fin["extracto"] = lectura.texto[:1500]
                    on_step(fin)
```

Nota: en los tests existentes cuya respuesta final no lleva JSON ("Veredicto final"), `procesar` invocará `_reparar_json`; el `create` falso lanzará `StopIteration`, que `_reparar_json` captura y devuelve `None` — los tests siguen pasando sin cambios.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS (toda la suite).

- [ ] **Step 5: Commit**

```bash
git add verificador/agent.py verificador/prompts.py tests/test_traza.py
git commit -m "feat: el agente valida, repara y enriquece el veredicto antes de responder"
```

---

### Task 8: streaming de la respuesta final (agente + servidor + CLI)

**Files:**
- Create: `tests/helpers.py`
- Create: `tests/test_streaming.py`
- Modify: `verificador/agent.py`
- Modify: `verificador/server.py`
- Modify: `verificador/cli.py`
- Modify: `tests/test_traza.py` (fakes pasan a streams), `tests/test_server.py` (test nuevo)

**Interfaces:**
- Consumes: `preguntar()` de Task 7.
- Produces: `Verificador._completar(messages: list[dict], on_step) -> tuple[str, list[dict]]` — una vuelta del modelo con `stream=True`; devuelve el contenido completo y las tool_calls reconstruidas como `[{"id": str, "name": str, "arguments": str}]`. Emite por `on_step` eventos `{"tipo": "delta", "texto": str}` (solo mientras la vuelta no pida herramientas) y un único `{"tipo": "delta_reset"}` si aparecen tools tras haber emitido texto. El servidor los mapea a eventos SSE `delta` / `delta_reset` (el frontend los consume en Task 12). Helper de tests: `tests.helpers.stream_de(content=None, tool_calls=None)` → iterador de chunks falsos (`tool_calls`: lista de tuplas `(id, nombre, argumentos)`).

- [ ] **Step 1: Write the failing tests**

1a. Crear `tests/helpers.py`:

```python
"""Utilidades compartidas de los tests."""
from types import SimpleNamespace


def _chunk(content=None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def stream_de(content=None, tool_calls=None):
    """Iterador de chunks con la forma del stream de OpenAI/DeepSeek.

    ``tool_calls``: lista de tuplas ``(id, nombre, argumentos)``. Cada una se
    parte en dos chunks (cabecera con id+nombre, luego los argumentos), como
    hace la API real. ``content`` se trocea en fragmentos de 7 caracteres.
    """
    chunks = []
    for i, (id_, nombre, args) in enumerate(tool_calls or []):
        chunks.append(_chunk(tool_calls=[SimpleNamespace(
            index=i, id=id_, function=SimpleNamespace(name=nombre, arguments=""))]))
        chunks.append(_chunk(tool_calls=[SimpleNamespace(
            index=i, id=None, function=SimpleNamespace(name=None, arguments=args))]))
    if content:
        for j in range(0, len(content), 7):
            chunks.append(_chunk(content=content[j:j + 7]))
    return iter(chunks)
```

1b. Crear `tests/test_streaming.py`:

```python
from verificador.agent import Verificador
from verificador.config import Config

from tests.helpers import stream_de


def _agente():
    return Verificador(config=Config(api_key="x", base_url="http://l", model="m"))


def test_completar_pide_stream_y_junta_el_contenido(monkeypatch):
    a = _agente()
    capturado = {}

    def fake_create(**k):
        capturado.update(k)
        return stream_de(content="Hola mundo verificado")

    monkeypatch.setattr(a._client.chat.completions, "create", fake_create)
    eventos = []
    content, tcs = a._completar([], eventos.append)
    assert capturado["stream"] is True
    assert content == "Hola mundo verificado"
    assert tcs == []
    deltas = [e for e in eventos if e["tipo"] == "delta"]
    assert "".join(d["texto"] for d in deltas) == "Hola mundo verificado"


def test_completar_reconstruye_tool_calls_sin_emitir_deltas(monkeypatch):
    a = _agente()
    monkeypatch.setattr(
        a._client.chat.completions, "create",
        lambda **k: stream_de(tool_calls=[("t1", "buscar_web", '{"query": "x"}')]))
    eventos = []
    content, tcs = a._completar([], eventos.append)
    assert tcs == [{"id": "t1", "name": "buscar_web", "arguments": '{"query": "x"}'}]
    assert not [e for e in eventos if e["tipo"] == "delta"]


def test_completar_resetea_si_llegan_tools_tras_texto(monkeypatch):
    a = _agente()

    def flujo(**k):
        yield from stream_de(content="pensando…")
        yield from stream_de(tool_calls=[("t1", "buscar_web", '{"query": "x"}')])

    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: flujo())
    eventos = []
    _content, tcs = a._completar([], eventos.append)
    assert [e for e in eventos if e["tipo"] == "delta_reset"]
    assert tcs and tcs[0]["name"] == "buscar_web"


def test_completar_sin_on_step_no_rompe(monkeypatch):
    a = _agente()
    monkeypatch.setattr(a._client.chat.completions, "create",
                        lambda **k: stream_de(content="Texto"))
    content, tcs = a._completar([], None)
    assert content == "Texto"
```

1c. Añadir a `tests/test_server.py`:

```python
def test_sse_emite_delta_y_reset(monkeypatch):
    class _FakeAgente:
        def preguntar(self, pregunta, *, country=None, rigor="riguroso",
                      largo="corta", detalle="simple", on_step=None):
            on_step({"tipo": "delta", "texto": "Hola "})
            on_step({"tipo": "delta_reset"})
            on_step({"tipo": "delta", "texto": "Veredicto"})
            return "Veredicto"

    monkeypatch.setattr(server, "_agente", lambda: _FakeAgente())
    client = TestClient(server.app)
    with client.stream("POST", "/api/verificar", json={"pregunta": "x"}) as r:
        cuerpo = "".join(chunk for chunk in r.iter_text())
    assert "event: delta" in cuerpo
    assert "event: delta_reset" in cuerpo
    assert "event: respuesta" in cuerpo
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_streaming.py tests/test_server.py -q`
Expected: FAIL — `AttributeError: 'Verificador' object has no attribute '_completar'` y, en el server, sin `event: delta`.

- [ ] **Step 3: Write the implementation**

3a. En `verificador/agent.py`, añadir el método `_completar` a `Verificador` (después de `_reparar_json`):

```python
    def _completar(self, messages: list[dict],
                   on_step: Callable[[dict], None] | None = None) -> tuple[str, list[dict]]:
        """Una vuelta del modelo, en streaming.

        Devuelve ``(content, tool_calls)`` con las tool_calls reconstruidas de
        los deltas (``[{"id", "name", "arguments"}]``). Mientras la vuelta no
        pida herramientas, cada fragmento de texto se reenvía por ``on_step``
        como ``{"tipo": "delta", "texto": ...}``; si a mitad aparecen tools,
        se emite un único ``{"tipo": "delta_reset"}`` para descartar lo emitido.
        """
        stream = self._client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.2,
            stream=True,
        )
        partes: list[str] = []
        tcs: dict[int, dict] = {}
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            texto = getattr(delta, "content", None)
            if texto:
                partes.append(texto)
                if not tcs and on_step:
                    on_step({"tipo": "delta", "texto": texto})
            for td in getattr(delta, "tool_calls", None) or []:
                if not tcs and partes and on_step:
                    on_step({"tipo": "delta_reset"})
                hueco = tcs.setdefault(td.index, {"id": "", "name": "", "arguments": ""})
                if getattr(td, "id", None):
                    hueco["id"] = td.id
                fn = getattr(td, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        hueco["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        hueco["arguments"] += fn.arguments
        return "".join(partes), [tcs[i] for i in sorted(tcs)]
```

3b. En `preguntar()`, reemplazar el bloque desde `resp = self._client.chat.completions.create(...)` hasta `messages.append(assistant)` (inclusive) por:

```python
            content, tool_calls = self._completar(messages, on_step)

            assistant: dict = {"role": "assistant", "content": content}
            if tool_calls:
                assistant["tool_calls"] = [
                    {
                        "id": t["id"],
                        "type": "function",
                        "function": {"name": t["name"], "arguments": t["arguments"]},
                    }
                    for t in tool_calls
                ]
            messages.append(assistant)
```

y adaptar el resto de la vuelta: `if not msg.tool_calls:` → `if not tool_calls:` (con `procesar(content, ...)` en vez de `msg.content or ""`), y el bucle `for tc in msg.tool_calls:` → `for t in tool_calls:` usando `t["arguments"]`, `t["id"]`, `t["name"]` (es decir, `args = json.loads(t["arguments"] or "{}")` y `ev = _evento_inicio(t["id"], t["name"], args)`; el `messages.append` de la tool usa `t["id"]`).

3c. En `verificador/server.py`, añadir tras `_sse`:

```python
def _evento_cola(ev: dict) -> tuple[str, dict]:
    """Mapea un evento de on_step a su evento SSE (delta, delta_reset o traza)."""
    tipo = ev.get("tipo")
    if tipo == "delta":
        return "delta", {"texto": ev.get("texto", "")}
    if tipo == "delta_reset":
        return "delta_reset", {}
    return "traza", ev
```

y en `trabajar()` cambiar `on_step=lambda ev: cola.put(("traza", ev))` por `on_step=lambda ev: cola.put(_evento_cola(ev))`.

3d. En `verificador/cli.py`, en `_responder`, al inicio de `on_step`:

```python
    def on_step(ev: dict) -> None:
        if isinstance(ev, dict) and ev.get("tipo") in ("delta", "delta_reset"):
            return  # los deltas son para la web; el CLI imprime la respuesta entera
        print(f"{_DIM}  {_formatear_paso(ev)}{_RESET}", flush=True)
```

3e. Actualizar los fakes de `tests/test_traza.py`: eliminar las clases `_FakeMsg`, `_FakeTC` y `_Choices` (las de nivel de módulo y las locales), importar `from tests.helpers import stream_de`, y en cada test sustituir la pareja "lista de respuestas + `_Choices`" por streams. Patrón (aplicarlo a los 6 tests que fakean `create`):

```python
    flujos = [
        stream_de(tool_calls=[("t1", "leer_pagina", '{"url": "https://www.elpais.com/n"}')]),
        stream_de(content="Veredicto final"),
    ]
    it = iter(flujos)
    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: next(it))
```

En los tests sin tools (`test_preguntar_captura_propuestas`, `test_preguntar_inyecta_instruccion_de_modo`, `test_cada_consulta_es_independiente`, `test_preguntar_enriquece_meta`) el fake es `stream_de(content=final)`; donde se capturan los kwargs se conserva la función:

```python
    def fake_create(**k):
        capturado["messages"] = k["messages"]
        return stream_de(content=final)
```

(en `test_cada_consulta_es_independiente`, `capturas.append(k["messages"])` y `return stream_de(content=final)`). En `test_preguntar_enriquece_meta` el flujo pasa a ser `stream_de(tool_calls=[...])` + `stream_de(content=final)` como en el patrón.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS (toda la suite, incluidos los fakes actualizados).

- [ ] **Step 5: Commit**

```bash
git add verificador/agent.py verificador/server.py verificador/cli.py tests/helpers.py tests/test_streaming.py tests/test_server.py tests/test_traza.py
git commit -m "feat: respuesta en streaming (deltas SSE) de punta a punta"
```

---

### Task 9: búsqueda más sólida — caché TTL y reintentos

**Files:**
- Modify: `verificador/search.py`
- Test: `tests/test_cache.py` (nuevo)

**Interfaces:**
- Consumes: `normalizar_url` (Task 1).
- Produces: `leer_pagina`/`ver_video` cachean lecturas **ok** en memoria (`search._cache`, TTL `search._CACHE_TTL = 900.0`, tope `_CACHE_MAX = 64`, claves = URL canónica); `buscar_web` reintenta hasta 3 intentos con backoff; nuevo helper `_ddgs_texto(query, region, max_resultados) -> list[dict]` (aísla la dependencia `ddgs` para poder testear); `_leer_rapido` reintenta 1 vez ante error de red o 5xx (nunca ante 4xx).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cache.py
import verificador.search as search
from verificador.search import buscar_web, leer_pagina


def setup_function(_f):
    search._cache.clear()


def test_leer_pagina_cachea_por_url_normalizada(monkeypatch):
    llamadas = []

    def rapido(url):
        llamadas.append(url)
        return "TEXTO LARGO"

    monkeypatch.setattr(search, "_leer_rapido", rapido)
    monkeypatch.setattr(search, "_leer_navegador", lambda url, **k: None)
    a = leer_pagina("https://www.ejemplo.com/nota?utm_source=x")
    b = leer_pagina("https://ejemplo.com/nota/")
    assert a.ok and b.ok
    assert len(llamadas) == 1          # la segunda salió de la caché
    assert b.texto == a.texto


def test_fallos_no_se_cachean(monkeypatch):
    intentos = {"n": 0}

    def rapido(url):
        intentos["n"] += 1
        return None if intentos["n"] == 1 else "YA FUNCIONA"

    monkeypatch.setattr(search, "_leer_rapido", rapido)
    monkeypatch.setattr(search, "_leer_navegador", lambda url, **k: None)
    assert leer_pagina("https://ejemplo.com/x").ok is False
    assert leer_pagina("https://ejemplo.com/x").ok is True


def test_cache_expira(monkeypatch):
    reloj = {"t": 1000.0}
    monkeypatch.setattr(search.time, "monotonic", lambda: reloj["t"])
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "TEXTO")
    monkeypatch.setattr(search, "_leer_navegador", lambda url, **k: None)
    leer_pagina("https://ejemplo.com/x")
    reloj["t"] += search._CACHE_TTL + 1
    llamadas = []

    def rapido2(url):
        llamadas.append(url)
        return "TEXTO2"

    monkeypatch.setattr(search, "_leer_rapido", rapido2)
    leer_pagina("https://ejemplo.com/x")
    assert llamadas                     # expiró: volvió a leer


def test_cache_respeta_el_tope(monkeypatch):
    monkeypatch.setattr(search, "_leer_rapido", lambda url: "T")
    monkeypatch.setattr(search, "_leer_navegador", lambda url, **k: None)
    for i in range(search._CACHE_MAX + 5):
        leer_pagina(f"https://ejemplo.com/{i}")
    assert len(search._cache) <= search._CACHE_MAX


def test_buscar_web_reintenta_y_recupera(monkeypatch):
    intentos = {"n": 0}

    def ddgs_texto(query, region, max_resultados):
        intentos["n"] += 1
        if intentos["n"] < 3:
            raise RuntimeError("ratelimit")
        return [{"title": "T", "href": "https://reuters.com/a", "body": "B"}]

    monkeypatch.setattr(search, "_ddgs_texto", ddgs_texto)
    monkeypatch.setattr(search.time, "sleep", lambda s: None)
    res = buscar_web("x")
    assert intentos["n"] == 3
    assert res[0]["titulo"] == "T"


def test_buscar_web_agota_reintentos_y_devuelve_error(monkeypatch):
    def revienta(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(search, "_ddgs_texto", revienta)
    monkeypatch.setattr(search.time, "sleep", lambda s: None)
    res = buscar_web("x")
    assert "error" in res[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cache.py -q`
Expected: FAIL — `AttributeError: module 'verificador.search' has no attribute '_cache'`

- [ ] **Step 3: Write the implementation** (en `verificador/search.py`)

3a. Imports: añadir `import time` y `from .urls import normalizar_url`.

3b. Añadir tras la definición de `Lectura`:

```python
# --- Caché en memoria de lecturas (solo éxitos) -------------------------------
# Clave: URL canónica (urls.normalizar_url). Evita re-descargar la misma página
# dentro de una consulta "a fondo" y entre consultas cercanas en el tiempo.
_CACHE_TTL = 900.0   # 15 min
_CACHE_MAX = 64
_cache: dict[str, tuple[float, Lectura]] = {}
_cache_lock = threading.Lock()


def _cache_get(clave: str) -> Lectura | None:
    if not clave:
        return None
    with _cache_lock:
        hit = _cache.get(clave)
        if hit is None:
            return None
        ts, lectura = hit
        if time.monotonic() - ts > _CACHE_TTL:
            del _cache[clave]
            return None
        return lectura


def _cache_put(clave: str, lectura: Lectura) -> None:
    if not clave:
        return
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))  # la más vieja
        _cache[clave] = (time.monotonic(), lectura)
```

3c. Reemplazar `buscar_web` por:

```python
def _ddgs_texto(query: str, region: str, max_resultados: int) -> list[dict]:
    """Llamada cruda a DuckDuckGo. Separada para poder reintentar y testear."""
    from ddgs import DDGS  # import perezoso: acelera el arranque del CLI

    with DDGS() as ddgs:
        return list(ddgs.text(query, region=region, max_results=max_resultados))


def buscar_web(query: str, max_resultados: int = 6, pais: str | None = None) -> list[dict]:
    """Busca en DuckDuckGo (con reintentos) y devuelve [{titulo, url, resumen, fiabilidad}]."""
    region = _REGION.get((pais or "").upper(), "wt-wt")
    ultimo: Exception | None = None
    for intento in range(3):
        try:
            filas = _ddgs_texto(query, region, max_resultados)
            break
        except Exception as e:  # noqa: BLE001 — ddgs es frágil: reintentamos
            ultimo = e
            if intento < 2:
                time.sleep(0.5 * (intento + 1))
    else:
        return [{"error": f"Fallo la búsqueda: {ultimo}"}]

    resultados: list[dict] = []
    for r in filas:
        url = r.get("href") or r.get("url", "")
        try:
            _fiab = fuentes.anotar(url)
        except Exception:  # noqa: BLE001
            _fiab = ""
        resultados.append(
            {
                "titulo": r.get("title", ""),
                "url": url,
                "resumen": r.get("body", ""),
                "fiabilidad": _fiab,
            }
        )
    return resultados or [{"aviso": "Sin resultados para esa búsqueda."}]
```

3d. Reemplazar `_leer_rapido` por:

```python
def _leer_rapido(url: str) -> str | None:
    """Ruta rápida: httpx + trafilatura, con un reintento ante fallo de red o
    5xx (nunca ante 4xx). None si falla o sale vacío."""
    for intento in range(2):
        try:
            resp = httpx.get(url, headers=_HEADERS, timeout=8.0, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500 or intento == 1:
                return None
            time.sleep(0.4)
            continue
        except Exception:  # noqa: BLE001 — red caída, timeout, DNS
            if intento == 1:
                return None
            time.sleep(0.4)
            continue
        return _extraer(resp.text) or None
    return None
```

3e. En `leer_pagina`, envolver con la caché:

```python
def leer_pagina(url: str, max_chars: int = 6000) -> Lectura:
    """Descarga una URL y devuelve su texto principal (caché → rápido → navegador).

    Devuelve ``Lectura(texto, ok)``: ``ok`` es False si no se pudo abrir ni
    extraer texto (el aviso no debe llegar al visor de evidencias). Solo los
    éxitos se cachean.
    """
    clave = normalizar_url(url)
    cacheada = _cache_get(clave)
    if cacheada is not None:
        return cacheada
    texto = _leer_rapido(url) or _leer_navegador(url)
    if not texto:
        return Lectura(f"[No pude abrir ni extraer texto de {url}.]", False)
    if len(texto) > max_chars:
        texto = texto[:max_chars] + "\n…[texto truncado]"
    try:
        _pref = fuentes.anotar(url) + "\n"
    except Exception:  # noqa: BLE001 — la anotación nunca rompe la respuesta
        _pref = ""
    lectura = Lectura(f"{_pref}{texto}", True)
    _cache_put(clave, lectura)
    return lectura
```

3f. En `ver_video`, cachear igual: al inicio `clave = normalizar_url(url)` + `_cache_get`; y antes del `return Lectura(f"{_pref}[Transcripción...", True)` construir la `lectura`, hacer `_cache_put(clave, lectura)` y devolverla.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS (incluye `tests/test_lectura.py` existente; si algún test suyo monkeypatchea `_leer_rapido`/`_leer_navegador` con URLs repetidas, añadir `search._cache.clear()` en un `setup_function` de ese archivo).

- [ ] **Step 5: Commit**

```bash
git add verificador/search.py tests/test_cache.py tests/test_lectura.py
git commit -m "feat: caché TTL de lecturas y reintentos en búsqueda y descarga"
```

---

### Task 10: herramientas en paralelo

**Files:**
- Modify: `verificador/agent.py`
- Test: `tests/test_paralelo.py` (nuevo)

**Interfaces:**
- Consumes: `_completar` (Task 8), `_ejecutar_tool` (existente).
- Produces: cuando una vuelta trae varias tool_calls, se ejecutan con `ThreadPoolExecutor` (máx. 4). Los eventos de inicio se emiten todos antes de lanzar; los de fin, al completar cada una (orden de llegada); los mensajes `role: tool` se anexan **en el orden original** de las tool_calls.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_paralelo.py
import threading

from verificador import agent as agentmod
from verificador.agent import Verificador
from verificador.config import Config
from verificador.search import Lectura

from tests.helpers import stream_de


def _agente():
    return Verificador(config=Config(api_key="x", base_url="http://l", model="m"))


def test_dos_lecturas_corren_a_la_vez(monkeypatch):
    """Una barrera de 2: solo se cruza si ambas lecturas corren en paralelo."""
    a = _agente()
    barrera = threading.Barrier(2, timeout=5)

    def lp(url, **k):
        barrera.wait()
        return Lectura(f"X:{url}", True)

    monkeypatch.setattr(agentmod, "leer_pagina", lp)
    flujos = [
        stream_de(tool_calls=[
            ("t1", "leer_pagina", '{"url": "https://a.com/1"}'),
            ("t2", "leer_pagina", '{"url": "https://b.com/2"}'),
        ]),
        stream_de(content="fin"),
    ]
    it = iter(flujos)
    monkeypatch.setattr(a._client.chat.completions, "create", lambda **k: next(it))
    out = a.preguntar("x")
    assert "fin" in out


def test_mensajes_tool_conservan_el_orden(monkeypatch):
    a = _agente()
    capturas = []

    def fake_create(**k):
        capturas.append(k["messages"])
        if len(capturas) == 1:
            return stream_de(tool_calls=[
                ("t1", "leer_pagina", '{"url": "https://a.com/1"}'),
                ("t2", "leer_pagina", '{"url": "https://b.com/2"}'),
            ])
        return stream_de(content="fin")

    monkeypatch.setattr(a._client.chat.completions, "create", fake_create)
    monkeypatch.setattr(agentmod, "leer_pagina",
                        lambda url, **k: Lectura(f"X:{url}", True))
    a.preguntar("x")
    tools = [m for m in capturas[1] if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in tools] == ["t1", "t2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_paralelo.py -q`
Expected: FAIL — `test_dos_lecturas_corren_a_la_vez` revienta con `BrokenBarrierError` (ejecución secuencial); el segundo puede pasar.

- [ ] **Step 3: Write the implementation**

En `verificador/agent.py`: añadir `from concurrent.futures import ThreadPoolExecutor, as_completed` a los imports, y reemplazar el bucle completo `for t in tool_calls:` (el que ejecuta herramientas, de Task 8) por:

```python
            # Ejecutar las herramientas (en paralelo si hay varias) y devolver
            # su resultado al modelo. Los eventos de inicio salen todos antes;
            # los de fin, según cada una termina; los mensajes `tool` se anexan
            # en el orden original de las tool_calls.
            llamadas = []
            for t in tool_calls:
                try:
                    args = json.loads(t["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                llamadas.append((t["id"], t["name"], args,
                                 _evento_inicio(t["id"], t["name"], args)))
            if on_step:
                for _tid, _nom, _args, ev in llamadas:
                    on_step(ev)

            def _correr(item):
                tid, nombre, args, ev = item
                return tid, ev, self._ejecutar_tool(nombre, args,
                                                    country=country, rigor=rigor)

            resultados: dict[str, Lectura] = {}
            with ThreadPoolExecutor(max_workers=min(4, len(llamadas))) as pool:
                futuros = [pool.submit(_correr, item) for item in llamadas]
                for futuro in as_completed(futuros):
                    tid, ev, lectura = futuro.result()
                    resultados[tid] = lectura
                    con_extracto = ev["tipo"] in ("pagina", "video") and lectura.ok
                    if con_extracto and ev["url"]:
                        extractos[ev["url"]] = lectura.texto[:1500]
                    if on_step:
                        fin = {"id": ev["id"], "tipo": ev["tipo"],
                               "estado": "ok" if lectura.ok else "fallo",
                               "titulo": ev["titulo"], "url": ev["url"],
                               "dominio": ev["dominio"]}
                        # Solo en éxito guardamos el extracto: el texto de error
                        # nunca debe llegar al visor "ver de dónde salió".
                        if con_extracto:
                            fin["extracto"] = lectura.texto[:1500]
                        on_step(fin)
            for t in tool_calls:
                messages.append({"role": "tool", "tool_call_id": t["id"],
                                 "content": resultados[t["id"]].texto})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS (toda la suite; los tests de traza siguen valiendo porque el caso de una sola tool también pasa por el pool).

- [ ] **Step 5: Commit**

```bash
git add verificador/agent.py tests/test_paralelo.py
git commit -m "feat: tool calls del mismo turno en paralelo (hasta 4 hilos)"
```

---

### Task 11: frontend — presets en el composer (B1)

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/faro.css`

**Interfaces:**
- Consumes: `useVerificador().preguntar(pregunta, opciones)` y el tipo `Opciones` (sin cambios).
- Produces: la cabecera queda solo con la marca; el composer lleva un segmentado único de presets (`esencial` / `normal` / `afondo`) que mapea a `Opciones`. El botón de enviar pasa a tener clase `enviar` (el CSS deja de estilar `.composer button` a secas — necesario para que los seg-opt del pie no hereden ese estilo).

- [ ] **Step 1: Implement**

1a. En `frontend/src/App.tsx`: borrar `OpcionSeg` y `CONTROLES`; añadir tras los imports:

```tsx
interface Preset {
  valor: string;
  texto: string;
  titulo: string;
  opciones: Opciones;
}

// Un solo eje de modo: cada preset fija rigor + largo + detalle de la API.
const PRESETS: Preset[] = [
  {
    valor: "esencial",
    texto: "Esencial",
    titulo: "Menos fuentes, respuesta en segundos.",
    opciones: { rigor: "rapido", largo: "corta", detalle: "simple" },
  },
  {
    valor: "normal",
    texto: "Normal",
    titulo: "Contraste completo, un párrafo.",
    opciones: { rigor: "riguroso", largo: "normal", detalle: "simple" },
  },
  {
    valor: "afondo",
    texto: "A fondo",
    titulo: "Contexto, matices y cifras.",
    opciones: { rigor: "riguroso", largo: "detallada", detalle: "tecnico" },
  },
];
```

1b. `Masthead` queda sin props ni controles:

```tsx
function Masthead() {
  return (
    <header className="masthead">
      <a
        className="brand"
        href="/"
        aria-label="Faro, inicio"
        title="Faro — Frente A la Réplica de lo falsO"
      >
        <span className="brand-face" aria-hidden="true">
          <MiniAvatar />
        </span>
        <span className="brand-text">
          <span className="brand-name">Faro</span>
          <span className="brand-sub">frente a lo falso</span>
        </span>
      </a>
    </header>
  );
}
```

1c. `Composer` recibe `preset`/`setPreset` y añade el pie (textarea y lógica de envío no cambian):

```tsx
function Composer({
  enCurso,
  preset,
  setPreset,
  onEnviar,
}: {
  enCurso: boolean;
  preset: string;
  setPreset: (p: string) => void;
  onEnviar: (texto: string) => void;
}) {
  const [texto, setTexto] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, window.innerHeight * 0.4) + "px";
  }, [texto]);

  const enviar = () => {
    const q = texto.trim();
    if (!q || enCurso) return;
    onEnviar(q);
    setTexto("");
  };

  return (
    <form
      className="composer"
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        enviar();
      }}
    >
      <div className="composer-inner">
        <textarea
          ref={ref}
          rows={1}
          value={texto}
          placeholder="Dime qué quieres que verifique…"
          aria-label="Tu pregunta o afirmación"
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              enviar();
            }
          }}
        />
        <div className="composer-pie">
          <div className="seg" role="group" aria-label="Modo de respuesta">
            {PRESETS.map((p) => (
              <button
                key={p.valor}
                type="button"
                title={p.titulo}
                className={"seg-opt" + (preset === p.valor ? " is-on" : "")}
                aria-pressed={preset === p.valor}
                onClick={() => setPreset(p.valor)}
              >
                {p.texto}
              </button>
            ))}
          </div>
          <button className="enviar" type="submit" aria-label="Validar" disabled={enCurso}>
            <span>Validar</span>
            <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
              <path
                d="M5 12h14M13 6l6 6-6 6"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>
      </div>
    </form>
  );
}
```

1d. En `App`: sustituir el estado `modo` por `const [preset, setPreset] = useState("normal");`, quitar las props de `Masthead`, y al final:

```tsx
  const opciones = (PRESETS.find((p) => p.valor === preset) ?? PRESETS[1]).opciones;
  return (
    <>
      <div className="grain" aria-hidden="true" />
      <Masthead />
      <main className="hilo">
        {turnos.length === 0 && <Hero />}
        {turnos.map((t) => (
          <TurnoView key={t.id} turno={t} />
        ))}
        <div ref={finRef} />
      </main>
      <Composer enCurso={enCurso} preset={preset} setPreset={setPreset}
                onEnviar={(q) => preguntar(q, opciones)} />
    </>
  );
```

1e. En `frontend/src/faro.css`:
- Borrar las reglas `.controls`, `.ctrl`, `.ctrl-lbl` (el `.seg`/`.seg-opt` se queda: lo reutiliza el composer).
- En `.masthead` cambiar `align-items: flex-end` por `align-items: center`.
- Reemplazar el bloque del composer (`.composer-inner`, `.composer textarea`, `.composer textarea:focus-visible`, `.composer button*`) por:

```css
.composer-inner {
  width: 100%; max-width: var(--wrap); margin: 0 auto; display: flex; flex-direction: column;
  background: var(--card); border: 1px solid var(--line); border-radius: 15px;
  box-shadow: 0 10px 26px -22px rgba(42, 36, 32, 0.5);
}
.composer-inner:focus-within { border-color: var(--faro); box-shadow: 0 0 0 2px rgba(47, 93, 114, 0.18); }
.composer textarea {
  resize: none; max-height: 40vh; padding: 0.9rem 1rem 0.55rem; border: 0; border-radius: 15px 15px 0 0;
  background: transparent; font-family: var(--serif); font-size: 1.04rem; line-height: 1.45; color: var(--ink);
}
.composer textarea::placeholder { color: var(--muted); }
.composer textarea:focus-visible { outline: none; }
.composer-pie { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; padding: 0.35rem 0.55rem 0.55rem; }
.composer-pie .seg { height: 34px; }
.composer .enviar {
  flex: none; display: inline-flex; align-items: center; gap: 0.4rem; height: 38px; padding: 0 1.05rem; border: 0; border-radius: 10px;
  background: var(--ink); color: var(--paper); font-family: var(--mono); font-size: 0.8rem; letter-spacing: 0.03em; cursor: pointer; transition: opacity 0.12s, transform 0.1s;
}
.composer .enviar:hover { opacity: 0.88; }
.composer .enviar:active { transform: translateY(1px); }
.composer .enviar:disabled { opacity: 0.4; cursor: progress; }
.composer .enviar:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.composer .enviar svg { display: block; }
```

- En la media query de 600px: sustituir las reglas `.composer button span` y `.composer button` por `.composer .enviar span { display: none; }` y `.composer .enviar { padding: 0 0.9rem; }`, y borrar la regla `.controls { ... }`.

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: build sin errores de TypeScript ni de Vite.

- [ ] **Step 3: Visual check**

Con uvicorn corriendo (`.venv/bin/uvicorn verificador.server:app`), abrir `http://127.0.0.1:8000`: cabecera solo con la marca; composer con el segmentado Esencial/Normal/A fondo (Normal activo) a la izquierda y Validar a la derecha; en móvil (ventana estrecha) el pie no se desborda.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/faro.css frontend/dist
git commit -m "feat(web): las opciones de respuesta bajan al composer como presets"
```

---

### Task 12: frontend — streaming de la respuesta

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/format.ts`
- Modify: `frontend/src/hooks/useVerificador.ts`
- Modify: `frontend/src/components/Answer.tsx`
- Modify: `frontend/src/faro.css`
- Test: `tests/test_citas.mjs`

**Interfaces:**
- Consumes: eventos SSE `delta` / `delta_reset` (Task 8).
- Produces: `Turno.estado` admite `"respondiendo"`; `partirRespuesta` corta también un bloque ```json **abierto** (streaming a medias) devolviendo `meta: null`; la prosa aparece palabra a palabra con un caret; sello y fuentes solo al llegar `respuesta`.

- [ ] **Step 1: Write the failing test** (añadir a `tests/test_citas.mjs`, antes del `console.log("ok")`)

```js
// partirRespuesta — copia de frontend/src/lib/format.ts (mantener idéntica).
function partirRespuesta(texto) {
  const m = texto.match(/```json\s*([\s\S]*?)```\s*$/i);
  if (m) {
    let meta = null;
    try { meta = JSON.parse(m[1].trim()); } catch { /* JSON inválido */ }
    return { prosa: texto.slice(0, m.index).trim(), meta };
  }
  // Bloque aún abierto (streaming): se oculta desde donde empieza.
  const abierto = texto.search(/```json/i);
  if (abierto !== -1) return { prosa: texto.slice(0, abierto).trim(), meta: null };
  return { prosa: texto.trim(), meta: null };
}

const pCompleta = partirRespuesta('Hola [1].\n\n```json\n{"veredicto":"falso"}\n```');
assert.equal(pCompleta.prosa, "Hola [1].");
assert.equal(pCompleta.meta.veredicto, "falso");

const pAbierta = partirRespuesta('Hola en curso\n\n```json\n{"vered');
assert.equal(pAbierta.prosa, "Hola en curso");
assert.equal(pAbierta.meta, null);

const pSinJson = partirRespuesta("Solo prosa");
assert.equal(pSinJson.prosa, "Solo prosa");
```

- [ ] **Step 2: Run test to verify the copy matches** (falla si la copia difiere del comportamiento nuevo)

Run: `node tests/test_citas.mjs`
Expected: `ok` (la copia ya incluye el comportamiento nuevo; el paso 3 lo lleva al código real).

- [ ] **Step 3: Implement**

3a. `frontend/src/lib/types.ts` — en `Turno`, cambiar `estado: "investigando" | "listo" | "error";` por:

```ts
  estado: "investigando" | "respondiendo" | "listo" | "error";
```

3b. `frontend/src/lib/format.ts` — reemplazar `partirRespuesta` por (misma lógica que la copia del test):

```ts
// Separa la prosa del bloque ```json final (el contrato de datos del medidor).
// Durante el streaming el bloque puede llegar a medias: también se oculta.
export function partirRespuesta(texto: string): { prosa: string; meta: Meta | null } {
  const m = texto.match(/```json\s*([\s\S]*?)```\s*$/i);
  if (m) {
    let meta: Meta | null = null;
    try {
      meta = JSON.parse(m[1].trim());
    } catch {
      /* JSON inválido: lo ignoramos */
    }
    return { prosa: texto.slice(0, m.index).trim(), meta };
  }
  const abierto = texto.search(/```json/i);
  if (abierto !== -1) return { prosa: texto.slice(0, abierto).trim(), meta: null };
  return { prosa: texto.trim(), meta: null };
}
```

3c. `frontend/src/hooks/useVerificador.ts` — en el callback de `streamVerificar`, añadir dos ramas antes de la de `"respuesta"`:

```ts
        if (evento === "traza") {
          parchar((t) => aplicarTraza(t, dato as TrazaEvento));
        } else if (evento === "delta") {
          parchar((t) => ({
            ...t,
            estado: "respondiendo",
            respuesta: (t.respuesta ?? "") + (dato.texto || ""),
          }));
        } else if (evento === "delta_reset") {
          parchar((t) => ({ ...t, estado: "investigando", respuesta: undefined }));
        } else if (evento === "respuesta") {
```

3d. `frontend/src/components/Answer.tsx` — señal de escritura: tras `if (!turno.respuesta) return null;` añadir `const escribiendo = turno.estado === "respondiendo";` y condicionar sello y fuentes (el resumen llega en Task 13):

```tsx
      {sello && !escribiendo && (
        ...bloque del sello igual...
      )}

      <div className="respuesta-cuerpo" dangerouslySetInnerHTML={{ __html: cuerpoHtml }} />
      {escribiendo && <span className="escribiendo" aria-hidden="true" />}

      {!escribiendo && <Sources fuentes={fuentes} extractos={extractos} />}
```

3e. `frontend/src/faro.css` — añadir junto a `.respuesta-cuerpo`:

```css
.escribiendo { display: inline-block; width: 9px; height: 1.05em; margin-left: 2px; vertical-align: text-bottom; background: var(--faro); animation: latido 1.1s ease-in-out infinite; }
```

- [ ] **Step 4: Verify**

Run: `node tests/test_citas.mjs` → `ok`. Después `cd frontend && npm run build` → sin errores. Con el servidor en marcha y una pregunta real: la traza corre, la prosa aparece palabra a palabra con caret, y al terminar entra el sello; el bloque ```json nunca se ve.

- [ ] **Step 5: Commit**

```bash
git add frontend/src tests/test_citas.mjs frontend/dist
git commit -m "feat(web): la respuesta aparece en streaming, con el bloque json oculto"
```

---

### Task 13: frontend — respuesta como portada (B2)

**Files:**
- Modify: `frontend/src/components/Answer.tsx`
- Modify: `frontend/src/lib/maps.ts`
- Modify: `frontend/src/faro.css`

**Interfaces:**
- Consumes: meta enriquecido (con `resumen`, `pais`, `confianza` calculada) de Tasks 6-7; `escribiendo` de Task 12.
- Produces: `nombrePais(codigo: string | undefined): string | null` en `maps.ts`; respuesta con firma+país, banda de veredicto (filete superior del color del veredicto, confianza integrada), titular en Fraunces con `meta.resumen`, y citas `[n]` como enlaces con recuadro.

- [ ] **Step 1: Implement**

1a. `frontend/src/lib/maps.ts` — añadir al final:

```ts
// Nombre legible de un país por su código ISO (los más citados); si no está,
// se muestra el valor tal cual (puede venir ya como nombre).
const PAISES: Record<string, string> = {
  CO: "Colombia", MX: "México", AR: "Argentina", ES: "España", CL: "Chile",
  PE: "Perú", VE: "Venezuela", US: "EE. UU.", UY: "Uruguay", EC: "Ecuador",
  BO: "Bolivia", PY: "Paraguay", CR: "Costa Rica", GT: "Guatemala",
  BR: "Brasil", FR: "Francia", DE: "Alemania", IT: "Italia",
  GB: "Reino Unido", PT: "Portugal",
};

export function nombrePais(codigo: string | undefined): string | null {
  if (!codigo || !codigo.trim()) return null;
  const c = codigo.trim();
  return PAISES[c.toUpperCase()] ?? c;
}
```

1b. `frontend/src/components/Answer.tsx` — versión completa nueva:

```tsx
// Una respuesta de Faro como portada: firma (+ país) + banda del veredicto con
// confianza + titular (resumen) + prosa con citas enlazadas + ficha de fuentes.
// Si el turno falló, muestra el aviso.

import { enlazarCitas, formatear, partirRespuesta } from "../lib/format";
import { nombrePais, selloDe } from "../lib/maps";
import { MiniAvatar } from "./avatars";
import { Sources } from "./Sources";
import type { Turno } from "../lib/types";

export function Answer({ turno }: { turno: Turno }) {
  if (turno.error) return <div className="aviso">{turno.error}</div>;
  if (!turno.respuesta) return null;

  const escribiendo = turno.estado === "respondiendo";
  const { prosa, meta } = partirRespuesta(turno.respuesta);
  const fuentes = meta?.fuentes ?? [];
  const sello = selloDe(meta, prosa);
  const cuerpoHtml = enlazarCitas(formatear(prosa), fuentes);
  const pais = nombrePais(meta?.pais);

  // Extractos por url, recogidos de la traza (respaldo si el meta no los trae).
  const extractos: Record<string, string> = {};
  for (const ev of turno.eventos) {
    if (ev.url && ev.extracto) extractos[ev.url] = ev.extracto;
  }

  const conf =
    meta &&
    meta.veredicto !== "informativo" &&
    meta.veredicto !== "no_verificable" &&
    typeof meta.confianza === "number" &&
    Number.isFinite(meta.confianza)
      ? Math.max(0, Math.min(100, Math.round(meta.confianza)))
      : null;

  return (
    <div className="veredicto">
      <div className="resp-firma">
        <MiniAvatar />
        <b>Faro</b>
        <span>verifica{pais ? " · " + pais : ""}</span>
      </div>

      {sello && !escribiendo && (
        <div className="sello-banda" data-v={sello.v}>
          <span className="sello-etiqueta">
            <span className="sello-em">{sello.emoji}</span> {sello.etiqueta}
          </span>
          {conf !== null && (
            <span className="conf">
              confianza {conf}{" "}
              <span className="conf-barra">
                <i style={{ width: conf + "%" }} />
              </span>
            </span>
          )}
        </div>
      )}

      {meta?.resumen && !escribiendo && <h2 className="resp-titular">{meta.resumen}</h2>}

      <div className="respuesta-cuerpo" dangerouslySetInnerHTML={{ __html: cuerpoHtml }} />
      {escribiendo && <span className="escribiendo" aria-hidden="true" />}

      {!escribiendo && <Sources fuentes={fuentes} extractos={extractos} />}
    </div>
  );
}
```

1c. `frontend/src/faro.css`:
- Borrar las reglas `.sello-fila`, `.pill`, `.pill[data-v=...]` (las cinco) y `.pill .pill-em`.
- Añadir en su lugar:

```css
/* Banda del veredicto: un fallo editorial con filete del color del veredicto. */
.sello-banda {
  display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap;
  gap: 0.5rem 1rem; margin: 0 0 0.95rem; padding: 0.55rem 0.1rem 0.6rem;
  border-top: 3px solid var(--ink); border-bottom: 1px solid var(--line);
}
.sello-banda[data-v="true"]  { border-top-color: var(--true); }
.sello-banda[data-v="false"] { border-top-color: var(--false); }
.sello-banda[data-v="warn"]  { border-top-color: var(--warn); }
.sello-banda[data-v="muted"] { border-top-color: var(--muted-v); }
.sello-banda[data-v="info"]  { border-top-color: var(--faro); }
.sello-etiqueta { font-family: var(--mono); font-weight: 700; font-size: 0.94rem; letter-spacing: 0.06em; text-transform: uppercase; display: inline-flex; align-items: center; gap: 0.5rem; }
.sello-banda[data-v="true"] .sello-etiqueta  { color: var(--true); }
.sello-banda[data-v="false"] .sello-etiqueta { color: var(--false); }
.sello-banda[data-v="warn"] .sello-etiqueta  { color: var(--warn); }
.sello-banda[data-v="muted"] .sello-etiqueta { color: var(--muted-v); }
.sello-banda[data-v="info"] .sello-etiqueta  { color: var(--faro); }
.sello-em { font-size: 1.15rem; }

.resp-titular { font-family: var(--display); font-weight: 600; font-size: 1.45rem; line-height: 1.15; letter-spacing: -0.015em; margin: 0 0 0.9rem; color: var(--ink); }
```

- Reemplazar la regla `.cita` (y su `:hover`) por:

```css
.cita {
  font-family: var(--mono); font-size: 0.72em; vertical-align: 0.14em; color: var(--faro);
  text-decoration: none; border: 1px solid var(--line); border-radius: 5px;
  padding: 0.05em 0.32em; margin: 0 0.12em; background: var(--card);
}
.cita:hover { border-color: var(--faro); }
```

1d. Nota: el `title` con el nombre del medio en cada cita se resuelve en `format.ts` — en `enlazarCitas`, al construir el enlace, añadir el atributo:

```ts
    const titulo = f.medio ? ' title="' + String(f.medio).replace(/"/g, "&quot;") + '"' : "";
    return (
      '<a class="cita" href="' +
      encodeURI(urlSegura(f.url)) +
      '"' + titulo + ' target="_blank" rel="noopener">[' +
      n +
      "]</a>"
    );
```

(y en `tests/test_citas.mjs`, actualizar la copia de `enlazarCitas` con las mismas líneas; añadir un assert: `assert.ok(enlazarCitas("x [1]", [{ n: 1, url: "https://a.com", medio: 'El "País"' }]).includes('title="El &quot;País&quot;"'));`)

- [ ] **Step 2: Verify**

Run: `node tests/test_citas.mjs` → `ok`; `cd frontend && npm run build` → sin errores.

- [ ] **Step 3: Visual check**

Pregunta real en el navegador: firma "Faro verifica · País", banda con filete del color del veredicto y confianza a la derecha, titular en Fraunces bajo la banda, citas `[n]` con recuadro y `title` del medio al pasar el ratón. Un veredicto `no_verificable` no muestra confianza.

- [ ] **Step 4: Commit**

```bash
git add frontend/src tests/test_citas.mjs frontend/dist
git commit -m "feat(web): respuesta como portada — banda de veredicto, titular y citas visibles"
```

---

### Task 14: frontend — ficha editorial de fuentes (B3)

**Files:**
- Modify: `frontend/src/components/Sources.tsx` (reescritura)
- Modify: `frontend/src/lib/types.ts` (campos `extracto`, `citada` en `FuenteMeta`)
- Modify: `frontend/src/lib/maps.ts` (`CREDIBILIDAD` con flag `aviso`, `TEND_ABREV`, quitar `TEND_CLASE`)
- Modify: `frontend/src/lib/format.ts` (`dominioDe`, `normalizarUrl`)
- Modify: `frontend/src/faro.css`

**Interfaces:**
- Consumes: fuentes del meta enriquecido (`extracto`, `citada` de Tasks 3-4, vía SSE); `extractos` por URL como respaldo.
- Produces: ficha tipo periódico: cabecera con recuento, una fila por fuente (nº, favicon+medio, tendencia abreviada, avisos solo si hay anomalía, relación, expandir), extracto expandible controlado, no citadas atenuadas al final. `normalizarUrl` y `dominioDe` exportadas de `format.ts`.

- [ ] **Step 1: Implement**

1a. `frontend/src/lib/types.ts` — en `FuenteMeta` añadir al final:

```ts
  extracto?: string;
  citada?: boolean;
```

1b. `frontend/src/lib/format.ts` — añadir al final (port de `verificador/urls.py`; misma semántica):

```ts
// Clave canónica de una URL (port de verificador/urls.py): sin esquema, sin
// www., sin parámetros de tracking, sin barra final ni fragmento.
const TRACKING = new Set(["fbclid", "gclid", "igshid", "mc_cid", "mc_eid"]);

export function normalizarUrl(u: string | undefined): string {
  if (!u || !u.trim()) return "";
  const crudo = u.trim();
  let p: URL;
  try {
    p = new URL(crudo.includes("://") ? crudo : "http://" + crudo);
  } catch {
    return crudo.toLowerCase();
  }
  let host = p.hostname.toLowerCase();
  if (host.startsWith("www.")) host = host.slice(4);
  const ruta = p.pathname.replace(/\/+$/, "");
  const pares: string[] = [];
  p.searchParams.forEach((v, k) => {
    const kl = k.toLowerCase();
    if (kl.startsWith("utm_") || TRACKING.has(kl)) return;
    pares.push(encodeURIComponent(k) + "=" + encodeURIComponent(v));
  });
  return host + ruta + (pares.length ? "?" + pares.join("&") : "");
}

export function dominioDe(u: string | undefined): string {
  try {
    const host = new URL(u ?? "").hostname.toLowerCase();
    return host.startsWith("www.") ? host.slice(4) : host;
  } catch {
    return "";
  }
}
```

1c. `frontend/src/lib/maps.ts` — reemplazar `CREDIBILIDAD` y `TEND_CLASE` por:

```ts
// Credibilidad: solo se anuncia lo anómalo (baja / no fiable); lo normal no
// ensucia la fila.
export const CREDIBILIDAD: Record<string, { txt: string; clase: string; aviso: boolean }> = {
  alta: { txt: "alta", clase: "b-alta", aviso: false },
  media: { txt: "media", clase: "b-media", aviso: false },
  baja: { txt: "cred. baja", clase: "b-baja", aviso: true },
  no_fiable: { txt: "no fiable", clase: "b-no", aviso: true },
};

export const TEND_ABREV: Record<string, string> = {
  izquierda: "izq",
  "centro-izquierda": "c-izq",
  centro: "centro",
  "centro-derecha": "c-der",
  derecha: "der",
  verificador: "verif.",
  internacional: "int.",
};
```

1d. `frontend/src/components/Sources.tsx` — reescritura completa:

```tsx
// Ficha editorial de fuentes: filetes finos, una fila por fuente; solo se
// anuncia lo anómalo (credibilidad baja, manipulación). Extracto expandible y
// fuentes nunca citadas atenuadas al final.

import { useState } from "react";
import { CREDIBILIDAD, MANIPULACION, TEND_ABREV } from "../lib/maps";
import { dominioDe, normalizarUrl, urlSegura } from "../lib/format";
import type { FuenteMeta } from "../lib/types";

function Avisos({ f }: { f: FuenteMeta }) {
  const cred = CREDIBILIDAD[(f.credibilidad || "").toLowerCase()];
  const manip = MANIPULACION[(f.manipulacion || "").toLowerCase()];
  return (
    <>
      {cred?.aviso && <span className={"f-aviso " + cred.clase}>{cred.txt}</span>}
      {manip && (
        <span
          className={"f-aviso " + manip.clase}
          title="Honestidad de la fuente: tiende a manipular la información"
        >
          ⚠ {manip.txt}
        </span>
      )}
    </>
  );
}

export function Sources({
  fuentes,
  extractos,
}: {
  fuentes: FuenteMeta[];
  extractos: Record<string, string>;
}) {
  const [abiertas, setAbiertas] = useState<Set<number>>(new Set());
  if (!fuentes.length) return null;

  const porUrl: Record<string, string> = {};
  for (const [u, x] of Object.entries(extractos)) porUrl[normalizarUrl(u)] = x;

  // Las citadas primero; las que el modelo listó pero nunca citó, al final.
  const orden = [...fuentes].sort(
    (a, b) => Number(b.citada !== false) - Number(a.citada !== false),
  );

  const alternar = (n: number) =>
    setAbiertas((prev) => {
      const s = new Set(prev);
      if (s.has(n)) s.delete(n);
      else s.add(n);
      return s;
    });

  return (
    <div className="fuentes-bloque">
      <div className="fuentes-cab">fuentes contrastadas · {fuentes.length}</div>
      <ul className="fuentes-lista">
        {orden.map((f, idx) => {
          const clave = f.n ?? idx;
          const dominio = dominioDe(f.url);
          const extracto = f.extracto ?? (f.url ? porUrl[normalizarUrl(f.url)] : undefined);
          const abierta = abiertas.has(clave);
          return (
            <li key={clave} className={"f-fila" + (f.citada === false ? " no-citada" : "")}>
              <div className="f-linea">
                <span className="f-n">[{f.n}]</span>
                {dominio ? (
                  <img
                    className="fav"
                    alt=""
                    src={
                      "https://www.google.com/s2/favicons?domain=" +
                      encodeURIComponent(dominio) +
                      "&sz=32"
                    }
                  />
                ) : (
                  <span className="fav fav--q">📄</span>
                )}
                <a className="fuente-medio" href={urlSegura(f.url)} target="_blank" rel="noopener">
                  {f.medio || dominio || "fuente"}
                </a>
                <span className="f-tend">{TEND_ABREV[(f.tendencia || "").toLowerCase()] ?? "—"}</span>
                <Avisos f={f} />
                <span className={"fuente-rel" + (f.coincide ? " si" : "")}>
                  {f.coincide ? "✓ respalda" : "· matiza"}
                </span>
                {extracto && (
                  <button
                    type="button"
                    className="f-toggle"
                    aria-expanded={abierta}
                    aria-label="Ver de dónde salió"
                    onClick={() => alternar(clave)}
                  >
                    ⌄
                  </button>
                )}
              </div>
              {abierta && extracto && (
                <blockquote className="f-extracto">
                  {extracto}
                  {f.url && (
                    <a className="f-abrir" href={urlSegura(f.url)} target="_blank" rel="noopener">
                      abrir ↗
                    </a>
                  )}
                </blockquote>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

1e. `frontend/src/faro.css` — en la sección "Fuentes y citas": borrar las reglas `.fuentes-lista`, `.fuentes-lista > li`, `.chip-t`, `.t-izq`, `.t-cen`, `.t-der`, `.t-ver`, `.t-int`, `.fuente-medio`, `.fuente-medio:hover`, `.fuente-rel`, `.badge-c`, `.badge-m`, `.m-sesgo`, `.m-eng`, `.m-desinfo`, `.prueba`, `.prueba summary`, `.prueba blockquote` (conservar `.fuentes-bloque`, `.fuentes-cab`, `.b-alta`, `.b-media`, `.b-baja`, `.b-no`) y añadir:

```css
.fuentes-lista { list-style: none; padding: 0; margin: 0; border-top: 2px solid var(--ink); }
.f-fila { border-bottom: 1px solid var(--line); }
.f-fila.no-citada { opacity: 0.55; }
.f-linea { display: flex; align-items: center; flex-wrap: wrap; gap: 0.55rem; padding: 0.52rem 0.1rem; font-family: var(--mono); font-size: 0.84rem; }
.f-n { flex: none; min-width: 1.9rem; color: var(--muted); }
.f-linea .fav { width: 18px; height: 18px; border-radius: 4px; flex: none; }
.fuente-medio { flex: 1; min-width: 8rem; color: var(--ink); text-decoration: none; }
.fuente-medio:hover { color: var(--faro); text-decoration: underline; text-underline-offset: 3px; }
.f-tend { flex: none; color: var(--ink-2); font-size: 0.7rem; letter-spacing: 0.06em; text-transform: uppercase; }
.f-aviso { flex: none; font-size: 0.64rem; padding: 0.16rem 0.5rem; border-radius: 999px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }
.m-sesgo { color: var(--warn); background: #f7efd9; }
.m-eng { color: var(--false); background: #fbeae8; }
.m-desinfo { color: #fff; background: var(--false); box-shadow: 0 2px 8px -3px rgba(194, 58, 44, 0.6); }
.fuente-rel { flex: none; color: var(--muted); font-size: 0.74rem; }
.fuente-rel.si { color: var(--true); }
.f-toggle { flex: none; appearance: none; border: 0; background: none; cursor: pointer; color: var(--muted); font-size: 0.9rem; padding: 0 0.2rem; transition: transform 0.15s ease; }
.f-toggle:hover { color: var(--faro); }
.f-toggle[aria-expanded="true"] { transform: rotate(180deg); }
.f-toggle:focus-visible { outline: 2px solid var(--faro); outline-offset: 1px; border-radius: 4px; }
.f-extracto { margin: 0 0 0.7rem 2.45rem; padding: 0.55rem 0.75rem; border-left: 2px solid var(--faro); font-family: var(--serif); font-style: italic; font-size: 0.9rem; color: var(--ink-2); white-space: pre-wrap; }
.f-abrir { display: inline-block; margin-left: 0.5rem; font-family: var(--mono); font-style: normal; font-size: 0.72rem; color: var(--faro); }
```

y en la media query de 600px añadir:

```css
  .f-linea { row-gap: 0.15rem; }
  .fuente-medio { min-width: 55%; }
  .f-extracto { margin-left: 0.5rem; }
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: sin errores (si `TEND_CLASE` se referenciara aún en algún sitio, TypeScript lo delata: quitar esa referencia).

- [ ] **Step 3: Visual check**

Pregunta real: ficha con filete grueso arriba, filas escaneables, tendencia como texto abreviado, "✓ respalda" en verde, avisos solo en fuentes problemáticas, ⌄ expande el extracto con "abrir ↗", y las fuentes no citadas (si las hay) atenuadas al final. En móvil las filas envuelven sin romperse.

- [ ] **Step 4: Commit**

```bash
git add frontend/src frontend/dist
git commit -m "feat(web): ficha editorial de fuentes — solo se anuncia lo anómalo"
```

---

### Task 15: verificación final y documentación

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: suite completa verde, build final commiteado, README al día.

- [ ] **Step 1: Suite completa**

Run: `.venv/bin/python -m pytest tests/ -q && node tests/test_citas.mjs`
Expected: todo PASS + `ok`.

- [ ] **Step 2: Build final y prueba end-to-end**

Run: `cd frontend && npm run build && cd .. && .venv/bin/uvicorn verificador.server:app`
Con una pregunta real verificar el flujo completo: traza en vivo → prosa en streaming → banda de veredicto + titular + confianza calculada → ficha de fuentes con extractos. Verificar también una consulta no verificable ("¿te gusta el fútbol?") — sin confianza, sin fuentes, sin banda rara.

- [ ] **Step 3: Actualizar README**

En la sección "Interfaz web (Faro)", reemplazar la frase «Eliges rigor (rápido / a fondo), largo y detalle desde la propia página.» por:

```
Eliges el modo desde el propio composer (Esencial / Normal / A fondo) y la
respuesta llega en streaming: primero la traza de validación, luego la prosa
palabra a palabra y al final el veredicto con su confianza —calculada a partir
de las fuentes reales que coinciden, no autodeclarada— y la ficha de fuentes
contrastadas con su extracto.
```

- [ ] **Step 4: Commit**

```bash
git add README.md frontend/dist
git commit -m "docs: README al día con presets, streaming y confianza calculada"
```
