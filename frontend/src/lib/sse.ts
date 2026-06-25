// Lectura del flujo SSE de /api/verificar, portada del frontend original.
// Llama a onEvento(nombre, dato) por cada evento del servidor: "traza",
// "respuesta", "error".

import type { Opciones } from "./types";

type Handler = (evento: string, dato: any) => void;

function parseSSE(bloque: string): { evento: string; dato: any } {
  let evento = "message";
  const datos: string[] = [];
  for (const linea of bloque.split("\n")) {
    if (linea.startsWith("event:")) evento = linea.slice(6).trim();
    else if (linea.startsWith("data:")) datos.push(linea.slice(5).trim());
  }
  let dato: any = {};
  try {
    dato = JSON.parse(datos.join("\n"));
  } catch {
    /* ignora */
  }
  return { evento, dato };
}

export async function streamVerificar(
  pregunta: string,
  opts: Opciones,
  onEvento: Handler,
): Promise<void> {
  const resp = await fetch("/api/verificar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pregunta,
      rigor: opts.rigor,
      largo: opts.largo,
      detalle: opts.detalle,
    }),
  });

  if (!resp.ok || !resp.body) {
    throw new Error("HTTP " + resp.status);
  }

  const lector = resp.body.getReader();
  const dec = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await lector.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });

    // Los eventos SSE se separan por una línea en blanco.
    let corte: number;
    while ((corte = buffer.indexOf("\n\n")) !== -1) {
      const bloque = buffer.slice(0, corte);
      buffer = buffer.slice(corte + 2);
      const { evento, dato } = parseSSE(bloque);
      onEvento(evento, dato);
    }
  }
}
