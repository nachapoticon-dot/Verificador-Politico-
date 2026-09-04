# Faro fases 1-2: el suelo y el contrato — plan de implementación

> **Para agentes ejecutores:** SUB-SKILL OBLIGATORIA: usa
> superpowers:subagent-driven-development (recomendada) o
> superpowers:executing-plans para implementar tarea a tarea. Los pasos usan
> casillas (`- [ ]`) para seguimiento.

**Objetivo:** que Faro deje de rechazar preguntas legítimas, deje de construir
solidez sobre muros anti-bot y deje de borrar respuestas ya escritas.

**Arquitectura:** dos bloques. El suelo (tareas 1-5) son arreglos independientes
sobre el código actual, sin cambiar contratos. El contrato (tareas 6-10) separa
`tipo` de `veredicto`, sustituye `confianza` por `solidez` con dos curvas y
convierte la degradación destructiva en degradación informativa.

**Stack:** Python 3.14 (FastAPI, pytest, httpx, trafilatura, Playwright),
TypeScript/React 
(Vite, oxlint). Modelo `deepseek-v4-flash` vía SDK de OpenAI.

**Diseño de referencia:**
`docs/superpowers/specs/2026-07-26-faro-siguiente-nivel-design.md`

## Restricciones globales

- **Todo en español**: código, comentarios, docstrings, nombres de variables,
  mensajes de commit. El dominio es la política hispanohablante.
- **Las pruebas no tocan la red.** Si una prueba necesita internet está mal
  planteada: mockea. Lo que exija API real va a `scripts/humo.py`.
- **`veredicto.py` no puede lanzar nunca.** Es el último paso antes del usuario:
  degrada campo a campo, la prosa siempre sobrevive.
- **Comando de pruebas:** `.venv/bin/python -m pytest -q`. Nunca
  `.venv/bin/pytest` (shebang roto).
- **Comentarios explican el porqué**, no el qué.
- **Commits** en imperativo con prefijo (`fix:`, `feat:`, `refactor:`).
- **Estado de partida:** `104 passed, 1 xfailed`. Cualquier tarea que lo empeore
  está incompleta.
- El contenido web pasa siempre por `_contenido_no_confiable()` antes de llegar
  al modelo.

## Estructura de ficheros

| Fichero | Responsabilidad | Tareas |
|---|---|---|
| `verificador/search.py` | Detección de muros; guardia SSRF inyectable | 1, 5 |
| `verificador/data/fuentes.json` | Alta de fuentes institucionales | 2 |
| `verificador/veredicto.py` | `tipo`, `solidez`, aviso no destructivo | 2, 7, 8, 9 |
| `verificador/prompts.py` | Defaults de `largo`; sellos y clasificación | 3, 6 |
| `verificador/agent.py` | Default de `largo`; despacho robusto de tools | 3, 4 |
| `verificador/server.py` | Default de `largo` | 3 |
| `frontend/src/lib/types.ts` | Contrato TS: `tipo`, `solidez`, `aviso` | 10 |
| `frontend/src/lib/maps.ts` | Sellos por tipo | 10 |
| `frontend/src/components/Answer.tsx` | Banda de aviso, medidor de solidez | 10 |

---

# BLOQUE 1 — EL SUELO

### Tarea 1: Un muro anti-bot deja de contar como lectura

**Ficheros:**
- Modificar: `verificador/search.py` (añadir `_es_muro`; usarla en
  `leer_pagina`, líneas 420-442)
- Test: `tests/test_lectura.py`

**Interfaces:**
- Produce: `search._es_muro(texto: str) -> bool`

**Contexto:** verificado en una corrida real — `banrep.gov.co` devolvió su
página de CAPTCHA, trafilatura extrajo ese texto, `leer_pagina` devolvió
`ok=True` y el muro acabó siendo la única fuente que sumó solidez.

El umbral de longitud importa: un artículo largo que *hable* de captchas no es
un muro. Solo lo es un texto corto que además contenga un marcador.

- [ ] **Paso 1: escribir los tests que fallan**

```python
# tests/test_lectura.py — añadir al final

def test_es_muro_detecta_captcha_corto():
    texto = ("pero su actividad y comportamiento nos hace pensar que usted es "
             "un Bot. Por favor resuelva este CAPTCHA para que se desbloquee "
             "el sitio.")
    assert search._es_muro(texto) is True


def test_es_muro_ignora_articulo_largo_que_menciona_captcha():
    """Un artículo sobre captchas no es un muro: lo corto es la señal."""
    texto = "Los captchas cumplen 25 años. " + ("Texto de relleno. " * 200)
    assert search._es_muro(texto) is False


def test_es_muro_detecta_paywall_y_cloudflare():
    assert search._es_muro("Artículo solo para suscriptores. Suscríbete para seguir leyendo.") is True
    assert search._es_muro("Checking your browser before accessing the site.") is True


def test_es_muro_no_marca_texto_normal_corto():
    assert search._es_muro("El Banco de la República es el banco central.") is False


def test_leer_pagina_rechaza_un_muro(monkeypatch):
    """Un muro no es evidencia: ok=False y no se cachea."""
    monkeypatch.setattr(
        search, "_leer_rapido",
        lambda url: "Por favor resuelva este CAPTCHA para continuar.",
    )
    monkeypatch.setattr(search, "_leer_navegador", lambda url: None)
    out = search.leer_pagina("https://banrep.gov.co/es/el-banco")
    assert out.ok is False
    assert "bloque" in out.texto.lower() or "muro" in out.texto.lower()
    assert search._cache_get("pagina:" + normalizar_url("https://banrep.gov.co/es/el-banco")) is None
```

Añade el import que hace falta al principio del fichero:

```python
from verificador.urls import normalizar_url
```

- [ ] **Paso 2: verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_lectura.py -q -k "muro"`
Esperado: FAIL, `AttributeError: module 'verificador.search' has no attribute '_es_muro'`

- [ ] **Paso 3: implementar**

En `verificador/search.py`, justo antes de `leer_pagina`:

```python
# Marcadores de "no estás leyendo el artículo, estás leyendo al portero".
# Se comprueban sobre texto ya extraído y en minúsculas.
_MARCAS_MURO = (
    "captcha",
    "verifica que eres humano",
    "verify you are human",
    "checking your browser",
    "cloudflare",
    "habilita javascript",
    "enable javascript",
    "acceso denegado",
    "access denied",
    "403 forbidden",
    "suscríbete para seguir leyendo",
    "solo para suscriptores",
    "contenido exclusivo para suscriptores",
)
# Un artículo largo que MENCIONE un captcha no es un muro. La señal es que el
# texto sea corto: los porteros no tienen cuerpo.
_TOPE_MURO = 1500


def _es_muro(texto: str) -> bool:
    """¿Lo extraído es un muro anti-bot o de pago, y no el contenido?"""
    if not texto:
        return False
    if len(texto) > _TOPE_MURO:
        return False
    bajo = texto.lower()
    return any(marca in bajo for marca in _MARCAS_MURO)
