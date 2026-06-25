// Traza de investigación en vivo: cada búsqueda/lectura como una tarjeta que pasa
// de "buscando…/leyendo…" a ✓ o ✗.

import type { TrazaEvento, Turno } from "../lib/types";

const ETIQUETAS: Record<string, string> = {
  buscando: "buscando…",
  leyendo: "leyendo…",
  ok: "✓",
  fallo: "✗",
};

function Favicon({ ev }: { ev: TrazaEvento }) {
  if (ev.dominio) {
    return (
      <img
        className="fav"
        alt=""
        src={
          "https://www.google.com/s2/favicons?domain=" +
          encodeURIComponent(ev.dominio) +
          "&sz=32"
        }
      />
    );
  }
  const icono = ev.tipo === "busqueda" ? "🔎" : ev.tipo === "video" ? "▶" : "📄";
  return <span className="fav fav--q">{icono}</span>;
}

export function Trace({ turno }: { turno: Turno }) {
  // Si la respuesta llegó sin ningún paso, la traza no aporta: no se muestra.
  if (turno.estado !== "investigando" && turno.eventos.length === 0) return null;

  const cerrada = turno.estado !== "investigando";

  return (
    <div className={"traza" + (cerrada ? " cerrada" : "")}>
      <div className="traza-cab">
        <span className="dot" />
        {cerrada ? "investigación cerrada" : "investigando"}
      </div>
      {turno.eventos.map((ev) => (
        <div key={ev.id} className="fuente-card" data-estado={ev.estado}>
          <Favicon ev={ev} />
          <span className="fuente-tit">{ev.titulo || ev.dominio || ""}</span>
          <span className="fuente-estado">{ETIQUETAS[ev.estado] || ""}</span>
        </div>
      ))}
    </div>
  );
}
