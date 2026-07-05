// Formateo de la prosa de la respuesta, portado del frontend original. Devuelve
// HTML como string (se inyecta con dangerouslySetInnerHTML), por lo que TODO se
// escapa primero: el contrato es "escapar → negrita → enlazar".

import type { FuenteMeta, Meta } from "./types";

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

function escapar(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function negrita(s: string): string {
  return s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function enlazar(s: string): string {
  // [texto](url)
  s = s.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  );
  // URLs sueltas que no estén ya dentro de un href.
  s = s.replace(
    /(^|[\s(])(https?:\/\/[^\s<)]+)/g,
    (_m, pre, url) =>
      pre + '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + "</a>",
  );
  return s;
}

function enLinea(s: string): string {
  return enlazar(negrita(escapar(s)));
}

function formatearBloque(bloque: string): string {
  const lineas = bloque.split("\n").filter((l) => l.trim());
  const esVinieta = (l: string) => /^[-*]\s+/.test(l.trim());
  if (lineas.length && lineas.every(esVinieta)) {
    const items = lineas
      .map((l) => "<li>" + enLinea(l.trim().replace(/^[-*]\s+/, "")) + "</li>")
      .join("");
    return "<ul class='resp-lista'>" + items + "</ul>";
  }
  const html = lineas
    .map((l) => {
      const h = l.match(/^#{1,6}\s*(.+)$/);
      return h ? "<strong>" + enLinea(h[1]) + "</strong>" : enLinea(l);
    })
    .join("<br>");
  return "<p>" + html + "</p>";
}

// Párrafos, **negrita**, enlaces, viñetas; encabezados markdown degradados a
// negrita (nunca se muestran "###" crudos).
export function formatear(texto: string): string {
  const bloques = texto
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
  return bloques.map(formatearBloque).join("");
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

// Convierte referencias [n] en la prosa (ya escapada y formateada) en enlaces a
// la fuente n. La URL pasa por urlSegura y encodeURI.
export function enlazarCitas(texto: string, fuentes: FuenteMeta[]): string {
  const porN: Record<number, FuenteMeta> = {};
  (fuentes || []).forEach((f) => {
    porN[f.n] = f;
  });
  return texto.replace(/\[(\d+)\]/g, (m, n) => {
    const f = porN[Number(n)];
    if (!f) return m;
    const titulo = f.medio ? ' title="' + String(f.medio).replace(/"/g, "&quot;") + '"' : "";
    return (
      '<a class="cita" href="' +
      encodeURI(urlSegura(f.url)) +
      '"' + titulo + ' target="_blank" rel="noopener">[' +
      n +
      "]</a>"
    );
  });
}