```

Y dentro de `leer_pagina`, sustituye el bloque que va desde
`texto = _leer_rapido(url) or _leer_navegador(url)` hasta el `if len(texto) > max_chars:`
por:

```python
    texto = _leer_rapido(url) or _leer_navegador(url)
    if not texto:
        return Lectura(f"[No pude abrir ni extraer texto de {url}.]", False)
    if _es_muro(texto):
        # Nunca se cachea ni se marca ok: si contara como lectura, un portero
        # alimentaría la solidez como si fuera evidencia. Ya pasó.
        return Lectura(
            f"[{url}: la página respondió con un muro anti-bot o de pago, "
            f"no con su contenido.]",
            False,
        )
    if len(texto) > max_chars:
```

- [ ] **Paso 4: verificar que pasan**

Run: `.venv/bin/python -m pytest tests/test_lectura.py -q`
Esperado: PASS (el `xfail` de afinidad sigue como `xfailed`)

- [ ] **Paso 5: suite completa y commit**

Run: `.venv/bin/python -m pytest -q` → esperado `109 passed, 1 xfailed`

```bash
git add verificador/search.py tests/test_lectura.py
git commit -m "fix: un muro anti-bot deja de contar como lectura

Verificado en una corrida real: banrep.gov.co devolvió su página de
CAPTCHA, trafilatura extrajo ese texto y leer_pagina lo dio por bueno.
El portero acabó siendo la única fuente que sumaba solidez."
```

---

### Tarea 2: Fuentes institucionales en el registro, y sin tope

**Ficheros:**
- Modificar: `verificador/data/fuentes.json`
- Modificar: `verificador/veredicto.py` (`aplicar_registro`, líneas 118-129;
  `calcular_confianza`, líneas 185-187)
- Test: `tests/test_fuentes.py`, `tests/test_veredicto.py`

**Interfaces:**
- Produce: cada fuente del meta gana `tipo_fuente: str | None` cuando su dominio
  está curado.

**Contexto:** el registro tiene 33 dominios y **ninguno institucional**. Como
`veredicto.py:186-187` capa a 0.6 la credibilidad de todo lo no curado, Faro
desconfía del Banco de la República más que de un periódico.

- [ ] **Paso 1: escribir los tests que fallan**

```python
# tests/test_fuentes.py — añadir al final
from verificador import fuentes


def test_registro_incluye_fuentes_institucionales():
    for url in (
        "https://www.banrep.gov.co/es/el-banco",
        "https://www.registraduria.gov.co/",
        "https://www.boe.es/diario_boe/",
        "https://www.dane.gov.co/",
        "https://www.ine.es/",
    ):
        ficha = fuentes.clasificar(url)
        assert ficha is not None, f"{url} debería estar registrada"
        assert ficha.tipo == "primaria_oficial"
        assert ficha.credibilidad == "alta"
```

```python
# tests/test_veredicto.py — añadir al final
def test_aplicar_registro_expone_el_tipo_de_fuente():
    meta = {"fuentes": [{"n": 1, "url": "https://www.banrep.gov.co/es/el-banco"}]}
    aplicar_registro(meta)
    assert meta["fuentes"][0]["tipo_fuente"] == "primaria_oficial"


def test_primaria_oficial_no_sufre_el_tope_de_no_curada():
    """El tope de 0.6 castiga lo no revisado; una institucional no lo necesita.

    Ojo: `_evidencia` pone `registro_curado: True` por defecto, y con eso el
    tope no se aplica a NADIE y el test pasaría sin probar nada. Hay que
    forzarlo a False en los dos lados para que la comparación signifique algo.
    """
    oficial = _evidencia(1, "banrep.gov.co", registro_curado=False,
                         tipo_fuente="primaria_oficial")
    medio = _evidencia(1, "cualquiermedio.com", registro_curado=False,
                       tipo_fuente="medio")
    curada = _evidencia(1, "reuters.com", registro_curado=True)
    assert calcular_confianza({"fuentes": [oficial]}) > calcular_confianza({"fuentes": [medio]})
    # Y pesa exactamente igual que una curada de credibilidad alta.
    assert calcular_confianza({"fuentes": [oficial]}) == calcular_confianza({"fuentes": [curada]})
```

- [ ] **Paso 2: verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_fuentes.py tests/test_veredicto.py -q -k "institucional or tipo_de_fuente or primaria"`
Esperado: FAIL (`assert None is not None` y `KeyError: 'tipo_fuente'`)

- [ ] **Paso 3: dar de alta las fuentes**

Añade a `verificador/data/fuentes.json` estas entradas (respeta el formato
existente: `credibilidad`, `tendencia`, `tipo`):

```json
  "banrep.gov.co":        {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "dane.gov.co":          {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "registraduria.gov.co": {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "corteconstitucional.gov.co": {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "senado.gov.co":        {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "camara.gov.co":        {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "boe.es":               {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "ine.es":               {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "congreso.es":          {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "senado.es":            {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "indec.gob.ar":         {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "argentina.gob.ar":     {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "inegi.org.mx":         {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "banxico.org.mx":       {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "ine.mx":               {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "bcentral.cl":          {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "ine.gob.cl":           {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "bcrp.gob.pe":          {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "inei.gob.pe":          {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "dof.gob.mx":           {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "scjn.gob.mx":          {"credibilidad": "alta", "tendencia": "centro", "tipo": "primaria_oficial"},
  "ec.europa.eu":         {"credibilidad": "alta", "tendencia": "internacional", "tipo": "primaria_oficial"},
  "europarl.europa.eu":   {"credibilidad": "alta", "tendencia": "internacional", "tipo": "primaria_oficial"},
  "eur-lex.europa.eu":    {"credibilidad": "alta", "tendencia": "internacional", "tipo": "primaria_oficial"},
  "un.org":               {"credibilidad": "alta", "tendencia": "internacional", "tipo": "primaria_oficial"},
  "worldbank.org":        {"credibilidad": "alta", "tendencia": "internacional", "tipo": "primaria_oficial"},
  "imf.org":              {"credibilidad": "alta", "tendencia": "internacional", "tipo": "primaria_oficial"}
```

Comprueba que el JSON sigue siendo válido:

```bash
.venv/bin/python -c "import json;d=json.load(open('verificador/data/fuentes.json'));print(len(d),'dominios')"
```

- [ ] **Paso 4: propagar el tipo y levantar el tope**

En `verificador/veredicto.py`, dentro de `aplicar_registro`, añade la línea del
tipo junto a las otras tres asignaciones:

```python
        f["registro_curado"] = True
        f["credibilidad"] = ficha.credibilidad
        f["manipulacion"] = ficha.manipulacion
        f["tendencia"] = ficha.tendencia
        f["tipo_fuente"] = ficha.tipo
```

Y en `calcular_confianza`, sustituye:

```python
        if f.get("registro_curado") is not True:
            cred = min(cred, 0.6)
```

por:

```python
        # El tope castiga a los dominios que nadie ha revisado. Una fuente
        # primaria oficial no necesita revisión editorial: es la fuente.
        if f.get("registro_curado") is not True and f.get("tipo_fuente") != "primaria_oficial":
            cred = min(cred, 0.6)
```

- [ ] **Paso 5: verificar y commitear**

