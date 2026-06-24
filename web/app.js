/* El Fiel — cliente del verificador.
 *
 * Conecta la interfaz con /api/verificar, que transmite por SSE la traza de
 * investigación (qué busca, qué lee) y luego la respuesta final. No usamos
 * EventSource porque necesitamos POST con cuerpo JSON, así que leemos el flujo
 * con fetch y parseamos los eventos a mano.
 */

const $ = (sel) => document.querySelector(sel);

const hilo = $("#hilo");
const hero = $("#hero");
const form = $("#composer");
const entrada = $("#entrada");
const enviar = $("#enviar");
const paisInput = $("#pais");

let rigor = "riguroso";
let enCurso = false;

// Identificador de sesión estable: mantiene la memoria de la conversación.
const sid = (() => {
  let s = localStorage.getItem("elfiel_sid");
  if (!s) {
    s = "s_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("elfiel_sid", s);
  }
  return s;
})();

// El modelo cierra cada respuesta con un bloque JSON (campo `veredicto`, etc.)
// que alimenta el sello y el medidor; el usuario no lo ve como texto. Mapeamos
// cada valor del campo a su sello visual.
const SELLOS = {
  verdadero:          { etiqueta: "Verdadero", v: "true", emoji: "✅" },
  falso:              { etiqueta: "Falso", v: "false", emoji: "❌" },
  enganoso:           { etiqueta: "Engañoso", v: "warn", emoji: "⚠️" },
  fuera_de_contexto:  { etiqueta: "Sacado de contexto", v: "warn", emoji: "🔀" },
  prediccion:         { etiqueta: "Predicción", v: "muted", emoji: "🔮" },
  sin_evidencia:      { etiqueta: "Sin evidencia", v: "muted", emoji: "❓" },
  informativo:        { etiqueta: "Información", v: "info", emoji: "ℹ️" },
};

// Respaldo: si faltara el JSON, detectamos el sello por el emoji de la prosa.
const SELLO_POR_EMOJI = {
  "✅": "verdadero", "❌": "falso", "⚠": "enganoso",
  "🔀": "fuera_de_contexto", "🔮": "prediccion", "❓": "sin_evidencia",
};

// Posición de cada tendencia en el eje izquierda(0)–derecha(1) del medidor.
const TEND_POS = {
  "izquierda": 0.04,
  "centro-izquierda": 0.27,
  "centro": 0.5,
  "centro-derecha": 0.73,
  "derecha": 0.96,
};
// Estas no caen en el eje: son árbitros (verificadores, agencias).
const ARBITROS = new Set(["verificador", "internacional"]);

// Etiquetas legibles de credibilidad (clave del JSON → texto + clase de color).
const CREDIBILIDAD = {
  alta:      { txt: "alta",      clase: "b-alta" },
  media:     { txt: "media",     clase: "b-media" },
  baja:      { txt: "baja",      clase: "b-baja" },
  no_fiable: { txt: "no fiable", clase: "b-no" },
};
// Bloque de color por tendencia.
const TEND_CLASE = {
  "izquierda": "t-izq", "centro-izquierda": "t-izq", "centro": "t-cen",
  "centro-derecha": "t-der", "derecha": "t-der",
  "verificador": "t-ver", "internacional": "t-int",
};

const EXTRACTOS = {}; // url -> { extracto, titulo } acumulado de la traza

// La mini-cara de Tomás para firmar cada respuesta (le da voz al personaje).
const MINI_AVATAR =
  '<svg viewBox="0 0 48 48" class="mini-avatar" aria-hidden="true">' +
  '<circle cx="24" cy="23" r="16" class="sk"/>' +
  '<path d="M9 22 Q12 7 24 7 Q36 7 39 22 Q31 15 24 15 Q17 15 9 22 Z" class="hair"/>' +
  '<circle cx="18" cy="24" r="6.4" class="lens"/><circle cx="31" cy="24" r="6.4" class="lens"/>' +
  '<circle cx="18" cy="24" r="1.7" class="eye"/><circle cx="31" cy="24" r="1.7" class="eye"/></svg>';

/* ---------- Toggle de profundidad ---------- */
document.querySelectorAll(".seg-opt").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".seg-opt").forEach((b) => b.classList.remove("is-on"));
    btn.classList.add("is-on");
    rigor = btn.dataset.rigor || "riguroso";
  });
});

