import { useEffect, useRef, useState } from "react";
import { Globe2, Plus, Send, Square } from "lucide-react";
import { FaroAvatar, MiniAvatar } from "./components/avatars";
import { Trace } from "./components/Trace";
import { Answer } from "./components/Answer";
import { useVerificador } from "./hooks/useVerificador";
import { nombrePais } from "./lib/maps";
import type { Opciones, Turno } from "./lib/types";

interface Preset {
  valor: string;
  texto: string;
  aria: string;
  opciones: Omit<Opciones, "pais">;
}

const PRESETS: Preset[] = [
  {
    valor: "esencial",
    texto: "Esencial",
    aria: "Esencial: investigación rigurosa y respuesta breve",
    opciones: { rigor: "riguroso", largo: "corta", detalle: "simple" },
  },
  {
    valor: "normal",
    texto: "Normal",
    aria: "Normal: investigación rigurosa con contexto breve",
    opciones: { rigor: "riguroso", largo: "normal", detalle: "simple" },
  },
  {
    valor: "afondo",
    texto: "A fondo",
    aria: "A fondo: investigación rigurosa, cifras y contexto técnico",
    opciones: { rigor: "riguroso", largo: "detallada", detalle: "tecnico" },
  },
];

const PAISES = [
  ["", "País automático"], ["AR", "Argentina"], ["BO", "Bolivia"],
  ["BR", "Brasil"], ["CL", "Chile"], ["CO", "Colombia"],
  ["CR", "Costa Rica"], ["EC", "Ecuador"], ["ES", "España"],
  ["GT", "Guatemala"], ["MX", "México"], ["PE", "Perú"],
  ["PY", "Paraguay"], ["US", "Estados Unidos"], ["UY", "Uruguay"],
  ["VE", "Venezuela"], ["GB", "Reino Unido"], ["FR", "Francia"],
] as const;

function Masthead({ hayTurnos, enCurso, onNuevo }: { hayTurnos: boolean; enCurso: boolean; onNuevo: () => void }) {
  return (
    <header className="masthead">
      <div className="masthead-inner">
        <button className="brand" type="button" onClick={onNuevo} aria-label="Faro, nueva verificación">
          <span className="brand-face" aria-hidden="true"><MiniAvatar /></span>
          <span className="brand-text">
            <span className="brand-name">Faro</span>
          </span>
        </button>
        {hayTurnos && (
          <button className="nuevo" type="button" onClick={onNuevo} disabled={enCurso}>
            <Plus size={18} aria-hidden="true" />
            <span>Nueva verificación</span>
          </button>
        )}
      </div>
    </header>
  );
}

function EmptyState() {
  return (
    <section className="inicio" aria-labelledby="inicio-titulo">
      <figure className="welcome-portrait">
        <FaroAvatar />
      </figure>
      <div className="inicio-copy">
        <span className="eyebrow">Hola, soy Faro</span>
        <h1 id="inicio-titulo">Cuéntame qué has oído.</h1>
      </div>
    </section>
  );
}

function TurnoView({
  turno,
  indice,
  onReintentar,
}: {
  turno: Turno;
  indice: number;
  onReintentar: () => void;
}) {
  const preset = PRESETS.find((p) => p.opciones.largo === turno.opciones.largo)?.texto ?? "Normal";
  const pais = nombrePais(turno.opciones.pais);
  return (
    <article className="turno" aria-labelledby={`consulta-${turno.id}`}>
      <header className="msg-consulta">
        <div className="consulta-meta">
          <span>Consulta {indice + 1}</span>
          <span>{preset}</span>
          {pais && <span>{pais}</span>}
        </div>
        <h2 id={`consulta-${turno.id}`}>{turno.pregunta}</h2>
      </header>
      <Trace turno={turno} />
      <Answer turno={turno} onReintentar={onReintentar} />
    </article>
  );
}

function Composer({
  enCurso,
  preset,
  pais,
  texto,
  setTexto,
  setPreset,
  setPais,
  onEnviar,
  onDetener,
}: {
  enCurso: boolean;
  preset: string;
  pais: string;
  texto: string;
  setTexto: (texto: string) => void;
  setPreset: (preset: string) => void;
  setPais: (pais: string) => void;
  onEnviar: () => void;
  onDetener: () => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
  }, [texto]);

  return (
    <div className="composer-dock">
      <form className="composer" onSubmit={(e) => { e.preventDefault(); onEnviar(); }}>
        <textarea
          ref={ref}
          rows={1}
          value={texto}
          maxLength={4000}
          placeholder="Escribí una afirmación, una cita o una pregunta política…"
          aria-label="Afirmación o pregunta política"
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onEnviar();
            }
          }}
        />
        <div className="composer-barra">
          <label className="pais-control">
            <Globe2 size={17} aria-hidden="true" />
            <span className="sr-only">País</span>
            <select value={pais} onChange={(e) => setPais(e.target.value)} disabled={enCurso}>
              {PAISES.map(([codigo, nombre]) => <option key={codigo || "auto"} value={codigo}>{nombre}</option>)}
            </select>
          </label>
          <div className="seg" role="group" aria-label="Profundidad del análisis">
            {PRESETS.map((p) => (
              <button
                key={p.valor}
                type="button"
                className={`seg-opt${preset === p.valor ? " is-on" : ""}`}
                aria-label={p.aria}
                aria-pressed={preset === p.valor}
                disabled={enCurso}
                onClick={() => setPreset(p.valor)}
              >
                {p.texto}
              </button>
            ))}
          </div>
          {enCurso ? (
            <button className="detener" type="button" onClick={onDetener} aria-label="Detener verificación">
              <Square size={15} fill="currentColor" aria-hidden="true" />
            </button>
          ) : (
            <button className="enviar" type="submit" disabled={!texto.trim()} aria-label="Verificar">
              <Send size={17} aria-hidden="true" />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

export default function App() {
  const { turnos, enCurso, preguntar, detener, limpiar } = useVerificador();
  const [preset, setPreset] = useState("normal");
  const [pais, setPais] = useState("");
  const [texto, setTexto] = useState("");
  const finRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (turnos.length > 0) finRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turnos.length]);

  const enviar = () => {
    const pregunta = texto.trim();
    if (!pregunta || enCurso) return;
    const opcionesBase = (PRESETS.find((p) => p.valor === preset) ?? PRESETS[1]).opciones;
    preguntar(pregunta, { ...opcionesBase, pais: pais || undefined });
    setTexto("");
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#contenido">Saltar al contenido</a>
      <Masthead hayTurnos={turnos.length > 0} enCurso={enCurso} onNuevo={limpiar} />
      <main className="workspace" id="contenido">
        {turnos.length === 0 ? <EmptyState /> : (
          <div className="hilo">
            {turnos.map((turno, i) => (
              <TurnoView
                key={turno.id}
                turno={turno}
                indice={i}
                onReintentar={() => preguntar(turno.pregunta, turno.opciones)}
              />
            ))}
          </div>
        )}
        <div ref={finRef} />
      </main>
      <Composer
        enCurso={enCurso}
        preset={preset}
        pais={pais}
        texto={texto}
        setTexto={setTexto}
        setPreset={setPreset}
        setPais={setPais}
        onEnviar={enviar}
        onDetener={detener}
      />
    </div>
  );
}
