import { useRef, useState, type CSSProperties } from "react";
import { Check, Copy, RotateCcw } from "lucide-react";
import { enPalabras, normalizarUrl, partirRespuesta } from "../lib/format";
import { nombrePais, selloDe } from "../lib/maps";
import { RichText } from "./RichText";
import { ListaFuentes, NotaMargen } from "./Sources";
import type { FuenteMeta, Meta, Turno } from "../lib/types";

// Alto estimado de una nota al margen. Solo se usa para que la nota no se
// ancle tan abajo que desborde el bloque; errar por poco no se nota.
const ALTO_NOTA = 260;

/** La glosa dice de qué está hecha la solidez. Sustituye a la rejilla de tres
 *  celdas: la misma información, en una línea que se lee como una frase. */
function glosaDe(meta: Meta | null): string | null {
  const partes: string[] = [];
  const e = meta?.evidencia;
  if (e && e.leidas > 0) {
    partes.push(`${enPalabras(e.leidas)} ${e.leidas === 1 ? "fuente leída" : "fuentes leídas"}`);
    if (e.dominios_independientes > 1) {
      partes.push(`${enPalabras(e.dominios_independientes)} dominios independientes`);
    }
    if (e.matizan > 0) {
      partes.push(`${enPalabras(e.matizan)} ${e.matizan === 1 ? "matiza" : "matizan"}`);
    }
  }
  const pais = nombrePais(meta?.pais);
  if (pais) partes.push(pais);
  return partes.length ? partes.join(" · ") : null;
}

export function Answer({ turno, onReintentar }: { turno: Turno; onReintentar: () => void }) {
  const [copiado, setCopiado] = useState(false);
  const [cita, setCita] = useState<{ n: number; y: number } | null>(null);
  const [lista, setLista] = useState(false);
  const grid = useRef<HTMLDivElement>(null);

  if (turno.error) return (
    <div className="aviso" role="alert">
      <span>{turno.error}</span>
      <button type="button" onClick={onReintentar}>
        <RotateCcw size={16} aria-hidden="true" />
        Reintentar
      </button>
    </div>
  );
  if (turno.estado === "cancelado" && !turno.respuesta) {
    return <div className="estado-cancelado" role="status">Verificación detenida.</div>;
  }
  if (!turno.respuesta) return null;

  const escribiendo = turno.estado === "respondiendo";
  const { prosa, meta } = partirRespuesta(turno.respuesta);
  const fuentes = meta?.fuentes ?? [];
  const sello = selloDe(meta, prosa);
  const glosa = glosaDe(meta);

  const conf =
    meta && typeof meta.solidez === "number" && Number.isFinite(meta.solidez)
      ? Math.max(0, Math.min(100, Math.round(meta.solidez)))
      : null;

  // Extractos de la traza, indexados por URL canónica: la fuente del meta y el
  // evento de lectura pueden traer la misma página escrita distinto.
  const porUrl: Record<string, string> = {};
  for (const ev of turno.eventos) {
    if (ev.url && ev.extracto) porUrl[normalizarUrl(ev.url)] = ev.extracto;
  }
  const extractoDe = (f: FuenteMeta) =>
    f.extracto ?? (f.url ? porUrl[normalizarUrl(f.url)] : undefined);

  const fuenteActiva = cita ? fuentes.find((f) => f.n === cita.n) : undefined;

  // Un segundo toque sobre la misma cita apaga la nota: invocar y retirar son
  // el mismo gesto, como encender y apagar una luz.
  const invocar = (n: number, el: HTMLElement) => {
    if (cita?.n === n) {
      setCita(null);
      return;
    }
    const caja = grid.current?.getBoundingClientRect();
    if (!caja) {
      setCita({ n, y: 0 });
      return;
    }
    const bruto = el.getBoundingClientRect().top - caja.top;
    setCita({ n, y: Math.max(0, Math.min(bruto, caja.height - ALTO_NOTA)) });
  };

  const copiar = async () => {
    const referencias = fuentes
      .filter((f) => f.url)
      .map((f) => `[${f.n}] ${f.medio || f.url}: ${f.url}`)
      .join("\n");
    try {
      await navigator.clipboard.writeText(`${prosa}${referencias ? `\n\nFuentes\n${referencias}` : ""}`);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 1800);
    } catch {
      setCopiado(false);
    }
  };

  return (
    <section className="pieza" aria-label="Resultado de la verificación">
      {/* La cabecera existe aunque no haya sello: en pregunta y mecanismo
          `selloDe` devuelve null a propósito, pero la solidez sigue siendo un
          dato real y no puede cambiar de sitio según el tipo de consulta. */}
      {!escribiendo && (sello || conf !== null) && (
        <header className="dictamen" data-v={sello?.v}>
          <div className="dictamen-linea">
            {sello && <h2 className="dictamen-sello">{sello.etiqueta}</h2>}
            {conf !== null && (
              <p className="dictamen-solidez">
                <span>solidez</span>
                <b>{conf}</b>
              </p>
            )}
          </div>
          {/* La regla mide lo que mide la evidencia: su largo ES la solidez.
              La estructura carga el dato en vez de decorarlo. */}
          <div className="regla" role="presentation">
            <span style={{ "--k": (conf ?? 0) / 100 } as CSSProperties} />
          </div>
          {glosa && <p className="glosa">{glosa}</p>}
        </header>
      )}

      <div className="pieza-grid" ref={grid}>
        <div className="pieza-col">
          {meta?.resumen && !escribiendo && <p className="entradilla">{meta.resumen}</p>}
          {meta?.aviso && <p className="salvedad" role="status">{meta.aviso.texto}</p>}

          <RichText
            texto={prosa}
            fuentes={fuentes}
            citaActiva={cita?.n ?? null}
            onCita={invocar}
          />
          {escribiendo && (
            <span className="escribiendo"><span className="sr-only">Redactando respuesta</span></span>
          )}

          {!escribiendo && (
            <footer className="pie">
              {fuentes.length > 0 && (
                <button
                  className="pie-accion"
                  type="button"
                  aria-expanded={lista}
                  onClick={() => setLista(!lista)}
                >
                  {lista ? "Ocultar las fuentes" : `Ver las ${enPalabras(fuentes.length)} fuentes`}
                </button>
              )}
              <button className="pie-accion" type="button" onClick={copiar}>
                {copiado ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
                {copiado ? "Copiado" : "Copiar"}
              </button>
            </footer>
          )}

          {!escribiendo && lista && (
            <ListaFuentes fuentes={fuentes} activa={cita?.n ?? null} onInvocar={invocar} />
          )}
        </div>

        <aside className="margen">
          {fuenteActiva && cita && (
            <NotaMargen
              fuente={fuenteActiva}
              extracto={extractoDe(fuenteActiva)}
              y={cita.y}
              onCerrar={() => setCita(null)}
            />
          )}
        </aside>
      </div>
    </section>
  );
}