/* ---------- País: solo letras, mayúsculas ---------- */
paisInput.addEventListener("input", () => {
  paisInput.value = paisInput.value.replace(/[^a-zA-Z]/g, "").toUpperCase().slice(0, 2);
});

/* ---------- Chips de ejemplo ---------- */
document.querySelectorAll("#ejemplos .chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    entrada.value = chip.textContent.trim();
    autoGrow();
    entrada.focus();
    form.requestSubmit();
  });
});

/* ---------- Autoajuste del textarea + Enter para enviar ---------- */
function autoGrow() {
  entrada.style.height = "auto";
  entrada.style.height = Math.min(entrada.scrollHeight, window.innerHeight * 0.4) + "px";
}
entrada.addEventListener("input", autoGrow);
entrada.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

/* ---------- Envío ---------- */
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (enCurso) return;
  const pregunta = entrada.value.trim();
  if (!pregunta) return;

  ocultarHero();
  pintarConsulta(pregunta);
  entrada.value = "";
  autoGrow();

  const traza = pintarTraza();
  setEnCurso(true);

  try {
    await stream(pregunta, traza);
  } catch (err) {
    cerrarTraza(traza);
    pintarAviso("No pude conectar con el verificador. ¿Está el servidor en marcha? (" + err.message + ")");
  } finally {
    setEnCurso(false);
    scrollAbajo();
  }
});

/* ---------- Lectura del flujo SSE ---------- */
async function stream(pregunta, traza) {
  const resp = await fetch("/api/verificar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pregunta,
      sid,
      pais: paisInput.value.trim() || null,
      rigor,
    }),
  });

  if (!resp.ok || !resp.body) {
    throw new Error("HTTP " + resp.status);
  }

  const lector = resp.body.getReader();
  const dec = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await lector.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });

    // Los eventos SSE se separan por una línea en blanco.
    let corte;
    while ((corte = buffer.indexOf("\n\n")) !== -1) {
      const bloque = buffer.slice(0, corte);
      buffer = buffer.slice(corte + 2);
      manejarEvento(parseSSE(bloque), traza);
    }
  }
}

function parseSSE(bloque) {
  let evento = "message";
  const datos = [];
  for (const linea of bloque.split("\n")) {
    if (linea.startsWith("event:")) evento = linea.slice(6).trim();
    else if (linea.startsWith("data:")) datos.push(linea.slice(5).trim());
  }
  let dato = {};
  try { dato = JSON.parse(datos.join("\n")); } catch (_) { /* ignora */ }
  return { evento, dato };
}

function manejarEvento({ evento, dato }, traza) {
  if (evento === "traza") {
    pintarTrazaEvento(traza, dato);
  } else if (evento === "respuesta") {
    cerrarTraza(traza);
    pintarRespuesta(dato.texto || "");
  } else if (evento === "moderacion") {
    cerrarTraza(traza, true);
    pintarAviso(dato.mensaje || "", true);
  } else if (evento === "error") {
    cerrarTraza(traza);
    pintarAviso(dato.mensaje || "Algo salió mal.");
  }
  scrollAbajo();
}

/* ---------- Pintado del hilo ---------- */
function ocultarHero() {
  if (hero && hero.parentNode) hero.remove();
}

function nuevoMsg() {
  const div = document.createElement("div");
  div.className = "msg";
  hilo.appendChild(div);
  return div;
}

function pintarConsulta(texto) {
  const msg = nuevoMsg();
  msg.classList.add("msg-consulta");
  const marca = document.createElement("span");
  marca.className = "q-mark";
  marca.textContent = "Consulta";
  const p = document.createElement("p");
  p.textContent = texto;
  msg.append(marca, p);
}

function pintarTraza() {
  const msg = nuevoMsg();
  const box = document.createElement("div");
  box.className = "traza";
  const cab = document.createElement("div");
  cab.className = "traza-cab";
  cab.innerHTML = '<span class="dot"></span> investigando';
  box.appendChild(cab);
  msg.appendChild(box);
  return box;
}

