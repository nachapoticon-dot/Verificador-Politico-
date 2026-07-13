// Separación del contrato de respuesta y utilidades canónicas de URL. La prosa
// se renderiza como nodos React en RichText; este módulo nunca produce HTML.

import type { Meta } from "./types";

// Separa la prosa del bloque ```json final (el contrato de datos del medidor).
// Durante el streaming el bloque puede llegar a medias: también se oculta.
export function partirRespuesta(texto: string): { prosa: string; meta: Meta | null } {
  const m = texto.match(/```json\s*([\s\S]*?)```\s*$/i);
  if (m) {
    let meta: Meta | null = null;
    try {
      meta = JSON.parse(m[1].trim());
    } catch {
      /* JSON inválido: lo ignoramos */
    }
    return { prosa: texto.slice(0, m.index).trim(), meta };
  }
  const abierto = texto.search(/```json/i);
  if (abierto !== -1) return { prosa: texto.slice(0, abierto).trim(), meta: null };
  return { prosa: texto.trim(), meta: null };
}

// Solo http/https son navegables; cualquier otra cosa se neutraliza a "#".
export function urlSegura(u: string | undefined): string {
  try {
    const p = new URL(u ?? "");
    return p.protocol === "http:" || p.protocol === "https:" ? u! : "#";
  } catch {
    return "#";
  }
}

// Clave canónica de una URL (port de verificador/urls.py): sin esquema, sin
// www., sin parámetros de tracking, sin barra final ni fragmento.
const TRACKING = new Set(["fbclid", "gclid", "igshid", "mc_cid", "mc_eid"]);

export function normalizarUrl(u: string | undefined): string {
  if (!u || !u.trim()) return "";
  const crudo = u.trim();
  let p: URL;
  try {
    p = new URL(crudo.includes("://") ? crudo : "http://" + crudo);
  } catch {
    return crudo.toLowerCase();
  }
  let host = p.hostname.toLowerCase();
  if (host.startsWith("www.")) host = host.slice(4);
  const ruta = p.pathname.replace(/\/+$/, "");
  const pares: string[] = [];
  p.searchParams.forEach((v, k) => {
    const kl = k.toLowerCase();
    if (kl.startsWith("utm_") || TRACKING.has(kl)) return;
    pares.push(encodeURIComponent(k) + "=" + encodeURIComponent(v));
  });
  return host + ruta + (pares.length ? "?" + pares.join("&") : "");
}

export function dominioDe(u: string | undefined): string {
  try {
    const host = new URL(u ?? "").hostname.toLowerCase();
    return host.startsWith("www.") ? host.slice(4) : host;
  } catch {
    return "";
  }
}
