import { useEffect, useState } from "react";
import {
  Check,
  ChevronDown,
  FileSearch,
  FileText,
  LoaderCircle,
  Play,
  Search,
  X,
} from "lucide-react";
import type { TrazaEvento, Turno } from "../lib/types";

function IconoPaso({ ev }: { ev: TrazaEvento }) {
  if (ev.tipo === "busqueda") return <Search size={17} aria-hidden="true" />;
  if (ev.tipo === "video") return <Play size={17} aria-hidden="true" />;
  return <FileText size={17} aria-hidden="true" />;
}

function EstadoPaso({ ev }: { ev: TrazaEvento }) {
  if (ev.estado === "ok") return <><Check size={16} aria-hidden="true" /><span className="sr-only">Completado</span></>;
  if (ev.estado === "fallo") return <><X size={16} aria-hidden="true" /><span className="sr-only">Falló</span></>;
  return <><LoaderCircle className="giro" size={16} aria-hidden="true" /><span className="sr-only">En curso</span></>;
}

export function Trace({ turno }: { turno: Turno }) {
  const investigando = turno.estado === "investigando";
  const [abierta, setAbierta] = useState(investigando);
  useEffect(() => {
    if (!investigando) setAbierta(false);
  }, [investigando]);

  if (!investigando && turno.eventos.length === 0) return null;
  const lecturas = turno.eventos.filter((e) => e.tipo !== "busqueda" && e.estado === "ok").length;
  const busquedas = turno.eventos.filter((e) => e.tipo === "busqueda").length;
  const fallos = turno.eventos.filter((e) => e.estado === "fallo").length;

  return (
    <section className={`traza${investigando ? " activa" : ""}`} aria-label="Proceso de investigación">
      <button className="traza-cab" type="button" onClick={() => setAbierta((v) => !v)} aria-expanded={abierta}>
        <span className="traza-icono">
          {investigando ? <LoaderCircle className="giro" size={18} aria-hidden="true" /> : <FileSearch size={18} aria-hidden="true" />}
        </span>
        <span className="traza-titulo" role="status" aria-live="polite">
          <strong>{investigando ? "Investigando fuentes" : "Recorrido de investigación"}</strong>
          <small>{busquedas} búsquedas · {lecturas} lecturas{fallos ? ` · ${fallos} sin acceso` : ""}</small>
        </span>
        <ChevronDown className="traza-chevron" size={18} aria-hidden="true" />
      </button>
      {abierta && (
        <ol className="traza-lista">
          {turno.eventos.map((ev) => (
            <li key={ev.id} className="fuente-card" data-estado={ev.estado}>
              <span className="paso-icono"><IconoPaso ev={ev} /></span>
              <span className="fuente-tit">{ev.titulo || ev.dominio || "Fuente sin título"}</span>
              <span className="fuente-estado"><EstadoPaso ev={ev} /></span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
