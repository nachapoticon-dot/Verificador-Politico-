// Maneja el hilo de turnos y el streaming. El motor es sin estado: cada turno es
// independiente, así que el hook solo acumula turnos en una lista.

import { useCallback, useRef, useState } from "react";
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
  const controlador = useRef<AbortController | null>(null);

  const preguntar = useCallback(async (pregunta: string, opts: Opciones) => {
    if (controlador.current) return;
    const id = nuevoId();
    const abort = new AbortController();
    controlador.current = abort;
    setTurnos((t) => [...t, { id, pregunta, opciones: opts, eventos: [], estado: "investigando" }]);
    setEnCurso(true);

    const parchar = (fn: (t: Turno) => Turno) =>
      setTurnos((lista) => lista.map((t) => (t.id === id ? fn(t) : t)));

    try {
      await streamVerificar(pregunta, opts, (evento, dato) => {
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
          parchar((t) => ({ ...t, estado: "listo", respuesta: dato.texto || "" }));
        } else if (evento === "error") {
          parchar((t) => ({ ...t, estado: "error", error: dato.mensaje || "Algo salió mal." }));
        }
      }, abort.signal);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        parchar((t) => ({ ...t, estado: "cancelado" }));
        return;
      }
      parchar((t) => ({
        ...t,
        estado: "error",
        error:
          err instanceof Error && !/load failed|failed to fetch|networkerror/i.test(err.message)
            ? err.message
            : "Se interrumpió la conexión antes de terminar la verificación.",
      }));
    } finally {
      controlador.current = null;
      setEnCurso(false);
    }
  }, []);

  const detener = useCallback(() => controlador.current?.abort(), []);
  const limpiar = useCallback(() => {
    if (!controlador.current) setTurnos([]);
  }, []);

  return { turnos, enCurso, preguntar, detener, limpiar };
}
