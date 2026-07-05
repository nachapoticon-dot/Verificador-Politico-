// Ficha editorial de fuentes: filetes finos, una fila por fuente; solo se
// anuncia lo anómalo (credibilidad baja, manipulación). Extracto expandible y
// fuentes nunca citadas atenuadas al final.

import { useState } from "react";
import { CREDIBILIDAD, MANIPULACION, TEND_ABREV } from "../lib/maps";
import { dominioDe, normalizarUrl, urlSegura } from "../lib/format";
import type { FuenteMeta } from "../lib/types";

function Avisos({ f }: { f: FuenteMeta }) {
  const cred = CREDIBILIDAD[(f.credibilidad || "").toLowerCase()];
  const manip = MANIPULACION[(f.manipulacion || "").toLowerCase()];
  return (
    <>
      {cred?.aviso && <span className={"f-aviso " + cred.clase}>{cred.txt}</span>}
      {manip && (
        <span
          className={"f-aviso " + manip.clase}
          title="Honestidad de la fuente: tiende a manipular la información"
        >
          ⚠ {manip.txt}
        </span>
      )}
    </>
  );
}

export function Sources({
  fuentes,
  extractos,
}: {
  fuentes: FuenteMeta[];
  extractos: Record<string, string>;
}) {
  const [abiertas, setAbiertas] = useState<Set<number>>(new Set());
  if (!fuentes.length) return null;

  const porUrl: Record<string, string> = {};
  for (const [u, x] of Object.entries(extractos)) porUrl[normalizarUrl(u)] = x;

  // Las citadas primero; las que el modelo listó pero nunca citó, al final.
  const orden = [...fuentes].sort(
    (a, b) => Number(b.citada !== false) - Number(a.citada !== false),
  );

  const alternar = (n: number) =>
    setAbiertas((prev) => {
      const s = new Set(prev);
      if (s.has(n)) s.delete(n);
      else s.add(n);
      return s;
    });

  return (
    <div className="fuentes-bloque">
      <div className="fuentes-cab">fuentes contrastadas · {fuentes.length}</div>
      <ul className="fuentes-lista">
        {orden.map((f, idx) => {
          const clave = f.n ?? idx;
          const dominio = dominioDe(f.url);
          const extracto = f.extracto ?? (f.url ? porUrl[normalizarUrl(f.url)] : undefined);
          const abierta = abiertas.has(clave);
          return (
            <li key={clave} className={"f-fila" + (f.citada === false ? " no-citada" : "")}>
              <div className="f-linea">
                <span className="f-n">[{f.n}]</span>
                {dominio ? (
                  <img
                    className="fav"
                    alt=""
                    src={
                      "https://www.google.com/s2/favicons?domain=" +
                      encodeURIComponent(dominio) +
                      "&sz=32"
                    }
                  />
                ) : (
                  <span className="fav fav--q">📄</span>
                )}
                <a className="fuente-medio" href={urlSegura(f.url)} target="_blank" rel="noopener">
                  {f.medio || dominio || "fuente"}
                </a>
                <span className="f-tend">{TEND_ABREV[(f.tendencia || "").toLowerCase()] ?? "—"}</span>
                <Avisos f={f} />
                <span className={"fuente-rel" + (f.coincide ? " si" : "")}>
                  {f.coincide ? "✓ respalda" : "· matiza"}
                </span>
                {extracto && (
                  <button
                    type="button"
                    className="f-toggle"
                    aria-expanded={abierta}
                    aria-label="Ver de dónde salió"
                    onClick={() => alternar(clave)}
                  >
                    ⌄
                  </button>
                )}
              </div>
              {abierta && extracto && (
                <blockquote className="f-extracto">
                  {extracto}
                  {f.url && (
                    <a className="f-abrir" href={urlSegura(f.url)} target="_blank" rel="noopener">
                      abrir ↗
                    </a>
                  )}
                </blockquote>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