Run: `.venv/bin/python -m pytest -q` → esperado `112 passed, 1 xfailed`

```bash
git add verificador/data/fuentes.json verificador/veredicto.py tests/
git commit -m "feat: fuentes institucionales en el registro, sin tope de credibilidad

El registro tenía 33 dominios y ninguno institucional, así que el tope de
las no curadas dejaba al Banco de la República por debajo de un periódico.
Una primaria oficial no necesita revisión editorial: es la fuente."
```

---

### Tarea 3: Un solo default de `largo`

**Ficheros:**
- Modificar: `verificador/prompts.py:263`, `verificador/agent.py:186`,
  `verificador/server.py:123`
- Test: `tests/test_prompt.py`

**Contexto:** hoy hay tres. Por HTTP omitiendo el campo sale `normal`
(`server.py:55`); mandando basura sale `corta` (`server.py:123`); el CLI y las
llamadas directas dan `corta` (`agent.py:186`, `prompts.py:263`). Se unifica en
`normal`, que es lo que ya envía el frontend.

- [ ] **Paso 1: escribir el test que falla**

```python
# tests/test_prompt.py — añadir al final
from verificador import agent as agent_mod
from verificador import server as server_mod
from verificador.prompts import instruccion_modo
import inspect


def test_todas_las_capas_comparten_el_mismo_default_de_largo():
    """Tres capas daban tres defaults distintos: normal, corta y corta."""
    por_defecto = inspect.signature(agent_mod.Verificador.preguntar).parameters["largo"].default
    pydantic = server_mod.VerificarEntrada().largo
    fallback = instruccion_modo("valor-invalido", "simple")
    assert por_defecto == "normal"
    assert pydantic == "normal"
    assert instruccion_modo("normal", "simple") == fallback
```

- [ ] **Paso 2: verificar que falla**

Run: `.venv/bin/python -m pytest tests/test_prompt.py -q -k "default_de_largo"`
Esperado: FAIL, `assert 'corta' == 'normal'`

- [ ] **Paso 3: implementar los tres cambios**

`verificador/prompts.py`, en `instruccion_modo`:

```python
    l = _MODO_LARGO.get(largo, _MODO_LARGO["normal"])
```

`verificador/agent.py`, en la firma de `preguntar`:

```python
        largo: str = "normal",
```

`verificador/server.py`, en `verificar`:

```python
    largo = largo if largo in ("corta", "normal", "detallada") else "normal"
```

Actualiza también el docstring de `instruccion_modo`, que dice
"cayendo al modo predeterminado (corta + simple)":

```python
    """Línea de modo que se antepone a cada consulta.

    Combina el eje de largo y el de detalle. Tolera valores fuera de
    vocabulario cayendo al modo predeterminado (normal + simple), el mismo
    en todas las capas.
    """
```

- [ ] **Paso 4: verificar y commitear**

Run: `.venv/bin/python -m pytest -q` → esperado `113 passed, 1 xfailed`

```bash
git add verificador/prompts.py verificador/agent.py verificador/server.py tests/test_prompt.py
git commit -m "fix: un solo default de largo en las tres capas

Omitir el campo por HTTP daba normal, mandar basura daba corta y el CLI
siempre corta. Ahora normal en todas."
```

---

### Tarea 4: El despacho de herramientas deja de reventar

**Ficheros:**
- Modificar: `verificador/agent.py:89-111` (`_ejecutar_tool`)
- Test: `tests/test_dispatch.py`

**Contexto:** `int(args.get("max_resultados", 6))` lanza `ValueError` si el
modelo manda `"seis"`, y `args.get` lanza `AttributeError` si `json.loads`
devolvió una lista en vez de un objeto. La excepción sube por `futuro.result()`
y el usuario ve "No se pudo completar la verificación".

- [ ] **Paso 1: escribir los tests que fallan**

```python
# tests/test_dispatch.py — añadir al final
def test_ejecutar_tool_tolera_max_resultados_no_numerico(monkeypatch):
    """El modelo puede mandar 'seis' en vez de 6; eso no puede tumbar la consulta."""
    from verificador import agent as agent_mod
    monkeypatch.setattr(agent_mod, "buscar_web", lambda **kw: [{"titulo": "x", "url": "https://a.com"}])
    v = _verificador_falso()
    out = v._ejecutar_tool("buscar_web", {"query": "x", "max_resultados": "seis"})
    assert out.ok is True


def test_ejecutar_tool_tolera_argumentos_que_no_son_objeto():
    """json.loads puede devolver una lista; args.get reventaría."""
    v = _verificador_falso()
    out = v._ejecutar_tool("buscar_web", ["query", "x"])
    assert out.ok is False
    assert "argumentos" in out.texto.lower()


def test_ejecutar_tool_tolera_argumentos_none():
    v = _verificador_falso()
    out = v._ejecutar_tool("leer_pagina", None)
    assert out.ok is False
```

Y añade el helper al principio del fichero, junto a lo que ya haya:

```python
def _verificador_falso():
    """Verificador con config de mentira: no llega a llamar a la API."""
    from verificador.agent import Verificador
    from verificador.config import Config
    return Verificador(config=Config(api_key="x", base_url="http://local",
                                     model="deepseek-v4-flash"))
```

- [ ] **Paso 2: verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_dispatch.py -q -k "tolera"`
Esperado: FAIL con `ValueError: invalid literal for int()` y `AttributeError: 'list' object has no attribute 'get'`

- [ ] **Paso 3: implementar**

En `verificador/agent.py`, sustituye el cuerpo entero de `_ejecutar_tool` por:

```python
    def _ejecutar_tool(self, nombre: str, args: dict,
                       country: str | None = None, rigor: str = "riguroso") -> Lectura:
        """Despacha una llamada de herramienta y devuelve ``Lectura(texto, ok)``.

        ``texto`` es lo que se le manda al modelo; ``ok`` decide el estado de la
        traza. Las herramientas de lectura ya devuelven ``Lectura``; las demás
        se envuelven aquí.

        El modelo puede mandar cualquier cosa como argumentos —una lista, un
        número donde va texto— y eso jamás debe tumbar la consulta entera: el
        error se le devuelve a él para que reintente.
        """
        if not isinstance(args, dict):
            return Lectura(
                f"[Argumentos inválidos para {nombre}: se esperaba un objeto JSON.]",
                False,
            )
        if nombre == "buscar_web":
            tope = 4 if rigor == "rapido" else 8
            try:
                pedido = int(args.get("max_resultados", 6))
            except (TypeError, ValueError, OverflowError):
                pedido = 6
            res = buscar_web(
                query=str(args.get("query", "")),
                max_resultados=max(1, min(pedido, tope)),
                pais=country,
            )
            ok = not (res and isinstance(res[0], dict) and "error" in res[0])
            return Lectura(json.dumps(res, ensure_ascii=False), ok)
        if nombre == "leer_pagina":
            return leer_pagina(url=str(args.get("url", "")))
        if nombre == "ver_video":
            return ver_video(url=str(args.get("url", "")))
        return Lectura(f"[Herramienta desconocida: {nombre}]", False)
