import assert from "node:assert/strict";
import {
  citasPegadas,
  enPalabras,
  normalizarUrl,
  partirRespuesta,
  urlSegura,
} from "../frontend/src/lib/format.ts";
import { selloDe } from "../frontend/src/lib/maps.ts";

const completa = partirRespuesta(
  'Hola [1].\n\n```json\n{"tipo":"afirmacion","veredicto":"falso","solidez":42}\n```',
);
assert.equal(completa.prosa, "Hola [1].");
assert.equal(completa.meta.veredicto, "falso");
assert.equal(completa.meta.solidez, 42);

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

// El sello solo existe para afirmaciones: una pregunta o un mecanismo bien
// respondidos no llevan etiqueta porque no hay nada que juzgar.
assert.equal(selloDe({ tipo: "pregunta", veredicto: "verdadero" }, ""), null);
assert.equal(selloDe({ tipo: "mecanismo" }, "✅ VERDADERO"), null);
assert.equal(selloDe({ tipo: "afirmacion", veredicto: "falso" }, "").etiqueta, "Falso");
// Sin `tipo` (respuesta vieja en curso) se sigue detectando por el emoji.
assert.equal(selloDe(null, "✅ VERDADERO y tal").etiqueta, "Verdadero");

// Solo llevan coma volada las citas PEGADAS: "[2][3]" se leería "23". Dos citas
// separadas por texto no llevan nada, por lejos o cerca que estén. Es la trampa
// que tenía la versión en CSS: el combinador `+` salta los nodos de texto y le
// ponía coma a la segunda cita de cada párrafo.
{
  const pegadas = (t) => [...citasPegadas(t)].sort((a, b) => a - b);
  // El índice guardado es el de la cita que RECIBE la coma, o sea la segunda.
  assert.deepEqual(pegadas("Coinciden [2][3] y nadie lo niega."), ["Coinciden ".length + 3]);
  assert.deepEqual(pegadas("Bajó [1] aunque otro informe lo matiza [2]."), []);
  assert.deepEqual(pegadas("Sin ninguna cita."), []);
  assert.deepEqual(pegadas("Tres seguidas [1][2][3]."), ["Tres seguidas ".length + 3, "Tres seguidas ".length + 6]);
  // Un espacio ya las separa: entonces el texto trae su propio separador.
  assert.deepEqual(pegadas("Separadas [1] [2]."), []);
  // La negrita entre medias también las separa.
  assert.deepEqual(pegadas("Roto [1]**y**[2]."), []);
}

// Las cantidades pequeñas se escriben; a partir de ahí, cifra.
assert.equal(enPalabras(1), "una");
assert.equal(enPalabras(4), "cuatro");
assert.equal(enPalabras(13), "13");
assert.equal(enPalabras(2.5), "2.5");

console.log("ok");