function pintarTrazaEvento(traza, ev) {
  if (ev.url && ev.extracto) EXTRACTOS[ev.url] = { extracto: ev.extracto, titulo: ev.titulo };
  let card = traza.querySelector('[data-id="' + ev.id + '"]');
  if (!card) {
    card = document.createElement("div");
    card.className = "fuente-card";
    card.dataset.id = ev.id;

    let fav;
    if (ev.dominio) {
      fav = document.createElement("img");
      fav.className = "fav";
      fav.alt = "";
      fav.src = "https://www.google.com/s2/favicons?domain=" + encodeURIComponent(ev.dominio) + "&sz=32";
    } else {
      fav = document.createElement("span");
      fav.className = "fav fav--q";
      fav.textContent = ev.tipo === "busqueda" ? "🔎" : ev.tipo === "video" ? "▶" : "📄";
    }

    const tit = document.createElement("span");
    tit.className = "fuente-tit";
    tit.textContent = ev.titulo || ev.dominio || "";

    const estadoEl = document.createElement("span");
    estadoEl.className = "fuente-estado";

    card.append(fav, tit, estadoEl);
    traza.appendChild(card);
  }
  const est = card.querySelector(".fuente-estado");
  const etiquetas = { buscando: "buscando…", leyendo: "leyendo…", ok: "✓", fallo: "✗" };
  est.textContent = etiquetas[ev.estado] || "";
  card.dataset.estado = ev.estado;
}

function cerrarTraza(traza, sinPasos) {
  if (!traza) return;
  traza.classList.add("cerrada");
  const cab = traza.querySelector(".traza-cab");
  if (cab) cab.lastChild.textContent = sinPasos ? " sin investigar" : " investigación cerrada";
  // Si no hubo ningún paso, la traza no aporta: la quitamos.
  if (!traza.querySelector(".fuente-card")) traza.closest(".msg")?.remove();
}

function pintarRespuesta(texto) {
  const msg = nuevoMsg();
  const cont = document.createElement("div");
  cont.className = "veredicto";

  const { prosa, meta } = partirRespuesta(texto);
  const fuentes = (meta && meta.fuentes) || [];
  const sello = selloDe(meta, prosa);

  const firma = document.createElement("div");
  firma.className = "resp-firma";
  firma.innerHTML = MINI_AVATAR + "<b>Tomás</b><span>verifica</span>";
  cont.appendChild(firma);

  if (sello) {
    const fila = document.createElement("div");
    fila.className = "sello-fila";
    const pill = document.createElement("span");
    pill.className = "pill";
    pill.dataset.v = sello.v;
    pill.innerHTML = '<span class="pill-em">' + sello.emoji + "</span> " + sello.etiqueta;
    fila.appendChild(pill);
    if (meta && meta.veredicto !== "informativo" && Number.isFinite(meta.confianza)) {
      const conf = document.createElement("span");
      conf.className = "conf";
      const pct = Math.max(0, Math.min(100, Math.round(meta.confianza)));
      conf.innerHTML = "confianza " + pct + '% <span class="conf-barra"><i style="width:' + pct + '%"></i></span>';
      fila.appendChild(conf);
    }
    cont.appendChild(fila);
  }

  const body = document.createElement("div");
  body.className = "respuesta-cuerpo";
  body.innerHTML = enlazarCitas(formatear(prosa), fuentes);
  cont.appendChild(body);

  const fuentesMeta = (meta && Array.isArray(meta.fuentes)) ? meta.fuentes : [];
  if (fuentesMeta.length) {
    cont.appendChild(pintarFuentes(fuentesMeta));
  }

  msg.appendChild(cont);
}

// Lista ponderada de fuentes: tendencia + medio + respalda/matiza + credibilidad
// + "ver de dónde salió". Sustituye al medidor político anterior.
function pintarFuentes(fuentes) {
  const box = document.createElement("div");
  box.className = "fuentes-bloque";
  const cab = document.createElement("div");
  cab.className = "fuentes-cab";
  cab.textContent = "fuentes contrastadas";
  box.appendChild(cab);

  const lista = document.createElement("ul");
  lista.className = "fuentes-lista";
  fuentes.forEach((f) => {
    const li = document.createElement("li");

    const tend = document.createElement("span");
    const tkey = (f.tendencia || "").toLowerCase();
    tend.className = "chip-t " + (TEND_CLASE[tkey] || "t-cen");
    tend.textContent = tkey || "—";
    li.appendChild(tend);

    const a = document.createElement("a");
    a.href = urlSegura(f.url);
    a.target = "_blank";
    a.rel = "noopener";
    a.className = "fuente-medio";
    a.textContent = "[" + f.n + "] " + (f.medio || f.url || "fuente");
    li.appendChild(a);

    const rel = document.createElement("span");
    rel.className = "fuente-rel";
    rel.textContent = f.coincide ? "✓ respalda" : "· matiza";
    li.appendChild(rel);

    const cred = CREDIBILIDAD[(f.credibilidad || "").toLowerCase()];
    if (cred) {
      const badge = document.createElement("span");
      badge.className = "badge-c " + cred.clase;
      badge.textContent = cred.txt;
      li.appendChild(badge);
    }

    const ex = EXTRACTOS[f.url];
    if (ex) {
      const det = document.createElement("details");
      det.className = "prueba";
      const sum = document.createElement("summary");
      sum.textContent = "ver de dónde salió";
      const bq = document.createElement("blockquote");
      bq.textContent = ex.extracto;
      det.appendChild(sum);
      det.appendChild(bq);
      li.appendChild(det);
    }

    lista.appendChild(li);
  });
  box.appendChild(lista);
  return box;
}