```

- [ ] **Paso 4: verificar y commitear**

Run: `.venv/bin/python -m pytest -q` → esperado `116 passed, 1 xfailed`

```bash
git add verificador/agent.py tests/test_dispatch.py
git commit -m "fix: argumentos raros del modelo ya no tumban la consulta

int('seis') lanzaba ValueError y args.get sobre una lista AttributeError;
ambas subían por futuro.result() y el usuario veía 'no se pudo completar'.
Ahora el error vuelve al modelo para que reintente."
```

---

### Tarea 5: Guardia SSRF inyectable, y el test de afinidad vuelve a proteger

**Ficheros:**
- Modificar: `verificador/search.py` (call sites de `_url_publica` en
  `_leer_en_pagina`, `_leer_rapido`, `_leer_navegador`)
- Modificar: `tests/test_lectura.py` (quitar el `xfail`)

**Interfaces:**
- Produce: `search._guardia` — variable de módulo, por defecto `_url_publica`.
  Los tests la sustituyen con `monkeypatch.setattr(search, "_guardia", ...)`.

**Contexto:** el test usa `file://` y el guardia rechaza todo lo que no sea
http/s hacia IP global, así que `_leer_navegador` devuelve `None` sin llegar a
Playwright. Lleva sin cobertura desde entonces la afinidad de hilo, que fue un
bug real y caro. **No debilites `_url_publica`**: hazla sustituible solo en
pruebas.

- [ ] **Paso 1: quitar el xfail y ver el fallo real**

Borra el decorador `@pytest.mark.xfail(...)` completo de
`test_navegador_reutilizado_entre_hilos` (deja el `skipif`), y añade al test,
justo antes de crear los hilos:

```python
    monkeypatch.setattr(search, "_guardia", lambda url: True)
```

Cambia la firma a `def test_navegador_reutilizado_entre_hilos(tmp_path, monkeypatch):`

- [ ] **Paso 2: verificar que falla**

Run: `.venv/bin/python -m pytest tests/test_lectura.py -q -k "afinidad or navegador_reutilizado"`
Esperado: FAIL, `AttributeError: module 'verificador.search' has no attribute '_guardia'`

- [ ] **Paso 3: implementar el punto de inyección**

En `verificador/search.py`, justo después de la definición de `_url_publica`:

```python
# Punto de inyección para pruebas. En producción es siempre `_url_publica`; los
# tests herméticos lo sustituyen para poder servir desde file:// sin debilitar
# el guardia real, que es la defensa contra SSRF.
_guardia = _url_publica
```

Y cambia las **cuatro** llamadas internas de `_url_publica(...)` a `_guardia(...)`:

1. En `_leer_en_pagina`: `if not _guardia(url):`
2. En `_leer_en_pagina`, dentro de `filtrar`: `if _guardia(route.request.url):`
3. En `_leer_rapido`, dentro del bucle de redirecciones: `if not _guardia(actual):`
4. En `_leer_navegador`: `if not _guardia(url):`

**Importante:** no toques la definición de `_url_publica` ni ninguna llamada
desde fuera del módulo.

- [ ] **Paso 4: verificar que pasa**

Run: `.venv/bin/python -m pytest tests/test_lectura.py -q`
Esperado: PASS, **sin xfailed**

- [ ] **Paso 5: verificar que el guardia real sigue intacto**

```bash
.venv/bin/python -c "
from verificador import search
assert search._guardia is search._url_publica
assert search._url_publica('file:///tmp/x') is False
assert search._url_publica('http://127.0.0.1/x') is False
assert search._url_publica('http://169.254.169.254/latest/meta-data/') is False
print('guardia intacto ✓')
"
```

- [ ] **Paso 6: actualizar AGENTS.md y commitear**

En `AGENTS.md`, borra el párrafo entero de la sección "Estado conocido" (el que
empieza por `tests/test_lectura.py::test_navegador_reutilizado_entre_hilos
**falla, y es preexistente.**`) y sustitúyelo por:

```markdown
## Estado conocido

La suite pasa entera. Si `npm install` nunca se corrió en esta máquina,
`frontend/node_modules` no existe y `npm run check` falla por ahí, no por el
código.
```

En `.claude/skills/check/SKILL.md`, borra el párrafo que empieza por
`**Estado esperado: todo verde.**` y déjalo en:

```markdown
**Estado esperado: todo verde.**
```

Run: `.venv/bin/python -m pytest -q` → esperado `117 passed` y **cero xfailed**

```bash
git add verificador/search.py tests/test_lectura.py AGENTS.md .claude/skills/check/SKILL.md
git commit -m "fix: guardia SSRF inyectable; vuelve la cobertura de afinidad de hilo

El test usaba file:// y el guardia lo rechazaba antes de llegar a
Playwright, así que la afinidad de hilo —un bug real y caro— llevaba
tiempo sin protección. El guardia real no se toca: solo se hace
sustituible en pruebas."
```

---

# BLOQUE 2 — EL CONTRATO

### Tarea 6: El prompt emite `tipo` y deja de forzar un sello imposible

**Ficheros:**
- Modificar: `verificador/prompts.py` (`SYSTEM_PROMPT`, secciones
  "Antes de verificar" líneas 130-151, "Cómo respondes" líneas 196-198, y el
  "Pie técnico" líneas 217-243; `PROMPT_REPARACION` líneas 270-288)
- Test: `tests/test_prompt.py`

**Interfaces:**
- Produce: el bloque JSON de cierre gana `"tipo"` y pierde `informativo` y
  `no_verificable` de la lista de `veredicto`.

**Contexto:** `informativo` no está entre los seis sellos de la primera línea
obligatoria, así que el modelo estampa ❓ SIN EVIDENCIA en respuestas educativas
correctas. Dejará de ser un veredicto para ser un tipo.

- [ ] **Paso 1: escribir los tests que fallan**

```python
# tests/test_prompt.py — añadir al final
from verificador.prompts import SYSTEM_PROMPT, PROMPT_REPARACION


def test_prompt_pide_el_campo_tipo():
    assert '"tipo"' in SYSTEM_PROMPT
    assert "afirmacion|pregunta|mecanismo" in SYSTEM_PROMPT
    assert '"tipo"' in PROMPT_REPARACION


def test_informativo_ya_no_es_un_veredicto():
    """Era un tipo disfrazado de veredicto: por eso no tenía sello."""
    assert "informativo" not in SYSTEM_PROMPT
    assert "informativo" not in PROMPT_REPARACION


def test_solo_las_afirmaciones_llevan_sello():
    assert "Solo si `tipo` es `afirmacion`" in SYSTEM_PROMPT
```

- [ ] **Paso 2: verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_prompt.py -q -k "tipo or informativo or sello"`
Esperado: FAIL

- [ ] **Paso 3: reescribir la sección de clasificación**

En `verificador/prompts.py`, sustituye la sección
`# Antes de verificar: ¿qué te están pidiendo?` entera (desde ese encabezado
hasta la línea en blanco antes de `# Pondera por credibilidad`) por:

