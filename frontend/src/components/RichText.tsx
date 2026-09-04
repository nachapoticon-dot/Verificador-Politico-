import { Fragment, type ReactNode } from "react";
import type { FuenteMeta } from "../lib/types";
import { citasPegadas, TOKEN_RICO, urlSegura } from "../lib/format";

/** Invoca la fuente `n` en el margen; recibe el propio marcador para que quien
 *  dibuje la nota pueda alinearla con la línea desde la que se citó. */
export type InvocarCita = (n: number, marcador: HTMLElement) => void;

interface RichTextProps {
  texto: string;
  fuentes: FuenteMeta[];
  citaActiva?: number | null;
  onCita?: InvocarCita;
}

interface Ctx {
  fuentes: FuenteMeta[];
  citaActiva: number | null;
  onCita?: InvocarCita;
}

function inline(texto: string, ctx: Ctx): ReactNode[] {
  const { fuentes, citaActiva, onCita } = ctx;
  const porN = new Map(fuentes.map((fuente) => [fuente.n, fuente]));
  const salida: ReactNode[] = [];
  const pegadas = citasPegadas(texto);
  let inicio = 0;
  let indice = 0;

  for (const match of texto.matchAll(TOKEN_RICO)) {
    const posicion = match.index ?? 0;
    if (posicion > inicio) salida.push(texto.slice(inicio, posicion));
    const token = match[0];
    const clave = `in-${indice++}`;

    if (token.startsWith("**")) {
      salida.push(<strong key={clave}>{token.slice(2, -2)}</strong>);
    } else if (/^\[\d+\]$/.test(token)) {
      const n = Number(token.slice(1, -1));
      const fuente = porN.get(n);
      // Dos voladas seguidas sin separador se leen como un número: [2][3]
      // daba "23". La coma volada es la solución de toda la vida.
      if (pegadas.has(posicion)) {
        salida.push(<span key={`coma-${clave}`} className="cita-coma">,</span>);
      }
      // La cita ya no saca al lector de la página: invoca la fuente en el
      // margen. El enlace externo vive dentro de esa nota. Sin fuente detrás
      // (cita huérfana) el marcador queda inerte, no roto.
      salida.push(
        fuente && onCita ? (
          <button
            key={clave}
            type="button"
            className={`cita${citaActiva === n ? " cita-viva" : ""}`}
            aria-expanded={citaActiva === n}
            aria-controls="nota-fuente"
            aria-label={`Fuente ${n}${fuente.medio ? `, ${fuente.medio}` : ""}`}
            onClick={(e) => onCita(n, e.currentTarget)}
          >
            {n}
          </button>
        ) : (
          <span key={clave} className="cita cita-inactiva">{n}</span>
        ),
      );
    } else {
      const partes = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      const url = urlSegura(partes?.[2]);
      salida.push(
        url !== "#" ? (
          <a key={clave} href={url} target="_blank" rel="noopener noreferrer">
            {partes?.[1]}
          </a>
        ) : (
          <span key={clave}>{partes?.[1] ?? token}</span>
        ),
      );
    }
    inicio = posicion + token.length;
  }
  if (inicio < texto.length) salida.push(texto.slice(inicio));
  return salida;
}

function lineas(texto: string, ctx: Ctx): ReactNode[] {
  return texto.split("\n").map((linea, i, todas) => (
    <Fragment key={`line-${i}`}>
      {inline(linea, ctx)}
      {i < todas.length - 1 && <br />}
    </Fragment>
  ));
}

export function RichText({ texto, fuentes, citaActiva = null, onCita }: RichTextProps) {
  const ctx: Ctx = { fuentes, citaActiva, onCita };
  const bloques = texto.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className="respuesta-cuerpo">
      {bloques.map((bloque, i) => {
        const ls = bloque.split("\n").filter(Boolean);
        if (ls.length && ls.every((l) => /^[-*]\s+/.test(l.trim()))) {
          return (
            <ul key={`block-${i}`}>
              {ls.map((l, j) => <li key={j}>{inline(l.trim().replace(/^[-*]\s+/, ""), ctx)}</li>)}
            </ul>
          );
        }
        const encabezado = bloque.match(/^#{1,6}\s+(.+)$/s);
        if (encabezado) return <h3 key={`block-${i}`}>{inline(encabezado[1], ctx)}</h3>;
        return <p key={`block-${i}`}>{lineas(bloque, ctx)}</p>;
      })}
    </div>
  );
}
