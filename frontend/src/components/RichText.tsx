import { Fragment, type ReactNode } from "react";
import type { FuenteMeta } from "../lib/types";
import { urlSegura } from "../lib/format";

interface RichTextProps {
  texto: string;
  fuentes: FuenteMeta[];
}

const TOKEN = /(\*\*[^*\n]+\*\*|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|\[\d+\])/g;

function inline(texto: string, fuentes: FuenteMeta[]): ReactNode[] {
  const porN = new Map(fuentes.map((fuente) => [fuente.n, fuente]));
  const salida: ReactNode[] = [];
  let inicio = 0;
  let indice = 0;

  for (const match of texto.matchAll(TOKEN)) {
    const posicion = match.index ?? 0;
    if (posicion > inicio) salida.push(texto.slice(inicio, posicion));
    const token = match[0];
    const clave = `in-${indice++}`;

    if (token.startsWith("**")) {
      salida.push(<strong key={clave}>{token.slice(2, -2)}</strong>);
    } else if (/^\[\d+\]$/.test(token)) {
      const n = Number(token.slice(1, -1));
      const fuente = porN.get(n);
      const url = urlSegura(fuente?.url);
      salida.push(
        url !== "#" ? (
          <a
            key={clave}
            className="cita"
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Fuente ${n}${fuente?.medio ? `, ${fuente.medio}` : ""}`}
          >
            {n}
          </a>
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

function lineas(texto: string, fuentes: FuenteMeta[]): ReactNode[] {
  return texto.split("\n").map((linea, i, todas) => (
    <Fragment key={`line-${i}`}>
      {inline(linea, fuentes)}
      {i < todas.length - 1 && <br />}
    </Fragment>
  ));
}

export function RichText({ texto, fuentes }: RichTextProps) {
  const bloques = texto.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className="respuesta-cuerpo">
      {bloques.map((bloque, i) => {
        const ls = bloque.split("\n").filter(Boolean);
        if (ls.length && ls.every((l) => /^[-*]\s+/.test(l.trim()))) {
          return (
            <ul key={`block-${i}`}>
              {ls.map((l, j) => <li key={j}>{inline(l.trim().replace(/^[-*]\s+/, ""), fuentes)}</li>)}
            </ul>
          );
        }
        const encabezado = bloque.match(/^#{1,6}\s+(.+)$/s);
        if (encabezado) return <h3 key={`block-${i}`}>{inline(encabezado[1], fuentes)}</h3>;
        return <p key={`block-${i}`}>{lineas(bloque, fuentes)}</p>;
      })}
    </div>
  );
}