```
# Antes de nada: ¿qué te están pidiendo?

Clasifica la consulta en uno de estos tres TIPOS. El tipo decide si hay sello \
o no; no lo decide la cantidad de evidencia que encuentres.

- `afirmacion` — algo que puede ser verdadero o falso ("X eliminó el Banco \
Central"). Investígala y emite veredicto con su sello.
- `pregunta` — te piden un dato o un hecho, sin afirmación que contrastar \
("¿quién preside Colombia ahora?"). Respóndela con búsqueda y citas, pero NO \
la marques como verdadera ni falsa: no hay nada que juzgar.
- `mecanismo` — te piden entender cómo funciona algo público: una ley, una \
institución, un procedimiento, una cifra ("¿cómo funciona el sistema \
electoral?", "explícame la reforma pensional", "¿qué hace un banco central?"). \
Explícalo bien, con fuentes, y prioriza que la persona SALGA ENTENDIENDO el \
mecanismo, no solo con el dato suelto. Tampoco lleva sello.

Tu materia son los asuntos públicos: política, economía, instituciones, leyes, \
elecciones, presupuesto y datos oficiales. Cualquier forma de preguntar sobre \
eso es bienvenida. NO conviertas una pregunta en una afirmación para poder \
estampar un sello, y NO rechaces una consulta legítima por venir en forma de \
pregunta.

Solo declina cuando de verdad no haya nada que verificar ni que explicar: \
opiniones puras ("¿qué te parece X?"), gustos o identidad tuyos, y encargos \
creativos ajenos a tu materia ("escríbeme un poema"). Ahí responde en UNA \
frase, amable, recordando con buen humor qué eres, y NO pongas sello. Ante la \
duda, NO declines: responde.
```

- [ ] **Paso 4: arreglar la estructura de respuesta**

Sustituye la "Estructura mínima" (líneas ~196-198) por:

```
Estructura mínima:
1) Solo si `tipo` es `afirmacion`, la primera línea es el veredicto con su \
   etiqueta (✅ VERDADERO, ❌ FALSO, ⚠️ ENGAÑOSO, 🔀 SACADO DE CONTEXTO, \
   🔮 PREDICCIÓN, ❓ SIN EVIDENCIA). Para `pregunta` y `mecanismo` NO pongas \
   ninguna etiqueta: entra directo en la respuesta.
2) Después, una explicación breve y directa. Cuando uses un dato, cítalo inline \
   con un número entre corchetes: "...el paro bajó al 7% [1] aunque otro informe \
   lo matiza [2]". Numera las citas por orden de aparición, empezando en [1].
```

- [ ] **Paso 5: arreglar el pie técnico**

En el bloque JSON del "Pie técnico", sustituye la línea del veredicto por estas
dos:

```
  "tipo": "afirmacion|pregunta|mecanismo",
  "veredicto": "verdadero|falso|enganoso|fuera_de_contexto|prediccion|sin_evidencia",
```

Y sustituye el párrafo que explica `confianza` (el que empieza por
"`n` numera la fuente") por:

```
`n` numera la fuente y DEBE coincidir con la cita `[n]` del texto; el orden sigue \
el de aparición de las citas. `coincide` indica si esa fuente respalda lo que \
dices. Incluye en `fuentes` las que realmente consultaste.

`veredicto` SOLO va cuando `tipo` es `afirmacion`; en los otros dos tipos, \
omítelo. `confianza` es 0-100 y es orientativa: el sistema recalcula la solidez \
real a partir de las fuentes que de verdad se abrieron y citaron.
```

Haz el mismo cambio de campos en `PROMPT_REPARACION` (el bloque JSON y la lista
de veredictos).

- [ ] **Paso 6: verificar y commitear**

Run: `.venv/bin/python -m pytest -q` → esperado `120 passed`

Un test viejo falla: `test_prompt_clasifica_pregunta_y_pondera_credibilidad`
(`tests/test_prompt.py:4-8`) asserta `"informativo" in p`. Sustituye esa línea y
su comentario por:

```python
    # las preguntas sin afirmación son un TIPO, no un veredicto:
    assert "pregunta" in p
    assert "mecanismo" in p
```

```bash
git add verificador/prompts.py tests/test_prompt.py
git commit -m "feat: el prompt clasifica por tipo y solo las afirmaciones llevan sello

informativo no estaba entre los seis sellos de la primera línea obligatoria,
así que el modelo estampaba SIN EVIDENCIA en respuestas educativas correctas.
Nunca fue un veredicto: era un tipo disfrazado."
```

---

### Tarea 7: `tipo` separado de `veredicto` en el contrato

**Ficheros:**
- Modificar: `verificador/veredicto.py` (`VEREDICTOS` línea 26, `validar_meta`
  líneas 50-103)
- Test: `tests/test_veredicto.py`

**Interfaces:**
- Produce: `veredicto.TIPOS = {"afirmacion", "pregunta", "mecanismo"}`
- Produce: `validar_meta` devuelve `out["tipo"]` (por defecto `"afirmacion"`) y
  solo incluye `out["veredicto"]` cuando `tipo == "afirmacion"`.

- [ ] **Paso 1: escribir los tests que fallan**

```python
# tests/test_veredicto.py — añadir al final
def test_validar_meta_acepta_tipo():
    m = validar_meta({"tipo": "mecanismo", "fuentes": []})
    assert m["tipo"] == "mecanismo"
    assert "veredicto" not in m


def test_tipo_invalido_cae_a_afirmacion():
    assert validar_meta({"tipo": "cualquier-cosa", "fuentes": []})["tipo"] == "afirmacion"
    assert validar_meta({"fuentes": []})["tipo"] == "afirmacion"


def test_una_pregunta_no_arrastra_veredicto():
    """Aunque el modelo mande un veredicto en una pregunta, se descarta."""
    m = validar_meta({"tipo": "pregunta", "veredicto": "verdadero", "fuentes": []})
    assert m["tipo"] == "pregunta"
    assert "veredicto" not in m


def test_afirmacion_conserva_su_veredicto():
    m = validar_meta({"tipo": "afirmacion", "veredicto": "falso", "fuentes": []})
    assert m["veredicto"] == "falso"


def test_informativo_ya_no_es_veredicto_valido():
    m = validar_meta({"tipo": "afirmacion", "veredicto": "informativo", "fuentes": []})
    assert "veredicto" not in m
```

- [ ] **Paso 2: verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q -k "tipo or informativo_ya"`
Esperado: FAIL, `KeyError: 'tipo'`

- [ ] **Paso 3: implementar**

En `verificador/veredicto.py`, sustituye la constante `VEREDICTOS`:

```python
# `informativo` y `no_verificable` ya no viven aquí: el primero era un tipo
# disfrazado de veredicto (y por eso nunca tuvo sello) y el segundo es un
# rechazo que se resuelve antes de investigar.
VEREDICTOS = {
    "verdadero", "falso", "enganoso", "fuera_de_contexto",
    "prediccion", "sin_evidencia",
}
TIPOS = {"afirmacion", "pregunta", "mecanismo"}
```

Y dentro de `validar_meta`, sustituye el bloque del veredicto (las cuatro
líneas que empiezan por `v = meta.get("veredicto")`) por:

```python
    t = meta.get("tipo")
    out["tipo"] = t.lower().strip() if isinstance(t, str) and t.lower().strip() in TIPOS else "afirmacion"
    # El sello solo existe para afirmaciones. Si el modelo manda uno en una
    # pregunta, se descarta: no hay nada que juzgar.
    if out["tipo"] == "afirmacion":
        v = meta.get("veredicto")
        if isinstance(v, str) and v.lower().strip() in VEREDICTOS:
            out["veredicto"] = v.lower().strip()
