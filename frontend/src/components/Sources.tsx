// Lista ponderada de fuentes: tendencia + medio + respalda/matiza + credibilidad
// + aviso de honestidad (manipulación) + "ver de dónde salió".

import { CREDIBILIDAD, MANIPULACION, TEND_CLASE } from "../lib/maps";
import { urlSegura } from "../lib/format";
import type { FuenteMeta } from "../lib/types";

export function Sources({
  fuentes,
  extractos,
}: {
  fuentes: FuenteMeta[];
  extractos: Record<string, string>;
}) {
  if (!fuentes.length) return null;

  return (
    <div className="fuentes-bloque">
      <div className="fuentes-cab">fuentes contrastadas</div>
      <ul className="fuentes-lista">
        {fuentes.map((f, idx) => {
          const tkey = (f.tendencia || "").toLowerCase();
          const cred = CREDIBILIDAD[(f.credibilidad || "").toLowerCase()];
          const manip = MANIPULACION[(f.manipulacion || "").toLowerCase()];
          const extracto = f.url ? extractos[f.url] : undefined;

          return (
            <li key={f.n ?? idx}>
              <span className={"chip-t " + (TEND_CLASE[tkey] || "t-cen")}>{tkey || "—"}</span>

              <a
                href={urlSegura(f.url)}
                target="_blank"
                rel="noopener"
                className="fuente-medio"
              >
                [{f.n}] {f.medio || f.url || "fuente"}
              </a>

              <span className="fuente-rel">{f.coincide ? "✓ respalda" : "· matiza"}</span>

              {cred && <span className={"badge-c " + cred.clase}>{cred.txt}</span>}

              {manip && (
                <span
                  className={"badge-m " + manip.clase}
                  title="Honestidad de la fuente: tiende a manipular la información"
                >
                  ⚠ {manip.txt}
                </span>
              )}

              {extracto && (
                <details className="prueba">
                  <summary>ver de dónde salió</summary>
                  <blockquote>{extracto}</blockquote>
                </details>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
