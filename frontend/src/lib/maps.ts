// Mapas de presentación (sello del veredicto, credibilidad, manipulación,
// tendencia), portados del frontend original.

import type { Meta } from "./types";

export interface Sello {
  etiqueta: string;
  v: string;
  emoji: string;
}

export const SELLOS: Record<string, Sello> = {
  verdadero: { etiqueta: "Verdadero", v: "true", emoji: "✅" },
  falso: { etiqueta: "Falso", v: "false", emoji: "❌" },
  enganoso: { etiqueta: "Engañoso", v: "warn", emoji: "⚠️" },
  fuera_de_contexto: { etiqueta: "Sacado de contexto", v: "warn", emoji: "🔀" },
  prediccion: { etiqueta: "Predicción", v: "muted", emoji: "🔮" },
  sin_evidencia: { etiqueta: "Sin evidencia", v: "muted", emoji: "❓" },
  informativo: { etiqueta: "Información", v: "info", emoji: "ℹ️" },
  no_verificable: { etiqueta: "No verificable", v: "muted", emoji: "💬" },
};

// Respaldo: si faltara el JSON, detectamos el sello por el emoji de la prosa.
const SELLO_POR_EMOJI: Record<string, string> = {
  "✅": "verdadero",
  "❌": "falso",
  "⚠": "enganoso",
  "🔀": "fuera_de_contexto",
  "🔮": "prediccion",
  "❓": "sin_evidencia",
  ℹ: "informativo",
};

export const CREDIBILIDAD: Record<string, { txt: string; clase: string }> = {
  alta: { txt: "alta", clase: "b-alta" },
  media: { txt: "media", clase: "b-media" },
  baja: { txt: "baja", clase: "b-baja" },
  no_fiable: { txt: "no fiable", clase: "b-no" },
};

// Aviso de honestidad por fuente. "ninguna" no pinta nada: el badge solo aparece
// cuando hay algo que advertir.
export const MANIPULACION: Record<string, { txt: string; clase: string }> = {
  sesgo: { txt: "sesgo", clase: "m-sesgo" },
  enganosa: { txt: "engañosa", clase: "m-eng" },
  desinformadora: { txt: "desinforma", clase: "m-desinfo" },
};

export const TEND_CLASE: Record<string, string> = {
  izquierda: "t-izq",
  "centro-izquierda": "t-izq",
  centro: "t-cen",
  "centro-derecha": "t-der",
  derecha: "t-der",
  verificador: "t-ver",
  internacional: "t-int",
};

// Determina el sello: primero por el campo `veredicto` del JSON; si falta, por
// el emoji que aparezca en la prosa.
export function selloDe(meta: Meta | null, prosa: string): Sello | null {
  const clave =
    meta && typeof meta.veredicto === "string" ? meta.veredicto.toLowerCase().trim() : null;
  if (clave && SELLOS[clave]) return SELLOS[clave];
  for (const [emoji, k] of Object.entries(SELLO_POR_EMOJI)) {
    if (prosa.includes(emoji)) return SELLOS[k];
  }
  return null;
}

// Nombre legible de un país por su código ISO (los más citados); si no está,
// se muestra el valor tal cual (puede venir ya como nombre).
const PAISES: Record<string, string> = {
  CO: "Colombia", MX: "México", AR: "Argentina", ES: "España", CL: "Chile",
  PE: "Perú", VE: "Venezuela", US: "EE. UU.", UY: "Uruguay", EC: "Ecuador",
  BO: "Bolivia", PY: "Paraguay", CR: "Costa Rica", GT: "Guatemala",
  BR: "Brasil", FR: "Francia", DE: "Alemania", IT: "Italia",
  GB: "Reino Unido", PT: "Portugal",
};

export function nombrePais(codigo: string | undefined): string | null {
  if (!codigo || !codigo.trim()) return null;
  const c = codigo.trim();
  return PAISES[c.toUpperCase()] ?? c;
}
