import assert from "node:assert/strict";
import {
  normalizarUrl,
  partirRespuesta,
  urlSegura,
} from "../frontend/src/lib/format.ts";

const completa = partirRespuesta(
  'Hola [1].\n\n```json\n{"veredicto":"falso","confianza":42}\n```',
);
assert.equal(completa.prosa, "Hola [1].");
assert.equal(completa.meta.veredicto, "falso");
assert.equal(completa.meta.confianza, 42);

const abierta = partirRespuesta('Hola en curso\n\n```json\n{"vered');
assert.equal(abierta.prosa, "Hola en curso");
assert.equal(abierta.meta, null);
assert.deepEqual(partirRespuesta("Solo prosa"), { prosa: "Solo prosa", meta: null });

assert.equal(urlSegura("https://ejemplo.com/nota"), "https://ejemplo.com/nota");
assert.equal(urlSegura("javascript:alert(1)"), "#");
assert.equal(urlSegura("data:text/html,hola"), "#");
assert.equal(urlSegura(undefined), "#");

assert.equal(
  normalizarUrl("https://www.ejemplo.com/nota/?utm_source=x&fbclid=1&id=7#parte"),
  "ejemplo.com/nota?id=7",
);
assert.equal(normalizarUrl("http://ejemplo.com/nota"), "ejemplo.com/nota");

console.log("ok");
