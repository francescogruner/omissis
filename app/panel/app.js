// Pannello di Omissis. Nessuna libreria: un file solo, diviso in parti.
//   1. strumenti (lingue, chiamate al programma, avvisi)      3. le viste, una funzione per ciascuna
//   2. guscio (menu, percorsi, stato della protezione)        4. avvio
// Ogni testo visibile passa da t(chiave): le frasi stanno in locales/<codice>.json, mai qui dentro.

const CODE = document.querySelector('meta[name="omissis-code"]').content;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
// dove scrivere a chi fa Omissis: un collegamento e basta, che si apre solo se lo si preme
const CONTACT = "https://francescogruner.it/contatti/", LINKEDIN = "https://www.linkedin.com/in/francescogruner/";
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

// ------------------------------------------------------------------ 1. strumenti

let TEXTS = {}, FALLBACK = {}, LANGUAGE = "it";
// Le scorciatoie in uso, già scritte come tasti: le frasi le nominano con {sostituisci}, {maschera}, {ripristina}.
let KEYSTROKES = {};
const readKeystrokes = async () => {
  const s = await api("/api/shortcuts");
  KEYSTROKES = Object.fromEntries(s.entries.map(v => [v.name, v.combo ? v.caption.split("+").map(k => `<kbd>${esc(k)}</kbd>`).join("+") : `<i>${esc(t("shortcuts.off"))}</i>`]));
};
/** La frase per una chiave, con i valori tra graffe sostituiti. Se manca nella lingua scelta vale l'italiano. */
function t(key, values) {
  const s = TEXTS[key] ?? FALLBACK[key] ?? key;
  return values ? s.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m)) : s;
}
/** Come t, ma senza segnalare la chiave se non c'è: restituisce il testo di riserva. Per le voci che arrivano dal programma. */
const tSe = (key, fallback) => TEXTS[key] ?? FALLBACK[key] ?? fallback;
const num = n => new Intl.NumberFormat(LANGUAGE).format(n);
const megabyte = n => num(Math.round(n / 1e6));
const dataKind = k => tSe("kind." + k, k);

async function api(path, data) {
  const r = await fetch(path, {method: data === undefined ? "GET" : "POST", headers: {"X-Panel": CODE, "Content-Type": "application/json"},
    body: data === undefined ? undefined : JSON.stringify(data)});
  if (r.status === 403) {   // il programma è ripartito (per esempio dopo un aggiornamento) con un codice nuovo
    const stamp = Date.now(), latest = +sessionStorage.getItem("reload") || 0;
    if (stamp - latest > 10000) { sessionStorage.setItem("reload", stamp); location.reload(); }
  }
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
}

function notify(text, error = false) {
  $$("#notices .notice").filter(x => x.textContent === text).forEach(x => x.remove());   // lo stesso avviso non si impila: riparte
  const a = document.createElement("div");
  a.className = "notice" + (error ? " error" : "");
  if (error) a.setAttribute("role", "alert");
  a.textContent = text;
  $("#notices").append(a);
  setTimeout(() => a.remove(), error ? 9000 : 5000);
}
/** Avvolge un'azione: se fallisce, l'errore compare come avviso invece di sparire nella console. */
const test = f => async (...a) => { try { return await f(...a); } catch (e) { notify(e.message, true); } };

async function copy(text, message) {
  try { await navigator.clipboard.writeText(text); }
  catch { const a = document.createElement("textarea"); a.value = text; document.body.append(a); a.select(); document.execCommand("copy"); a.remove(); }
  notify(message || t("general.copied"));
}

function confirm(title, text, yes) {
  const d = $("#confirm");
  $("#confirmTitle").textContent = title; $("#confirmText").textContent = text;
  $("#confirmYes").textContent = yes; $("#confirmNo").textContent = t("general.cancel");
  return new Promise(done => { d.onclose = () => done(d.returnValue === "yes"); d.returnValue = "no"; d.showModal(); $("#confirmNo").focus(); });
}

const ICONS = {
  start: '<path d="M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
  text: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  documents: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  connections: '<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/>',
  services: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  vault: '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6M4 11.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  settings: '<path d="M4 6h8M18 6h2M4 12h2M12 12h8M4 18h7M17 18h3"/><circle cx="15" cy="6" r="2.5"/><circle cx="9" cy="12" r="2.5"/><circle cx="14" cy="18" r="2.5"/>',
  guide: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.1 1-1.1 1.8M12 17h.01"/>',
  browser: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18"/>',
  app: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 10 3 2.5L7 15M13 15h4"/>',
  proxy: '<path d="M4 8h14l-3-3M20 16H6l3 3"/>',
  mcp: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 13h6M9 17h4"/>',
};
const icon = n => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n]}</svg>`;

const label = (text, kind = "") => `<span class="label ${kind}">${esc(text)}</span>`;
const card = (inside, footer = "", classes = "") => `<section class="card ${classes}"><div class="inside">${inside}</div>${footer ? `<div class="footer">${footer}</div>` : ""}</section>`;
const head = id => `<header class="head"><h1>${esc(t(`${id}.title`))}</h1><p>${t(`${id}.below`, KEYSTROKES)}</p></header>`;
const counts = c => Object.entries(c || {}).filter(([, n]) => n).map(([k, n]) => label(`${dataKind(k)} ${n}`, "ok")).join("");
/** Larghezze e altezze dei grafici: scritte dal codice e non nell'HTML, così la pagina non ha bisogno di stili "in linea". */
function measures(root) {
  $$("[data-l]", root).forEach(e => { e.style.width = e.dataset.l + "%"; });
  $$("[data-a]", root).forEach(e => { e.style.height = e.dataset.a + "%"; });
}
function bars(el, lines, name = x => x) {
  const m = Math.max(1, ...lines.map(r => r[1]));
  el.innerHTML = lines.length ? lines.map(r => `<div><span>${esc(name(r[0]))}</span><i data-l="${Math.round(100 * r[1] / m)}"></i><span>${num(r[1])}</span></div>`).join("")
    : `<span class="faded">${esc(t("general.no_data"))}</span>`;
  measures(el);
}
function table(title, lines, columns) {
  if (!lines || !lines.length) return "";
  return `<h3>${esc(title)} <span class="faded">(${lines.length})</span></h3><div class="table"><table><tbody>${
    lines.map(r => "<tr>" + columns.map(c => `<td>${c(r)}</td>`).join("") + "</tr>").join("")}</tbody></table></div>`;
}
const line = (name, help, command) => `<div class="setting"><span class="name">${esc(name)}</span>${help ? `<span class="help">${help}</span>` : ""}<span class="command">${command}</span></div>`;
const toggle = (id, name) => `<span class="toggle"><input type="checkbox" role="switch" id="${id}" aria-label="${esc(name)}"><span></span></span>`;

// ------------------------------------------------------------------ 2. guscio

const VIEWS = [
  {id: "start"}, {id: "text"}, {id: "documents"}, {id: "guide"},
  {id: "settings", cards: ["general", "recognition"], advancedCards: ["recognition"]},
  {id: "connections", advanced: true, cards: ["browser", "app", "terminal", "mcp", "proxy", "compatibility"]},
  {id: "services", advanced: true, cards: ["rules", "detected"]},
  {id: "activity", advanced: true}, {id: "vault", advanced: true},
];
const DRAW = {}, REFRESH = {};
let S = null;              // l'ultimo stato letto dal programma
let view = "simple";    // semplice | avanzata
let opened = {id: "", card: ""};
let extension = null;     // ciò che dice di sé l'estensione, se questo browser ce l'ha
let guide = null;         // la configurazione guidata, mentre è aperta
let wantConnect = false;  // la pagina è stata aperta dall'estensione appena installata, per collegarla

function drawMenu() {
  const entry = v => `<a href="#/${v.id}" data-view="${v.id}">${icon(v.id)}<span>${esc(t(`menu.${v.id}`))}</span></a>`;
  $("#menu").setAttribute("aria-label", t("menu.name"));
  $("#menu").innerHTML = VIEWS.filter(v => !v.advanced).map(entry).join("")
    + `<div class="group only-advanced">${esc(t("menu.group_technical"))}</div>`
    + VIEWS.filter(v => v.advanced).map(v => entry(v).replace("<a ", '<a class="only-advanced" ')).join("");
  $("#skip").textContent = t("general.skip");
  $("#advancedText").textContent = t("menu.advanced");
  $("#contact").href = CONTACT;
  $("#contact").textContent = t("general.made_by");
}

function path() {
  const [, id = "start", card = ""] = location.hash.split("/");
  const v = VIEWS.find(x => x.id === id) || VIEWS[0];
  const allowed = (v.cards || []).filter(s => view === "advanced" || !(v.advancedCards || []).includes(s));
  return {v, card: allowed.includes(card) ? card : (allowed[0] || ""), allowed};
}

function show(move = true) {
  const {v, card, allowed} = path();
  if (v.advanced && view !== "advanced") { location.hash = "#/start"; return; }
  opened = {id: v.id, card};
  $$("#menu a").forEach(a => a.dataset.view === v.id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  document.title = `${t(`menu.${v.id}`)} · Omissis`;
  const el = $("#content");
  el.innerHTML = head(v.id) + (allowed.length > 1 ? `<div class="cards-menu" role="tablist" aria-label="${esc(t(`menu.${v.id}`))}">${
    allowed.map(s => `<button role="tab" id="tab-${s}" data-card="${s}" aria-selected="${s === card}" aria-controls="panel" tabindex="${s === card ? 0 : -1}">${esc(t(`${v.id}.card.${s}`))}</button>`).join("")}</div>` : "")
    + `<div class="block" id="panel" ${allowed.length > 1 ? `role="tabpanel" aria-labelledby="tab-${card}"` : ""}></div>`;
  $$(".cards-menu button", el).forEach(b => {
    b.onclick = () => { location.hash = `#/${v.id}/${b.dataset.card}`; };
    b.onkeydown = e => {
      const toward = {ArrowRight: 1, ArrowLeft: -1}[e.key];
      if (!toward) return;
      const all_of = $$(".cards-menu button", el), upcoming = all_of[(all_of.indexOf(b) + toward + all_of.length) % all_of.length];
      location.hash = `#/${v.id}/${upcoming.dataset.card}`;
      requestAnimationFrame(() => $(`#tab-${upcoming.dataset.card}`)?.focus());
    };
  });
  DRAW[v.id]($("#panel"), card);
  if (S) REFRESH[v.id]?.(S);
  if (move) { el.focus({preventScroll: true}); scrollTo(0, 0); }
}

function applyView() {
  document.body.classList.toggle("simple", view === "simple");
  $("#advanced").checked = view === "advanced";
}

const PHASES = ["active", "startup", "error", "stop", "model"];
const readStatus = test(async () => {
  S = await api("/api/status");
  const phase = PHASES.includes(S.phase) ? S.phase : "stop";
  $("#sidePoint").className = "point " + phase;
  $("#sideText").textContent = t(`status.short.${phase}`);
  $("#version").textContent = t("general.version", {v: S.version});
  REFRESH[opened.id]?.(S);
  guide?.refresh();
});

// ------------------------------------------------------------------ 3. le viste

