import { useEffect, useRef, useState } from "react";
import { TomasAvatar, MiniAvatar } from "./components/avatars";
import { Trace } from "./components/Trace";
import { Answer } from "./components/Answer";
import { useVerificador } from "./hooks/useVerificador";
import type { Opciones, Turno } from "./lib/types";

interface OpcionSeg {
  valor: string;
  texto: string;
  titulo: string;
}

const CONTROLES: { clave: keyof Opciones; etiqueta: string; aria: string; opciones: OpcionSeg[] }[] = [
  {
    clave: "rigor",
    etiqueta: "Profundidad",
    aria: "Profundidad del análisis",
    opciones: [
      { valor: "rapido", texto: "Rápido", titulo: "Menos fuentes, respuesta más rápida." },
      { valor: "riguroso", texto: "A fondo", titulo: "Más fuentes y contraste." },
    ],
  },
  {
    clave: "largo",
    etiqueta: "Respuesta",
    aria: "Largo de la respuesta",
    opciones: [
      { valor: "corta", texto: "Corta", titulo: "1-2 frases." },
      { valor: "normal", texto: "Normal", titulo: "Un párrafo." },
      { valor: "detallada", texto: "Detallada", titulo: "Con contexto y matices." },
    ],
  },
  {
    clave: "detalle",
    etiqueta: "Detalle",
    aria: "Nivel de detalle",
    opciones: [
      { valor: "simple", texto: "Simple", titulo: "Lenguaje llano." },
      { valor: "tecnico", texto: "Técnico", titulo: "Cifras y metodología." },
    ],
  },
];

function Masthead({ modo, setModo }: { modo: Opciones; setModo: (m: Opciones) => void }) {
  return (
    <header className="masthead">
      <a className="brand" href="/" aria-label="Tomás, inicio">
        <span className="brand-face" aria-hidden="true">
          <MiniAvatar />
        </span>
        <span className="brand-text">
          <span className="brand-name">Tomás</span>
          <span className="brand-sub">análisis factual</span>
        </span>
      </a>
      <div className="controls">
        {CONTROLES.map((ctrl) => (
          <div className="ctrl" key={ctrl.clave}>
            <span className="ctrl-lbl">{ctrl.etiqueta}</span>
            <div className="seg" role="group" aria-label={ctrl.aria}>
              {ctrl.opciones.map((op) => (
                <button
                  key={op.valor}
                  type="button"
                  title={op.titulo}
                  className={"seg-opt" + (modo[ctrl.clave] === op.valor ? " is-on" : "")}
                  aria-pressed={modo[ctrl.clave] === op.valor}
                  onClick={() => setModo({ ...modo, [ctrl.clave]: op.valor })}
                >
                  {op.texto}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="hero">
      <figure className="hero-retrato">
        <span className="retrato-disco" aria-hidden="true" />
        <TomasAvatar />
      </figure>
      <div className="hero-copy">
        <h1 className="hero-title">Cuéntame qué has&nbsp;oído.</h1>
        <p className="hero-lead">Y te digo si es verdad —con las pruebas a la vista.</p>
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

function Composer({ enCurso, onEnviar }: { enCurso: boolean; onEnviar: (texto: string) => void }) {
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
        <button type="submit" aria-label="Validar" disabled={enCurso}>
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
    </form>
  );
}

export default function App() {
  const { turnos, enCurso, preguntar } = useVerificador();
  const [modo, setModo] = useState<Opciones>({
    rigor: "riguroso",
    largo: "corta",
    detalle: "simple",
  });
  const finRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turnos]);

  return (
    <>
      <div className="grain" aria-hidden="true" />
      <Masthead modo={modo} setModo={setModo} />
      <main className="hilo">
        {turnos.length === 0 && <Hero />}
        {turnos.map((t) => (
          <TurnoView key={t.id} turno={t} />
        ))}
        <div ref={finRef} />
      </main>
      <Composer enCurso={enCurso} onEnviar={(q) => preguntar(q, modo)} />
    </>
  );
}
