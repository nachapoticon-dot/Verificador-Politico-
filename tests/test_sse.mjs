import assert from "node:assert/strict";
import { streamVerificar } from "../frontend/src/lib/sse.ts";

const encoder = new TextEncoder();

function respuestaSSE(texto) {
  return new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(texto));
      controller.close();
    },
  }), { status: 200 });
}

globalThis.fetch = async () => respuestaSSE(
  'event: delta\ndata: {"texto":"Hola"}\n\n' +
  'event: respuesta\ndata: {"texto":"Hola final"}\n\n',
);
const eventos = [];
await streamVerificar("consulta", { rigor: "riguroso", largo: "normal", detalle: "simple" }, (evento) => eventos.push(evento));
assert.deepEqual(eventos, ["delta", "respuesta"]);

globalThis.fetch = async () => respuestaSSE('event: delta\ndata: {"texto":"incompleto"}\n\n');
await assert.rejects(
  () => streamVerificar("consulta", { rigor: "riguroso", largo: "normal", detalle: "simple" }, () => {}),
  /interrumpió la conexión/i,
);

console.log("ok");