// ---- Inizio
DRAW.start = el => {
  el.innerHTML = `
    <section class="card" aria-labelledby="titleStatus"><div class="inside"><div class="status-large">
      <span class="point" id="pointStatus"></span><div><strong id="titleStatus">…</strong><div class="faded" id="belowStatus"></div></div>
      <span class="space"></span>
      <button class="button" id="restart" hidden>${esc(t("start.restart"))}</button><button class="button primary" id="main_switch">…</button>
    </div></div></section>
    <div id="reduced"></div>
    <div id="remoteDown"></div>
    <div id="update"></div>
    <div class="badges">${["text", "documents", "guide"].map(v => `<a class="badge" href="#/${v}">${icon(v)}<b>${esc(t(`start.badge.${v}`))}</b><span>${esc(t(`start.badge.${v}.below`))}</span></a>`).join("")}</div>
    <div class="grid">${["messages", "replacements", "blocked"].map(k => card(`<div class="number" id="n-${k}">0</div><div class="faded small">${esc(t(`start.today.${k}`))}</div>`)).join("")}
      ${card(`<div class="number" id="n-entries">–</div><div class="faded small">${esc(t("start.entries"))}</div>`, "", "only-advanced")}</div>
    <div id="cautions" class="block only-advanced"></div>
    <section class="card only-advanced" aria-label="${esc(t("start.channels"))}" id="channels"></section>
    <div class="two only-advanced">
      ${card(`<h2>${esc(t("start.chart.days"))}</h2><div class="columns" id="days"></div>`)}
      ${card(`<h2>${esc(t("start.chart.services"))}</h2><div class="bars" id="byService"></div>`)}
    </div>
    ${card(`<h2>${esc(t("start.chart.kinds"))}</h2><div class="bars" id="byKind"></div>`, "", "only-advanced")}`;
  $("#main_switch").onclick = test(async () => { await api("/api/protection", {action: ["active", "model"].includes(S?.phase) ? "stop" : "launch"}); readStatus(); });
  $("#restart").onclick = test(async () => { await api("/api/protection", {action: "restart"}); readStatus(); });
  channels();
};
REFRESH.start = s => {
  const phase = PHASES.includes(s.phase) ? s.phase : "stop", sc = s.downloading;
  $("#pointStatus").className = "point " + phase;
  $("#titleStatus").textContent = t(`status.${phase}`);
  const below = $("#belowStatus");
  if (phase === "model" && sc && sc.total) {
    const pc = Math.min(100, Math.floor(100 * sc.completed / sc.total));
    below.innerHTML = `${esc(t("status.model.progress", {completed: megabyte(sc.completed), total: megabyte(sc.total), pc}))}
      <progress class="progress" max="100" value="${pc}" aria-label="${esc(t("status.model"))}"></progress>`;
  } else {
    below.textContent = phase === "active" ? t("status.active.below", {model: s.model, where: t(s.device === "server" ? "status.on_server" : s.device === "cuda" ? "status.graphics_card" : "status.cpu")})
      : phase === "error" ? s.error + (sc && sc.missing && sc.downloadable ? " " + t("status.retry") : "")
      : t(`status.${phase}.below`);
  }
  const b = $("#main_switch"), is_on = phase === "active" || phase === "model";
  b.textContent = t(phase === "model" ? "general.cancel" : is_on ? "start.stop" : "start.launch");
  b.className = "button" + (is_on ? "" : " primary");
  const fixed = !!s.always_on && is_on;   // deciso da chi amministra il PC o dalla console: qui non si ferma
  b.disabled = phase === "startup" || fixed;
  b.title = fixed ? t("managed.always_on") : "";
  if (fixed && phase === "active") below.textContent += " · " + t("managed.always_on");
  $("#restart").hidden = !s.restart_needed;
  updateNotice(s.update);
  // chi ha spento un gruppo di dati lo deve vedere ogni volta che apre il programma, non solo nelle impostazioni
  const off = (s.groups_off || []).map(g => t(`groups.${g}`)).join(", ");
  if ($("#reduced").dataset.off !== off) {
    $("#reduced").dataset.off = off;
    $("#reduced").innerHTML = off ? `<div class="note warning"><span class="space">${esc(t("groups.reduced", {listing: off}))}</span><a class="button" href="#/settings/recognition">${esc(t("groups.reduced.change"))}</a></div>` : "";
  }
  // chi usa il modello di un server della rete deve sapere subito se quello non risponde: i suoi messaggi vengono fermati
  const down = s.remote && s.remote.ok === false ? s.remote.host || "" : null;
  if ($("#remoteDown").dataset.down !== String(down)) {
    $("#remoteDown").dataset.down = String(down);
    $("#remoteDown").innerHTML = down === null ? "" : `<div class="note error"><span class="space">${esc(t("server.down", {host: down}))}</span></div>`;
  }
  const st = s.stats;
  for (const k of ["messages", "replacements", "blocked"]) $(`#n-${k}`).textContent = num(st.today[k]);
  $("#n-entries").textContent = s.entries == null ? "–" : num(s.entries);
  $("#cautions").innerHTML = st.notices.map(a => `<div class="note warning">${esc(t(`start.caution.${a.code}`, {n: num(a.n)}))}</div>`).join("");
  const m = Math.max(1, ...st.days.map(g => g.n));
  $("#days").innerHTML = st.days.map(g => `<div><span>${g.n || ""}</span><i data-a="${Math.round(100 * g.n / m)}"></i><span>${esc(g.day.slice(8) + "/" + g.day.slice(5, 7))}</span></div>`).join("");
  measures($("#days"));
  bars($("#byService"), st.services, s => tSe("service." + s, s)); bars($("#byKind"), st.kinds, dataKind);
};
let seenNotice = "";
function updateNotice(a) {
  const el = $("#update");
  if (!a || !el) return;
  const pc = a.total ? Math.min(100, Math.floor(100 * a.completed / a.total)) : 0, v = esc(a.version);
  const notes = a.notes ? `<div class="small">${esc(a.notes)}</div>` : "";
  const html = a.phase === "ready_now" ? `<div class="note"><div class="space"><b>${esc(t("updates.ready_now", {v}))}</b><div class="small faded">${esc(t("updates.ready_now.below"))}</div>${notes}</div><button class="button primary" data-action="install">${esc(t("updates.install"))}</button></div>`
    : a.phase === "downloading" ? `<div class="note"><span>${esc(t("updates.downloading", {v, pc}))}</span></div>`
    : a.phase === "available" ? `<div class="note"><div class="space"><b>${esc(t("updates.available", {v}))}</b>${notes}</div>${a.installable
      ? `<button class="button" data-action="download">${esc(t("updates.download"))}</button>`
      : `<a class="button" href="${esc(a.page)}" target="_blank" rel="noopener">${esc(t("updates.page"))}</a>`}</div>` : "";
  if (html === seenNotice && el.innerHTML) return;   // riscritto solo se cambia: un pulsante non deve sparire sotto il clic
  seenNotice = html; el.innerHTML = html;
  $$("button[data-action]", el).forEach(b => b.onclick = test(async () => {
    b.disabled = true;
    await api("/api/updates", {action: b.dataset.action});
    if (b.dataset.action === "install") notify(t("updates.installation_launched"));
    readStatus();
  }));
}
/** Le quattro strade della protezione automatica, con il loro stato: un colpo d'occhio che porta a Collegamenti. */
const channels = test(async () => {
  const el = $("#channels");
  if (!el || view !== "advanced") return;
  const [app, gw, mcp] = await Promise.all([api("/api/app"), api("/api/gateway"), api("/api/mcp")]);
  if (!$("#channels")) return;
  const reg = mcp.claude_desktop;
  const connected_ones = app.filter(a => a.connected).length, unprotected_ones = app.filter(a => a.installed && a.open_unprotected).length;
  const entry = (id, status, kind) => `<a class="channel" href="#/connections/${id}">${icon(id)}<b>${esc(t(`connections.card.${id}`))}</b>${label(status, kind)}<span class="below">${esc(t(`start.channel.${id}`))}</span></a>`;
  el.innerHTML = entry("browser", !extension ? t("browser.status.absent") : extension.connected && extension.ok ? t("browser.status.connected") : t("browser.status.to_connect"), extension && extension.connected && extension.ok ? "ok" : "")
    + entry("app", unprotected_ones ? t("app.unprotected_ones", {n: unprotected_ones}) : connected_ones ? t("app.connected_ones", {n: connected_ones}) : t("app.no_connected"),
            unprotected_ones ? "warning" : connected_ones ? "ok" : "")
    + entry("terminal", gw.is_active ? t("terminal.is_active", {port: gw.port}) : (gw.error || t("terminal.stopped")), gw.is_active ? "ok" : gw.error ? "error" : "")
    + entry("mcp", reg.registered ? t(reg.current ? "mcp.registered" : "mcp.registered_old") : t("mcp.not_registered"), reg.registered ? (reg.current ? "ok" : "warning") : "")
    + entry("proxy", S && S.phase === "active" ? t("proxy.is_active", {port: S.port}) : t("proxy.stopped"), S && S.phase === "active" ? "ok" : "");
});

// ---- Testo
// Una casella sola: un testo normale viene mascherato, uno che contiene segnaposto viene riportato ai valori veri.
// Incollando parte da solo, e il risultato va da solo negli appunti (si può spegnere).
// Il risultato si corregge sul posto: un segnaposto di troppo si lascia in chiaro, un dato sfuggito si maschera a mano.
const RX_PLACEHOLDER = /\[[A-Z][A-Z_]{1,22}_\d{1,7}\]/;
const MANUAL_KINDS = ["ELENCO", "PERSONA", "ORG", "INDIRIZZO", "TELEFONO", "EMAIL", "ID_PRATICA", "SEGRETO"];
const memory = (key, value) => { try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch { /* memoria del browser non disponibile */ } return null; };
let result = "";
DRAW.text = el => {
  let corrections = {never: [], also: {}};   // valgono per il testo che c'è nella casella: si azzerano quando se ne incolla un altro
  el.innerHTML = card(`<label class="field" for="inbound">${esc(t("text.inbound"))}<span class="help">${esc(t("text.inbound.below"))}</span></label>
      <textarea id="inbound" placeholder="${esc(t("text.example"))}"></textarea>
      <div class="line"><button class="button primary" id="paste">${esc(t("text.paste"))}</button>
        <button class="button" id="mask">${esc(t("text.mask"))}</button><button class="button" id="restore">${esc(t("text.restore"))}</button>
        <button class="button" id="clearText">${esc(t("text.clear"))}</button>
        <span class="space"></span><label class="line">${toggle("copyByItself", t("text.copy_by_itself"))}<span>${esc(t("text.copy_by_itself"))}</span></label></div>`)
    + card(`<div class="line"><h2 id="resultTitle">${esc(t("text.result"))}</h2><span class="space"></span><span class="faded small" id="noteResult"></span></div>
      <div class="outcome" id="outcome" aria-live="polite" aria-labelledby="resultTitle"></div>
      <div class="labels" id="found_items"></div>
      <div class="correct" id="correct" hidden>
        <p class="help" id="correctHelp">${esc(t("text.correct.help"))}</p>
        <div class="line" id="onPlaceholder" hidden></div>
        <form class="line" id="aggiungi">
          <input type="text" id="daMascherare" class="space" maxlength="200" aria-label="${esc(t("text.correct.field"))}" placeholder="${esc(t("text.correct.field"))}">
          <select id="manualKind" aria-label="${esc(t("text.correct.kind"))}">${MANUAL_KINDS.map(k => `<option value="${k}">${esc(k === "ELENCO" ? t("text.correct.kind.other") : dataKind(k))}</option>`).join("")}</select>
          <label class="line small"><input type="checkbox" id="alsoAlways">${esc(t("text.correct.always"))}</label>
          <button class="button" id="maskAlso">${esc(t("text.correct.mask"))}</button>
        </form>
        <div class="labels" id="correctionsDone"></div>
      </div>`,
      `<span id="whatDone">${esc(t("text.result.empty"))}</span><span class="space"></span><button class="button" id="copyResult" disabled>${esc(t("text.copy"))}</button>`);
  const alone = $("#copyByItself");
  alone.checked = memory("copy_by_itself") !== "no";
  alone.onchange = () => memory("copy_by_itself", alone.checked ? "yes" : "no");
  const deliver = async (what, note) => {
    $("#copyResult").disabled = false;
    $("#noteResult").textContent = note;
    if (alone.checked && result) { await copy(result, t(`text.${what}.copied`)); $("#whatDone").textContent = t(`text.${what}.copied`); }
    else $("#whatDone").textContent = t(`text.${what}.done`);
  };
  const completed_ones = () => {
    const entry = (what, value) => `<button type="button" class="label drop" data-what="${what}" data-value="${esc(value)}" title="${esc(t("text.correct.drop"))}">${esc(t(`text.correct.done_one.${what}`, {value}))} <span aria-hidden="true">×</span></button>`;
    $("#correctionsDone").innerHTML = corrections.never.map(v => entry("never", v)).join("") + Object.keys(corrections.also).map(v => entry("also", v)).join("");
    $$("#correctionsDone button").forEach(b => b.onclick = () => {
      if (b.dataset.what === "never") corrections.never = corrections.never.filter(v => v !== b.dataset.value); else delete corrections.also[b.dataset.value];
      mask();
    });
  };
  const mask = test(async () => {
    const r = await api("/api/try", {text: $("#inbound").value, never: corrections.never, also: corrections.also});
    result = r.texts[0];
    $("#outcome").innerHTML = esc(result).replace(new RegExp(RX_PLACEHOLDER, "g"), s => `<button type="button" class="placeholder" data-s="${s}" data-v="${esc(r.mapping[s] ?? "")}" title="${esc(r.mapping[s] ?? "")}">${s}</button>`);
    $$("#outcome button").forEach(b => b.onclick = () => onPlaceholder(b.dataset.s, b.dataset.v));
    $("#found_items").innerHTML = counts(r.counts) || `<span class="faded">${esc(t("text.no_data"))}</span>`;
    $("#correct").hidden = false; $("#onPlaceholder").hidden = true;
    completed_ones();
    await deliver("masked", `${r.ms} ms`);
  });
  const restore = test(async () => {
    const r = await api("/api/restore", {text: $("#inbound").value});
    result = r.text;
    $("#outcome").textContent = r.text;
    $("#found_items").innerHTML = "";
    $("#correct").hidden = true;
    await deliver("restored", t("text.restored", {n: r.restored}) + (r.unknown ? " " + t("text.unknown", {n: r.unknown}) : ""));
  });
  // un segnaposto premuto: cosa nasconde, e i due modi per toglierlo (solo questa volta, oppure per sempre)
  const onPlaceholder = (placeholder, value) => {
    const zone = $("#onPlaceholder");
    zone.hidden = false;
    zone.innerHTML = `<span>${t("text.correct.about_to", {placeholder: `<span class="placeholder">${esc(placeholder)}</span>`, value: `<b>${esc(value)}</b>`})}</span><span class="space"></span>
      <button type="button" class="button" data-make="light">${esc(t("text.correct.light"))}</button><button type="button" class="button" data-make="never">${esc(t("text.correct.never"))}</button>
      <button type="button" class="button" data-make="close" aria-label="${esc(t("general.close"))}">×</button>`;
    $$("button", zone).forEach(b => b.onclick = test(async () => {
      if (b.dataset.make === "close") { zone.hidden = true; return; }
      if (b.dataset.make === "never") { await api("/api/lists/add", {list_name: "never", term: value}); notify(t("text.correct.never.done", {value})); }
      if (!corrections.never.includes(value)) corrections.never.push(value);
      await mask();
    }));
    $("button", zone).focus();
  };
  $("#aggiungi").onsubmit = test(async e => {
    e.preventDefault();
    const term = $("#daMascherare").value.trim();
    if (term.length < 2) { $("#daMascherare").focus(); return; }
    if ($("#alsoAlways").checked) { await api("/api/lists/add", {list_name: "always", term}); notify(t("text.correct.always.done", {value: term})); }
    corrections.never = corrections.never.filter(v => v !== term);
    corrections.also[term] = $("#manualKind").value;
    $("#daMascherare").value = ""; $("#alsoAlways").checked = false;
    await mask();
  });
  // il testo selezionato nel risultato finisce nella casella «manca qualcosa»: basta premere il pulsante
  const selection = () => {
    const s = getSelection(), text = String(s).trim();
    if (text.length >= 2 && text.length <= 200 && !text.includes("\n") && !RX_PLACEHOLDER.test(text) && s.anchorNode && $("#outcome").contains(s.anchorNode) && !$("#correct").hidden) $("#daMascherare").value = text;
  };
  $("#outcome").addEventListener("mouseup", selection);
  $("#outcome").addEventListener("keyup", selection);
  const fresh = () => { corrections = {never: [], also: {}}; };
  const byItself = () => { if ($("#inbound").value.trim()) (RX_PLACEHOLDER.test($("#inbound").value) ? restore : mask)(); };
  $("#mask").onclick = mask;
  $("#restore").onclick = restore;
  $("#inbound").addEventListener("paste", () => { fresh(); setTimeout(byItself); });   // il testo incollato c'è solo un attimo dopo
  $("#inbound").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); byItself(); } });
  $("#paste").onclick = test(async () => {
    let text;
    try { text = await navigator.clipboard.readText(); } catch { throw new Error(t("text.paste.denied")); }
    $("#inbound").value = text;
    fresh(); byItself();
  });
  $("#clearText").onclick = () => {
    fresh(); result = "";
    $("#inbound").value = ""; $("#outcome").textContent = ""; $("#found_items").innerHTML = ""; $("#noteResult").textContent = "";
    $("#correct").hidden = true; $("#copyResult").disabled = true; $("#whatDone").textContent = t("text.result.empty");
    $("#inbound").focus();
  };
  $("#copyResult").onclick = () => copy(result);
};

