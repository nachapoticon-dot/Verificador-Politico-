import assert from "node:assert";

// Copia mínima de las funciones a probar (sin DOM). Debe mantenerse IDÉNTICA a
// la lógica enviada en web/app.js para que el test guarde el comportamiento real.
function urlSegura(u) {
  try {
    const p = new URL(u);
    return (p.protocol === "http:" || p.protocol === "https:") ? u : "#";
  } catch (_) {
    return "#";
  }
}

function enlazarCitas(texto, fuentes) {
  const porN = {};
  (fuentes || []).forEach((f) => { porN[f.n] = f; });
  return texto.replace(/\[(\d+)\]/g, (m, n) => {
    const f = porN[n];
    if (!f) return m;
    return '<a class="cita" href="' + encodeURI(urlSegura(f.url)) + '" target="_blank" rel="noopener">[' + n + "]</a>";
  });
}

const out = enlazarCitas("el paro bajó [1] pero [2] lo matiza", [
  { n: 1, url: "https://a.com" }, { n: 2, url: "https://b.com" },
]);
assert.ok(out.includes('href="https://a.com"'));
assert.ok(out.includes('>[2]</a>'));
assert.ok(enlazarCitas("sin [9] fuente", []).includes("[9]")); // sin enlace si no existe

// La URL se codifica (no se deja cruda): el espacio pasa a %20.
const enc = enlazarCitas("ver [1]", [{ n: 1, url: "https://x.com/a b" }]);
assert.ok(enc.includes("a%20b"));
assert.ok(!enc.includes('href="https://x.com/a b"'));

// Esquemas no navegables (javascript:, data:, etc.) se neutralizan a "#".
const js = enlazarCitas("mira [1]", [{ n: 1, url: "javascript:alert(1)" }]);
assert.ok(js.includes('href="#"'));
assert.ok(!js.includes("javascript:"));

// URL ausente/inválida → enlace inofensivo "#", nunca el literal "undefined".
const sinUrl = enlazarCitas("vacío [1]", [{ n: 1 }]);
assert.ok(sinUrl.includes('href="#"'));
assert.ok(!sinUrl.includes("undefined"));

console.log("ok");
