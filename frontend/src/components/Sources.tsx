import type { CSSProperties } from "react";
import { ArrowUpRight, X } from "lucide-react";
import { CREDIBILIDAD, MANIPULACION, TENDENCIA_NOMBRE } from "../lib/maps";
import { dominioDe, urlSegura } from "../lib/format";
import type { FuenteMeta } from "../lib/types";

/** Avisos de credibilidad y honestidad. Solo aparecen cuando hay algo que
 *  advertir: una fuente normal no gasta tinta en decir que es normal. */
function Avisos({ f }: { f: FuenteMeta }) {
  const cred = CREDIBILIDAD[(f.credibilidad || "").toLowerCase()];
  const manip = MANIPULACION[(f.manipulacion || "").toLowerCase()];
  if (!cred?.aviso && !manip) return null;
  return (
    <span className="f-avisos">
      {cred?.aviso && <span className={cred.clase}>{cred.txt}</span>}
      {manip && <span className={manip.clase}>{manip.txt}</span>}
    </span>
  );
}

function tendenciaDe(f: FuenteMeta): string | null {
  const t = (f.tendencia || "").toLowerCase();
  return TENDENCIA_NOMBRE[t] ?? null;
}

/** La nota al margen: una fuente por vez, alineada con la línea que la citó.
 *  Es todo el aparato que ve el lector salvo que pida la lista entera. */
export function NotaMargen({
  fuente,
  extracto,
  y,
  onCerrar,
}: {
  fuente: FuenteMeta;
  extracto?: string;
  y: number;
  onCerrar: () => void;
}) {
  const dominio = dominioDe(fuente.url);
  const url = urlSegura(fuente.url);
  const tendencia = tendenciaDe(fuente);
  return (
    <div
      className="nota"
      id="nota-fuente"
      role="region"
      aria-label={`Fuente ${fuente.n}`}
      style={{ "--y": `${y}px` } as CSSProperties}
    >
      <button className="nota-cerrar" type="button" onClick={onCerrar} aria-label="Cerrar la fuente">
        <X size={14} aria-hidden="true" />
      </button>
      <p className="nota-n">{fuente.n}</p>
      <p className="nota-medio">{fuente.medio || dominio || "Fuente"}</p>
      <p className="nota-origen">
        {dominio || "sin URL"}
        {tendencia && <> · {tendencia}</>}
      </p>
      <Avisos f={fuente} />
      <p className={`nota-rel${fuente.coincide ? " si" : ""}`}>
        {fuente.coincide ? "Respalda" : "Matiza"}
      </p>
      {extracto ? (
        <blockquote className="nota-extracto">{extracto}</blockquote>
      ) : (
        <p className="nota-sin-lectura">No se pudo abrir. Queda listada, no cuenta como evidencia.</p>
      )}
      {url !== "#" && (
        <a className="nota-abrir" href={url} target="_blank" rel="noopener noreferrer">
          Abrir fuente <ArrowUpRight size={13} aria-hidden="true" />
        </a>
      )}
    </div>
  );
}

/** La lista entera, solo cuando se pide. Cada entrada invoca la misma nota que
 *  una cita: un único gesto para llegar a una fuente, venga de donde venga. */
export function ListaFuentes({
  fuentes,
  activa,
  onInvocar,
}: {
  fuentes: FuenteMeta[];
  activa: number | null;
  onInvocar: (n: number, el: HTMLElement) => void;
}) {
  // Las citadas primero: son las que sostienen el texto que se acaba de leer.
  const orden = [...fuentes].sort((a, b) => Number(b.citada !== false) - Number(a.citada !== false));
  return (
    <ol className="lista-fuentes">
      {orden.map((f, i) => {
        const dominio = dominioDe(f.url);
        const tendencia = tendenciaDe(f);
        return (
          <li key={`${f.n ?? i}-${i}`} className={f.citada === false ? "no-citada" : undefined}>
            <button
              type="button"
              className={`lf-fila${activa === f.n ? " lf-viva" : ""}`}
              aria-expanded={activa === f.n}
              aria-controls="nota-fuente"
              onClick={(e) => onInvocar(f.n, e.currentTarget)}
            >
              <span className="lf-n">{f.n}</span>
              <span className="lf-medio">{f.medio || dominio || "Fuente"}</span>
              <span className="lf-origen">
                {dominio || "sin URL"}
                {tendencia && <> · {tendencia}</>}
              </span>
              <Avisos f={f} />
              <span className={`lf-rel${f.coincide ? " si" : ""}`}>
                {f.coincide ? "Respalda" : "Matiza"}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