```

- [ ] **Paso 4: reparar los tests viejos**

Dos sitios exactos de `tests/test_veredicto.py`:

1. **Línea 274-276**, `test_no_verificable_no_se_fuerza_a_sin_evidencia` →
   **bórralo entero**. Protegía la puerta que desaparece en la tarea 9, y
   `no_verificable` ya no es un veredicto válido.

2. **Línea 262**, dentro del fixture de reparación, el literal
   `'```json\n{"veredicto": "informativo", "fuentes": []}\n```'` → cámbialo a:

```python
        return '```json\n{"tipo": "pregunta", "fuentes": []}\n```'
```

Ajusta también el assert de ese test para que compruebe
`p.meta["tipo"] == "pregunta"` en vez del veredicto.

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`

- [ ] **Paso 5: commitear**

```bash
git add verificador/veredicto.py tests/test_veredicto.py
git commit -m "feat: separa tipo de veredicto en el contrato

Qué te preguntaron y qué se concluyó eran el mismo campo, y de ahí salía
que una pregunta bien respondida tuviera que llevar sello de veredicto."
```

---

### Tarea 8: `solidez` con dos curvas según el tipo

**Ficheros:**
- Modificar: `verificador/veredicto.py` (`calcular_confianza` líneas 156-206,
  `procesar` líneas 276-278)
- Test: `tests/test_veredicto.py`

**Interfaces:**
- Produce: `veredicto.calcular_solidez(meta: dict) -> int`. `calcular_confianza`
  desaparece.
- Produce: `meta["solidez"]` sustituye a `meta["confianza"]`;
  `meta["solidez_modelo"]` sustituye a `meta["confianza_modelo"]`.

**Contexto:** para una afirmación en disputa, lo que da solidez son
confirmaciones independientes con bono por contraste. Para una pregunta o un
mecanismo eso es absurdo: nadie necesita que un medio de izquierda y otro de
derecha coincidan en qué hace un banco central. Ahí manda la mejor fuente.

**Criterio de aceptación del diseño:** el caso del Banco de la República, leído
de verdad, no puede dar 33.

- [ ] **Paso 1: escribir los tests que fallan**

```python
# tests/test_veredicto.py — añadir al final
from verificador.veredicto import calcular_solidez


def test_mecanismo_con_una_primaria_oficial_da_solidez_alta():
    """El criterio de aceptación del diseño: esto ya no puede dar 33."""
    meta = {"tipo": "mecanismo", "fuentes": [
        _evidencia(1, "banrep.gov.co", tipo_fuente="primaria_oficial", tendencia="centro"),
    ]}
    assert calcular_solidez(meta) >= 75


def test_afirmacion_con_una_sola_fuente_no_da_solidez_alta():
    """En disputa, una sola fuente nunca basta, por buena que sea."""
    meta = {"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "banrep.gov.co", tipo_fuente="primaria_oficial"),
    ]}
    assert calcular_solidez(meta) < 60


def test_mecanismo_solo_con_wikipedia_no_da_solidez_alta():
    meta = {"tipo": "mecanismo", "fuentes": [
        _evidencia(1, "wikipedia.org", credibilidad="baja", tipo_fuente="enciclopedia_editable"),
    ]}
    assert calcular_solidez(meta) < 50


def test_afirmacion_contrastada_sigue_subiendo():
    meta = {"tipo": "afirmacion", "fuentes": [
        _evidencia(1, "a.com", tendencia="izquierda"),
        _evidencia(2, "b.com", tendencia="derecha"),
        _evidencia(3, "c.com", tendencia="verificador"),
    ]}
    assert 85 <= calcular_solidez(meta) < 100


def test_solidez_sin_fuentes_es_cero_en_los_tres_tipos():
    for t in ("afirmacion", "pregunta", "mecanismo"):
        assert calcular_solidez({"tipo": t, "fuentes": []}) == 0


def test_un_muro_no_leido_no_da_solidez():
    meta = {"tipo": "mecanismo", "fuentes": [
        _evidencia(1, "banrep.gov.co", tipo_fuente="primaria_oficial", extracto=""),
    ]}
    assert calcular_solidez(meta) == 0
```

- [ ] **Paso 2: verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q -k "solidez or mecanismo"`
Esperado: FAIL, `ImportError: cannot import name 'calcular_solidez'`

- [ ] **Paso 3: implementar**

En `verificador/veredicto.py`, renombra `calcular_confianza` a
`calcular_solidez` y sustituye su cuerpo entero por:

```python
def _fuentes_utiles(meta: dict) -> list[dict]:
    """Fuentes que cuentan: abiertas, citadas, con URL comprobable y dominio único.

    La solidez se deriva del ledger de la consulta, no de lo que el modelo diga
    de sí mismo. Una fuente que no se abrió no es evidencia.
    """
    utiles: list[dict] = []
    dominios: set[str] = set()
    for f in meta.get("fuentes") or []:
        dominio = _dominio_fuente(f.get("url") or "")
        if not dominio or dominio in dominios or f.get("citada") is not True:
            continue
        if not isinstance(f.get("extracto"), str) or not f["extracto"].strip():
            continue
        dominios.add(dominio)
        utiles.append(f)
    return utiles


def _peso_credibilidad(f: dict) -> float:
    """Peso 0-1 de una fuente, ya descontada su deshonestidad."""
    if (f.get("manipulacion") or "ninguna").lower() in ("enganosa", "desinformadora"):
        return 0.0
    cred = _PESO_CRED.get((f.get("credibilidad") or "").lower(), 0.25)
    # El tope castiga a los dominios que nadie ha revisado. Una fuente primaria
    # oficial no necesita revisión editorial: es la fuente.
    if f.get("registro_curado") is not True and f.get("tipo_fuente") != "primaria_oficial":
        cred = min(cred, 0.6)
    return cred


def _solidez_afirmacion(utiles: list[dict]) -> int:
    """Curva para lo que está en disputa: cuentan confirmaciones independientes.

    Una sola fuente nunca basta, por buena que sea; que fuentes que trabajan por
    separado —y mejor de tendencias opuestas— lleguen al mismo dato, sí.
    """
    peso = penal = contrapeso = 0.0
    tendencias: set[str] = set()
    for f in utiles:
        if (f.get("manipulacion") or "ninguna").lower() in ("enganosa", "desinformadora"):
            if f.get("coincide"):
                penal += 0.15
            continue
        cred = _peso_credibilidad(f)
        if not f.get("coincide"):
            contrapeso += cred * 0.12
            continue
        peso += cred
        t = (f.get("tendencia") or "").lower()
        if t:
            tendencias.add(t)
    contraste = bool(
        (tendencias & _IZQ and tendencias & _DER)
        or ("verificador" in tendencias and len(tendencias) > 1)
    )
    if contraste:
        peso *= 1.25
    conf = 95.0 * (1.0 - math.exp(-0.7 * peso))
    conf *= max(0.0, 1.0 - penal - contrapeso)
    return int(round(conf))


