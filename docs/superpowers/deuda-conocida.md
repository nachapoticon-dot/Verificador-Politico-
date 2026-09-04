# Deuda conocida

Hallazgos reales de las revisiones de la rama `faro-siguiente-nivel`
(2026-07-26) que se triaron como no bloqueantes. Ninguno es una suposición: los
encontró un revisor ejecutando el código. Están por orden de valor.

## Vale la pena antes que nada

**La solidez no distingue "no hay evidencia" de "la evidencia no cuenta".** La
puerta del aviso dispara con `evidencia.leidas == 0`, pero `_fuentes_utiles`
exige además `citada`, y la curva explicativa exige `respaldan` no vacío. Dos
huecos reproducidos: una fuente leída pero no citada da solidez 0 **sin aviso**;
un mecanismo cuya única fuente leída y citada tiene `coincide: False` da 0
**sin aviso**. El usuario ve un 0% junto a una fuente marcada como leída y nadie
le dice por qué.

**El dedupe por dominio se queda con la primera, no con la mejor.**
`veredicto.py`, en `_fuentes_utiles`. Dos URLs del mismo dominio con `coincide`
distinto: orden `no/sí` da solidez 0; orden `sí/no` da 48. El resultado depende
del orden en que el modelo listó las fuentes.

**El filtro de rutas de Playwright no tiene ningún test.** `filtrar`, dentro de
`_leer_en_pagina`, es lo que impide que una página cargue subrecursos internos.
El test de afinidad parchea `_guardia` a `True`, así que la rama `route.abort()`
nunca se ejecuta en la suite. Es el único punto donde un refactor podría
invertir la condición y el CI seguiría verde. Ahora es barato de cubrir gracias
al punto de inyección.

**`.claude/rules/contrato.md` afirma un invariante que no se cumple.** Dice que
el bloque JSON sobrevive el viaje `partir → validar_meta → reserializar`; en la
práctica una segunda vuelta pierde `solidez`, `aviso`, `evidencia` y `resumen`, y
resucita `confianza: 0`. Hoy nadie revalida, así que es latente — pero la regla
enseña algo falso.

## Cobertura que falta

- Los arreglos del prompt de la tarea 6 (la referencia colgada a "no sea
  verificable" y las dos reglas duras de credibilidad) no tienen test dedicado:
  solo los cubre la inspección manual.
- La lista blanca `excepciones_un_punto` de
  `test_ningun_paraguas_de_gobierno_en_el_registro` se autoaprueba: un commit
  futuro podría reintroducir `gob.mx` y añadirlo a la lista a la vez, y el test
  pasaría. La lista negra que se añadió después lo mitiga, no lo cierra.

## Trampas latentes

- **La base 88 de la curva explicativa ignora `mejor`**, así que una primaria
  oficial de credibilidad baja daría 88 y una agencia curada alta da 70. Hoy es
  inalcanzable: ninguna `primaria_oficial` del registro es no-alta y
  `validar_meta` nunca copia `tipo_fuente` del modelo. Muerde el día que se
  registre una institución mediocre.
- **`coincide` ausente** cuenta como respaldo pleno en la curva explicativa y
  como matiz en la de afirmación. Mitigado porque `validar_meta` lo fuerza a
  booleano.

## Limpieza

- `_es_muro` no cubre variantes de paywall en español: "hazte socio",
  "contenido premium", "regístrate para seguir leyendo".
- Código muerto inalcanzable: la rama `"info"` de `IconoVeredicto`
  (`Answer.tsx`) y `.sello-banda[data-v="info"]` en `faro.css`. `SELLOS` ya no
  tiene ninguna entrada con `v: "info"`.
- Campos que se producen y nadie consume: `aviso.codigo` (el frontend solo lee
  `.texto`), `solidez_modelo`, `evidencia.listadas`, `evidencia.citadas`,
  `evidencia.diversidad_editorial`, `FuenteMeta.tipo_fuente`.
- Fixtures zombis: `tests/test_traza.py` y `tests/test_fuentes.py` siguen usando
  el valor `informativo`, que ya no existe en el contrato. Pasan, pero enseñan
  lo contrario de lo que hay.
- Los stubs `_FakeAgente.preguntar` de `tests/test_server.py` conservan
  `largo="corta"` como default. Inerte, pero confunde con el default real.
- El aviso se monta junto al resto del bloque post-streaming, así que su
  anuncio en lectores de pantalla puede ser inconsistente entre navegadores.
