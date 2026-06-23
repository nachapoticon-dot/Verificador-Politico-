import assert from "node:assert";

// Copia mínima de la función a probar (sin DOM).
function enlazarCitas(texto, fuentes) {
  const porN = {};
  (fuentes || []).forEach((f) => { porN[f.n] = f; });
  return texto.replace(/\[(\d+)\]/g, (m, n) => {
    const f = porN[n];
    if (!f) return m;
    return '<a class="cita" href="' + f.url + '" target="_blank" rel="noopener">[' + n + "]</a>";
  });
}

const out = enlazarCitas("el paro bajó [1] pero [2] lo matiza", [
  { n: 1, url: "https://a.com" }, { n: 2, url: "https://b.com" },
]);
assert.ok(out.includes('href="https://a.com"'));
assert.ok(out.includes('>[2]</a>'));
assert.ok(enlazarCitas("sin [9] fuente", []).includes("[9]")); // sin enlace si no existe
console.log("ok");