def _solidez_explicativa(utiles: list[dict]) -> int:
    """Curva para preguntas y mecanismos: manda la MEJOR fuente disponible.

    Aquí no hay nada en disputa, así que el contraste editorial no aporta: nadie
    necesita que un medio de izquierda y otro de derecha coincidan en qué hace
    un banco central. Lo que importa es si lo dice quien tiene autoridad.
    """
    respaldan = [f for f in utiles if f.get("coincide") is not False]
    if not respaldan:
        return 0
    mejor = max(_peso_credibilidad(f) for f in respaldan)
    if any(f.get("tipo_fuente") == "primaria_oficial" and _peso_credibilidad(f) > 0
           for f in respaldan):
        base = 88.0
    else:
        base = 70.0 * mejor
    # Corroborar suma, pero poco: no es lo que decide.
    extra = min(2, len(respaldan) - 1) * 4.0
    return int(round(min(95.0, base + extra)))


def calcular_solidez(meta: dict) -> int:
    """Solidez 0-100 calculada de las fuentes reales, no autodeclarada.

    Dos curvas, porque "qué tan respaldado está esto" significa cosas distintas
    según lo que te hayan preguntado.
    """
    utiles = _fuentes_utiles(meta)
    if not utiles:
        return 0
    if meta.get("tipo", "afirmacion") == "afirmacion":
        return _solidez_afirmacion(utiles)
    return _solidez_explicativa(utiles)
```

En `procesar`, sustituye las dos líneas de confianza por:

```python
    meta["solidez_modelo"] = meta.pop("confianza", 0)
    meta["solidez"] = calcular_solidez(meta)
```

- [ ] **Paso 4: adaptar los tests viejos de confianza**

Estos **ocho** tests llaman `calcular_confianza` y fallarán por el nombre:

```
test_confianza_cero_sin_fuentes_que_coincidan
test_confianza_una_fuente_alta_es_media
test_confianza_contraste_izq_der_sube
test_confianza_tres_buenas_contrastadas_ronda_90_y_nunca_100
test_fuentes_deshonestas_no_suman_y_penalizan
test_sin_tendencia_no_cuenta_como_contraste
test_confianza_ignora_no_leidas_no_citadas_y_dominios_duplicados
test_evidencia_que_matiza_reduce_solidez
```

En los ocho: cambia la llamada a `calcular_solidez` y añade `"tipo": "afirmacion"`
al dict del meta. Es la curva que ya estaban probando y su comportamiento no
cambia, así que los rangos siguen valiendo. Actualiza también el import de la
línea 2 del fichero.

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q`

- [ ] **Paso 5: commitear**

```bash
git add verificador/veredicto.py tests/test_veredicto.py
git commit -m "feat: solidez con dos curvas según el tipo de consulta

Una sola curva trataba toda la evidencia como confirmaciones independientes.
Eso es correcto para lo que está en disputa y absurdo para un mecanismo:
nadie necesita que izquierda y derecha coincidan en qué hace un banco central."
```

---

### Tarea 9: La prosa no se borra nunca

**Ficheros:**
- Modificar: `verificador/veredicto.py:279-287` (la puerta destructiva)
- Test: `tests/test_veredicto.py`, `tests/test_traza.py`

**Interfaces:**
- Produce: `meta["aviso"] = {"codigo": str, "texto": str}` cuando la evidencia
  es floja. Códigos: `"nada_encontrado"`, `"sin_abrir"`.

**Contexto:** hoy, si no se abrió ninguna página, se descarta la prosa que el
modelo ya escribió —y que el streaming ya envió al navegador— y se sustituye por
un enlatado que pide "reformular la afirmación". El usuario ve borrarse una
buena respuesta delante de él.

- [ ] **Paso 1: escribir los tests que fallan**

```python
# tests/test_veredicto.py — añadir al final
def test_la_prosa_sobrevive_sin_evidencia_abierta():
    """Lo que el modelo escribió no se destruye jamás: se anota."""
    texto = ('El Banco de la República es el banco central [1].\n\n```json\n'
             '{"tipo": "mecanismo", "confianza": 90, "fuentes": '
             '[{"n": 1, "url": "https://banrep.gov.co/x", "coincide": true}]}\n```')
    p = procesar(texto)
    assert "banco central" in p.prosa
    assert "reformul" not in p.prosa.lower()
    assert p.meta["aviso"]["codigo"] == "sin_abrir"
    assert p.meta["solidez"] == 0


def test_aviso_distingue_no_encontrar_de_no_poder_abrir():
    sin_nada = procesar('Texto.\n\n```json\n{"tipo": "pregunta", "fuentes": []}\n```')
    assert sin_nada.meta["aviso"]["codigo"] == "nada_encontrado"


def test_sin_aviso_cuando_hay_evidencia_abierta():
    texto = ('Es falso [1].\n\n```json\n'
             '{"tipo": "afirmacion", "veredicto": "falso", "fuentes": '
             '[{"n": 1, "url": "https://reuters.com/x", "coincide": true}]}\n```')
    p = procesar(texto, extractos={"https://reuters.com/x": "Texto leído de verdad"})
    assert "aviso" not in p.meta
    assert p.meta["solidez"] > 0
```

- [ ] **Paso 2: verificar que fallan**

Run: `.venv/bin/python -m pytest tests/test_veredicto.py -q -k "prosa_sobrevive or aviso"`
Esperado: FAIL — la prosa sale reemplazada por el enlatado

- [ ] **Paso 3: implementar**

En `verificador/veredicto.py`, sustituye el bloque completo que empieza por
`if meta.get("veredicto") != "no_verificable" and meta["evidencia"]["leidas"] == 0:`
(hasta el `)` que cierra la asignación de `prosa`) por:

```python
    # Degradar informando, jamás borrando. La prosa que el modelo escribió ya
    # viajó al navegador por streaming: sustituirla es borrar una respuesta
    # delante del usuario. Se anota qué le falta y por qué.
    if meta["evidencia"]["leidas"] == 0:
        if meta["evidencia"]["listadas"] == 0:
            meta["aviso"] = {
                "codigo": "nada_encontrado",
                "texto": "No encontré ninguna fuente sobre esto.",
            }
        else:
            meta["aviso"] = {
                "codigo": "sin_abrir",
                "texto": ("Encontré fuentes pero no pude abrir ninguna, así que "
                          "no puedo respaldar esto con lo que dicen por dentro."),
            }
        meta["solidez"] = 0
```

- [ ] **Paso 4: arreglar el test que consagra el bug**

En `tests/test_traza.py`, el test `test_preguntar_captura_propuestas` afirma en
sus líneas ~101-102 que la salida contiene `'"veredicto": "sin_evidencia"'` y
`'"veredicto_modelo": "informativo"'`. **Bórralas**: estaban protegiendo el
fallo. Sustitúyelas por:

```python
    assert '"aviso"' in salida
    assert '"sin_abrir"' in salida
