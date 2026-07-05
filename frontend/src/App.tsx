import { useEffect, useRef, useState } from "react";
import { FaroAvatar, MiniAvatar } from "./components/avatars";
import { Trace } from "./components/Trace";
import { Answer } from "./components/Answer";
import { useVerificador } from "./hooks/useVerificador";
import type { Opciones, Turno } from "./lib/types";

interface Preset {
  valor: string;
  texto: string;
  titulo: string;
  opciones: Opciones;
}

// Un solo eje de modo: cada preset fija rigor + largo + detalle de la API.
const PRESETS: Preset[] = [
  {
    valor: "esencial",
    texto: "Esencial",
    titulo: "Menos fuentes, respuesta en segundos.",
    opciones: { rigor: "rapido", largo: "corta", detalle: "simple" },
  },
  {
    valor: "normal",
    texto: "Normal",
    titulo: "Contraste completo, un párrafo.",
    opciones: { rigor: "riguroso", largo: "normal", detalle: "simple" },
  },
  {
    valor: "afondo",
    texto: "A fondo",
    titulo: "Contexto, matices y cifras.",
    opciones: { rigor: "riguroso", largo: "detallada", detalle: "tecnico" },
  },
];

function Masthead() {
  return (
    <header className="masthead">
      <a
        className="brand"
        href="/"
        aria-label="Faro, inicio"
        title="Faro — Frente A la Réplica de lo falsO"
      >
        <span className="brand-face" aria-hidden="true">
          <MiniAvatar />
        </span>
        <span className="brand-text">
          <span className="brand-name">Faro</span>
          <span className="brand-sub">frente a lo falso</span>
        </span>
      </a>
    </header>
  );
}

function Hero() {
  return (
    <section className="hero">
      <figure className="hero-retrato">
        <span className="retrato-disco" aria-hidden="true" />
        <FaroAvatar />
      </figure>
      <div className="hero-copy">
        <h1 className="hero-title">Cuéntame qué has&nbsp;oído.</h1>
      </div>
    </section>
  );
}

function TurnoView({ turno }: { turno: Turno }) {
  return (
    <>
      <div className="msg msg-consulta">
        <span className="q-mark">Consulta</span>
        <p>{turno.pregunta}</p>
      </div>
      <div className="msg">
        <Trace turno={turno} />
        <Answer turno={turno} />
      </div>
    </>
  );
}

function Composer({
  enCurso,
  preset,
  setPreset,
  onEnviar,
}: {
  enCurso: boolean;
  preset: string;
  setPreset: (p: string) => void;
  onEnviar: (texto: string) => void;
}) {
  const [texto, setTexto] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, window.innerHeight * 0.4) + "px";
  }, [texto]);

  const enviar = () => {
    const q = texto.trim();
    if (!q || enCurso) return;
    onEnviar(q);
    setTexto("");
  };

  return (
    <form
      className="composer"
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        enviar();
      }}
    >
      <div className="composer-inner">
        <textarea
          ref={ref}
          rows={1}
          value={texto}
          placeholder="Dime qué quieres que verifique…"
          aria-label="Tu pregunta o afirmación"
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              enviar();
            }
          }}
        />
        <div className="composer-pie">
          <div className="seg" role="group" aria-label="Modo de respuesta">
            {PRESETS.map((p) => (
              <button
                key={p.valor}
                type="button"
                title={p.titulo}
                className={"seg-opt" + (preset === p.valor ? " is-on" : "")}
                aria-pressed={preset === p.valor}
                onClick={() => setPreset(p.valor)}
              >
                {p.texto}
              </button>
            ))}
          </div>
          <button className="enviar" type="submit" aria-label="Validar" disabled={enCurso}>
            <span>Validar</span>
            <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
              <path
                d="M5 12h14M13 6l6 6-6 6"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        </div>
      </div>
    </form>
  );
}

export default function App() {
  const { turnos, enCurso, preguntar } = useVerificador();
  const [preset, setPreset] = useState("normal");
  const finRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turnos]);

  const opciones = (PRESETS.find((p) => p.valor === preset) ?? PRESETS[1]).opciones;
  return (
    <>
      <div className="grain" aria-hidden="true" />
      <Masthead />
      <main className="hilo">
        {turnos.length === 0 && <Hero />}
        {turnos.map((t) => (
          <TurnoView key={t.id} turno={t} />
        ))}
        <div ref={finRef} />
      </main>
      <Composer enCurso={enCurso} preset={preset} setPreset={setPreset}
                onEnviar={(q) => preguntar(q, opciones)} />
    </>
  );
}
