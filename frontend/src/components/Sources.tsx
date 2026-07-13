import { useState } from "react";
import { ChevronDown, ExternalLink, Globe2, ShieldAlert } from "lucide-react";
import { CREDIBILIDAD, MANIPULACION, TEND_ABREV } from "../lib/maps";
import { dominioDe, normalizarUrl, urlSegura } from "../lib/format";
import type { FuenteMeta } from "../lib/types";

const TENDENCIA_NOMBRE: Record<string, string> = {
  izquierda: "Izquierda",
  "centro-izquierda": "Centro izquierda",
  centro: "Centro",
  "centro-derecha": "Centro derecha",
  derecha: "Derecha",
  verificador: "Verificador",
  internacional: "Internacional",
};

function Avisos({ f }: { f: FuenteMeta }) {
  const cred = CREDIBILIDAD[(f.credibilidad || "").toLowerCase()];
  const manip = MANIPULACION[(f.manipulacion || "").toLowerCase()];
  if (!cred?.aviso && !manip) return null;
  return (
    <span className="f-avisos">
      <ShieldAlert size={14} aria-hidden="true" />
      {cred?.aviso && <span className={cred.clase}>{cred.txt}</span>}
      {manip && <span className={manip.clase}>{manip.txt}</span>}
    </span>
  );
}

export function Sources({ fuentes, extractos }: { fuentes: FuenteMeta[]; extractos: Record<string, string> }) {
  const [abiertas, setAbiertas] = useState<Set<string>>(new Set());
  if (!fuentes.length) return null;

  const porUrl: Record<string, string> = {};
  for (const [u, x] of Object.entries(extractos)) porUrl[normalizarUrl(u)] = x;
  const orden = [...fuentes].sort((a, b) => Number(b.citada !== false) - Number(a.citada !== false));
  const leidas = fuentes.filter((f) => f.extracto || (f.url && porUrl[normalizarUrl(f.url)])).length;

  const alternar = (clave: string) => setAbiertas((prev) => {
    const siguiente = new Set(prev);
    if (siguiente.has(clave)) siguiente.delete(clave);
    else siguiente.add(clave);
    return siguiente;
  });

  return (
    <section className="fuentes-bloque" aria-labelledby="fuentes-titulo">
      <div className="fuentes-cab">
        <div>
          <span className="eyebrow">Evidencia</span>
          <h3 id="fuentes-titulo">Fuentes contrastadas</h3>
        </div>
        <span>{leidas} leídas · {fuentes.length} listadas</span>
      </div>
      <ol className="fuentes-lista">
        {orden.map((f, idx) => {
          const clave = `${f.n ?? idx}-${idx}`;
          const dominio = dominioDe(f.url);
          const extracto = f.extracto ?? (f.url ? porUrl[normalizarUrl(f.url)] : undefined);
          const abierta = abiertas.has(clave);
          const panelId = `evidencia-${clave}`;
          const url = urlSegura(f.url);
          const tendencia = (f.tendencia || "").toLowerCase();
          return (
            <li key={clave} className={`f-fila${f.citada === false ? " no-citada" : ""}`}>
              <div className="f-linea">
                <span className="f-n">{f.n}</span>
                <span className="f-icono"><Globe2 size={17} aria-hidden="true" /></span>
                <div className="fuente-identidad">
                  {url !== "#" ? (
                    <a className="fuente-medio" href={url} target="_blank" rel="noopener noreferrer">
                      {f.medio || dominio || "Fuente"}
                    </a>
                  ) : <span className="fuente-medio">{f.medio || dominio || "Fuente"}</span>}
                  <span className="fuente-dominio">{dominio || "URL no disponible"}</span>
                </div>
                <span className="f-tend" title={TENDENCIA_NOMBRE[tendencia] || "Tendencia no clasificada"}>
                  {TEND_ABREV[tendencia] ?? "sin clasificar"}
                </span>
                <Avisos f={f} />
                <span className={`fuente-rel${f.coincide ? " si" : ""}`}>
                  {f.coincide ? "Respalda" : "Matiza"}
                </span>
                {extracto ? (
                  <button
                    type="button"
                    className="f-toggle"
                    aria-expanded={abierta}
                    aria-controls={panelId}
                    aria-label={`${abierta ? "Ocultar" : "Ver"} evidencia de ${f.medio || dominio || "la fuente"}`}
                    onClick={() => alternar(clave)}
                  >
                    <ChevronDown size={18} aria-hidden="true" />
                  </button>
                ) : <span className="f-sin-lectura">No abierta</span>}
              </div>
              {abierta && extracto && (
                <blockquote className="f-extracto" id={panelId}>
                  <p>{extracto}</p>
                  {url !== "#" && (
                    <a className="f-abrir" href={url} target="_blank" rel="noopener noreferrer">
                      Abrir fuente <ExternalLink size={14} aria-hidden="true" />
                    </a>
                  )}
                </blockquote>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