```

Revisa también `test_preguntar_enriquece_meta` (`tests/test_traza.py:166`), que
asserta `40 <= confianza <= 55`. Cámbialo a `solidez`. Para saber qué rango
poner sin adivinar, calcula el valor exacto con la curva nueva antes de editar:

```bash
.venv/bin/python -c "
from verificador.veredicto import calcular_solidez
# copia aquí el meta que construye el test y mira qué da
print(calcular_solidez({'tipo': 'afirmacion', 'fuentes': [...]}))
"
```

Pon un rango de ±7 alrededor de ese valor: suficiente para no ser frágil, lo
bastante estrecho para detectar una regresión de la curva.

- [ ] **Paso 5: verificar y commitear**

Run: `.venv/bin/python -m pytest -q` → todo en verde

```bash
git add verificador/veredicto.py tests/
git commit -m "fix: la prosa del modelo no se borra nunca

Si no se abría ninguna página se descartaba la respuesta ya escrita —y ya
enviada al navegador por streaming— y se sustituía por un enlatado que pedía
reformular la afirmación. Ahora se anota el aviso y se distingue no haber
encontrado nada de no haber podido abrirlo."
```

---

### Tarea 10: La interfaz entiende `tipo`, `solidez` y `aviso`

**Ficheros:**
- Modificar: `frontend/src/lib/types.ts`, `frontend/src/lib/maps.ts`,
  `frontend/src/components/Answer.tsx`
- Test: `tests/test_format.mjs`

**Interfaces:**
- Consume: `meta.tipo`, `meta.solidez`, `meta.aviso` de la tarea 9.

- [ ] **Paso 1: actualizar el contrato TypeScript**

En `frontend/src/lib/types.ts`, dentro de `FuenteMeta` añade:

```typescript
  tipo_fuente?: string;
```

Y sustituye la interfaz `Meta` por:

```typescript
export type TipoConsulta = "afirmacion" | "pregunta" | "mecanismo";

export interface Aviso {
  codigo: "nada_encontrado" | "sin_abrir";
  texto: string;
}

export interface Meta {
  tipo?: TipoConsulta;
  veredicto?: string;
  solidez?: number;
  solidez_modelo?: number;
  aviso?: Aviso;
  resumen?: string;
  pais?: string;
  fuentes?: FuenteMeta[];
  evidencia?: {
    listadas: number;
    leidas: number;
    citadas: number;
    dominios_independientes: number;
    respaldan: number;
    matizan: number;
    diversidad_editorial: number;
  };
}
```

- [ ] **Paso 2: el sello solo aparece en afirmaciones**

En `frontend/src/lib/maps.ts`, borra las entradas `informativo` y
`no_verificable` de `SELLOS` y de `SELLO_POR_EMOJI` (ya no existen), y sustituye
`selloDe` por:

```typescript
// El sello solo existe para afirmaciones. Una pregunta o un mecanismo bien
// respondidos no llevan etiqueta: no hay nada que juzgar.
export function selloDe(meta: Meta | null, prosa: string): Sello | null {
  if (meta?.tipo && meta.tipo !== "afirmacion") return null;
  const clave =
    meta && typeof meta.veredicto === "string" ? meta.veredicto.toLowerCase().trim() : null;
  if (clave && SELLOS[clave]) return SELLOS[clave];
  for (const [emoji, k] of Object.entries(SELLO_POR_EMOJI)) {
    if (prosa.includes(emoji)) return SELLOS[k];
  }
  return null;
}
```

- [ ] **Paso 3: escribir el test del contrato**

`tests/test_format.mjs` importa de `format.ts`, no de `maps.ts`, así que hay que
añadir el import. Al principio del fichero, junto al bloque que ya existe:

```javascript
import { selloDe } from "../frontend/src/lib/maps.ts";
```

Y al final del fichero:

```javascript
// El sello solo existe para afirmaciones: una pregunta o un mecanismo bien
// respondidos no llevan etiqueta porque no hay nada que juzgar.
assert.equal(selloDe({ tipo: "pregunta", veredicto: "verdadero" }, ""), null);
assert.equal(selloDe({ tipo: "mecanismo" }, "✅ VERDADERO"), null);
assert.equal(selloDe({ tipo: "afirmacion", veredicto: "falso" }, "").etiqueta, "Falso");
// Sin `tipo` (respuesta vieja en curso) se sigue detectando por el emoji.
assert.equal(selloDe(null, "✅ VERDADERO y tal").etiqueta, "Verdadero");
```

El fixture de la línea 10 usa `{"veredicto":"falso","confianza":42}`. Cámbialo a
`{"tipo":"afirmacion","veredicto":"falso","solidez":42}` y el assert de
`completa.meta.confianza` a `completa.meta.solidez`.

- [ ] **Paso 4: pintar el aviso y la solidez**

En `frontend/src/components/Answer.tsx`, donde hoy se lee `meta.confianza`,
cámbialo a `meta.solidez`. Y justo **antes** del bloque de la prosa (para que
no se inserte encima de texto ya leído), añade:

```tsx
{meta?.aviso && (
  <p className="aviso-evidencia" role="status">
    {meta.aviso.texto}
  </p>
)}
```

En `frontend/src/faro.css`, añade junto a los demás estilos de respuesta:

```css
/* Aviso de evidencia floja: informa sin gritar, y sin sustituir la respuesta. */
.aviso-evidencia {
  margin: 0 0 .75rem;
  padding: .5rem .75rem;
  border-left: 3px solid var(--warn);
  background: var(--surface-2);
  border-radius: 0 8px 8px 0;
  font-family: var(--display);
  font-size: .8rem;
  color: var(--ink-2);
}
```

- [ ] **Paso 5: verificar y commitear**

```bash
cd frontend && npm run check
```

Esperado: contratos, lint y build en verde.

```bash
git add frontend/src tests/test_format.mjs
git commit -m "feat: la interfaz entiende tipo, solidez y aviso

El sello solo aparece en afirmaciones; una pregunta o un mecanismo bien
respondidos no llevan etiqueta. El aviso de evidencia floja se pinta antes
de la prosa para no insertarse encima de lo que ya se estaba leyendo."
```

---

## Cierre

- [ ] **Puerta completa**

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run check
```

- [ ] **Prueba de humo contra la API real**

```bash
.venv/bin/python scripts/humo.py
```

- [ ] **Verificación manual del objetivo**

Levanta el servidor y prueba las tres formas que antes fallaban:

```bash
uvicorn verificador.server:app --reload
```

1. `¿Cómo funciona el sistema electoral de Colombia?` → debe responder sin sello
   y sin pedir que reformules.
2. `Explícame la reforma pensional` → ídem, `tipo: mecanismo`.
3. `El Banco de la República es el banco central de Colombia` → sello
   ✅ VERDADERO; si banrep bloquea la lectura, debe salir el aviso `sin_abrir`
   en vez de borrarse la respuesta.

- [ ] **Actualizar el README**

La sección "Capacidades" dice "Veredictos: verdadero, falso, engañoso, fuera de
contexto, predicción y sin evidencia" y "Confianza calculada". Actualízalas a
los tres tipos y a `solidez`.