// ---- Documenti
const base64 = buf => { let s = ""; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };
DRAW.documents = el => {
  const choice = `<div class="choice" role="radiogroup" aria-label="${esc(t("documents.action"))}">${["auto", "anonymize", "restore"].map((a, i) =>
      `<label><input type="radio" name="action" value="${a}"${i ? "" : " checked"}>${esc(t(`documents.${a}`))}</label>`).join("")}</div>`;
  el.innerHTML = card(`<div class="line"><h2>${esc(t("documents.file"))}</h2><span class="space"></span>${choice}</div>
      <div class="zone" id="zone"><span>${esc(t("documents.drag"))}</span>
        <label class="button"><input type="file" id="choose" class="vh" multiple>${esc(t("documents.choose"))}</label></div>
      <label class="line">${toggle("downloadByItself", t("documents.download_by_itself"))}<span>${esc(t("documents.download_by_itself"))}</span></label>
      <div id="outcomesFile" class="block" aria-live="polite"></div>`)
    + card(`<h2>${esc(t("documents.folder"))}</h2><p>${t("documents.folder.below")}</p>
      <div class="line"><input type="text" id="folderPath" class="space" aria-label="${esc(t("documents.folder.path"))}" placeholder="C:\\Lavoro\\Pratica Rossi">
        <button class="button" id="browse">${esc(t("documents.folder.browse"))}</button>
        <button class="button primary" data-folder="anonymize">${esc(t("documents.anonymize"))}</button><button class="button" data-folder="restore">${esc(t("documents.restore"))}</button></div>
      <div id="outcomeFolder" class="block" aria-live="polite"></div>`);
  const alone = $("#downloadByItself");
  alone.checked = memory("download_by_itself") !== "no";
  alone.onchange = () => memory("download_by_itself", alone.checked ? "yes" : "no");
  const work_on = async listing => {
    const action = $("input[name=action]:checked").value;
    for (const f of listing) {
      const r = document.createElement("div");
      r.className = "line";
      r.innerHTML = `<b>${esc(f.name)}</b><span class="faded">${esc(t("general.in_processing"))}</span>`;
      $("#outcomesFile").prepend(r);
      try {
        if (f.size > 40e6) throw new Error(t("documents.too_large"));
        const d = await api("/api/documents/file", {name: f.name, action, content: base64(await f.arrayBuffer())});
        const url = URL.createObjectURL(new Blob([Uint8Array.from(atob(d.content), c => c.charCodeAt(0))]));
        r.innerHTML = `<b>${esc(f.name)}</b>${label(t(`documents.done.${d.action}`))}<span class="labels">${counts(d.counts) || label(t("documents.no_replacement"))}</span><span class="space"></span>
          <a class="button${alone.checked ? "" : " primary"}" download="${esc(d.name)}" href="${url}">${esc(t("documents.download", {name: d.name}))}</a>`;
        if (alone.checked) $("a[download]", r).click();
      } catch (e) { r.innerHTML = `<b>${esc(f.name)}</b>${label(e.message, "error")}`; }
    }
  };
  $("#choose").onchange = e => { work_on([...e.target.files]); e.target.value = ""; };
  const zone = $("#zone");
  ["dragenter", "dragover"].forEach(n => zone.addEventListener(n, e => { e.preventDefault(); zone.classList.add("above"); }));
  ["dragleave", "drop"].forEach(n => zone.addEventListener(n, e => { e.preventDefault(); zone.classList.remove("above"); }));
  zone.addEventListener("drop", e => {
    // una cartella trascinata non si può leggere da qui: si usa «Cartella intera», che lavora direttamente sul disco
    const folders = [...(e.dataTransfer.items || [])].filter(x => x.webkitGetAsEntry?.()?.isDirectory).length;
    if (folders) { notify(t("documents.dragged_folder"), true); $("#browse").focus(); }
    if (folders < e.dataTransfer.files.length) work_on([...e.dataTransfer.files].filter((f, i) => !e.dataTransfer.items?.[i]?.webkitGetAsEntry?.()?.isDirectory));
  });
  $("#browse").onclick = test(async e => {
    e.target.disabled = true;
    try {
      const r = await api("/api/folder/choose", {initial: $("#folderPath").value});
      if (r.path) $("#folderPath").value = r.path;
    } finally { e.target.disabled = false; e.target.focus(); }
  });
  $$("button[data-folder]").forEach(b => b.onclick = test(async () => {
    const outcome = $("#outcomeFolder");
    if (!$("#folderPath").value.trim()) { $("#folderPath").focus(); return; }
    outcome.innerHTML = `<span class="faded">${esc(t("general.in_processing"))}</span>`;
    try {
      const r = await api("/api/documents/path", {path: $("#folderPath").value, action: b.dataset.folder});
      outcome.innerHTML = `<div class="line"><p class="space">${t("documents.folder.outcome", {completed: `<b>${r.completed.length}</b>`, skipped: `<b>${r.skipped.length}</b>`, where: `<code>${esc(r.destination)}</code>`})}</p>
          <button class="button" id="openFolder">${esc(t("documents.folder.open_up"))}</button></div>
        <div class="labels">${counts(r.counts) || label(t("documents.no_replacement"))}</div>`
        + table(t("documents.processed"), r.completed, [x => esc(x.file), x => `<span class="below">${esc(x.output)}</span>`, x => `<span class="labels">${counts(x.counts)}</span>`])
        + table(t("documents.skipped"), r.skipped, [x => esc(x.file), x => label(x.reason, "warning")]);
      $("#openFolder").onclick = test(() => api("/api/folder/open", {path: r.destination}));
    } catch (e) { outcome.innerHTML = ""; throw e; }
  }));
};

// ---- Guida
DRAW.guide = el => {
  const steps = (key, n) => `<ol class="listing">${Array.from({length: n}, (_, i) => `<li>${t(`${key}.${i + 1}`, KEYSTROKES)}</li>`).join("")}</ol>`;
  el.innerHTML = card(`<h2>${esc(t("guide.text"))}</h2>${steps("guide.text", 4)}`)
    + card(`<h2>${esc(t("guide.keyboard"))}</h2>${steps("guide.keyboard", 4)}<p class="help">${t("guide.keyboard.note")}</p>`)
    + card(`<h2>${esc(t("guide.documents"))}</h2>${steps("guide.documents", 3)}`)
    + card(`<h2>${esc(t("guide.automatic"))}</h2><p>${t("guide.automatic.text")}</p>`)
    + card(`<h2>${esc(t("guide.know"))}</h2><ul class="listing">${[1, 2, 3, 4].map(i => `<li>${t(`guide.know.${i}`)}</li>`).join("")}</ul>`)
    + card(`<h2>${esc(t("guide.welcome"))}</h2><p>${esc(t("guide.welcome.text"))}</p>`, `<button class="button" id="welcomeAgain">${esc(t("guide.welcome.again"))}</button>`)
    + card(`<h2>${esc(t("guide.contact"))}</h2><p>${esc(t("guide.contact.text"))}</p>`,
        `<a class="button" href="${CONTACT}" target="_blank" rel="noopener">${esc(t("general.write_me"))}</a><a class="button" href="${LINKEDIN}" target="_blank" rel="noopener">LinkedIn</a>`);
  $("#welcomeAgain").onclick = () => welcome(1);
};

// ---- Impostazioni
const save = async (data, message = "settings.saved") => { const r = await api("/api/settings", data); notify(t(message) + (r.restart_needed ? " " + t("settings.restart_needed") : "")); readStatus(); return r; };
DRAW.settings = (el, which) => (which === "recognition" ? recognitionSettings : generalSettings)(el);
// Le impostazioni decise da chi amministra il PC (registro di Windows): i comandi restano visibili, ma fermi.
const managedNote = i => ((i.managed || {}).keys || []).length || ((i.managed || {}).policies || []).length
  ? `<div class="note block" id="managedNote"><span class="space">${esc(t("managed.note"))}</span></div>` : "";
