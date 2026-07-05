// Contratos compartidos entre el stream SSE, el hook y los componentes.

export type EstadoPaso = "buscando" | "leyendo" | "ok" | "fallo";
export type TipoPaso = "busqueda" | "pagina" | "video";

export interface TrazaEvento {
  id: string;
  tipo: TipoPaso;
  estado: EstadoPaso;
  titulo: string | null;
  url: string | null;
  dominio: string | null;
  extracto?: string;
}

export interface FuenteMeta {
  n: number;
  medio?: string;
  tendencia?: string;
  credibilidad?: string;
  manipulacion?: string;
  url?: string;
  coincide?: boolean;
}

export interface Meta {
  veredicto?: string;
  confianza?: number;
  resumen?: string;
  pais?: string;
  fuentes?: FuenteMeta[];
}

export interface Opciones {
  rigor: string;
  largo: string;
  detalle: string;
}

export interface Turno {
  id: string;
  pregunta: string;
  eventos: TrazaEvento[];
  estado: "investigando" | "respondiendo" | "listo" | "error";
  respuesta?: string;
  error?: string;
}
