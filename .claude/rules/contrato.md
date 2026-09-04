---
paths:
  - "verificador/veredicto.py"
  - "verificador/fuentes.py"
  - "verificador/server.py"
  - "frontend/src/lib/types.ts"
  - "frontend/src/lib/sse.ts"
  - "frontend/src/lib/maps.ts"
---

Invariantes del contrato entre el modelo, el servidor y la interfaz. Son fáciles
de romper sin que ningún test lo note.

**Los nombres de los eventos SSE son contrato con el frontend.** `delta`,
`delta_reset`, `traza`, `respuesta`, `error`. Cambiar uno rompe la interfaz en
silencio: el navegador simplemente deja de recibir. `tests/test_sse.mjs` los
verifica desde el lado del cliente — si añades un evento, añádelo también ahí.

**Para que una fuente sume solidez tiene que cumplirlo todo:** URL http(s)
comprobable, dominio no repetido, `citada` con su `[n]` presente en la prosa, y
un extracto real (o sea, la página se abrió de verdad). Falla cualquiera y la
fuente vale cero. Antes de tocar el cálculo, mira cuántas de esas condiciones se
incumplen por accidente en una consulta legítima.

**El registro curado manda sobre el modelo.** Si un dominio está en
`data/fuentes.json`, sus etiquetas de credibilidad, manipulación y tendencia
sustituyen a las que propuso el modelo. El modelo solo decide en dominios no
registrados, y esa decisión queda como propuesta en `propuestas.jsonl`, sin
aplicarse sola.

**El bloque ```json de cierre debe sobrevivir el viaje de ida y vuelta.**
`partir()` → `validar_meta()` → `reserializar()`. Si añades un campo al meta,
tiene que pasar por `validar_meta` o desaparecerá en la re-serialización.

**El sello de veredicto solo existe para `tipo == "afirmacion"`.** Una pregunta
o un mecanismo bien respondidos no llevan etiqueta: no hay nada que juzgar.
`validar_meta` solo traslada `veredicto` al meta final cuando el tipo es ese;
en cualquier otro caso el campo desaparece antes de llegar a la interfaz. El
frontend (`selloDe` en `maps.ts`) repite la comprobación por su cuenta, como
cinturón de seguridad para el modo sin `tipo` (respuesta vieja en curso que se
detecta por el emoji) — no porque el dato pueda llegarle ya sucio.

**`aviso` avisa de evidencia floja sin sustituir la respuesta.** Si
`evidencia.leidas` queda en cero se añade `meta.aviso`: `codigo:
"nada_encontrado"` cuando tampoco se listó ninguna fuente, `codigo: "sin_abrir"`
cuando se listaron pero no se pudo abrir ninguna. En ambos casos la `solidez`
se fuerza a 0. Es la misma regla de siempre — degradar informando, jamás
borrando — aplicada al caso donde no hay nada que citar: la prosa ya viajó al
navegador por streaming, y sustituirla sería borrar una respuesta delante del
usuario.

**Validar es degradar, no rechazar.** Campo inválido se descarta; el resto
sobrevive. Nunca todo-o-nada, y nunca una excepción: es el último paso antes del
usuario.
