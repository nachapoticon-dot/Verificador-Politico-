import { useState } from "react";
import {
  Check,
  CircleCheck,
  CircleHelp,
  Copy,
  Info,
  Scale,
  RotateCcw,
  TriangleAlert,
  X,
} from "lucide-react";
import { partirRespuesta } from "../lib/format";
import { nombrePais, selloDe } from "../lib/maps";
import { MiniAvatar } from "./avatars";
import { RichText } from "./RichText";
import { Sources } from "./Sources";
import type { Turno } from "../lib/types";

function IconoVeredicto({ valor }: { valor: string }) {
  const props = { size: 20, strokeWidth: 2.2, "aria-hidden": true as const };
  if (valor === "true") return <CircleCheck {...props} />;
  if (valor === "false") return <X {...props} />;
  if (valor === "warn") return <TriangleAlert {...props} />;
  if (valor === "info") return <Info {...props} />;
  return <CircleHelp {...props} />;
}

export function Answer({ turno, onReintentar }: { turno: Turno; onReintentar: () => void }) {
  const [copiado, setCopiado] = useState(false);
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
  const pais = nombrePais(meta?.pais);
  const extractos: Record<string, string> = {};
  for (const ev of turno.eventos) {
    if (ev.url && ev.extracto) extractos[ev.url] = ev.extracto;
  }

  const conf =
    meta &&
    meta.veredicto !== "informativo" &&
    meta.veredicto !== "no_verificable" &&
    typeof meta.confianza === "number" &&
    Number.isFinite(meta.confianza)
      ? Math.max(0, Math.min(100, Math.round(meta.confianza)))
      : null;
  const evidencia = meta?.evidencia;

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
    <section className="veredicto" aria-label="Resultado de la verificación">
      <div className="resp-firma">
        <MiniAvatar />
        <div>
          <b>Faro</b>
          <span>análisis{pais ? ` · ${pais}` : ""}</span>
        </div>
        {!escribiendo && (
          <button className="accion-icono" type="button" onClick={copiar} aria-label="Copiar análisis">
            {copiado ? <Check size={17} aria-hidden="true" /> : <Copy size={17} aria-hidden="true" />}
            <span>{copiado ? "Copiado" : "Copiar"}</span>
          </button>
        )}
      </div>

      {sello && !escribiendo && (
        <div className="sello-banda" data-v={sello.v}>
          <span className="sello-etiqueta">
            <IconoVeredicto valor={sello.v} />
            {sello.etiqueta}
          </span>
          {conf !== null && (
            <div className="conf">
              <span>Solidez de la evidencia</span>
              <strong>{conf}%</strong>
              <progress value={conf} max={100} aria-label={`Solidez de la evidencia: ${conf}%`} />
            </div>
          )}
        </div>
      )}

      {meta?.resumen && !escribiendo && <h2 className="resp-titular">{meta.resumen}</h2>}
      <RichText texto={prosa} fuentes={fuentes} />
      {escribiendo && <span className="escribiendo"><span className="sr-only">Redactando respuesta</span></span>}

      {!escribiendo && evidencia && evidencia.leidas > 0 && (
        <div className="evidencia-resumen" aria-label="Resumen de evidencia">
          <div><span>Evidencia leída</span><strong>{evidencia.leidas}</strong></div>
          <div><span>Dominios distintos</span><strong>{evidencia.dominios_independientes}</strong></div>
          <div>
            <span>Contraste</span>
            <strong>{evidencia.respaldan} / {evidencia.matizan}</strong>
            <small>respaldan / matizan</small>
          </div>
          <Scale size={20} aria-hidden="true" />
        </div>
      )}

      {!escribiendo && <Sources fuentes={fuentes} extractos={extractos} />}
    </section>
  );
}
