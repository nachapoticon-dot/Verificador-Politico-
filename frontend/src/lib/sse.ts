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
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch("/api/verificar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pregunta,
      rigor: opts.rigor,
      largo: opts.largo,
      detalle: opts.detalle,
      pais: opts.pais || undefined,
    }),
    signal,
  });

  if (!resp.ok || !resp.body) {
    if (resp.status === 422) throw new Error("La consulta no tiene un formato válido.");
    throw new Error("El servidor respondió con estado " + resp.status + ".");
  }

  const lector = resp.body.getReader();
  const dec = new TextDecoder();
  let buffer = "";
  let terminal = false;

  while (true) {
    const { value, done } = await lector.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });
    buffer = buffer.replace(/\r\n/g, "\n");

    // Los eventos SSE se separan por una línea en blanco.
    let corte: number;
    while ((corte = buffer.indexOf("\n\n")) !== -1) {
      const bloque = buffer.slice(0, corte);
      buffer = buffer.slice(corte + 2);
      const { evento, dato } = parseSSE(bloque);
      if (evento === "respuesta" || evento === "error") terminal = true;
      onEvento(evento, dato);
    }
  }

  if (!terminal) {
    throw new Error("Se interrumpió la conexión antes de recibir una respuesta final.");
  }
}