const lock = (i, pairs) => { for (const [selector, key] of pairs) if (((i.managed || {}).keys || []).includes(key)) $$(selector).forEach(x => { x.disabled = true; x.title = t("managed.locked"); }); };
// La console centrale di un'organizzazione: di serie questo PC non manda nulla a nessuno.
const drawConsole = test(async () => {
  const el = $("#console");
  if (!el) return;
  const c = await api("/api/console");
  const problem = c.error ? t(`console.error.${["address", "unreachable", "certificate"].includes(c.error) ? c.error : c.error === "http_401" || c.error === "http_403" ? "refused" : c.error === "http_402" ? "licence" : "answer"}`) : "";
  el.closest("section").classList.toggle("only-advanced", !c.configured);
  el.innerHTML = c.configured
    ? line(t("console.connected", {host: c.host}), esc(t(c.names ? "console.sends.names" : "console.sends")) + (c.pinned ? " " + esc(t("console.pinned")) : "") + (c.managed ? " " + esc(t("managed.locked")) : ""),
        label(problem || (c.last ? t("console.last", {when: c.last}) : t("console.never")), problem ? "error" : c.last ? "ok" : ""))
      + (c.rules ? `<div class="setting"><span class="name">${esc(t("console.rules"))}</span><span class="help">${esc(t("console.rules.below"))}${c.rules.accept ? " " + esc(c.rules.count ? t("console.rules.count", {n: c.rules.count, when: c.rules.received}) : t("console.rules.none")) : ""}${c.rules.managed ? " " + esc(t("managed.locked")) : ""}</span><span class="command">${toggle("conRules", t("console.rules"))}</span></div>` : "")
      + `<div class="setting"><span class="help">${esc(t("console.what"))}</span><span class="command"><button class="button" id="conPreview">${esc(t("console.preview"))}</button><button class="button" id="conSend">${esc(t("console.send"))}</button>${c.managed ? "" : `<button class="button" id="conOff">${esc(t("console.disconnect"))}</button>`}</span></div><pre id="conData" hidden></pre>`
    : `<div class="setting"><span class="name">${esc(t("console.none"))}</span><span class="help">${esc(t("console.none.below"))} <a href="${CONTACT}" target="_blank" rel="noopener">${esc(t("console.contact"))}</a></span></div>
       <div class="setting"><span class="help"><input type="text" class="wide" id="conUrl" placeholder="https://" aria-label="${esc(t("console.url"))}"> <input type="text" class="wide" id="conKey" placeholder="${esc(t("console.key"))}" aria-label="${esc(t("console.key"))}" autocomplete="off"> <input type="text" class="wide" id="conPin" placeholder="${esc(t("console.pin"))}" aria-label="${esc(t("console.pin"))}" autocomplete="off"></span><span class="command"><button class="button" id="conOn">${esc(t("console.connect"))}</button></span></div>`;
  const act = (id, f) => { if ($(id)) $(id).onclick = test(async e => { e.target.disabled = true; try { await f(); } finally { e.target.disabled = false; } }); };
  act("#conPreview", async () => { const p = $("#conData"); p.textContent = JSON.stringify((await api("/api/console", {action: "preview"})).preview, null, 1); p.hidden = false; });
  act("#conSend", async () => { await api("/api/console", {action: "send"}); await drawConsole(); });
  act("#conOff", async () => { if (await confirm(t("console.disconnect"), t("console.disconnect.confirm"), t("console.disconnect"))) { await api("/api/console", {action: "disconnect"}); await drawConsole(); } });
  if ($("#conRules")) { $("#conRules").checked = c.rules.accept; $("#conRules").disabled = c.rules.managed; }
  if ($("#conRules")) $("#conRules").onchange = test(async e => { await api("/api/console", {action: "rules", accept: e.target.checked}); await drawConsole(); });
  act("#conOn", async () => { await api("/api/console", {action: "connect", url: $("#conUrl").value, key: $("#conKey").value, pin: $("#conPin").value}); await drawConsole(); });
});
// Il server di inferenza in rete: di serie ogni PC usa il suo modello; uno puo' prestarlo agli altri, oppure usare quello di un altro.
let serverSeen = "";
const drawServer = test(async () => {
  const el = $("#server");
  if (!el) return;
  const typed = $("#srvConfig")?.value || "";   // la scheda si ridisegna quando lo stato cambia: cio' che si stava scrivendo resta
  const s = await api("/api/server");
  el.dataset.mode = s.mode;
  el.dataset.listening = s.server && s.server.listening ? "yes" : "no";
  const fixed = s.managed ? " " + esc(t("managed.locked")) : "";
  if (s.mode === "server") {
    const sv = s.server;
    el.innerHTML = line(t("server.sharing"), esc(t("server.sharing.below")) + fixed,
        label(t(sv.listening ? "server.listening" : s.active ? "server.not_listening" : "server.waiting", {port: sv.port}), sv.listening ? "ok" : "warning"))
      + `<div class="setting"><span class="name">${esc(t("server.address"))}</span><span class="help">${esc(t("server.address.below"))}</span></div>
        <div class="inside"><div class="labels">${sv.addresses.map(a => `<code>${esc(a)}</code>`).join("")}</div></div>`
      + line(t("server.pin"), esc(t("server.pin.below")), `<code id="srvPin">${esc(sv.pin.replace(/(.{4})/g, "$1 ").trim())}</code>`)
      + `<div class="setting"><span class="help">${esc(t("server.give"))}</span><span class="command"><button class="button" id="srvCopy">${esc(t("server.copy"))}</button><button class="button" id="srvShow">${esc(t("server.show"))}</button>${
          s.managed ? "" : `<button class="button" id="srvStop">${esc(t("server.stop"))}</button>`}</span></div><pre id="srvData" hidden></pre>
        <div class="inside" id="srvClients"></div>`;
    drawClients(sv.clients);
  } else if (s.mode === "client") {
    const c = s.client, problem = c.ok === false && c.error ? t(`server.error.${["refused", "certificate", "unreachable"].includes(c.error) ? c.error : "answer"}`) : "";
    el.innerHTML = line(t("server.using", {host: c.host}), esc(t("server.using.below")) + (c.pinned ? " " + esc(t("console.pinned")) : "") + fixed,
        label(problem || (c.ok ? t("server.answers", {model: c.model, ms: c.ms}) : t("server.waiting")), problem ? "error" : c.ok ? "ok" : "warning"))
      + `<div class="setting"><span class="help">${esc(t("server.stays"))}</span><span class="command"><button class="button" id="srvTest">${esc(t("server.test"))}</button>${
          s.managed ? "" : `<button class="button" id="srvLeave">${esc(t("server.leave"))}</button>`}</span></div>`;
  } else {
    el.innerHTML = line(t("server.local"), esc(t("server.local.below")) + fixed, s.managed ? "" : `<button class="button" id="srvShare">${esc(t("server.share"))}</button>`)
      + (s.managed ? "" : `<div class="setting"><span class="name">${esc(t("server.use"))}</span><span class="help">${esc(t("server.use.below"))}</span></div>
        <div class="inside"><textarea class="short" id="srvConfig" spellcheck="false" autocomplete="off" aria-label="${esc(t("server.use.field"))}" placeholder='{"engine_url": "https://…", "engine_key": "…", "engine_pin": "…"}'></textarea>
          <div class="line"><button class="button" id="srvUse">${esc(t("server.use.button"))}</button></div></div>`);
    if ($("#srvConfig")) $("#srvConfig").value = typed;
  }
  const act = (id, f) => { if ($(id)) $(id).onclick = test(async e => { e.target.disabled = true; try { await f(); } finally { e.target.disabled = false; } }); };
  const change = async data => { await api("/api/server", data); serverSeen = ""; await readStatus(); await drawServer(); };
  act("#srvShare", async () => { if (await confirm(t("server.share.confirm.title"), t("server.share.confirm"), t("server.share"))) await change({action: "share", on: true}); });
  act("#srvStop", async () => { if (await confirm(t("server.stop.confirm.title"), t("server.stop.confirm"), t("server.stop"))) await change({action: "share", on: false}); });
  act("#srvLeave", async () => { if (await confirm(t("server.leave.confirm.title"), t("server.leave.confirm"), t("server.leave"))) await change({action: "leave"}); });
  act("#srvUse", async () => { await change({action: "use", config: $("#srvConfig").value}); notify(t("server.use.done")); });
  act("#srvCopy", async () => copy(JSON.stringify((await api("/api/server", {action: "config"})).config, null, 1), t("server.copied")));
  act("#srvShow", async () => { const p = $("#srvData"); p.textContent = JSON.stringify((await api("/api/server", {action: "config"})).config, null, 1); p.hidden = false; });
  act("#srvTest", async () => { const r = (await api("/api/server", {action: "test"})).test; notify(r.ok ? t("server.test.ok", {model: r.model}) : t(`server.error.${r.error}`), !r.ok); await drawServer(); });
});
function drawClients(clients) {
  const el = $("#srvClients");
  if (!el) return;
  const when = s => new Date(s * 1000).toLocaleString(LANGUAGE, {dateStyle: "short", timeStyle: "short"});
  el.innerHTML = clients.length
    ? `<h3>${esc(t("server.clients"))} <span class="faded">(${clients.length})</span></h3><div class="table"><table><thead><tr>${["name", "texts", "last"].map(c => `<th scope="col">${esc(t(`server.clients.${c}`))}</th>`).join("")}</tr></thead><tbody>${
        clients.map(c => `<tr><td><b>${esc(c.name)}</b></td><td>${num(c.texts)}</td><td>${esc(when(c.last))}</td></tr>`).join("")}</tbody></table></div>`
    : `<span class="faded">${esc(t("server.clients.none"))}</span>`;
}
// lo stato cambia da solo (il motore riparte, il server torna a rispondere, un PC chiede qualcosa): la scheda lo segue
async function followServer(s) {
  if (!$("#server")) return;
  const now = [s.phase, s.shared, s.remote && s.remote.ok, s.remote && s.remote.error].join("|");
  if (now !== serverSeen) { serverSeen = now; await drawServer(); }
  else if ($("#srvClients")) { try { drawClients(((await api("/api/server")).server || {clients: []}).clients); } catch { /* al prossimo giro */ } }
}
const generalSettings = test(async el => {
  const [i, l] = await Promise.all([api("/api/settings"), api("/api/languages")]);
  const options = (entries, choice) => entries.map(([v, n]) => `<option value="${esc(v)}"${v === choice ? " selected" : ""}>${esc(n)}</option>`).join("");
  el.innerHTML = `${managedNote(i)}<section class="card" aria-label="${esc(t("settings.appearance"))}">
      ${line(t("settings.language"), esc(t("settings.language.below")), `<select id="language" aria-label="${esc(t("settings.language"))}">${options([["auto", t("settings.automatic")], ...l.available.map(x => [x.code, x.name])], l.choice)}</select>`)}
      ${line(t("settings.theme"), "", `<select id="theme" aria-label="${esc(t("settings.theme"))}">${options([["auto", t("settings.theme.auto")], ["light", t("settings.theme.light")], ["dark", t("settings.theme.dark")]], i.theme || "auto")}</select>`)}
      ${line(t("menu.advanced"), esc(t("settings.advanced.below")), toggle("advanced2", t("menu.advanced")))}
    </section>
    <section class="card" aria-labelledby="scTitle">
      <div class="inside"><h2 id="scTitle">${esc(t("shortcuts.title"))}</h2><p>${t("shortcuts.below")}</p></div>
      <div id="shortcuts"></div>
    </section>
    <section class="card" aria-labelledby="aggTitle">
      <div class="inside"><h2 id="aggTitle">${esc(t("updates.title"))}</h2><p id="aggNote"></p></div>
      ${line(t("updates.installed"), `<span id="aggWhen"></span>`, `<b id="aggVersion">…</b>`)}
      <div id="aggChoice">${line(t("updates.new_ones"), "", `<select id="updates" aria-label="${esc(t("updates.new_ones"))}">${options(["automatic", "notify", "never"].map(v => [v, t(`updates.mode.${v}`)]), i.updates)}</select><button class="button" id="aggCheck">${esc(t("updates.check_now"))}</button>`)}</div>
    </section>
    <section class="card only-advanced" aria-labelledby="conTitle">
      <div class="inside"><h2 id="conTitle">${esc(t("console.title"))}</h2><p>${esc(t("console.below"))}</p></div>
      <div id="console"></div>
    </section>`;
  lock(i, [["#language", "language"], ["#theme", "theme"], ["#advanced2", "view"], ["#advanced", "view"], ["#updates", "updates"]]);
  drawConsole();
  $("#language").onchange = test(async e => { await api("/api/settings", {language: e.target.value}); location.reload(); });
  $("#theme").onchange = test(async e => { applyTheme(e.target.value); await save({theme: e.target.value}); });
  $("#advanced2").checked = view === "advanced";
  $("#advanced2").onchange = e => changeView(e.target.checked);
  $("#updates").onchange = test(e => save({updates: e.target.value}));
  $("#aggCheck").onclick = test(async e => {
    e.target.disabled = true;
    try {
      const a = await api("/api/updates", {action: "check"});
      notify(a.phase === "error" ? a.error : a.phase === "updated" ? t("updates.latest") : t("updates.available", {v: a.version}), a.phase === "error");
      readStatus();
    } finally { e.target.disabled = false; }
  });
  drawShortcuts();
  if (S) REFRESH.settings(S);
});
// Le scorciatoie da tastiera: una riga ciascuna, con la lettera da premere insieme a Ctrl+Alt (oppure spenta) e lo stato.
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
const drawShortcuts = test(async () => {
  const el = $("#shortcuts");
  if (!el) return;
  const s = await api("/api/shortcuts");
  el.innerHTML = s.entries.map(v => {
    const simple = /^ctrl\+alt\+[a-z]$/.test(v.combo), letter = simple ? v.combo.slice(-1).toUpperCase() : "";
    const status = !v.combo ? label(t("shortcuts.off")) : !s.available ? "" : v.active ? label(t("shortcuts.active"), "ok") : label(t(`shortcuts.error.${v.error === "not_valid" ? "not_valid" : "busy"}`), "error");
    return line(t(`shortcuts.${v.name}`), t(`shortcuts.${v.name}.below`), `${status}<span class="keystrokes" aria-hidden="true"><kbd>Ctrl</kbd>+<kbd>Alt</kbd>+</span>
      <select data-sc="${esc(v.name)}" aria-label="${esc(t("shortcuts.letter_for", {name: t(`shortcuts.${v.name}`)}))}">
        <option value=""${v.combo ? "" : " selected"}>${esc(t("shortcuts.off"))}</option>
        ${v.combo && !simple ? `<option value="${esc(v.combo)}" selected>${esc(v.caption)}</option>` : ""}
        ${LETTERS.map(l => `<option value="ctrl+alt+${l.toLowerCase()}"${l === letter ? " selected" : ""}>${l}</option>`).join("")}</select>`);
  }).join("") + (s.available ? "" : `<div class="setting"><span class="help">${esc(t("shortcuts.without_icon"))}</span></div>`);
  $$("select[data-sc]", el).forEach(x => x.onchange = test(async () => {
    const choices = Object.fromEntries(s.entries.map(v => [v.name, v.combo]));
    choices[x.dataset.sc] = x.value;
    await api("/api/settings", {shortcuts: choices});
    const after = (await api("/api/shortcuts")).entries.find(v => v.name === x.dataset.sc);
    if (after.combo && !after.active && after.error) notify(t(`shortcuts.error.${after.error === "not_valid" ? "not_valid" : "busy"}.long`, {keystrokes: after.caption}), true);
    else notify(t("settings.saved"));
    await readKeystrokes();
    drawShortcuts();
  }));
});
REFRESH.settings = s => {
  followServer(s);
  const a = s.update;
  if (!a || !$("#aggVersion")) return;
  $("#aggVersion").textContent = a.current;
  $("#aggWhen").textContent = a.channel === "store" ? "" : a.phase === "check" ? t("updates.checking") : a.phase === "error" ? a.error
    : a.last_check ? t("updates.last_check", {when: a.last_check}) + (a.phase === "updated" ? " " + t("updates.latest") : "") : "";
  $("#aggChoice").hidden = a.channel === "store";
  $("#aggNote").textContent = t(`updates.note.${["store", "source_code"].includes(a.channel) ? a.channel : "installer"}`);
};
const recognitionSettings = test(async el => {
  const [i, l, cat] = await Promise.all([api("/api/settings"), api("/api/lists"), api("/api/categories")]);
  // le categorie in più del modello, in due gruppi: si accendono insieme perché da sole servono a poco
  const GROUPS = {special: ["SALUTE", "RELIGIONE", "POLITICA", "ORIENTAMENTO", "ORIGINE"],
                  details: ["DATA", "ORA", "ETA", "GENERE", "TITOLO", "PROFESSIONE", "ISTRUZIONE", "LUOGO"]};
  const groups = Object.entries(GROUPS).map(([name, entries]) => [name, entries.filter(v => cat.known.includes(v))]).filter(([, entries]) => entries.length);
  el.innerHTML = `${managedNote(i)}<section class="card" aria-label="${esc(t("settings.card.recognition"))}">
      ${line(t("recognition.model"), esc(t("recognition.model.below")), `<select id="model" aria-label="${esc(t("recognition.model"))}"><option value="omissis-base">${esc(t("recognition.model.base"))}</option><option value="omissis-small">${esc(t("recognition.model.small"))}</option></select>`)}
      ${line(t("recognition.where"), "", `<select id="device" aria-label="${esc(t("recognition.where"))}">${["auto", "cuda", "cpu"].map(v => `<option value="${v}">${esc(t(`recognition.where.${v}`))}</option>`).join("")}</select>`)}
      ${["box", "attachments", "restore", "block_files"].map(k => line(t(`recognition.${k}`), esc(t(`recognition.${k}.below`)), toggle(k, t(`recognition.${k}`)))).join("")}
    </section>
    <section class="card" aria-labelledby="srvTitle">
      <div class="inside"><h2 id="srvTitle">${esc(t("server.title"))}</h2><p>${esc(t("server.below"))}</p></div>
      <div id="server"></div>
    </section>
    <section class="card" aria-labelledby="grpTitle">
      <div class="inside"><h2 id="grpTitle">${esc(t("groups.title"))}</h2><p>${esc(t("groups.below"))}</p></div>
      ${Object.entries(i.groups_always).map(([name, entries]) => line(t(`groups.${name}`), esc(entries.map(dataKind).join(", ")), label(t("groups.always"), "ok"))).join("")}
      ${Object.entries(i.groups).map(([name, entries]) => line(t(`groups.${name}`), esc(entries.map(dataKind).concat(tSe(`groups.${name}.more`, "") || []).join(", ")), toggle(`grp-${name}`, t(`groups.${name}`)))).join("")}
    </section>
    ${groups.length ? `<section class="card" aria-labelledby="catTitle">
      <div class="inside"><h2 id="catTitle">${esc(t("categories.title"))}</h2><p>${esc(t("categories.below"))}</p></div>
      ${groups.map(([name, entries]) => line(t(`categories.${name}`), esc(t(`categories.${name}.below`, {listing: entries.map(dataKind).join(", ").toLowerCase()})), toggle(`cat-${name}`, t(`categories.${name}`)))).join("")}
    </section>` : ""}
    <div class="two">
      ${card(`<h2 id="lAlways">${esc(t("lists.always"))}</h2><p>${esc(t("lists.always.below"))}</p><textarea id="always" aria-labelledby="lAlways"></textarea>`)}
      ${card(`<h2 id="lNever">${esc(t("lists.never"))}</h2><p>${esc(t("lists.never.below"))}</p><textarea id="never" aria-labelledby="lNever"></textarea>`)}
    </div>
    <div class="line"><button class="button primary" id="saveLists">${esc(t("lists.save"))}</button><span class="faded small">${esc(t("lists.note"))}</span></div>`;
  for (const k of ["model", "device"]) { $(`#${k}`).value = i[k]; $(`#${k}`).onchange = test(e => save({[k]: e.target.value})); }
  for (const k of ["box", "attachments", "restore", "block_files"]) { $(`#${k}`).checked = i[k] !== false && !!i[k]; $(`#${k}`).onchange = test(e => save({[k]: e.target.checked})); }
  let off = (i.groups_off || []).slice();
  for (const name of Object.keys(i.groups)) {
    $(`#grp-${name}`).checked = !off.includes(name);
    $(`#grp-${name}`).onchange = test(async e => {
      // spegnere riduce la protezione: lo si fa solo dopo una conferma, e la pagina iniziale lo ricorda
      if (!e.target.checked && !await confirm(t("groups.confirm.title", {name: t(`groups.${name}`)}), t("groups.confirm"), t("groups.confirm.yes"))) { e.target.checked = true; return; }
      off = off.filter(g => g !== name).concat(e.target.checked ? [] : [name]);
      await save({groups_off: off}, e.target.checked ? "groups.saved_on" : "groups.saved_off");
    });
  }
  let enabled = cat.enabled.slice();
  for (const [name, entries] of groups) {
    $(`#cat-${name}`).checked = entries.every(v => enabled.includes(v));
    $(`#cat-${name}`).onchange = test(async e => {
      enabled = enabled.filter(v => !entries.includes(v)).concat(e.target.checked ? entries : []);
      await save({categories: enabled});
    });
  }
  lock(i, [["#model", "model"], ["#device", "device"], ...["box", "attachments", "restore", "block_files"].map(k => [`#${k}`, k]),
           ['[id^="grp-"]', "groups_off"], ['[id^="cat-"]', "categories"]]);
  $("#always").value = l.always.join("\n"); $("#never").value = l.never.join("\n");
  serverSeen = "";
  drawServer();
  $("#saveLists").onclick = test(async () => {
    const r = await api("/api/lists", {always: $("#always").value.split("\n"), never: $("#never").value.split("\n")});
    notify(t("lists.saved", {always: r.always.length, never: r.never.length}));
  });
});

