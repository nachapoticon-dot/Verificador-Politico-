// Maneja el hilo de turnos y el streaming. El motor es sin estado: cada turno es
// independiente, así que el hook solo acumula turnos en una lista.

import { useCallback, useState } from "react";
import { streamVerificar } from "../lib/sse";
import type { Opciones, TrazaEvento, Turno } from "../lib/types";

function nuevoId(): string {
  return "t_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function aplicarTraza(turno: Turno, ev: TrazaEvento): Turno {
  const eventos = [...turno.eventos];
  const i = eventos.findIndex((e) => e.id === ev.id);
  if (i === -1) {
    eventos.push(ev);
  } else {
    // El evento de fin completa el de inicio (estado ok/fallo + extracto).
    eventos[i] = { ...eventos[i], ...ev, extracto: ev.extracto ?? eventos[i].extracto };
  }
  return { ...turno, eventos };
}

export function useVerificador() {
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [enCurso, setEnCurso] = useState(false);

  const preguntar = useCallback(async (pregunta: string, opts: Opciones) => {
    const id = nuevoId();
    setTurnos((t) => [...t, { id, pregunta, eventos: [], estado: "investigando" }]);
    setEnCurso(true);

    const parchar = (fn: (t: Turno) => Turno) =>
      setTurnos((lista) => lista.map((t) => (t.id === id ? fn(t) : t)));

    try {
      await streamVerificar(pregunta, opts, (evento, dato) => {
        if (evento === "traza") {
          parchar((t) => aplicarTraza(t, dato as TrazaEvento));
        } else if (evento === "respuesta") {
          parchar((t) => ({ ...t, estado: "listo", respuesta: dato.texto || "" }));
        } else if (evento === "error") {
          parchar((t) => ({ ...t, estado: "error", error: dato.mensaje || "Algo salió mal." }));
        }
      });
    } catch (err) {
      parchar((t) => ({
        ...t,
        estado: "error",
        error:
          "No pude conectar con el verificador. ¿Está el servidor en marcha? (" +
          (err instanceof Error ? err.message : String(err)) +
          ")",
      }));
    } finally {
      setEnCurso(false);
    }
  }, []);

  return { turnos, enCurso, preguntar };
}
