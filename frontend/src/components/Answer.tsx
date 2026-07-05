// Una respuesta de Faro: firma + sello del veredicto (+ confianza) + prosa con
// citas enlazadas + fuentes contrastadas. Si el turno falló, muestra el aviso.

import { enlazarCitas, formatear, partirRespuesta } from "../lib/format";
import { selloDe } from "../lib/maps";
import { MiniAvatar } from "./avatars";
import { Sources } from "./Sources";
import type { Turno } from "../lib/types";

export function Answer({ turno }: { turno: Turno }) {
  if (turno.error) return <div className="aviso">{turno.error}</div>;
  if (!turno.respuesta) return null;
  const escribiendo = turno.estado === "respondiendo";

  const { prosa, meta } = partirRespuesta(turno.respuesta);
  const fuentes = meta?.fuentes ?? [];
  const sello = selloDe(meta, prosa);
  const cuerpoHtml = enlazarCitas(formatear(prosa), fuentes);

  // Extractos por url, recogidos de la traza ("ver de dónde salió").
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

  return (
    <div className="veredicto">
      <div className="resp-firma">
        <MiniAvatar />
        <b>Faro</b>
        <span>verifica</span>
      </div>

      {sello && !escribiendo && (
        <div className="sello-fila">
          <span className="pill" data-v={sello.v}>
            <span className="pill-em">{sello.emoji}</span> {sello.etiqueta}
          </span>
          {conf !== null && (
            <span className="conf">
              confianza {conf}%{" "}
              <span className="conf-barra">
                <i style={{ width: conf + "%" }} />
              </span>
            </span>
          )}
        </div>
      )}

      <div className="respuesta-cuerpo" dangerouslySetInnerHTML={{ __html: cuerpoHtml }} />
      {escribiendo && <span className="escribiendo" aria-hidden="true" />}

      {!escribiendo && <Sources fuentes={fuentes} extractos={extractos} />}
    </div>
  );
}