// ---- Collegamenti
DRAW.connections = (el, which) => ({browser: connectBrowser, app: connectApp, terminal: connectTerminal, mcp: connectMcp, proxy: connectProxy, compatibility: connectCompatibility}[which])(el);
REFRESH.connections = () => { if (opened.card === "app" && !$("button[data-app]:disabled")) appListing(); if (opened.card === "terminal") gatewayStatus(); };

function drawExtension() {
  const e = $("#estStatus");
  if (!e) return;
  const status = !extension ? "absent" : !extension.connected ? "to_connect" : extension.ok ? "connected" : "no_response";
  e.dataset.status = status;
  e.className = "label " + (status === "connected" ? "ok" : status === "absent" ? "" : "warning");
  e.textContent = (extension ? t("browser.version", {v: extension.version}) + " · " : "") + t(`browser.status.${status}`);
  $("#estConnect").disabled = !extension;
  $("#estConnect").textContent = t(extension && extension.connected ? "browser.reconnect" : "browser.connect");
}
// la pagina dello store da cui installare l'estensione in questo browser, se è già pubblicata (Edge accetta anche quello di Chrome)
const storeLink = d => { const s = d.store || {}; return (/Edg\//.test(navigator.userAgent) && s.edge) || s.chrome || ""; };
const extensionData = async () => { const d = await api("/api/extension"); if (!d.token) throw new Error(t("browser.code_not_ready")); return d; };
const connectBrowser = test(async el => {
  el.innerHTML = card(`<h2>${esc(t("browser.connection"))}</h2><p>${esc(t("browser.connection.below"))}</p>`,
      `<span id="estStatus" class="label">…</span><span class="space"></span><button class="button primary" id="estConnect">${esc(t("browser.connect"))}</button>`)
    + card(`<div id="estStoreBox" hidden><h2>${esc(t("browser.store.title"))}</h2><p>${esc(t("browser.store.below"))}</p>
        <div class="line"><a class="button primary" id="estStore" target="_blank" rel="noopener">${esc(t("browser.store"))}</a></div></div>
      <h2>${esc(t("browser.installation"))}</h2>
      <ol class="listing"><li>${t("browser.installation.1")}</li><li>${t("browser.installation.2")}
        <div class="line"><code id="estFolder">…</code><button class="button" id="estCopyFolder">${esc(t("browser.copy_path"))}</button></div></li>
        <li>${t("browser.installation.3")}</li><li>${t("browser.installation.4")}</li></ol>`)
    + card(`<h2>${esc(t("browser.by_hand"))}</h2><p>${esc(t("browser.by_hand.below"))}</p>`, `<button class="button" id="estCopyCode">${esc(t("browser.copy_code"))}</button>`);
  drawExtension();
  $("#estConnect").onclick = test(async () => { const d = await extensionData(); window.postMessage({omissis: "connect", token: d.token, port: d.port}, location.origin); });
  $("#estCopyFolder").onclick = () => copy($("#estFolder").textContent);
  $("#estCopyCode").onclick = test(async () => copy((await extensionData()).token));
  window.postMessage({omissis: "ping"}, location.origin);
  const ext = await api("/api/extension");
  $("#estFolder").textContent = ext.folder;
  if (storeLink(ext)) { $("#estStore").href = storeLink(ext); $("#estStoreBox").hidden = false; }
});

function drawApp(listing, even_if_same = true) {
  const el = $("#appListing");
  if (!el) return;
  // l'elenco si rilegge da solo ogni pochi secondi: se nulla e' cambiato non lo si ridisegna (chi e' su un pulsante con la tastiera ci resta)
  const now = JSON.stringify(listing);
  if (!even_if_same && el.dataset.drawn === now) return;
  el.dataset.drawn = now;
  el.innerHTML = listing.map(a => {
    const c = a.counts;
    const pl = a.plugin;
    const status = !a.installed ? label(t("app.status.not_installed"))
      : pl ? (pl.installed ? label(t("app.plugin.status.yes"), "ok") : label(t("app.plugin.status.no")))
      : !a.connected ? (a.open_unprotected ? label(t("app.status.open_unprotected"), "error") : label(t("app.status.not_connected")))
      : a.outcome === "yes" ? label(t("app.status.yes"), "ok") : a.outcome === "waiting" ? label(t("app.status.waiting"), "warning") : label(t("app.status.no"), "error");
    const numbers = c ? `<span class="help">${esc(t("app.numbers", {pages: c.pages, messages: c.messages, checked_count: c.checked_count, replacements: c.replacements, blocked: c.blocked}))}</span>` : "";
    const button = !a.installed ? "" : pl ? `<button class="button${pl.ready ? "" : " primary"}" data-app="${esc(a.id)}" data-action="plugin">${esc(t(pl.ready ? "app.plugin.update" : "app.plugin.prepare"))}</button>`
      : a.refuses ? "" : a.connected ? `<button class="button" data-app="${esc(a.id)}" data-action="detach">${esc(t("app.detach"))}</button>`
      : a.open_unprotected ? `<button class="button primary" data-app="${esc(a.id)}" data-name="${esc(a.name)}" data-action="relaunch">${esc(t("app.relaunch"))}</button>`
      : `<button class="button primary" data-app="${esc(a.id)}" data-action="launch">${esc(t("app.launch"))}</button>`;
    const errors = (a.errors || []).map(e => `<div class="note error">${esc(e)}</div>`).join("");
    // cio' che conviene sapere prima di fidarsi: un servizio non impostato su «Proteggi», un profilo separato
    const notes = !a.installed ? "" : pl ? `<div class="note" data-app-note="plugin">${esc(t("app.plugin.note", {name: a.name}))}</div>`
        + (a.policy !== "protect" ? `<div class="note warning" data-app-note="policy">${esc(t("app.plugin.policy", {service: a.service, policy: t(`services.policy.${a.policy}`)}))}</div>` : "")
        + (pl.ready && !pl.installed ? `<div class="note" data-app-note="plugin-steps"><b>${esc(t("app.plugin.steps"))}</b><ol class="listing"><li>${esc(t("app.plugin.step.1", {name: a.name}))}<br><code id="pluginSentence">${esc(pl.sentence)}</code> <button class="button" id="pluginCopy">${esc(t("app.plugin.copy"))}</button></li><li>${esc(t("app.plugin.step.2"))}</li><li>${esc(t("app.plugin.step.3"))}</li></ol><span class="help">${esc(t("app.plugin.folder", {folder: pl.folder}))}</span></div>` : "")
      : a.refuses ? `<div class="note warning" data-app-note="refuses">${esc(t("app.note.refuses", {name: a.name}))}</div>`
      : (a.policy !== "protect" ? `<div class="note warning" data-app-note="policy">${esc(t("app.note.policy", {service: a.service, policy: t(`services.policy.${a.policy}`)}))}</div>` : "")
      + (a.own_profile ? `<div class="note" data-app-note="profile">${esc(t("app.note.own_profile", {name: a.name}))}</div>` : "");
    return `<div class="setting" data-app-line="${esc(a.id)}" data-outcome="${esc(a.connected ? a.outcome || "no" : "")}" data-open="${a.open_unprotected ? "unprotected" : ""}"><span class="name">${esc(a.name)} ${status}</span>${numbers}<span class="command">${button}</span></div>${notes}${errors}`;
  }).join("");
  if ($("#pluginCopy", el)) $("#pluginCopy", el).onclick = async () => { try { await navigator.clipboard.writeText($("#pluginSentence", el).textContent); notify(t("app.plugin.copied")); } catch (e) { /* la frase resta leggibile nella pagina */ } };
  $$("button[data-app]", el).forEach(b => b.onclick = test(async () => {
    if (b.dataset.action === "relaunch" && !await confirm(t("app.relaunch.title", {name: b.dataset.name}), t("app.relaunch.text", {name: b.dataset.name}), t("app.relaunch"))) return;
    b.disabled = true;
    b.textContent = b.dataset.action === "launch" ? t("app.startup_pending") : "…";
    try { drawApp(await api("/api/app", {id: b.dataset.app, action: b.dataset.action})); } catch (e) { appListing(); throw e; }
  }));
}
const appListing = test(async () => drawApp(await api("/api/app")));
/** Lo stato delle app cambia senza che nessuno tocchi la pagina (una finestra agganciata, un'app chiusa): lo si rilegge da soli. */
const appListingQuiet = async () => {
  const el = $("#appListing");
  if (!el || $("button:disabled", el) || document.querySelector("dialog[open]")) return;   // non durante un avvio o una conferma
  try { drawApp(await api("/api/app"), false); } catch (e) { /* al prossimo giro */ }
};
const connectApp = el => {
  el.innerHTML = `<section class="card" aria-label="${esc(t("connections.card.app"))}" id="appListing"><div class="empty">…</div></section>`
    + card(`<h2>${esc(t("app.know"))}</h2><ul class="listing faded">${[1, 2, 3, 4, 5].map(i => `<li>${t(`app.know.${i}`)}</li>`).join("")}</ul>`);
  appListing();
};

const gatewayStatus = test(async () => {
  const g = await api("/api/gateway"), e = $("#gwStatus");
  if (!e) return g;
  e.textContent = g.is_active ? t("terminal.is_active", {port: g.port}) : g.error || t("terminal.stopped");
  e.className = "label " + (g.is_active ? "ok" : g.error ? "error" : "");
  $("#gwNumbers").textContent = g.counts ? t("terminal.numbers", g.counts) : "";
  return g;
});
const connectTerminal = test(async el => {
  el.innerHTML = card(`<div class="line"><h2>${esc(t("terminal.status"))}</h2><span id="gwStatus" class="label">…</span><span class="space"></span><span class="faded small" id="gwNumbers"></span></div>`)
    + card(`<h2>${esc(t("terminal.how"))}</h2><p>${esc(t("terminal.how.below"))}</p><div class="block" id="gwLines"></div>`)
    + `<section class="card" aria-label="${esc(t("terminal.own"))}"><div class="inside"><h2>${esc(t("terminal.own"))}</h2><p>${esc(t("terminal.own.below"))}</p></div>
        ${["anthropic", "openai"].map(n => line(t(`terminal.own.${n}`), "", `<input type="text" class="wide" data-own="${n}" placeholder="https://" aria-label="${esc(t(`terminal.own.${n}`))}">`)).join("")}
        <div class="footer"><span class="space"></span><button class="button" id="ownSave">${esc(t("general.save"))}</button></div></section>`
    + card(`<h2>${esc(t("terminal.verified"))}</h2><ul class="listing faded">${[1, 2, 3, 4, 5].map(i => `<li>${t(`terminal.verified.${i}`)}</li>`).join("")}</ul>`);
  const g = await gatewayStatus(), u = `http://127.0.0.1:${g.port}`;
  // Codex con l'accesso di ChatGPT: un fornitore in piu' nella sua configurazione, che manda qui le richieste con quell'accesso
  const codex = `# ${t("terminal.codex.top")}\nmodel_provider = "omissis"\n\n# ${t("terminal.codex.bottom")}\n[model_providers.omissis]\nname = "Omissis"\nbase_url = "${u}/openai/v1"\nwire_api = "responses"\nrequires_openai_auth = true`;
  const lines = [["claude", `$env:ANTHROPIC_BASE_URL="${u}/anthropic"; claude`], ["codex", codex], ["openai", `$env:OPENAI_BASE_URL="${u}/openai/v1"`],
    ["others", g.routes.filter(r => !["anthropic", "openai", "codex", "ollama", "lmstudio"].includes(r)).map(r => `${u}/${r}`).join("\n")], ["local", `${u}/ollama/v1\n${u}/lmstudio/v1`]];
  $("#gwLines").innerHTML = lines.map(([n, r]) => `<div><div class="line"><h3>${esc(t(`terminal.line.${n}`))}</h3><span class="space"></span><button class="button" data-copy="${esc(r)}">${esc(t("general.copy"))}</button></div><pre>${esc(r)}</pre></div>`).join("");
  $$("button[data-copy]").forEach(b => b.onclick = () => copy(b.dataset.copy));
  $$("input[data-own]").forEach(i => { i.value = g.upstreams[i.dataset.own] || ""; });
  $("#ownSave").onclick = test(async () => {
    const upstreams = {...g.upstreams};
    $$("input[data-own]").forEach(i => { upstreams[i.dataset.own] = i.value.trim(); });
    g.upstreams = (await api("/api/gateway", {upstreams})).upstreams;
    notify(t("terminal.own.saved"));
  });
});

// Il server MCP: la strada ufficiale dentro Claude Desktop e gli editor, per i documenti. Si registra nella configurazione dell'app.
const drawMcp = m => {
  const c = m.claude_desktop, e = $("#mcpStatus");
  if (!e) return;
  e.textContent = c.registered ? t(c.current ? "mcp.registered" : "mcp.registered_old") : t("mcp.not_registered");
  e.className = "label " + (c.registered ? (c.current ? "ok" : "warning") : "");
  $("#mcpClaude").innerHTML = !c.installed ? `<span class="faded">${esc(t(c.by_hand ? "mcp.claude.by_hand" : "mcp.claude.absent"))}</span>`
    : (c.registered && c.current ? "" : `<button class="button primary" data-mcp="install">${esc(t("mcp.install"))}</button>`)
      + (c.registered ? `<button class="button" data-mcp="uninstall">${esc(t("mcp.uninstall"))}</button>` : "");
  $$("button[data-mcp]").forEach(b => b.onclick = test(async () => {
    const action = b.dataset.mcp;
    drawMcp(await api("/api/mcp", {action}));
    notify(t(action === "install" ? "mcp.installed" : "mcp.uninstalled"));
  }));
};
const connectMcp = test(async el => {
  const m = await api("/api/mcp");
  el.innerHTML = card(`<div class="line"><h2>${esc(t("mcp.status"))}</h2><span id="mcpStatus" class="label">…</span></div><p>${esc(t("mcp.what.below"))}</p>`)
    + `<section class="card" aria-label="${esc(t("mcp.claude"))}">${line(t("mcp.claude"), esc(t("mcp.claude.below")), `<span id="mcpClaude" class="line"></span>`)}</section>`
    + card(`<h2>${esc(t("mcp.others"))}</h2><p>${esc(t("mcp.others.below"))}</p><div class="block">${["json", "claude_code", "codex"].map(n =>
      `<div><div class="line"><h3>${esc(t(`mcp.line.${n}`))}</h3><span class="space"></span><button class="button" data-copy="${esc(m.snippets[n])}">${esc(t("general.copy"))}</button></div><pre>${esc(m.snippets[n])}</pre></div>`).join("")}</div>`)
    + card(`<h2>${esc(t("mcp.folders"))}</h2><p>${esc(t("mcp.folders.below", {folders: m.folders.join(" · ")}))}</p>
      <textarea id="mcpFolders" class="short" aria-label="${esc(t("mcp.folders"))}">${esc(m.extra.join("\n"))}</textarea>
      <div class="line"><span class="space"></span><button class="button" id="mcpSave">${esc(t("general.save"))}</button></div>`)
    + card(`<h2>${esc(t("mcp.know"))}</h2><ul class="listing faded">${[1, 2, 3, 4].map(i => `<li>${t(`mcp.know.${i}`)}</li>`).join("")}</ul>`);
  drawMcp(m);
  $$("button[data-copy]").forEach(b => b.onclick = () => copy(b.dataset.copy));
  $("#mcpSave").onclick = test(async () => {
    await api("/api/mcp", {action: "folders", folders: $("#mcpFolders").value.split("\n")});
    notify(t("mcp.folders.saved"));
  });
});

const connectProxy = test(async el => {
  const i = await api("/api/settings");
  el.innerHTML = `<section class="card" aria-label="${esc(t("connections.card.proxy"))}">
      ${line(t("proxy.port"), esc(t("proxy.port.below")), `<input type="number" id="port" min="1024" max="65535" value="${esc(i.port)}" aria-label="${esc(t("proxy.port"))}"><button class="button" id="savePort">${esc(t("general.save"))}</button>`)}
      ${line(t("proxy.certificate"), esc(t("proxy.certificate.below")), `<span id="certStatus" class="label">…</span><button class="button" id="certInstall">${esc(t("proxy.certificate.install"))}</button><button class="button danger" id="certRemove">${esc(t("proxy.certificate.remove"))}</button>`)}
    </section>`
    + card(`<h2>${esc(t("proxy.win"))}</h2><p>${esc(t("proxy.win.below"))}</p>
      <div class="line">${[["Claude", "https://claude.ai"], ["ChatGPT", "https://chatgpt.com"], ["Gemini", "https://gemini.google.com"], ["Perplexity", "https://www.perplexity.ai"], ["Copilot", "https://copilot.microsoft.com"]]
        .map(([n, u]) => `<button class="button" data-address="${u}">${n}</button>`).join("")}</div>`);
  const certificate = c => {
    $("#certStatus").textContent = t(c.installed ? "proxy.certificate.installed" : c.exists ? "proxy.certificate.not_installed" : "proxy.certificate.not_created");
    $("#certStatus").className = "label " + (c.installed ? "warning" : "");
    $("#certInstall").disabled = !c.exists || c.installed; $("#certRemove").disabled = !c.installed;
  };
  certificate(i.certificate);
  $("#savePort").onclick = test(() => save({port: +$("#port").value}));
  $("#certInstall").onclick = test(async () => certificate(await api("/api/certificate", {action: "install"})));
  $("#certRemove").onclick = test(async () => certificate(await api("/api/certificate", {action: "remove"})));
  $$("button[data-address]").forEach(b => b.onclick = test(async () => notify((await api("/api/browser", {address: b.dataset.address})).outcome)));
});

const connectCompatibility = test(async el => {
  const c = await api("/api/compatibility");
  const when = s => esc((s || "").slice(0, 16));
  const line = g => `<tr><td><b>${esc(g.name)}</b></td><td>${esc(tSe("via." + g.via, g.via))}</td><td>${esc(g.client || t("compatibility.unknown"))}</td>
    <td>${label(t(`compatibility.status.${g.status}`), g.status === "works" ? "ok" : "warning")}<div class="below">${g.methods.map(m => esc(t(`compatibility.method.${m}`))).join(", ")}</div></td>
    <td>${when(g.last_ok) || "–"}<div class="below">${esc(t("compatibility.counts", {ok: g.ok, restoring: g.restoring, unread: g.unread}))}</div></td></tr>`;
  const verified = v => `<tr><td><b>${esc(v.name || t("compatibility.every_service"))}</b></td><td>${esc(tSe("via." + v.via, v.via))}</td><td>${esc([v.client, v.version].filter(Boolean).join(" "))}</td>
    <td>${label(t(`compatibility.level.${v.level}`), v.level === "live" ? "ok" : "")}<div class="below">${esc(t(`compatibility.method.${v.method}`))}</div></td><td>${esc(v.data || "")}</td></tr>`;
  const head = columns => `<thead><tr>${columns.map(k => `<th scope="col">${esc(t(`compatibility.column.${k}`))}</th>`).join("")}</tr></thead>`;
  el.innerHTML = `<section class="card"><div class="inside"><div class="line"><h2>${esc(t("compatibility.sightings"))}</h2><span class="space"></span><button class="button" id="copyCompatibility">${esc(t("compatibility.copy"))}</button></div>
      <p>${esc(t("compatibility.sightings.below"))}</p></div>
      <div class="table"><table><caption class="vh">${esc(t("compatibility.sightings"))}</caption>${head(["service", "way", "program", "status", "last"])}<tbody>${
        c.sightings.map(line).join("") || `<tr><td colspan="5" class="empty">${esc(t("compatibility.empty"))}</td></tr>`}</tbody></table></div></section>
    <section class="card"><div class="inside"><h2>${esc(t("compatibility.verified_ones"))}</h2><p>${esc(t("compatibility.verified_ones.below", {data: c.updated}))}</p></div>
      <div class="table"><table><caption class="vh">${esc(t("compatibility.verified_ones"))}</caption>${head(["service", "way", "program", "level", "data"])}<tbody>${c.verified_ones.map(verified).join("")}</tbody></table></div></section>`;
  $("#copyCompatibility").onclick = () => copy(c.sightings.map(g => `${g.name} | ${g.via} | ${g.client || "?"} | ${g.status} | ok ${g.ok}, ripristini ${g.restoring}, non letti ${g.unread} | ultimo ${g.last_ok || "-"}`).join("\n") || t("compatibility.empty"));
});

// ---- Servizi AI
let servicesListing = [];
DRAW.services = (el, which) => (which === "detected" ? detectedServices : serviceRules)(el);
const serviceRules = test(async el => {
  el.innerHTML = `<div class="line"><input type="search" id="filt" placeholder="${esc(t("services.search"))}" aria-label="${esc(t("services.search"))}">
      <select id="which_ones" aria-label="${esc(t("services.which_ones"))}">${["everyone", "catalog", "radar"].map(q => `<option value="${q}">${esc(t(`services.which_ones.${q}`))}</option>`).join("")}</select>
      <span class="faded small" id="count" aria-live="polite"></span></div>
    <p class="help">${esc(t("services.radar.note"))}</p>
    <section class="card"><div class="table"><table><caption class="vh">${esc(t("services.card.rules"))}</caption><thead><tr>
      ${["service", "kind", "reading", "what_make", "contacts"].map(c => `<th scope="col">${esc(t(`services.column.${c}`))}</th>`).join("")}</tr></thead><tbody id="tabServices"></tbody></table></div></section>`;
  servicesListing = await api("/api/services");
  const draw = () => {
    const f = $("#filt").value.toLowerCase(), which_ones = $("#which_ones").value;
    const visible = servicesListing.filter(s => which_ones === "everyone" || (which_ones === "radar") === !!s.radar).filter(s => `${s.name} ${s.vendor} ${tSe("services.kind." + s.kind, s.kind)} ${s.domains.join(" ")}`.toLowerCase().includes(f));
    $("#count").textContent = t("services.count", {visible: visible.length, everyone: servicesListing.length, guarded: servicesListing.filter(s => s.policy === "protect" && s.readable).length, blocked_items: servicesListing.filter(s => s.policy === "block").length});
    $("#tabServices").innerHTML = visible.map(s => {
      const options = ["protect", "record", "block", "ignore"].filter(p => p !== "protect" || s.readable)
        .map(p => `<option value="${p}"${p === s.policy ? " selected" : ""}>${esc(t(`services.policy.${p}`))}</option>`).join("");
      return `<tr><td><b>${esc(s.name)}</b><div class="below">${esc(s.vendor)} · ${esc(s.domains.join(", "))}</div></td><td>${esc(tSe("services.kind." + s.kind, s.kind))}</td>
        <td>${label(t(`services.reading.${s.reading}`), s.reading === "tested" ? "ok" : s.readable ? "warning" : "")}</td>
        <td><select data-id="${esc(s.id)}" aria-label="${esc(t("services.what_make_for", {name: s.name}))}"${s.locked ? ` disabled title="${esc(t("managed.locked"))}"` : ""}>${options}</select></td>
        <td>${s.contacts || ""}<div class="below">${esc((s.last || "").slice(0, 16))}</div></td></tr>`;
    }).join("");
    $$("#tabServices select").forEach(x => x.onchange = test(async () => { await api("/api/services", {id: x.dataset.id, policy: x.value}); servicesListing = await api("/api/services"); draw(); readStatus(); }));
  };
  $("#filt").oninput = draw;
  $("#which_ones").onchange = draw;
  draw();
});
const choice = p => p ? label(t(`detected.choice.${p}`), p === "block" ? "error" : p === "protect" ? "" : "warning") : "";
const CATEGORIES = ["programs", "browser_extensions", "editor_extensions", "commands", "local_models", "listening", "processes", "contacted"];
const day = s => s ? `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}` : "";
// L'inventario si tiene nel tempo: ogni analisi viene salvata e confrontata con la precedente (novità, da quando una cosa c'è,
// giudizio di chi gestisce il PC). La parte «In rete adesso» resta una fotografia del momento.
const detectedServices = test(async el => {
  el.innerHTML = `<div class="note"><span>${t("detected.note")}</span></div>`
    + `<section class="card"><div class="inside">
        <div class="line"><div><h2>${esc(t("inventory.title"))}</h2><div class="faded small" id="invWhen" aria-live="polite"></div></div><span class="space"></span>
          <label class="line small" for="invEvery">${esc(t("inventory.repeat"))}<select id="invEvery">${["weekly", "daily", "never"].map(v => `<option value="${v}">${esc(t(`inventory.repeat.${v}`))}</option>`).join("")}</select></label>
          <button class="button primary" id="analyze">${esc(t("inventory.analyze"))}</button></div>
        <div id="invNews" class="block"></div>
        <div class="line"><input type="search" id="invSearch" class="space" placeholder="${esc(t("inventory.search"))}" aria-label="${esc(t("inventory.search"))}">
          <select id="invWhich" aria-label="${esc(t("inventory.which_ones"))}">${["present", "everyone", "gone", "to_review", "to_remove"].map(v => `<option value="${v}">${esc(t(`inventory.which_ones.${v}`))}</option>`).join("")}</select>
          <button class="button" id="invExport">${esc(t("inventory.export"))}</button><button class="button" id="invForget">${esc(t("inventory.forget"))}</button></div>
      </div>
      <div class="table"><table><caption class="vh">${esc(t("inventory.title"))}</caption><thead><tr>
        ${["name", "category", "seen", "rule", "verdict"].map(c => `<th scope="col">${esc(t(`inventory.column.${c}`))}</th>`).join("")}</tr></thead><tbody id="invTable"></tbody></table></div></section>`
    + card(`<div class="line"><h2>${esc(t("detected.network"))}</h2><span class="space"></span><span class="faded small" id="networkWhen"></span><button class="button" id="analyzeNetwork">${esc(t("detected.refresh"))}</button></div>
      <div id="network" class="block faded" aria-live="polite">${esc(t("detected.network.below"))}</div>`);
  const name = (a, b) => `<b>${esc(a)}</b><div class="below">${esc(b)}</div>`;
  let inv = await api("/api/inventory");
  const draw = () => {
    const latest = inv.scan[0];
    $("#invEvery").value = inv.every || "weekly";
    $("#invWhen").textContent = !latest ? t("inventory.never_done")
      : t("inventory.latest", {when: `${day(latest.stamp)} ${latest.stamp.slice(11, 16)}`, origin: t(`inventory.origin.${latest.origin === "automatic" ? "automatic" : "manual"}`), n: inv.scan_count})
        + (inv.upcoming ? " " + t("inventory.upcoming", {when: `${day(inv.upcoming)} ${inv.upcoming.slice(11, 16)}`}) : "");
    const recent = inv.events.slice(0, 12);
    $("#invNews").innerHTML = recent.length ? `<h3>${esc(t("inventory.news"))}</h3><ul class="listing events">${recent.map(e =>
      `<li>${label(t(`inventory.event.${e.kind}`), e.kind === "appeared" ? "warning" : "")} <b>${esc(e.name)}</b> <span class="faded">${esc(t(`inventory.category.${e.category}`))} · ${esc(day(e.stamp))}</span></li>`).join("")}</ul>` : "";
    const f = $("#invSearch").value.toLowerCase(), which_ones = $("#invWhich").value;
    const visible = inv.items.filter(e => which_ones === "everyone" || (which_ones === "present" && e.present) || (which_ones === "gone" && !e.present)
        || (which_ones === "to_review" && e.present && !e.verdict) || (which_ones === "to_remove" && e.verdict === "to_remove"))
      .filter(e => `${e.name} ${e.detail} ${e.note} ${t(`inventory.category.${e.category}`)}`.toLowerCase().includes(f))
      .sort((a, b) => CATEGORIES.indexOf(a.category) - CATEGORIES.indexOf(b.category));
    $("#invTable").innerHTML = visible.length ? visible.map(e => `<tr>
        <td>${name(e.name, [e.detail, e.version].filter(Boolean).join(" · "))}</td>
        <td>${esc(t(`inventory.category.${e.category}`))}</td>
        <td>${e.present ? "" : label(t("inventory.not_more"), "warning")}<div class="below">${esc(t("inventory.since", {first: day(e.first), last: day(e.last)}))}</div></td>
        <td><span class="labels">${choice(e.policy)}${e.signal === "all_sites" ? label(t("detected.all_sites"), "error") : ""}</span></td>
        <td><select data-key="${esc(e.key)}" aria-label="${esc(t("inventory.verdict_for", {name: e.name}))}">${["", "approved", "to_remove"].map(g => `<option value="${g}"${g === (e.verdict || "") ? " selected" : ""}>${esc(t(`inventory.verdict.${g || "to_review"}`))}</option>`).join("")}</select>
          <input type="text" class="note-short" data-note="${esc(e.key)}" value="${esc(e.note || "")}" maxlength="300" placeholder="${esc(t("inventory.note"))}" aria-label="${esc(t("inventory.note_for", {name: e.name}))}"></td></tr>`).join("")
      : `<tr><td colspan="5" class="empty">${esc((inv.items.length ? t("inventory.none_filter") : t("inventory.empty")))}</td></tr>`;
    $$("#invTable select").forEach(x => x.onchange = test(async () => {
      await api("/api/inventory/verdict", {key: x.dataset.key, verdict: x.value});
      inv.items.find(e => e.key === x.dataset.key).verdict = x.value;
    }));
    $$("#invTable input").forEach(x => x.onchange = test(async () => {
      await api("/api/inventory/verdict", {key: x.dataset.note, note: x.value});
      inv.items.find(e => e.key === x.dataset.note).note = x.value;
    }));
  };
  $("#invSearch").oninput = draw;
  $("#invWhich").onchange = draw;
  $("#invEvery").onchange = test(async e => { await save({scan: e.target.value}); inv = await api("/api/inventory"); draw(); });
  $("#analyze").onclick = test(async e => {
    e.target.disabled = true;
    $("#invWhen").textContent = t("detected.pending");
    try {
      inv = await api("/api/inventory/scan", {});
      const n = inv.news;
      notify(n.before ? t("inventory.before_done", {n: inv.items.length}) : n.new_items.length || n.gone.length ? t("inventory.changed", {new_items: n.new_items.length, gone: n.gone.length}) : t("inventory.unchanged"));
    } finally { e.target.disabled = false; draw(); }
  });
  $("#invExport").onclick = test(async () => {
    const r = await fetch("/api/inventory/csv", {headers: {"X-Panel": CODE}});
    if (!r.ok) throw new Error(String(r.status));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await r.blob()); a.download = `omissis-inventario-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.append(a); a.click(); a.remove();
  });
  $("#invForget").onclick = test(async () => {
    const n = inv.items.filter(e => !e.present).length;
    if (!n) { notify(t("inventory.forget.nothing")); return; }
    if (!await confirm(t("inventory.forget.title"), t("inventory.forget.text", {n}), t("inventory.forget"))) return;
    inv = await api("/api/inventory/forget", {}); draw();
  });
  $("#analyzeNetwork").onclick = test(async () => {
    $("#network").textContent = t("detected.pending");
    const r = await api("/api/shadow/network");
    $("#networkWhen").textContent = r.when.slice(11, 16);
    $("#network").className = "block";
    $("#network").innerHTML = (table(t("detected.contacted"), r.proxy, [x => `<b>${esc(x.service)}</b>`, x => `<span class="labels">${Object.entries(x.outcomes).map(([e, n]) => label(`${tSe("detected.outcome." + e, e)} ${n}`, e === "guarded" ? "ok" : e === "blocked" ? "error" : "warning")).join("")}</span>`, x => `<span class="below">${esc(x.last.slice(0, 16))}</span>`])
      + table(t("detected.linked"), r.connected_programs, [x => name(x.service.name, x.process), x => esc(t("detected.n_links", {n: x.links})), x => choice(x.service.policy) || label(t("detected.locale"))])
      + table(t("detected.links"), r.links, [x => name(x.service, x.host), x => esc(x.process), x => esc(t("detected.n_links", {n: x.links})), x => choice(x.policy)])
      + table(t("detected.dns"), r.dns, [x => name(x.service, x.host), x => esc(x.what), x => choice(x.policy)])
      || `<span class="faded">${esc(t("detected.network.nothing"))}</span>`) + (r.dns_cache_empty ? `<p class="help">${esc(t("detected.dns_empty"))}</p>` : "");
  });
  draw();
});

// ---- Attività
DRAW.activity = el => {
  el.innerHTML = `<section class="card"><div class="table"><table><caption class="vh">${esc(t("activity.title"))}</caption><thead><tr>
    ${["stamp", "service", "outcome", "details"].map(c => `<th scope="col">${esc(t(`activity.column.${c}`))}</th>`).join("")}</tr></thead><tbody id="log"></tbody></table></div></section>`;
  log();
};
REFRESH.activity = () => log();
const log = test(async () => {
  const lines = await api("/api/activity?n=300"), body = $("#log");
  if (!body) return;
  body.innerHTML = lines.length ? lines.map(v => {
    const ev = v.event || "", tone = ev === "masked" ? "ok" : /blocked/.test(ev) ? "error" : /not_|no_text|without/.test(ev) ? "warning" : "";
    let d = Object.entries(v.replacements || {}).map(([k, n]) => label(`${dataKind(k)} ${n}`)).join("");
    if (v.restored) d += label(t("activity.restored", {n: v.restored}));
    if (v.CLEAR_VALUES) d += label(t("activity.reveal", {n: v.CLEAR_VALUES}), "error");
    if (v.ms !== undefined) d += label(`${v.ms} ms`);
    const structure = v.structure ? `<details><summary>${esc(t("activity.structure"))}</summary><code>${esc(JSON.stringify(v.structure))}</code></details>` : "";
    return `<tr><td class="below">${esc((v.stamp || "").slice(5, 16))}</td><td>${esc(tSe("service." + (v.service || ""), v.service || ""))}</td>
      <td>${label(tSe("event." + ev, ev), tone)}<div class="below">${esc(v.path || "")}${v.via ? " · " + esc(tSe("via." + v.via, v.via)) : ""}</div></td>
      <td><span class="labels">${d}</span>${structure}</td></tr>`;
  }).join("") : `<tr><td colspan="4" class="empty">${esc(t("activity.empty"))}</td></tr>`;
});

// ---- Archivio
// Si cerca per segnaposto o per valore vero (la ricerca guarda i valori anche quando restano nascosti), si elimina una voce,
// un gruppo scelto o ciò che non si usa da tempo. I numeri eliminati non vengono riusati.
DRAW.vault = el => {
  const options = (entries, choice) => entries.map(([v, n]) => `<option value="${esc(v)}"${String(v) === String(choice) ? " selected" : ""}>${esc(n)}</option>`).join("");
  el.innerHTML = `<section class="card">
      <div class="inside">
        <div class="line"><input type="search" id="archSearch" class="space" placeholder="${esc(t("vault.search"))}" aria-label="${esc(t("vault.search"))}">
          <select id="archKind" aria-label="${esc(t("vault.kind"))}"></select>
          <select id="archOrder" aria-label="${esc(t("vault.order"))}">${options(["recent", "used", "idle", "kind"].map(v => [v, t(`vault.order.${v}`)]), "recent")}</select>
          <label class="line">${toggle("showClear", t("vault.show"))}<span>${esc(t("vault.show"))}</span></label></div>
        <div class="line"><span class="faded small" id="archCount" aria-live="polite"></span><span class="space"></span>
          <button class="button danger" id="archRemove" disabled>${esc(t("vault.remove_choices"))}</button></div>
      </div>
      <div class="table"><table><caption class="vh">${esc(t("vault.title"))}</caption><thead><tr>
        <th scope="col"><input type="checkbox" id="archAll" aria-label="${esc(t("vault.choose_all"))}"></th>
        ${["placeholder", "value", "created", "used"].map(c => `<th scope="col">${esc(t(`vault.column.${c}`))}</th>`).join("")}</tr></thead><tbody id="tabVault"></tbody></table></div>
    </section>
    <section class="card" aria-labelledby="pulTitle">
      <div class="inside"><h2 id="pulTitle">${esc(t("vault.cleanup"))}</h2><p>${esc(t("vault.cleanup.below"))}</p></div>
      ${line(t("vault.cleanup.idle"), esc(t("vault.cleanup.idle.below")), `<select id="pulDays" aria-label="${esc(t("vault.cleanup.days"))}">${options([30, 90, 180, 365].map(g => [g, t("vault.days", {n: g})]), 90)}</select><button class="button" id="pulIdle">${esc(t("vault.cleanup.remove"))}</button>`)}
      ${line(t("vault.cleanup.by_itself"), esc(t("vault.cleanup.by_itself.below")), `<select id="pulByItself" aria-label="${esc(t("vault.cleanup.by_itself"))}">${options([[0, t("vault.cleanup.never")], ...[90, 180, 365].map(g => [g, t("vault.cleanup.after", {n: g})])], 0)}</select>`)}
      ${line(t("vault.clear.short_title"), esc(t("vault.clear.text")), `<button class="button danger" id="clear">${esc(t("vault.clear"))}</button>`)}
    </section>`;
  let timeout;
  const choices = () => $$("#tabVault input:checked").map(x => x.value);
  const refreshChoices = () => { const n = choices().length; $("#archRemove").disabled = !n; $("#archRemove").textContent = n ? t("vault.remove_n", {n}) : t("vault.remove_choices"); };
  const read = test(async () => {
    const a = await api("/api/vault", {reveal: $("#showClear").checked, search: $("#archSearch").value, label: $("#archKind").value, order: $("#archOrder").value});
    const kind = $("#archKind").value;
    $("#archKind").innerHTML = options([["", t("vault.kind.everyone", {n: num(a.total)})], ...Object.entries(a.by_label).sort((x, y) => y[1] - x[1]).map(([k, n]) => [k, `${dataKind(k)} (${num(n)})`])], kind);
    $("#archCount").innerHTML = (a.total ? esc(t("vault.count", {shown: num(a.entries.length), matches: num(a.matches), total: num(a.total)})) : esc(t("vault.empty")))
      + (a.encrypted ? " " + label(t("vault.encrypted"), "ok") : "");
    $("#tabVault").innerHTML = a.entries.length ? a.entries.map(v => `<tr><td><input type="checkbox" value="${esc(v.placeholder)}" aria-label="${esc(t("vault.choose", {placeholder: v.placeholder}))}"></td>
        <td><span class="placeholder">${esc(v.placeholder)}</span></td><td>${esc(v.value)}</td><td class="below">${esc(v.created)}</td><td class="below">${esc(v.used)}</td></tr>`).join("")
      : `<tr><td colspan="5" class="empty">${esc((a.total ? t("vault.no_found") : t("vault.empty")))}</td></tr>`;
    $("#archAll").checked = false;
    $$("#tabVault input").forEach(x => x.onchange = refreshChoices);
    refreshChoices();
  });
  $("#archSearch").oninput = () => { clearTimeout(timeout); timeout = setTimeout(read, 250); };
  for (const id of ["archKind", "archOrder", "showClear"]) $(`#${id}`).onchange = read;
  $("#archAll").onchange = e => { $$("#tabVault input").forEach(x => { x.checked = e.target.checked; }); refreshChoices(); };
  const remove = async (data, title) => {
    const how_many = (await api("/api/vault/delete", {...data, count_only: true})).removed;
    if (!how_many) { notify(t("vault.remove.nothing")); return; }
    if (!await confirm(title, t("vault.remove.text", {n: num(how_many)}), t("vault.remove.yes", {n: num(how_many)}))) return;
    const r = await api("/api/vault/delete", data);
    notify(t("vault.removed", {n: num(r.removed)}));
    read(); readStatus();
  };
  $("#archRemove").onclick = test(() => remove({placeholder: choices()}, t("vault.remove.title")));
  $("#pulIdle").onclick = test(() => remove({idle_days: +$("#pulDays").value, label: $("#archKind").value}, t("vault.cleanup.title", {n: $("#pulDays").value})));
  api("/api/settings").then(i => { $("#pulByItself").value = String(i.vault_days || 0); }).catch(() => {});
  $("#pulByItself").onchange = test(e => save({vault_days: +e.target.value}));
  $("#clear").onclick = test(async () => {
    if (!await confirm(t("vault.clear.title"), t("vault.clear.text"), t("vault.clear"))) return;
    await api("/api/vault/clear", {}); read(); readStatus();
  });
  read();
};

// ------------------------------------------------------------------ 4. configurazione guidata

// Al primo avvio, e quando la si richiama dalla Guida: pochi passi, ognuno saltabile. Non decide nulla che non si possa
// cambiare dopo dalle pagine normali; alla chiusura il programma si ricorda che e' stata vista.
const session = (key, value) => { try { if (value === undefined) return sessionStorage.getItem(key); sessionStorage.setItem(key, value); } catch { /* memoria del browser non disponibile */ } return null; };
const connectThis = test(async () => { const d = await extensionData(); window.postMessage({omissis: "connect", token: d.token, port: d.port}, location.origin); });

function welcome(from = 0) {
  const d = $("#welcome");
  if (d.open) return;
  // se la pagina viene ricaricata a meta' (serve dopo aver installato l'estensione) si riprende dal passo in cui si era
  const st = {step: from || Number(session("welcome_step")) || 1, where: {browser: true, app: false, terminal: false}, tried: false};
  try { if (!from) Object.assign(st.where, JSON.parse(session("welcome_where") || "{}")); } catch { /* si riparte dalle scelte di serie */ }
  const steps = () => [1, 2, ...(st.where.browser ? [3] : []), 4];
  const finish = async to => {
    guide = null;
    session("welcome_step", ""); session("welcome_where", "");
    if (d.open) d.close();
    await api("/api/settings", {onboarded: true}).catch(() => {});
    if (to) { if (view !== "advanced") changeView(true); location.hash = to; }
    else if (location.hash === "#/welcome") location.hash = "#/start";
  };
  // dopo un cambio di passo il fuoco va al pulsante per proseguire: chi usa la tastiera continua con Invio
  const move = by => { const all = steps(), i = Math.max(0, all.indexOf(st.step)); st.step = all[Math.max(0, Math.min(all.length - 1, i + by))]; session("welcome_step", String(st.step)); draw(); $("#welcomeNext").focus(); };
  const body = {
    1: () => `<textarea id="welcomeText" aria-label="${esc(t("welcome.1.field"))}">${esc(t("welcome.1.example"))}</textarea>
      <div class="line"><button class="button primary" id="welcomeTry">${esc(t("welcome.1.try"))}</button><button class="button" id="welcomeStart" hidden>${esc(t("start.launch"))}</button><span class="faded small" id="welcomeState" role="status"></span></div>
      <div class="outcome" id="welcomeResult" aria-live="polite" hidden></div><p class="help" id="welcomeFound" hidden></p>`,
    2: () => ["browser", "app", "terminal"].map(k => `<label class="pick"><input type="checkbox" data-where="${k}" ${st.where[k] ? "checked" : ""}><span><b>${esc(t(`welcome.where.${k}`))}</b><span class="help">${esc(t(`welcome.where.${k}.below`))}</span></span></label>`).join(""),
    3: () => `<div class="line"><span class="label" id="welcomeExt">…</span><span class="space"></span><button class="button primary" id="welcomeConnect" hidden>${esc(t("browser.connect"))}</button></div>
      <div id="welcomeInstall" hidden><div id="welcomeStoreBox" hidden><p class="help">${esc(t("welcome.3.store"))}</p>
        <div class="line"><a class="button primary" id="welcomeStore" target="_blank" rel="noopener">${esc(t("browser.store"))}</a></div><p class="help">${esc(t("welcome.3.reload"))}</p></div>
      <div id="welcomeManual"><p class="help">${esc(t("welcome.3.absent"))}</p><ol class="listing"><li>${t("browser.installation.1")}</li><li>${t("browser.installation.2")}<div class="line"><code id="welcomeFolder">…</code></div></li><li>${esc(t("welcome.3.reload"))}</li></ol></div></div>`,
    4: () => `<ul class="listing"><li>${esc(t("welcome.4.default"))}</li><li>${esc(t("welcome.4.icon"))}</li>${st.where.app || st.where.terminal ? `<li>${esc(t("welcome.4.more"))}</li>` : ""}</ul>`,
  };
  const refresh = () => {
    if (st.step === 1 && $("#welcomeTry")) {
      const phase = !S ? "startup" : PHASES.includes(S.phase) ? S.phase : "stop", sc = S && S.downloading;
      $("#welcomeTry").disabled = phase !== "active";
      $("#welcomeStart").hidden = !["stop", "error"].includes(phase);
      $("#welcomeState").textContent = phase === "active" ? ""
        : phase === "model" && sc && sc.total ? t("status.model.progress", {completed: megabyte(sc.completed), total: megabyte(sc.total), pc: Math.min(100, Math.floor(100 * sc.completed / sc.total))})
        : phase === "error" ? S.error : t(`status.${phase}`);
    }
    if (st.step === 3 && $("#welcomeExt")) {
      const status = !extension ? "absent" : !extension.connected ? "to_connect" : extension.ok ? "connected" : "no_response";
      const e = $("#welcomeExt");
      e.dataset.status = status;
      e.className = "label " + (status === "connected" ? "ok" : status === "absent" ? "" : "warning");
      e.textContent = t(`browser.status.${status}`);
      $("#welcomeConnect").hidden = !extension || status === "connected";
      $("#welcomeInstall").hidden = !!extension;
    }
  };
  const draw = () => {
    const all = steps(), i = Math.max(0, all.indexOf(st.step)), last = i === all.length - 1;
    st.step = all[i];
    d.dataset.step = st.step;
    d.innerHTML = `<div class="inside">
        <div class="line"><span class="faded small" id="welcomeCount">${esc(t("welcome.step", {n: i + 1, total: all.length}))}</span><span class="space"></span><button class="button" id="welcomeSkip">${esc(t("welcome.skip"))}</button></div>
        <h2 id="welcomeTitle">${esc(t(`welcome.${st.step}.title`))}</h2><p class="faded">${esc(t(`welcome.${st.step}.below`))}</p>${body[st.step]()}</div>
      <div class="footer">${i ? `<button class="button" id="welcomeBack">${esc(t("welcome.back"))}</button>` : ""}${
        last && (st.where.app || st.where.terminal) ? `<button class="button" id="welcomeMore">${esc(t("welcome.4.open_connections"))}</button>` : ""}
        <button class="button${st.step !== 1 || st.tried ? " primary" : ""}" id="welcomeNext">${esc(t(last ? "welcome.finish" : "welcome.next"))}</button></div>`;
    $("#welcomeSkip").onclick = () => finish();
    if ($("#welcomeBack")) $("#welcomeBack").onclick = () => move(-1);
    if ($("#welcomeMore")) $("#welcomeMore").onclick = () => finish(`#/connections/${st.where.app ? "app" : "terminal"}`);
    $("#welcomeNext").onclick = () => last ? finish() : move(1);
    if (st.step === 1) {
      $("#welcomeStart").onclick = test(async () => { await api("/api/protection", {action: "launch"}); readStatus(); });
      $("#welcomeTry").onclick = test(async () => {
        const r = await api("/api/try", {text: $("#welcomeText").value, demo: true});
        const out = $("#welcomeResult"), found = $("#welcomeFound"), n = Object.values(r.counts || {}).reduce((a, b) => a + b, 0);
        out.innerHTML = esc(r.texts[0]).replace(new RegExp(RX_PLACEHOLDER, "g"), s => `<span class="placeholder">${s}</span>`);
        found.textContent = n ? t("welcome.1.found", {n: num(n)}) : t("welcome.1.nothing");
        out.hidden = found.hidden = false;
        st.tried = true;
        $("#welcomeNext").className = "button primary";
      });
    }
    if (st.step === 2) $$("#welcome input[data-where]").forEach(c => { c.onchange = () => { st.where[c.dataset.where] = c.checked; session("welcome_where", JSON.stringify(st.where)); }; });
    if (st.step === 3) {
      $("#welcomeConnect").onclick = connectThis;
      api("/api/extension").then(x => {
        if (!$("#welcomeFolder")) return;
        $("#welcomeFolder").textContent = x.folder;
        // estensione gia' pubblicata: basta un clic nello store, e le istruzioni a mano non servono
        if (storeLink(x)) { $("#welcomeStore").href = storeLink(x); $("#welcomeStoreBox").hidden = false; $("#welcomeManual").hidden = true; }
      }).catch(() => {});
      window.postMessage({omissis: "ping"}, location.origin);
    }
    refresh();
  };
  guide = {refresh};
  d.oncancel = e => { e.preventDefault(); finish(); };
  draw();
  d.showModal();
  d.focus();   // all'apertura il fuoco sta sulla finestra, non su un pulsante a caso: il primo Tab porta dentro
}

// ------------------------------------------------------------------ 5. avvio

function applyTheme(theme) {
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme; else delete document.documentElement.dataset.theme;
  try { localStorage.setItem("theme", theme); } catch { /* memoria del browser non disponibile: pazienza */ }
}
function changeView(advanced) {
  view = advanced ? "advanced" : "simple";
  applyView();
  api("/api/settings", {view}).catch(() => {});
  show(false);
}

// l'estensione, se c'è in questo browser, si presenta con un messaggio alla pagina
window.addEventListener("message", e => {
  const d = e.data;
  if (e.source !== window || e.origin !== location.origin || !d || d.omissis !== "extension") return;
  extension = d;
  drawExtension(); channels();
  // aperta dalla pagina di benvenuto dell'estensione: il collegamento parte da solo, una volta
  if (wantConnect && !d.just) { wantConnect = false; if (!(d.connected && d.ok)) connectThis(); }
  guide?.refresh();
  if (d.just) notify(t(d.ok ? "browser.connected_now" : "browser.connected_no_response"), !d.ok);
});

async function launch() {
  try { applyTheme(localStorage.getItem("theme") || "auto"); } catch { /* vedi sopra */ }
  const languages = await api("/api/languages");
  LANGUAGE = languages.active;
  document.documentElement.lang = LANGUAGE;
  const read = async code => (await fetch(`/locales/${code}.json`)).json();
  [TEXTS, FALLBACK] = await Promise.all([read(LANGUAGE), LANGUAGE === "it" ? Promise.resolve({}) : read("it")]);
  const i = await api("/api/settings");
  await readKeystrokes();
  view = i.view === "advanced" ? "advanced" : "simple";
  lock(i, [["#advanced", "view"]]);
  applyTheme(i.theme || "auto");
  drawMenu(); applyView();
  $("#advanced").onchange = e => changeView(e.target.checked);
  addEventListener("hashchange", () => show());
  wantConnect = location.hash === "#/connect";
  const again = location.hash === "#/welcome";
  if (wantConnect) history.replaceState(null, "", "#/start");
  show(false);
  if (i.first_run || again) welcome(again ? 1 : 0);
  window.postMessage({omissis: "ping"}, location.origin);
  await readStatus();
  setInterval(() => { readStatus(); if (opened.id === "start") channels(); appListingQuiet(); }, 3000);
}
launch().catch(e => { $("#content").textContent = "Omissis: " + e.message; });