function pintarAviso(texto, esLimite) {
  const msg = nuevoMsg();
  const div = document.createElement("div");
  div.className = "aviso" + (esLimite ? " limite" : "");
  div.textContent = texto;
  msg.appendChild(div);
}

/* ---------- Utilidades ---------- */
// Separa la prosa del bloque ```json final (el contrato de datos del medidor).
function partirRespuesta(texto) {
  const m = texto.match(/```json\s*([\s\S]*?)```\s*$/i);
  if (!m) return { prosa: texto.trim(), meta: null };
  let meta = null;
  try { meta = JSON.parse(m[1].trim()); } catch (_) { /* JSON inválido: lo ignoramos */ }
  return { prosa: texto.slice(0, m.index).trim(), meta };
}

// Determina el sello: primero por el campo `veredicto` del JSON; si falta,
// como respaldo, por el emoji que aparezca en la prosa.
function selloDe(meta, prosa) {
  const clave = meta && typeof meta.veredicto === "string" ? meta.veredicto.toLowerCase().trim() : null;
  if (clave && SELLOS[clave]) return SELLOS[clave];
  for (const [emoji, k] of Object.entries(SELLO_POR_EMOJI)) {
    if (prosa.includes(emoji)) return SELLOS[k];
  }
  return null;
}

// Formateo ligero: párrafos, **negrita**, enlaces markdown y URLs sueltas.
function formatear(texto) {
  const parrafos = texto.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean);
  return parrafos.map((p) => "<p>" + enlazar(negrita(escapar(p))).replace(/\n/g, "<br>") + "</p>").join("");
}
function escapar(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function negrita(s) {
  return s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}
function enlazar(s) {
  // [texto](url)
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  // URLs sueltas que no estén ya dentro de un href.
  s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g,
    (m, pre, url) => pre + '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + url + "</a>");
  return s;
}

// Solo http/https son navegables de forma segura; cualquier otra cosa
// (javascript:, data:, una URL ausente, etc.) se neutraliza a "#". Devuelve la
// URL original sin normalizar para no alterar enlaces válidos; el cifrado de
// caracteres se hace en el punto de uso (encodeURI / propiedad .href).
function urlSegura(u) {
  try {
    const p = new URL(u);
    return (p.protocol === "http:" || p.protocol === "https:") ? u : "#";
  } catch (_) {
    return "#";
  }
}

// Convierte referencias [n] en la prosa (ya escapada y formateada) en enlaces
// clicables a la fuente n. La URL pasa por urlSegura (bloquea esquemas no
// navegables) y encodeURI (evita inyección de atributos si llegara una URL con
// comillas u otros caracteres). El [n] es numérico, así que es seguro inline.
function enlazarCitas(texto, fuentes) {
  const porN = {};
  (fuentes || []).forEach((f) => { porN[f.n] = f; });
  return texto.replace(/\[(\d+)\]/g, (m, n) => {
    const f = porN[n];
    if (!f) return m;
    return '<a class="cita" href="' + encodeURI(urlSegura(f.url)) + '" target="_blank" rel="noopener">[' + n + "]</a>";
  });
}

function setEnCurso(v) {
  enCurso = v;
  enviar.disabled = v;
  entrada.readOnly = v;
}

function scrollAbajo() {
  requestAnimationFrame(() => {
    const ultimo = hilo.lastElementChild;
    if (ultimo) ultimo.scrollIntoView({ behavior: "smooth", block: "end" });
  });
}
