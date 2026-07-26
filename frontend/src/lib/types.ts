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
  tipo_fuente?: string;
  url?: string;
  coincide?: boolean;
  extracto?: string;
  citada?: boolean;
}

export type TipoConsulta = "afirmacion" | "pregunta" | "mecanismo";

export interface Aviso {
  codigo: "nada_encontrado" | "sin_abrir";
  texto: string;
}

export interface Meta {
  tipo?: TipoConsulta;
  veredicto?: string;
  solidez?: number;
  solidez_modelo?: number;
  aviso?: Aviso;
  resumen?: string;
  pais?: string;
  fuentes?: FuenteMeta[];
  evidencia?: {
    listadas: number;
    leidas: number;
    citadas: number;
    dominios_independientes: number;
    respaldan: number;
    matizan: number;
    diversidad_editorial: number;
  };
}

export interface Opciones {
  rigor: string;
  largo: string;
  detalle: string;
  pais?: string;
}

export interface Turno {
  id: string;
  pregunta: string;
  opciones: Opciones;
  eventos: TrazaEvento[];
  estado: "investigando" | "respondiendo" | "listo" | "cancelado" | "error";
  respuesta?: string;
  error?: string;
}
