// Pannello di Omissis. Nessuna libreria: un file solo, diviso in parti.
//   1. strumenti (lingue, chiamate al programma, avvisi)      3. le viste, una funzione per ciascuna
//   2. guscio (menu, percorsi, stato della protezione)        4. avvio
// Ogni testo visibile passa da t(chiave): le frasi stanno in locales/<codice>.json, mai qui dentro.

const CODICE = document.querySelector('meta[name="omissis-codice"]').content;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

// ------------------------------------------------------------------ 1. strumenti

let TESTI = {}, RISERVA = {}, LINGUA = "it";
/** La frase per una chiave, con i valori tra graffe sostituiti. Se manca nella lingua scelta vale l'italiano. */
function t(chiave, valori) {
  const s = TESTI[chiave] ?? RISERVA[chiave] ?? chiave;
  return valori ? s.replace(/\{(\w+)\}/g, (m, k) => (k in valori ? valori[k] : m)) : s;
}
/** Come t, ma senza segnalare la chiave se non c'è: restituisce il testo di riserva. Per le voci che arrivano dal programma. */
const tSe = (chiave, riserva) => TESTI[chiave] ?? RISERVA[chiave] ?? riserva;
const num = n => new Intl.NumberFormat(LINGUA).format(n);
const megabyte = n => num(Math.round(n / 1e6));
const tipoDato = k => tSe("tipo." + k, k);

async function api(percorso, dati) {
  const r = await fetch(percorso, {method: dati === undefined ? "GET" : "POST", headers: {"X-Pannello": CODICE, "Content-Type": "application/json"},
    body: dati === undefined ? undefined : JSON.stringify(dati)});
  if (r.status === 403) {   // il programma è ripartito (per esempio dopo un aggiornamento) con un codice nuovo
    const ora = Date.now(), ultima = +sessionStorage.getItem("ricarica") || 0;
    if (ora - ultima > 10000) { sessionStorage.setItem("ricarica", ora); location.reload(); }
  }
  const j = await r.json();
  if (!r.ok) throw new Error(j.errore || r.status);
  return j;
}

function avvisa(testo, errore = false) {
  $$("#avvisi .avviso").filter(x => x.textContent === testo).forEach(x => x.remove());   // lo stesso avviso non si impila: riparte
  const a = document.createElement("div");
  a.className = "avviso" + (errore ? " errore" : "");
  if (errore) a.setAttribute("role", "alert");
  a.textContent = testo;
  $("#avvisi").append(a);
  setTimeout(() => a.remove(), errore ? 9000 : 5000);
}
/** Avvolge un'azione: se fallisce, l'errore compare come avviso invece di sparire nella console. */
const prova = f => async (...a) => { try { return await f(...a); } catch (e) { avvisa(e.message, true); } };

async function copia(testo, messaggio) {
  try { await navigator.clipboard.writeText(testo); }
  catch { const a = document.createElement("textarea"); a.value = testo; document.body.append(a); a.select(); document.execCommand("copy"); a.remove(); }
  avvisa(messaggio || t("generale.copiato"));
}

function conferma(titolo, testo, si) {
  const d = $("#conferma");
  $("#confermaTitolo").textContent = titolo; $("#confermaTesto").textContent = testo;
  $("#confermaSi").textContent = si; $("#confermaNo").textContent = t("generale.annulla");
  return new Promise(fatto => { d.onclose = () => fatto(d.returnValue === "si"); d.returnValue = "no"; d.showModal(); $("#confermaNo").focus(); });
}

const ICONE = {
  inizio: '<path d="M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
  testo: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  documenti: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  collegamenti: '<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/>',
  servizi: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  attivita: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  archivio: '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6M4 11.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  impostazioni: '<path d="M4 6h8M18 6h2M4 12h2M12 12h8M4 18h7M17 18h3"/><circle cx="15" cy="6" r="2.5"/><circle cx="9" cy="12" r="2.5"/><circle cx="14" cy="18" r="2.5"/>',
  guida: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.1 1-1.1 1.8M12 17h.01"/>',
  browser: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18"/>',
  app: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>',
  terminale: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 10 3 2.5L7 15M13 15h4"/>',
  proxy: '<path d="M4 8h14l-3-3M20 16H6l3 3"/>',
};
const icona = n => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONE[n]}</svg>`;

const etichetta = (testo, tipo = "") => `<span class="etichetta ${tipo}">${esc(testo)}</span>`;
const scheda = (dentro, piede = "", classi = "") => `<section class="scheda ${classi}"><div class="dentro">${dentro}</div>${piede ? `<div class="piede">${piede}</div>` : ""}</section>`;
const testa = id => `<header class="testa"><h1>${esc(t(`${id}.titolo`))}</h1><p>${t(`${id}.sotto`)}</p></header>`;
const conteggi = c => Object.entries(c || {}).filter(([, n]) => n).map(([k, n]) => etichetta(`${tipoDato(k)} ${n}`, "ok")).join("");
/** Larghezze e altezze dei grafici: scritte dal codice e non nell'HTML, così la pagina non ha bisogno di stili "in linea". */
function misure(radice) {
  $$("[data-l]", radice).forEach(e => { e.style.width = e.dataset.l + "%"; });
  $$("[data-a]", radice).forEach(e => { e.style.height = e.dataset.a + "%"; });
}
function barre(el, righe, nome = x => x) {
  const m = Math.max(1, ...righe.map(r => r[1]));
  el.innerHTML = righe.length ? righe.map(r => `<div><span>${esc(nome(r[0]))}</span><i data-l="${Math.round(100 * r[1] / m)}"></i><span>${num(r[1])}</span></div>`).join("")
    : `<span class="sfumato">${esc(t("generale.nessun_dato"))}</span>`;
  misure(el);
}
function tabella(titolo, righe, colonne) {
  if (!righe || !righe.length) return "";
  return `<h3>${esc(titolo)} <span class="sfumato">(${righe.length})</span></h3><div class="tabella"><table><tbody>${
    righe.map(r => "<tr>" + colonne.map(c => `<td>${c(r)}</td>`).join("") + "</tr>").join("")}</tbody></table></div>`;
}
const riga = (nome, aiuto, comando) => `<div class="impostazione"><span class="nome">${esc(nome)}</span>${aiuto ? `<span class="aiuto">${aiuto}</span>` : ""}<span class="comando">${comando}</span></div>`;
const levetta = (id, nome) => `<span class="levetta"><input type="checkbox" role="switch" id="${id}" aria-label="${esc(nome)}"><span></span></span>`;

// ------------------------------------------------------------------ 2. guscio

const VISTE = [
  {id: "inizio"}, {id: "testo"}, {id: "documenti"}, {id: "guida"},
  {id: "impostazioni", schede: ["generali", "riconoscimento"], schedeAvanzate: ["riconoscimento"]},
  {id: "collegamenti", avanzata: true, schede: ["browser", "app", "terminale", "proxy", "compatibilita"]},
  {id: "servizi", avanzata: true, schede: ["regole", "rilevati"]},
  {id: "attivita", avanzata: true}, {id: "archivio", avanzata: true},
];
const DISEGNA = {}, AGGIORNA = {};
let S = null;              // l'ultimo stato letto dal programma
let vista = "semplice";    // semplice | avanzata
let aperta = {id: "", scheda: ""};
let estensione = null;     // ciò che dice di sé l'estensione, se questo browser ce l'ha

function disegnaMenu() {
  const voce = v => `<a href="#/${v.id}" data-vista="${v.id}">${icona(v.id)}<span>${esc(t(`menu.${v.id}`))}</span></a>`;
  $("#menu").setAttribute("aria-label", t("menu.nome"));
  $("#menu").innerHTML = VISTE.filter(v => !v.avanzata).map(voce).join("")
    + `<div class="gruppo solo-avanzata">${esc(t("menu.gruppo_tecnico"))}</div>`
    + VISTE.filter(v => v.avanzata).map(v => voce(v).replace("<a ", '<a class="solo-avanzata" ')).join("");
  $("#salta").textContent = t("generale.salta");
  $("#avanzataTesto").textContent = t("menu.avanzata");
}

function percorso() {
  const [, id = "inizio", scheda = ""] = location.hash.split("/");
  const v = VISTE.find(x => x.id === id) || VISTE[0];
  const ammesse = (v.schede || []).filter(s => vista === "avanzata" || !(v.schedeAvanzate || []).includes(s));
  return {v, scheda: ammesse.includes(scheda) ? scheda : (ammesse[0] || ""), ammesse};
}

function mostra(sposta = true) {
  const {v, scheda, ammesse} = percorso();
  if (v.avanzata && vista !== "avanzata") { location.hash = "#/inizio"; return; }
  aperta = {id: v.id, scheda};
  $$("#menu a").forEach(a => a.dataset.vista === v.id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  document.title = `${t(`menu.${v.id}`)} · Omissis`;
  const el = $("#contenuto");
  el.innerHTML = testa(v.id) + (ammesse.length > 1 ? `<div class="schede-menu" role="tablist" aria-label="${esc(t(`menu.${v.id}`))}">${
    ammesse.map(s => `<button role="tab" id="linguetta-${s}" data-scheda="${s}" aria-selected="${s === scheda}" aria-controls="pannello" tabindex="${s === scheda ? 0 : -1}">${esc(t(`${v.id}.scheda.${s}`))}</button>`).join("")}</div>` : "")
    + `<div class="blocco" id="pannello" ${ammesse.length > 1 ? `role="tabpanel" aria-labelledby="linguetta-${scheda}"` : ""}></div>`;
  $$(".schede-menu button", el).forEach(b => {
    b.onclick = () => { location.hash = `#/${v.id}/${b.dataset.scheda}`; };
    b.onkeydown = e => {
      const verso = {ArrowRight: 1, ArrowLeft: -1}[e.key];
      if (!verso) return;
      const tutte = $$(".schede-menu button", el), prossima = tutte[(tutte.indexOf(b) + verso + tutte.length) % tutte.length];
      location.hash = `#/${v.id}/${prossima.dataset.scheda}`;
      requestAnimationFrame(() => $(`#linguetta-${prossima.dataset.scheda}`)?.focus());
    };
  });
  DISEGNA[v.id]($("#pannello"), scheda);
  if (S) AGGIORNA[v.id]?.(S);
  if (sposta) { el.focus({preventScroll: true}); scrollTo(0, 0); }
}

function applicaVista() {
  document.body.classList.toggle("semplice", vista === "semplice");
  $("#avanzata").checked = vista === "avanzata";
}

const FASI = ["attiva", "avvio", "errore", "ferma", "modello"];
const leggiStato = prova(async () => {
  S = await api("/api/stato");
  const fase = FASI.includes(S.fase) ? S.fase : "ferma";
  $("#latoPunto").className = "punto " + fase;
  $("#latoTesto").textContent = t(`stato.breve.${fase}`);
  $("#versione").textContent = t("generale.versione", {v: S.versione});
  AGGIORNA[aperta.id]?.(S);
});

// ------------------------------------------------------------------ 3. le viste

// ---- Inizio
DISEGNA.inizio = el => {
  el.innerHTML = `
    <section class="scheda" aria-labelledby="statoTitolo"><div class="dentro"><div class="stato-grande">
      <span class="punto" id="statoPunto"></span><div><strong id="statoTitolo">…</strong><div class="sfumato" id="statoSotto"></div></div>
      <span class="spazio"></span>
      <button class="bottone" id="riavvia" hidden>${esc(t("inizio.riavvia"))}</button><button class="bottone primario" id="interruttore">…</button>
    </div></div></section>
    <div id="aggiornamento"></div>
    <div class="tessere">${["testo", "documenti", "guida"].map(v => `<a class="tessera" href="#/${v}">${icona(v)}<b>${esc(t(`inizio.tessera.${v}`))}</b><span>${esc(t(`inizio.tessera.${v}.sotto`))}</span></a>`).join("")}</div>
    <div class="griglia">${["messaggi", "sostituzioni", "bloccate"].map(k => scheda(`<div class="numero" id="n-${k}">0</div><div class="sfumato piccolo">${esc(t(`inizio.oggi.${k}`))}</div>`)).join("")}
      ${scheda(`<div class="numero" id="n-voci">–</div><div class="sfumato piccolo">${esc(t("inizio.voci"))}</div>`, "", "solo-avanzata")}</div>
    <div id="avvertenze" class="blocco solo-avanzata"></div>
    <section class="scheda solo-avanzata" aria-label="${esc(t("inizio.canali"))}" id="canali"></section>
    <div class="due solo-avanzata">
      ${scheda(`<h2>${esc(t("inizio.grafico.giorni"))}</h2><div class="colonne" id="giorni"></div>`)}
      ${scheda(`<h2>${esc(t("inizio.grafico.servizi"))}</h2><div class="barre" id="perServizio"></div>`)}
    </div>
    ${scheda(`<h2>${esc(t("inizio.grafico.tipi"))}</h2><div class="barre" id="perTipo"></div>`, "", "solo-avanzata")}`;
  $("#interruttore").onclick = prova(async () => { await api("/api/protezione", {azione: ["attiva", "modello"].includes(S?.fase) ? "ferma" : "avvia"}); leggiStato(); });
  $("#riavvia").onclick = prova(async () => { await api("/api/protezione", {azione: "riavvia"}); leggiStato(); });
  canali();
};
AGGIORNA.inizio = s => {
  const fase = FASI.includes(s.fase) ? s.fase : "ferma", sc = s.scaricamento;
  $("#statoPunto").className = "punto " + fase;
  $("#statoTitolo").textContent = t(`stato.${fase}`);
  const sotto = $("#statoSotto");
  if (fase === "modello" && sc && sc.totale) {
    const pc = Math.min(100, Math.floor(100 * sc.fatti / sc.totale));
    sotto.innerHTML = `${esc(t("stato.modello.avanzamento", {fatti: megabyte(sc.fatti), totale: megabyte(sc.totale), pc}))}
      <progress class="avanzamento" max="100" value="${pc}" aria-label="${esc(t("stato.modello"))}"></progress>`;
  } else {
    sotto.textContent = fase === "attiva" ? t("stato.attiva.sotto", {modello: s.modello, dove: t(s.device === "cuda" ? "stato.scheda_grafica" : "stato.processore")})
      : fase === "errore" ? s.errore + (sc && sc.manca && sc.scaricabile ? " " + t("stato.riprova") : "")
      : t(`stato.${fase}.sotto`);
  }
  const b = $("#interruttore"), acceso = fase === "attiva" || fase === "modello";
  b.textContent = t(fase === "modello" ? "generale.annulla" : acceso ? "inizio.ferma" : "inizio.avvia");
  b.className = "bottone" + (acceso ? "" : " primario");
  b.disabled = fase === "avvio";
  $("#riavvia").hidden = !s.da_riavviare;
  avvisoAggiornamento(s.aggiornamento);
  const st = s.statistiche;
  for (const k of ["messaggi", "sostituzioni", "bloccate"]) $(`#n-${k}`).textContent = num(st.oggi[k]);
  $("#n-voci").textContent = s.voci == null ? "–" : num(s.voci);
  $("#avvertenze").innerHTML = st.avvisi.map(a => `<div class="nota attenzione">${esc(t(`inizio.avvertenza.${a.codice}`, {n: num(a.n)}))}</div>`).join("");
  const m = Math.max(1, ...st.giorni.map(g => g.n));
  $("#giorni").innerHTML = st.giorni.map(g => `<div><span>${g.n || ""}</span><i data-a="${Math.round(100 * g.n / m)}"></i><span>${esc(g.giorno.slice(8) + "/" + g.giorno.slice(5, 7))}</span></div>`).join("");
  misure($("#giorni"));
  barre($("#perServizio"), st.servizi); barre($("#perTipo"), st.tipi, tipoDato);
};
let avvisoVisto = "";
function avvisoAggiornamento(a) {
  const el = $("#aggiornamento");
  if (!a || !el) return;
  const pc = a.totale ? Math.min(100, Math.floor(100 * a.fatti / a.totale)) : 0, v = esc(a.versione);
  const note = a.note ? `<div class="piccolo">${esc(a.note)}</div>` : "";
  const html = a.fase === "pronto" ? `<div class="nota"><div class="spazio"><b>${esc(t("aggiornamenti.pronto", {v}))}</b><div class="piccolo sfumato">${esc(t("aggiornamenti.pronto.sotto"))}</div>${note}</div><button class="bottone primario" data-azione="installa">${esc(t("aggiornamenti.installa"))}</button></div>`
    : a.fase === "scarico" ? `<div class="nota"><span>${esc(t("aggiornamenti.scarico", {v, pc}))}</span></div>`
    : a.fase === "disponibile" ? `<div class="nota"><div class="spazio"><b>${esc(t("aggiornamenti.disponibile", {v}))}</b>${note}</div>${a.installabile
      ? `<button class="bottone" data-azione="scarica">${esc(t("aggiornamenti.scarica"))}</button>`
      : `<a class="bottone" href="${esc(a.pagina)}" target="_blank" rel="noopener">${esc(t("aggiornamenti.pagina"))}</a>`}</div>` : "";
  if (html === avvisoVisto && el.innerHTML) return;   // riscritto solo se cambia: un pulsante non deve sparire sotto il clic
  avvisoVisto = html; el.innerHTML = html;
  $$("button[data-azione]", el).forEach(b => b.onclick = prova(async () => {
    b.disabled = true;
    await api("/api/aggiornamenti", {azione: b.dataset.azione});
    if (b.dataset.azione === "installa") avvisa(t("aggiornamenti.installazione_avviata"));
    leggiStato();
  }));
}
/** Le quattro strade della protezione automatica, con il loro stato: un colpo d'occhio che porta a Collegamenti. */
const canali = prova(async () => {
  const el = $("#canali");
  if (!el || vista !== "avanzata") return;
  const [app, gw] = await Promise.all([api("/api/app"), api("/api/gateway")]);
  if (!$("#canali")) return;
  const collegate = app.filter(a => a.collegata).length;
  const voce = (id, stato, tipo) => `<a class="canale" href="#/collegamenti/${id}">${icona(id)}<b>${esc(t(`collegamenti.scheda.${id}`))}</b>${etichetta(stato, tipo)}<span class="sotto">${esc(t(`inizio.canale.${id}`))}</span></a>`;
  el.innerHTML = voce("browser", !estensione ? t("browser.stato.assente") : estensione.collegata && estensione.ok ? t("browser.stato.collegata") : t("browser.stato.da_collegare"), estensione && estensione.collegata && estensione.ok ? "ok" : "")
    + voce("app", collegate ? t("app.collegate", {n: collegate}) : t("app.nessuna_collegata"), collegate ? "ok" : "")
    + voce("terminale", gw.attivo ? t("terminale.attivo", {porta: gw.porta}) : (gw.errore || t("terminale.fermo")), gw.attivo ? "ok" : gw.errore ? "errore" : "")
    + voce("proxy", S && S.fase === "attiva" ? t("proxy.attivo", {porta: S.porta}) : t("proxy.fermo"), S && S.fase === "attiva" ? "ok" : "");
});

// ---- Testo
// Una casella sola: un testo normale viene mascherato, uno che contiene segnaposto viene riportato ai valori veri.
// Incollando parte da solo, e il risultato va da solo negli appunti (si può spegnere).
// Il risultato si corregge sul posto: un segnaposto di troppo si lascia in chiaro, un dato sfuggito si maschera a mano.
const RX_SEGNAPOSTO = /\[[A-Z][A-Z_]{1,22}_\d{1,7}\]/;
const TIPI_A_MANO = ["ELENCO", "PERSONA", "ORG", "INDIRIZZO", "TELEFONO", "EMAIL", "ID_PRATICA", "SEGRETO"];
const ricordo = (chiave, valore) => { try { if (valore === undefined) return localStorage.getItem(chiave); localStorage.setItem(chiave, valore); } catch { /* memoria del browser non disponibile */ } return null; };
let risultato = "";
DISEGNA.testo = el => {
  let correzioni = {mai: [], anche: {}};   // valgono per il testo che c'è nella casella: si azzerano quando se ne incolla un altro
  el.innerHTML = scheda(`<label class="campo" for="ingresso">${esc(t("testo.ingresso"))}<span class="aiuto">${esc(t("testo.ingresso.sotto"))}</span></label>
      <textarea id="ingresso" placeholder="${esc(t("testo.esempio"))}"></textarea>
      <div class="riga"><button class="bottone primario" id="incolla">${esc(t("testo.incolla"))}</button>
        <button class="bottone" id="maschera">${esc(t("testo.maschera"))}</button><button class="bottone" id="ripristina">${esc(t("testo.ripristina"))}</button>
        <button class="bottone" id="svuotaTesto">${esc(t("testo.svuota"))}</button>
        <span class="spazio"></span><label class="riga">${levetta("copiaDaSolo", t("testo.copia_da_solo"))}<span>${esc(t("testo.copia_da_solo"))}</span></label></div>`)
    + scheda(`<div class="riga"><h2 id="titoloRisultato">${esc(t("testo.risultato"))}</h2><span class="spazio"></span><span class="sfumato piccolo" id="notaRisultato"></span></div>
      <div class="esito" id="esito" aria-live="polite" aria-labelledby="titoloRisultato"></div>
      <div class="etichette" id="trovati"></div>
      <div class="correggi" id="correggi" hidden>
        <p class="aiuto" id="correggiAiuto">${esc(t("testo.correggi.aiuto"))}</p>
        <div class="riga" id="suSegnaposto" hidden></div>
        <form class="riga" id="aggiungi">
          <input type="text" id="daMascherare" class="spazio" maxlength="200" aria-label="${esc(t("testo.correggi.campo"))}" placeholder="${esc(t("testo.correggi.campo"))}">
          <select id="tipoAMano" aria-label="${esc(t("testo.correggi.tipo"))}">${TIPI_A_MANO.map(k => `<option value="${k}">${esc(k === "ELENCO" ? t("testo.correggi.tipo.altro") : tipoDato(k))}</option>`).join("")}</select>
          <label class="riga piccolo"><input type="checkbox" id="ancheSempre">${esc(t("testo.correggi.sempre"))}</label>
          <button class="bottone" id="mascheraAnche">${esc(t("testo.correggi.maschera"))}</button>
        </form>
        <div class="etichette" id="correzioniFatte"></div>
      </div>`,
      `<span id="cosaFatto">${esc(t("testo.risultato.vuoto"))}</span><span class="spazio"></span><button class="bottone" id="copiaRisultato" disabled>${esc(t("testo.copia"))}</button>`);
  const daSolo = $("#copiaDaSolo");
  daSolo.checked = ricordo("copia_da_solo") !== "no";
  daSolo.onchange = () => ricordo("copia_da_solo", daSolo.checked ? "si" : "no");
  const consegna = async (cosa, nota) => {
    $("#copiaRisultato").disabled = false;
    $("#notaRisultato").textContent = nota;
    if (daSolo.checked && risultato) { await copia(risultato, t(`testo.${cosa}.copiato`)); $("#cosaFatto").textContent = t(`testo.${cosa}.copiato`); }
    else $("#cosaFatto").textContent = t(`testo.${cosa}.fatto`);
  };
  const fatte = () => {
    const voce = (cosa, valore) => `<button type="button" class="etichetta togli" data-cosa="${cosa}" data-valore="${esc(valore)}" title="${esc(t("testo.correggi.togli"))}">${esc(t(`testo.correggi.fatta.${cosa}`, {valore}))} <span aria-hidden="true">×</span></button>`;
    $("#correzioniFatte").innerHTML = correzioni.mai.map(v => voce("mai", v)).join("") + Object.keys(correzioni.anche).map(v => voce("anche", v)).join("");
    $$("#correzioniFatte button").forEach(b => b.onclick = () => {
      if (b.dataset.cosa === "mai") correzioni.mai = correzioni.mai.filter(v => v !== b.dataset.valore); else delete correzioni.anche[b.dataset.valore];
      maschera();
    });
  };
  const maschera = prova(async () => {
    const r = await api("/api/prova", {testo: $("#ingresso").value, mai: correzioni.mai, anche: correzioni.anche});
    risultato = r.testi[0];
    $("#esito").innerHTML = esc(risultato).replace(new RegExp(RX_SEGNAPOSTO, "g"), s => `<button type="button" class="segnaposto" data-s="${s}" data-v="${esc(r.mappa[s] ?? "")}" title="${esc(r.mappa[s] ?? "")}">${s}</button>`);
    $$("#esito button").forEach(b => b.onclick = () => suSegnaposto(b.dataset.s, b.dataset.v));
    $("#trovati").innerHTML = conteggi(r.conteggi) || `<span class="sfumato">${esc(t("testo.nessun_dato"))}</span>`;
    $("#correggi").hidden = false; $("#suSegnaposto").hidden = true;
    fatte();
    await consegna("mascherato", `${r.ms} ms`);
  });
  const ripristina = prova(async () => {
    const r = await api("/api/ripristina", {testo: $("#ingresso").value});
    risultato = r.testo;
    $("#esito").textContent = r.testo;
    $("#trovati").innerHTML = "";
    $("#correggi").hidden = true;
    await consegna("ripristinato", t("testo.ripristinati", {n: r.ripristinati}) + (r.sconosciuti ? " " + t("testo.sconosciuti", {n: r.sconosciuti}) : ""));
  });
  // un segnaposto premuto: cosa nasconde, e i due modi per toglierlo (solo questa volta, oppure per sempre)
  const suSegnaposto = (segnaposto, valore) => {
    const zona = $("#suSegnaposto");
    zona.hidden = false;
    zona.innerHTML = `<span>${t("testo.correggi.sta_per", {segnaposto: `<span class="segnaposto">${esc(segnaposto)}</span>`, valore: `<b>${esc(valore)}</b>`})}</span><span class="spazio"></span>
      <button type="button" class="bottone" data-fai="chiaro">${esc(t("testo.correggi.chiaro"))}</button><button type="button" class="bottone" data-fai="mai">${esc(t("testo.correggi.mai"))}</button>
      <button type="button" class="bottone" data-fai="chiudi" aria-label="${esc(t("generale.chiudi"))}">×</button>`;
    $$("button", zona).forEach(b => b.onclick = prova(async () => {
      if (b.dataset.fai === "chiudi") { zona.hidden = true; return; }
      if (b.dataset.fai === "mai") { await api("/api/liste/aggiungi", {lista: "mai", termine: valore}); avvisa(t("testo.correggi.mai.fatto", {valore})); }
      if (!correzioni.mai.includes(valore)) correzioni.mai.push(valore);
      await maschera();
    }));
    $("button", zona).focus();
  };
  $("#aggiungi").onsubmit = prova(async e => {
    e.preventDefault();
    const termine = $("#daMascherare").value.trim();
    if (termine.length < 2) { $("#daMascherare").focus(); return; }
    if ($("#ancheSempre").checked) { await api("/api/liste/aggiungi", {lista: "sempre", termine}); avvisa(t("testo.correggi.sempre.fatto", {valore: termine})); }
    correzioni.mai = correzioni.mai.filter(v => v !== termine);
    correzioni.anche[termine] = $("#tipoAMano").value;
    $("#daMascherare").value = ""; $("#ancheSempre").checked = false;
    await maschera();
  });
  // il testo selezionato nel risultato finisce nella casella «manca qualcosa»: basta premere il pulsante
  const selezione = () => {
    const s = getSelection(), testo = String(s).trim();
    if (testo.length >= 2 && testo.length <= 200 && !testo.includes("\n") && !RX_SEGNAPOSTO.test(testo) && s.anchorNode && $("#esito").contains(s.anchorNode) && !$("#correggi").hidden) $("#daMascherare").value = testo;
  };
  $("#esito").addEventListener("mouseup", selezione);
  $("#esito").addEventListener("keyup", selezione);
  const nuovo = () => { correzioni = {mai: [], anche: {}}; };
  const daSe = () => { if ($("#ingresso").value.trim()) (RX_SEGNAPOSTO.test($("#ingresso").value) ? ripristina : maschera)(); };
  $("#maschera").onclick = maschera;
  $("#ripristina").onclick = ripristina;
  $("#ingresso").addEventListener("paste", () => { nuovo(); setTimeout(daSe); });   // il testo incollato c'è solo un attimo dopo
  $("#ingresso").addEventListener("keydown", e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); daSe(); } });
  $("#incolla").onclick = prova(async () => {
    let testo;
    try { testo = await navigator.clipboard.readText(); } catch { throw new Error(t("testo.incolla.negato")); }
    $("#ingresso").value = testo;
    nuovo(); daSe();
  });
  $("#svuotaTesto").onclick = () => {
    nuovo(); risultato = "";
    $("#ingresso").value = ""; $("#esito").textContent = ""; $("#trovati").innerHTML = ""; $("#notaRisultato").textContent = "";
    $("#correggi").hidden = true; $("#copiaRisultato").disabled = true; $("#cosaFatto").textContent = t("testo.risultato.vuoto");
    $("#ingresso").focus();
  };
  $("#copiaRisultato").onclick = () => copia(risultato);
};

// ---- Documenti
const base64 = buf => { let s = ""; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };
DISEGNA.documenti = el => {
  const scelta = `<div class="scelta" role="radiogroup" aria-label="${esc(t("documenti.azione"))}">${["auto", "anonimizza", "ripristina"].map((a, i) =>
      `<label><input type="radio" name="azione" value="${a}"${i ? "" : " checked"}>${esc(t(`documenti.${a}`))}</label>`).join("")}</div>`;
  el.innerHTML = scheda(`<div class="riga"><h2>${esc(t("documenti.file"))}</h2><span class="spazio"></span>${scelta}</div>
      <div class="zona" id="zona"><span>${esc(t("documenti.trascina"))}</span>
        <label class="bottone"><input type="file" id="scegli" class="vh" multiple>${esc(t("documenti.scegli"))}</label></div>
      <label class="riga">${levetta("scaricaDaSolo", t("documenti.scarica_da_solo"))}<span>${esc(t("documenti.scarica_da_solo"))}</span></label>
      <div id="esitiFile" class="blocco" aria-live="polite"></div>`)
    + scheda(`<h2>${esc(t("documenti.cartella"))}</h2><p>${t("documenti.cartella.sotto")}</p>
      <div class="riga"><input type="text" id="percorsoCartella" class="spazio" aria-label="${esc(t("documenti.cartella.percorso"))}" placeholder="C:\\Lavoro\\Pratica Rossi">
        <button class="bottone" id="sfoglia">${esc(t("documenti.cartella.sfoglia"))}</button>
        <button class="bottone primario" data-cartella="anonimizza">${esc(t("documenti.anonimizza"))}</button><button class="bottone" data-cartella="ripristina">${esc(t("documenti.ripristina"))}</button></div>
      <div id="esitoCartella" class="blocco" aria-live="polite"></div>`);
  const daSolo = $("#scaricaDaSolo");
  daSolo.checked = ricordo("scarica_da_solo") !== "no";
  daSolo.onchange = () => ricordo("scarica_da_solo", daSolo.checked ? "si" : "no");
  const elabora = async elenco => {
    const azione = $("input[name=azione]:checked").value;
    for (const f of elenco) {
      const r = document.createElement("div");
      r.className = "riga";
      r.innerHTML = `<b>${esc(f.name)}</b><span class="sfumato">${esc(t("generale.in_lavorazione"))}</span>`;
      $("#esitiFile").prepend(r);
      try {
        if (f.size > 40e6) throw new Error(t("documenti.troppo_grande"));
        const d = await api("/api/documenti/file", {nome: f.name, azione, contenuto: base64(await f.arrayBuffer())});
        const url = URL.createObjectURL(new Blob([Uint8Array.from(atob(d.contenuto), c => c.charCodeAt(0))]));
        r.innerHTML = `<b>${esc(f.name)}</b>${etichetta(t(`documenti.fatto.${d.azione}`))}<span class="etichette">${conteggi(d.conteggi) || etichetta(t("documenti.nessuna_sostituzione"))}</span><span class="spazio"></span>
          <a class="bottone${daSolo.checked ? "" : " primario"}" download="${esc(d.nome)}" href="${url}">${esc(t("documenti.scarica", {nome: d.nome}))}</a>`;
        if (daSolo.checked) $("a[download]", r).click();
      } catch (e) { r.innerHTML = `<b>${esc(f.name)}</b>${etichetta(e.message, "errore")}`; }
    }
  };
  $("#scegli").onchange = e => { elabora([...e.target.files]); e.target.value = ""; };
  const zona = $("#zona");
  ["dragenter", "dragover"].forEach(n => zona.addEventListener(n, e => { e.preventDefault(); zona.classList.add("sopra"); }));
  ["dragleave", "drop"].forEach(n => zona.addEventListener(n, e => { e.preventDefault(); zona.classList.remove("sopra"); }));
  zona.addEventListener("drop", e => {
    // una cartella trascinata non si può leggere da qui: si usa «Cartella intera», che lavora direttamente sul disco
    const cartelle = [...(e.dataTransfer.items || [])].filter(x => x.webkitGetAsEntry?.()?.isDirectory).length;
    if (cartelle) { avvisa(t("documenti.cartella_trascinata"), true); $("#sfoglia").focus(); }
    if (cartelle < e.dataTransfer.files.length) elabora([...e.dataTransfer.files].filter((f, i) => !e.dataTransfer.items?.[i]?.webkitGetAsEntry?.()?.isDirectory));
  });
  $("#sfoglia").onclick = prova(async e => {
    e.target.disabled = true;
    try {
      const r = await api("/api/cartella/scegli", {iniziale: $("#percorsoCartella").value});
      if (r.percorso) $("#percorsoCartella").value = r.percorso;
    } finally { e.target.disabled = false; e.target.focus(); }
  });
  $$("button[data-cartella]").forEach(b => b.onclick = prova(async () => {
    const esito = $("#esitoCartella");
    if (!$("#percorsoCartella").value.trim()) { $("#percorsoCartella").focus(); return; }
    esito.innerHTML = `<span class="sfumato">${esc(t("generale.in_lavorazione"))}</span>`;
    try {
      const r = await api("/api/documenti/percorso", {percorso: $("#percorsoCartella").value, azione: b.dataset.cartella});
      esito.innerHTML = `<div class="riga"><p class="spazio">${t("documenti.cartella.esito", {fatti: `<b>${r.fatti.length}</b>`, saltati: `<b>${r.saltati.length}</b>`, dove: `<code>${esc(r.destinazione)}</code>`})}</p>
          <button class="bottone" id="apriCartella">${esc(t("documenti.cartella.apri"))}</button></div>
        <div class="etichette">${conteggi(r.conteggi) || etichetta(t("documenti.nessuna_sostituzione"))}</div>`
        + tabella(t("documenti.elaborati"), r.fatti, [x => esc(x.file), x => `<span class="sotto">${esc(x.uscita)}</span>`, x => `<span class="etichette">${conteggi(x.conteggi)}</span>`])
        + tabella(t("documenti.saltati"), r.saltati, [x => esc(x.file), x => etichetta(x.motivo, "attenzione")]);
      $("#apriCartella").onclick = prova(() => api("/api/cartella/apri", {percorso: r.destinazione}));
    } catch (e) { esito.innerHTML = ""; throw e; }
  }));
};

// ---- Guida
DISEGNA.guida = el => {
  const passi = (chiave, n) => `<ol class="elenco">${Array.from({length: n}, (_, i) => `<li>${t(`${chiave}.${i + 1}`)}</li>`).join("")}</ol>`;
  el.innerHTML = scheda(`<h2>${esc(t("guida.testo"))}</h2>${passi("guida.testo", 4)}`)
    + scheda(`<h2>${esc(t("guida.tastiera"))}</h2>${passi("guida.tastiera", 4)}<p class="aiuto">${t("guida.tastiera.nota")}</p>`)
    + scheda(`<h2>${esc(t("guida.documenti"))}</h2>${passi("guida.documenti", 3)}`)
    + scheda(`<h2>${esc(t("guida.automatico"))}</h2><p>${t("guida.automatico.testo")}</p>`)
    + scheda(`<h2>${esc(t("guida.sapere"))}</h2><ul class="elenco">${[1, 2, 3, 4].map(i => `<li>${t(`guida.sapere.${i}`)}</li>`).join("")}</ul>`);
};

// ---- Impostazioni
const salva = async (dati, messaggio = "impostazioni.salvata") => { const r = await api("/api/impostazioni", dati); avvisa(t(messaggio) + (r.da_riavviare ? " " + t("impostazioni.da_riavviare") : "")); leggiStato(); return r; };
DISEGNA.impostazioni = (el, quale) => (quale === "riconoscimento" ? impostazioniRiconoscimento : impostazioniGenerali)(el);
const impostazioniGenerali = prova(async el => {
  const [i, l] = await Promise.all([api("/api/impostazioni"), api("/api/lingue")]);
  const opzioni = (voci, scelta) => voci.map(([v, n]) => `<option value="${esc(v)}"${v === scelta ? " selected" : ""}>${esc(n)}</option>`).join("");
  el.innerHTML = `<section class="scheda" aria-label="${esc(t("impostazioni.aspetto"))}">
      ${riga(t("impostazioni.lingua"), esc(t("impostazioni.lingua.sotto")), `<select id="lingua" aria-label="${esc(t("impostazioni.lingua"))}">${opzioni([["auto", t("impostazioni.automatica")], ...l.disponibili.map(x => [x.codice, x.nome])], l.scelta)}</select>`)}
      ${riga(t("impostazioni.tema"), "", `<select id="tema" aria-label="${esc(t("impostazioni.tema"))}">${opzioni([["auto", t("impostazioni.tema.auto")], ["chiaro", t("impostazioni.tema.chiaro")], ["scuro", t("impostazioni.tema.scuro")]], i.tema || "auto")}</select>`)}
      ${riga(t("menu.avanzata"), esc(t("impostazioni.avanzata.sotto")), levetta("avanzata2", t("menu.avanzata")))}
    </section>
    <section class="scheda" aria-labelledby="scTitolo">
      <div class="dentro"><h2 id="scTitolo">${esc(t("scorciatoie.titolo"))}</h2><p>${t("scorciatoie.sotto")}</p></div>
      <div id="scorciatoie"></div>
    </section>
    <section class="scheda" aria-labelledby="aggTitolo">
      <div class="dentro"><h2 id="aggTitolo">${esc(t("aggiornamenti.titolo"))}</h2><p id="aggNota"></p></div>
      ${riga(t("aggiornamenti.installata"), `<span id="aggQuando"></span>`, `<b id="aggVersione">…</b>`)}
      <div id="aggScelta">${riga(t("aggiornamenti.nuove"), "", `<select id="aggiornamenti" aria-label="${esc(t("aggiornamenti.nuove"))}">${opzioni(["automatici", "avvisa", "mai"].map(v => [v, t(`aggiornamenti.modo.${v}`)]), i.aggiornamenti)}</select><button class="bottone" id="aggControlla">${esc(t("aggiornamenti.controlla"))}</button>`)}</div>
    </section>`;
  $("#lingua").onchange = prova(async e => { await api("/api/impostazioni", {lingua: e.target.value}); location.reload(); });
  $("#tema").onchange = prova(async e => { applicaTema(e.target.value); await salva({tema: e.target.value}); });
  $("#avanzata2").checked = vista === "avanzata";
  $("#avanzata2").onchange = e => cambiaVista(e.target.checked);
  $("#aggiornamenti").onchange = prova(e => salva({aggiornamenti: e.target.value}));
  $("#aggControlla").onclick = prova(async e => {
    e.target.disabled = true;
    try {
      const a = await api("/api/aggiornamenti", {azione: "controlla"});
      avvisa(a.fase === "errore" ? a.errore : a.fase === "aggiornato" ? t("aggiornamenti.ultima") : t("aggiornamenti.disponibile", {v: a.versione}), a.fase === "errore");
      leggiStato();
    } finally { e.target.disabled = false; }
  });
  disegnaScorciatoie();
  if (S) AGGIORNA.impostazioni(S);
});
// Le scorciatoie da tastiera: una riga ciascuna, con la lettera da premere insieme a Ctrl+Alt (oppure spenta) e lo stato.
const LETTERE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
const disegnaScorciatoie = prova(async () => {
  const el = $("#scorciatoie");
  if (!el) return;
  const s = await api("/api/scorciatoie");
  el.innerHTML = s.voci.map(v => {
    const semplice = /^ctrl\+alt\+[a-z]$/.test(v.combinazione), lettera = semplice ? v.combinazione.slice(-1).toUpperCase() : "";
    const stato = !v.combinazione ? etichetta(t("scorciatoie.spenta")) : !s.disponibili ? "" : v.attiva ? etichetta(t("scorciatoie.attiva"), "ok") : etichetta(t(`scorciatoie.errore.${v.errore === "non_valida" ? "non_valida" : "occupata"}`), "errore");
    return riga(t(`scorciatoie.${v.nome}`), t(`scorciatoie.${v.nome}.sotto`), `${stato}<span class="tasti" aria-hidden="true"><kbd>Ctrl</kbd>+<kbd>Alt</kbd>+</span>
      <select data-sc="${esc(v.nome)}" aria-label="${esc(t("scorciatoie.lettera_per", {nome: t(`scorciatoie.${v.nome}`)}))}">
        <option value=""${v.combinazione ? "" : " selected"}>${esc(t("scorciatoie.spenta"))}</option>
        ${v.combinazione && !semplice ? `<option value="${esc(v.combinazione)}" selected>${esc(v.scritta)}</option>` : ""}
        ${LETTERE.map(l => `<option value="ctrl+alt+${l.toLowerCase()}"${l === lettera ? " selected" : ""}>${l}</option>`).join("")}</select>`);
  }).join("") + (s.disponibili ? "" : `<div class="impostazione"><span class="aiuto">${esc(t("scorciatoie.senza_icona"))}</span></div>`);
  $$("select[data-sc]", el).forEach(x => x.onchange = prova(async () => {
    const scelte = Object.fromEntries(s.voci.map(v => [v.nome, v.combinazione]));
    scelte[x.dataset.sc] = x.value;
    await api("/api/impostazioni", {scorciatoie: scelte});
    const dopo = (await api("/api/scorciatoie")).voci.find(v => v.nome === x.dataset.sc);
    if (dopo.combinazione && !dopo.attiva && dopo.errore) avvisa(t(`scorciatoie.errore.${dopo.errore === "non_valida" ? "non_valida" : "occupata"}.lungo`, {tasti: dopo.scritta}), true);
    else avvisa(t("impostazioni.salvata"));
    disegnaScorciatoie();
  }));
});
AGGIORNA.impostazioni = s => {
  const a = s.aggiornamento;
  if (!a || !$("#aggVersione")) return;
  $("#aggVersione").textContent = a.attuale;
  $("#aggQuando").textContent = a.canale === "store" ? "" : a.fase === "controllo" ? t("aggiornamenti.controllo") : a.fase === "errore" ? a.errore
    : a.controllato ? t("aggiornamenti.ultimo_controllo", {quando: a.controllato}) + (a.fase === "aggiornato" ? " " + t("aggiornamenti.ultima") : "") : "";
  $("#aggScelta").hidden = a.canale === "store";
  $("#aggNota").textContent = t(`aggiornamenti.nota.${["store", "sorgenti"].includes(a.canale) ? a.canale : "installer"}`);
};
const impostazioniRiconoscimento = prova(async el => {
  const [i, l] = await Promise.all([api("/api/impostazioni"), api("/api/liste")]);
  el.innerHTML = `<section class="scheda" aria-label="${esc(t("impostazioni.scheda.riconoscimento"))}">
      ${riga(t("riconoscimento.modello"), esc(t("riconoscimento.modello.sotto")), `<select id="modello" aria-label="${esc(t("riconoscimento.modello"))}"><option value="omissis-base">${esc(t("riconoscimento.modello.base"))}</option><option value="omissis-small">${esc(t("riconoscimento.modello.small"))}</option></select>`)}
      ${riga(t("riconoscimento.dove"), "", `<select id="device" aria-label="${esc(t("riconoscimento.dove"))}">${["auto", "cuda", "cpu"].map(v => `<option value="${v}">${esc(t(`riconoscimento.dove.${v}`))}</option>`).join("")}</select>`)}
      ${["casella", "allegati", "ripristina", "blocca_file"].map(k => riga(t(`riconoscimento.${k}`), esc(t(`riconoscimento.${k}.sotto`)), levetta(k, t(`riconoscimento.${k}`)))).join("")}
    </section>
    <div class="due">
      ${scheda(`<h2 id="lSempre">${esc(t("liste.sempre"))}</h2><p>${esc(t("liste.sempre.sotto"))}</p><textarea id="sempre" aria-labelledby="lSempre"></textarea>`)}
      ${scheda(`<h2 id="lMai">${esc(t("liste.mai"))}</h2><p>${esc(t("liste.mai.sotto"))}</p><textarea id="mai" aria-labelledby="lMai"></textarea>`)}
    </div>
    <div class="riga"><button class="bottone primario" id="salvaListe">${esc(t("liste.salva"))}</button><span class="sfumato piccolo">${esc(t("liste.nota"))}</span></div>`;
  for (const k of ["modello", "device"]) { $(`#${k}`).value = i[k]; $(`#${k}`).onchange = prova(e => salva({[k]: e.target.value})); }
  for (const k of ["casella", "allegati", "ripristina", "blocca_file"]) { $(`#${k}`).checked = i[k] !== false && !!i[k]; $(`#${k}`).onchange = prova(e => salva({[k]: e.target.checked})); }
  $("#sempre").value = l.sempre.join("\n"); $("#mai").value = l.mai.join("\n");
  $("#salvaListe").onclick = prova(async () => {
    const r = await api("/api/liste", {sempre: $("#sempre").value.split("\n"), mai: $("#mai").value.split("\n")});
    avvisa(t("liste.salvate", {sempre: r.sempre.length, mai: r.mai.length}));
  });
});

// ---- Collegamenti
DISEGNA.collegamenti = (el, quale) => ({browser: collegaBrowser, app: collegaApp, terminale: collegaTerminale, proxy: collegaProxy, compatibilita: collegaCompatibilita}[quale])(el);
AGGIORNA.collegamenti = () => { if (aperta.scheda === "app" && !$("button[data-app]:disabled")) elencoApp(); if (aperta.scheda === "terminale") statoGateway(); };

function disegnaEstensione() {
  const e = $("#estStato");
  if (!e) return;
  const stato = !estensione ? "assente" : !estensione.collegata ? "da_collegare" : estensione.ok ? "collegata" : "senza_risposta";
  e.dataset.stato = stato;
  e.className = "etichetta " + (stato === "collegata" ? "ok" : stato === "assente" ? "" : "attenzione");
  e.textContent = (estensione ? t("browser.versione", {v: estensione.versione}) + " · " : "") + t(`browser.stato.${stato}`);
  $("#estCollega").disabled = !estensione;
  $("#estCollega").textContent = t(estensione && estensione.collegata ? "browser.ricollega" : "browser.collega");
}
const datiEstensione = async () => { const d = await api("/api/estensione"); if (!d.token) throw new Error(t("browser.codice_non_pronto")); return d; };
const collegaBrowser = prova(async el => {
  el.innerHTML = scheda(`<h2>${esc(t("browser.collegamento"))}</h2><p>${esc(t("browser.collegamento.sotto"))}</p>`,
      `<span id="estStato" class="etichetta">…</span><span class="spazio"></span><button class="bottone primario" id="estCollega">${esc(t("browser.collega"))}</button>`)
    + scheda(`<h2>${esc(t("browser.installazione"))}</h2>
      <ol class="elenco"><li>${t("browser.installazione.1")}</li><li>${t("browser.installazione.2")}
        <div class="riga"><code id="estCartella">…</code><button class="bottone" id="estCopiaCartella">${esc(t("browser.copia_percorso"))}</button></div></li>
        <li>${t("browser.installazione.3")}</li><li>${t("browser.installazione.4")}</li></ol>`)
    + scheda(`<h2>${esc(t("browser.a_mano"))}</h2><p>${esc(t("browser.a_mano.sotto"))}</p>`, `<button class="bottone" id="estCopiaCodice">${esc(t("browser.copia_codice"))}</button>`);
  disegnaEstensione();
  $("#estCollega").onclick = prova(async () => { const d = await datiEstensione(); window.postMessage({msp_pii: "collega", token: d.token, porta: d.porta}, location.origin); });
  $("#estCopiaCartella").onclick = () => copia($("#estCartella").textContent);
  $("#estCopiaCodice").onclick = prova(async () => copia((await datiEstensione()).token));
  window.postMessage({msp_pii: "ci sei?"}, location.origin);
  $("#estCartella").textContent = (await api("/api/estensione")).cartella;
});

function disegnaApp(elenco) {
  const el = $("#appElenco");
  if (!el) return;
  el.innerHTML = elenco.map(a => {
    const c = a.conteggi;
    const stato = !a.installata ? etichetta(t("app.stato.non_installata")) : !a.collegata ? etichetta(t("app.stato.non_collegata"))
      : a.esito === "si" ? etichetta(t("app.stato.si"), "ok") : a.esito === "attesa" ? etichetta(t("app.stato.attesa"), "attenzione") : etichetta(t("app.stato.no"), "errore");
    const numeri = c ? `<span class="aiuto">${esc(t("app.numeri", {pagine: c.pagine, messaggi: c.messaggi, controllati: c.controllati, sostituzioni: c.sostituzioni, bloccate: c.bloccate}))}</span>` : "";
    const bottone = !a.installata ? "" : a.collegata ? `<button class="bottone" data-app="${esc(a.id)}" data-azione="stacca">${esc(t("app.stacca"))}</button>`
      : `<button class="bottone primario" data-app="${esc(a.id)}" data-azione="avvia">${esc(t("app.avvia"))}</button>`;
    const errori = (a.errori || []).map(e => `<div class="nota errore">${esc(e)}</div>`).join("");
    return `<div class="impostazione" data-app-riga="${esc(a.id)}" data-esito="${esc(a.collegata ? a.esito || "no" : "")}"><span class="nome">${esc(a.nome)} ${stato}</span>${numeri}<span class="comando">${bottone}</span></div>${errori}`;
  }).join("");
  $$("button[data-app]", el).forEach(b => b.onclick = prova(async () => {
    b.disabled = true;
    b.textContent = b.dataset.azione === "avvia" ? t("app.avvio_in_corso") : "…";
    try { disegnaApp(await api("/api/app", {id: b.dataset.app, azione: b.dataset.azione})); } catch (e) { elencoApp(); throw e; }
  }));
}
const elencoApp = prova(async () => disegnaApp(await api("/api/app")));
const collegaApp = el => {
  el.innerHTML = `<section class="scheda" aria-label="${esc(t("collegamenti.scheda.app"))}" id="appElenco"><div class="vuoto">…</div></section>`
    + scheda(`<h2>${esc(t("app.sapere"))}</h2><ul class="elenco sfumato">${[1, 2, 3, 4, 5].map(i => `<li>${t(`app.sapere.${i}`)}</li>`).join("")}</ul>`);
  elencoApp();
};

const statoGateway = prova(async () => {
  const g = await api("/api/gateway"), e = $("#gwStato");
  if (!e) return g;
  e.textContent = g.attivo ? t("terminale.attivo", {porta: g.porta}) : g.errore || t("terminale.fermo");
  e.className = "etichetta " + (g.attivo ? "ok" : g.errore ? "errore" : "");
  $("#gwNumeri").textContent = g.conteggi ? t("terminale.numeri", g.conteggi) : "";
  return g;
});
const collegaTerminale = prova(async el => {
  el.innerHTML = scheda(`<div class="riga"><h2>${esc(t("terminale.stato"))}</h2><span id="gwStato" class="etichetta">…</span><span class="spazio"></span><span class="sfumato piccolo" id="gwNumeri"></span></div>`)
    + scheda(`<h2>${esc(t("terminale.come"))}</h2><p>${esc(t("terminale.come.sotto"))}</p><div class="blocco" id="gwRighe"></div>`)
    + scheda(`<h2>${esc(t("terminale.verificato"))}</h2><ul class="elenco sfumato">${[1, 2, 3, 4].map(i => `<li>${t(`terminale.verificato.${i}`)}</li>`).join("")}</ul>`);
  const g = await statoGateway(), u = `http://127.0.0.1:${g.porta}`;
  const righe = [["claude", `$env:ANTHROPIC_BASE_URL="${u}/anthropic"; claude`], ["openai", `$env:OPENAI_BASE_URL="${u}/openai/v1"`],
    ["altri", g.rotte.filter(r => !["anthropic", "openai", "ollama", "lmstudio"].includes(r)).map(r => `${u}/${r}`).join("\n")], ["locali", `${u}/ollama/v1\n${u}/lmstudio/v1`]];
  $("#gwRighe").innerHTML = righe.map(([n, r]) => `<div><div class="riga"><h3>${esc(t(`terminale.riga.${n}`))}</h3><span class="spazio"></span><button class="bottone" data-copia="${esc(r)}">${esc(t("generale.copia"))}</button></div><pre>${esc(r)}</pre></div>`).join("");
  $$("button[data-copia]").forEach(b => b.onclick = () => copia(b.dataset.copia));
});

const collegaProxy = prova(async el => {
  const i = await api("/api/impostazioni");
  el.innerHTML = `<section class="scheda" aria-label="${esc(t("collegamenti.scheda.proxy"))}">
      ${riga(t("proxy.porta"), esc(t("proxy.porta.sotto")), `<input type="number" id="porta" min="1024" max="65535" value="${esc(i.porta)}" aria-label="${esc(t("proxy.porta"))}"><button class="bottone" id="salvaPorta">${esc(t("generale.salva"))}</button>`)}
      ${riga(t("proxy.certificato"), esc(t("proxy.certificato.sotto")), `<span id="certStato" class="etichetta">…</span><button class="bottone" id="certInstalla">${esc(t("proxy.certificato.installa"))}</button><button class="bottone pericolo" id="certRimuovi">${esc(t("proxy.certificato.rimuovi"))}</button>`)}
    </section>`
    + scheda(`<h2>${esc(t("proxy.finestra"))}</h2><p>${esc(t("proxy.finestra.sotto"))}</p>
      <div class="riga">${[["Claude", "https://claude.ai"], ["ChatGPT", "https://chatgpt.com"], ["Gemini", "https://gemini.google.com"], ["Perplexity", "https://www.perplexity.ai"], ["Copilot", "https://copilot.microsoft.com"]]
        .map(([n, u]) => `<button class="bottone" data-indirizzo="${u}">${n}</button>`).join("")}</div>`);
  const certificato = c => {
    $("#certStato").textContent = t(c.installato ? "proxy.certificato.installato" : c.esiste ? "proxy.certificato.non_installato" : "proxy.certificato.non_creato");
    $("#certStato").className = "etichetta " + (c.installato ? "attenzione" : "");
    $("#certInstalla").disabled = !c.esiste || c.installato; $("#certRimuovi").disabled = !c.installato;
  };
  certificato(i.certificato);
  $("#salvaPorta").onclick = prova(() => salva({porta: +$("#porta").value}));
  $("#certInstalla").onclick = prova(async () => certificato(await api("/api/certificato", {azione: "installa"})));
  $("#certRimuovi").onclick = prova(async () => certificato(await api("/api/certificato", {azione: "rimuovi"})));
  $$("button[data-indirizzo]").forEach(b => b.onclick = prova(async () => avvisa((await api("/api/browser", {indirizzo: b.dataset.indirizzo})).esito)));
});

const collegaCompatibilita = prova(async el => {
  const c = await api("/api/compatibilita");
  const quando = s => esc((s || "").slice(0, 16));
  const riga = g => `<tr><td><b>${esc(g.nome)}</b></td><td>${esc(tSe("via." + g.via, g.via))}</td><td>${esc(g.cliente || t("compatibilita.sconosciuto"))}</td>
    <td>${etichetta(t(`compatibilita.stato.${g.stato}`), g.stato === "funziona" ? "ok" : "attenzione")}<div class="sotto">${g.metodi.map(m => esc(t(`compatibilita.metodo.${m}`))).join(", ")}</div></td>
    <td>${quando(g.ultimo_ok) || "–"}<div class="sotto">${esc(t("compatibilita.conteggi", {ok: g.ok, ripristino: g.ripristino, non_letto: g.non_letto}))}</div></td></tr>`;
  const verificato = v => `<tr><td><b>${esc(v.nome || t("compatibilita.ogni_servizio"))}</b></td><td>${esc(tSe("via." + v.via, v.via))}</td><td>${esc([v.cliente, v.versione].filter(Boolean).join(" "))}</td>
    <td>${etichetta(t(`compatibilita.livello.${v.livello}`), v.livello === "dal_vivo" ? "ok" : "")}<div class="sotto">${esc(t(`compatibilita.metodo.${v.metodo}`))}</div></td><td>${esc(v.data || "")}</td></tr>`;
  const testa = colonne => `<thead><tr>${colonne.map(k => `<th scope="col">${esc(t(`compatibilita.colonna.${k}`))}</th>`).join("")}</tr></thead>`;
  el.innerHTML = `<section class="scheda"><div class="dentro"><div class="riga"><h2>${esc(t("compatibilita.visti"))}</h2><span class="spazio"></span><button class="bottone" id="copiaCompatibilita">${esc(t("compatibilita.copia"))}</button></div>
      <p>${esc(t("compatibilita.visti.sotto"))}</p></div>
      <div class="tabella"><table><caption class="vh">${esc(t("compatibilita.visti"))}</caption>${testa(["servizio", "strada", "programma", "stato", "ultimo"])}<tbody>${
        c.visti.map(riga).join("") || `<tr><td colspan="5" class="vuoto">${esc(t("compatibilita.vuoto"))}</td></tr>`}</tbody></table></div></section>
    <section class="scheda"><div class="dentro"><h2>${esc(t("compatibilita.verificati"))}</h2><p>${esc(t("compatibilita.verificati.sotto", {data: c.aggiornato}))}</p></div>
      <div class="tabella"><table><caption class="vh">${esc(t("compatibilita.verificati"))}</caption>${testa(["servizio", "strada", "programma", "livello", "data"])}<tbody>${c.verificati.map(verificato).join("")}</tbody></table></div></section>`;
  $("#copiaCompatibilita").onclick = () => copia(c.visti.map(g => `${g.nome} | ${g.via} | ${g.cliente || "?"} | ${g.stato} | ok ${g.ok}, ripristini ${g.ripristino}, non letti ${g.non_letto} | ultimo ${g.ultimo_ok || "-"}`).join("\n") || t("compatibilita.vuoto"));
});

// ---- Servizi AI
let elencoServizi = [];
DISEGNA.servizi = (el, quale) => (quale === "rilevati" ? serviziRilevati : serviziRegole)(el);
const serviziRegole = prova(async el => {
  el.innerHTML = `<div class="riga"><input type="search" id="filtro" placeholder="${esc(t("servizi.cerca"))}" aria-label="${esc(t("servizi.cerca"))}">
      <select id="quali" aria-label="${esc(t("servizi.quali"))}">${["tutti", "catalogo", "radar"].map(q => `<option value="${q}">${esc(t(`servizi.quali.${q}`))}</option>`).join("")}</select>
      <span class="sfumato piccolo" id="conta" aria-live="polite"></span></div>
    <p class="aiuto">${esc(t("servizi.radar.nota"))}</p>
    <section class="scheda"><div class="tabella"><table><caption class="vh">${esc(t("servizi.scheda.regole"))}</caption><thead><tr>
      ${["servizio", "tipo", "lettura", "cosa_fare", "contatti"].map(c => `<th scope="col">${esc(t(`servizi.colonna.${c}`))}</th>`).join("")}</tr></thead><tbody id="tabServizi"></tbody></table></div></section>`;
  elencoServizi = await api("/api/servizi");
  const disegna = () => {
    const f = $("#filtro").value.toLowerCase(), quali = $("#quali").value;
    const visibili = elencoServizi.filter(s => quali === "tutti" || (quali === "radar") === !!s.radar).filter(s => `${s.nome} ${s.fornitore} ${tSe("servizi.tipo." + s.tipo, s.tipo)} ${s.domini.join(" ")}`.toLowerCase().includes(f));
    $("#conta").textContent = t("servizi.conta", {visibili: visibili.length, tutti: elencoServizi.length, protetti: elencoServizi.filter(s => s.politica === "proteggi" && s.leggibile).length, bloccati: elencoServizi.filter(s => s.politica === "blocca").length});
    $("#tabServizi").innerHTML = visibili.map(s => {
      const opzioni = ["proteggi", "registra", "blocca", "ignora"].filter(p => p !== "proteggi" || s.leggibile)
        .map(p => `<option value="${p}"${p === s.politica ? " selected" : ""}>${esc(t(`servizi.politica.${p}`))}</option>`).join("");
      return `<tr><td><b>${esc(s.nome)}</b><div class="sotto">${esc(s.fornitore)} · ${esc(s.domini.join(", "))}</div></td><td>${esc(tSe("servizi.tipo." + s.tipo, s.tipo))}</td>
        <td>${etichetta(t(`servizi.lettura.${s.lettura}`), s.lettura === "provato" ? "ok" : s.leggibile ? "attenzione" : "")}</td>
        <td><select data-id="${esc(s.id)}" aria-label="${esc(t("servizi.cosa_fare_per", {nome: s.nome}))}">${opzioni}</select></td>
        <td>${s.contatti || ""}<div class="sotto">${esc((s.ultimo || "").slice(0, 16))}</div></td></tr>`;
    }).join("");
    $$("#tabServizi select").forEach(x => x.onchange = prova(async () => { await api("/api/servizi", {id: x.dataset.id, politica: x.value}); elencoServizi = await api("/api/servizi"); disegna(); leggiStato(); }));
  };
  $("#filtro").oninput = disegna;
  $("#quali").onchange = disegna;
  disegna();
});
const scelta = p => p ? etichetta(t(`rilevati.scelta.${p}`), p === "blocca" ? "errore" : p === "proteggi" ? "" : "attenzione") : "";
const CATEGORIE = ["programmi", "estensioni_browser", "estensioni_editor", "comandi", "modelli_locali", "in_ascolto", "processi", "contattati"];
const giorno = s => s ? `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}` : "";
// L'inventario si tiene nel tempo: ogni analisi viene salvata e confrontata con la precedente (novità, da quando una cosa c'è,
// giudizio di chi gestisce il PC). La parte «In rete adesso» resta una fotografia del momento.
const serviziRilevati = prova(async el => {
  el.innerHTML = `<div class="nota"><span>${t("rilevati.nota")}</span></div>`
    + `<section class="scheda"><div class="dentro">
        <div class="riga"><div><h2>${esc(t("inventario.titolo"))}</h2><div class="sfumato piccolo" id="invQuando" aria-live="polite"></div></div><span class="spazio"></span>
          <label class="riga piccolo" for="invOgni">${esc(t("inventario.ripeti"))}<select id="invOgni">${["settimanale", "giornaliera", "mai"].map(v => `<option value="${v}">${esc(t(`inventario.ripeti.${v}`))}</option>`).join("")}</select></label>
          <button class="bottone primario" id="analizza">${esc(t("inventario.analizza"))}</button></div>
        <div id="invNovita" class="blocco"></div>
        <div class="riga"><input type="search" id="invCerca" class="spazio" placeholder="${esc(t("inventario.cerca"))}" aria-label="${esc(t("inventario.cerca"))}">
          <select id="invQuali" aria-label="${esc(t("inventario.quali"))}">${["presenti", "tutti", "spariti", "da_valutare", "da_rimuovere"].map(v => `<option value="${v}">${esc(t(`inventario.quali.${v}`))}</option>`).join("")}</select>
          <button class="bottone" id="invEsporta">${esc(t("inventario.esporta"))}</button><button class="bottone" id="invDimentica">${esc(t("inventario.dimentica"))}</button></div>
      </div>
      <div class="tabella"><table><caption class="vh">${esc(t("inventario.titolo"))}</caption><thead><tr>
        ${["nome", "categoria", "visto", "regola", "giudizio"].map(c => `<th scope="col">${esc(t(`inventario.colonna.${c}`))}</th>`).join("")}</tr></thead><tbody id="invTabella"></tbody></table></div></section>`
    + scheda(`<div class="riga"><h2>${esc(t("rilevati.rete"))}</h2><span class="spazio"></span><span class="sfumato piccolo" id="reteQuando"></span><button class="bottone" id="analizzaRete">${esc(t("rilevati.aggiorna"))}</button></div>
      <div id="rete" class="blocco sfumato" aria-live="polite">${esc(t("rilevati.rete.sotto"))}</div>`);
  const nome = (a, b) => `<b>${esc(a)}</b><div class="sotto">${esc(b)}</div>`;
  let inv = await api("/api/inventario");
  const disegna = () => {
    const ultima = inv.analisi[0];
    $("#invOgni").value = inv.ogni || "settimanale";
    $("#invQuando").textContent = !ultima ? t("inventario.mai_fatta")
      : t("inventario.ultima", {quando: `${giorno(ultima.ora)} ${ultima.ora.slice(11, 16)}`, origine: t(`inventario.origine.${ultima.origine === "automatica" ? "automatica" : "manuale"}`), n: inv.n_analisi})
        + (inv.prossima ? " " + t("inventario.prossima", {quando: `${giorno(inv.prossima)} ${inv.prossima.slice(11, 16)}`}) : "");
    const recenti = inv.eventi.slice(0, 12);
    $("#invNovita").innerHTML = recenti.length ? `<h3>${esc(t("inventario.novita"))}</h3><ul class="elenco eventi">${recenti.map(e =>
      `<li>${etichetta(t(`inventario.evento.${e.tipo}`), e.tipo === "comparso" ? "attenzione" : "")} <b>${esc(e.nome)}</b> <span class="sfumato">${esc(t(`inventario.categoria.${e.categoria}`))} · ${esc(giorno(e.ora))}</span></li>`).join("")}</ul>` : "";
    const f = $("#invCerca").value.toLowerCase(), quali = $("#invQuali").value;
    const visibili = inv.elementi.filter(e => quali === "tutti" || (quali === "presenti" && e.presente) || (quali === "spariti" && !e.presente)
        || (quali === "da_valutare" && e.presente && !e.giudizio) || (quali === "da_rimuovere" && e.giudizio === "da_rimuovere"))
      .filter(e => `${e.nome} ${e.dettaglio} ${e.nota} ${t(`inventario.categoria.${e.categoria}`)}`.toLowerCase().includes(f))
      .sort((a, b) => CATEGORIE.indexOf(a.categoria) - CATEGORIE.indexOf(b.categoria));
    $("#invTabella").innerHTML = visibili.length ? visibili.map(e => `<tr>
        <td>${nome(e.nome, [e.dettaglio, e.versione].filter(Boolean).join(" · "))}</td>
        <td>${esc(t(`inventario.categoria.${e.categoria}`))}</td>
        <td>${e.presente ? "" : etichetta(t("inventario.non_piu"), "attenzione")}<div class="sotto">${esc(t("inventario.dal", {primo: giorno(e.primo), ultimo: giorno(e.ultimo)}))}</div></td>
        <td><span class="etichette">${scelta(e.politica)}${e.segnale === "tutti_i_siti" ? etichetta(t("rilevati.tutti_i_siti"), "errore") : ""}</span></td>
        <td><select data-chiave="${esc(e.chiave)}" aria-label="${esc(t("inventario.giudizio_per", {nome: e.nome}))}">${["", "approvato", "da_rimuovere"].map(g => `<option value="${g}"${g === (e.giudizio || "") ? " selected" : ""}>${esc(t(`inventario.giudizio.${g || "da_valutare"}`))}</option>`).join("")}</select>
          <input type="text" class="nota-breve" data-nota="${esc(e.chiave)}" value="${esc(e.nota || "")}" maxlength="300" placeholder="${esc(t("inventario.nota"))}" aria-label="${esc(t("inventario.nota_per", {nome: e.nome}))}"></td></tr>`).join("")
      : `<tr><td colspan="5" class="vuoto">${esc((inv.elementi.length ? t("inventario.nessuno_filtro") : t("inventario.vuoto")))}</td></tr>`;
    $$("#invTabella select").forEach(x => x.onchange = prova(async () => {
      await api("/api/inventario/giudizio", {chiave: x.dataset.chiave, giudizio: x.value});
      inv.elementi.find(e => e.chiave === x.dataset.chiave).giudizio = x.value;
    }));
    $$("#invTabella input").forEach(x => x.onchange = prova(async () => {
      await api("/api/inventario/giudizio", {chiave: x.dataset.nota, nota: x.value});
      inv.elementi.find(e => e.chiave === x.dataset.nota).nota = x.value;
    }));
  };
  $("#invCerca").oninput = disegna;
  $("#invQuali").onchange = disegna;
  $("#invOgni").onchange = prova(async e => { await salva({analisi: e.target.value}); inv = await api("/api/inventario"); disegna(); });
  $("#analizza").onclick = prova(async e => {
    e.target.disabled = true;
    $("#invQuando").textContent = t("rilevati.in_corso");
    try {
      inv = await api("/api/inventario/analizza", {});
      const n = inv.novita;
      avvisa(n.prima ? t("inventario.prima_fatta", {n: inv.elementi.length}) : n.nuovi.length || n.spariti.length ? t("inventario.cambiato", {nuovi: n.nuovi.length, spariti: n.spariti.length}) : t("inventario.invariato"));
    } finally { e.target.disabled = false; disegna(); }
  });
  $("#invEsporta").onclick = prova(async () => {
    const r = await fetch("/api/inventario/csv", {headers: {"X-Pannello": CODICE}});
    if (!r.ok) throw new Error(String(r.status));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await r.blob()); a.download = `omissis-inventario-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.append(a); a.click(); a.remove();
  });
  $("#invDimentica").onclick = prova(async () => {
    const n = inv.elementi.filter(e => !e.presente).length;
    if (!n) { avvisa(t("inventario.dimentica.niente")); return; }
    if (!await conferma(t("inventario.dimentica.titolo"), t("inventario.dimentica.testo", {n}), t("inventario.dimentica"))) return;
    inv = await api("/api/inventario/dimentica", {}); disegna();
  });
  $("#analizzaRete").onclick = prova(async () => {
    $("#rete").textContent = t("rilevati.in_corso");
    const r = await api("/api/shadow/rete");
    $("#reteQuando").textContent = r.quando.slice(11, 16);
    $("#rete").className = "blocco";
    $("#rete").innerHTML = (tabella(t("rilevati.contattati"), r.proxy, [x => `<b>${esc(x.servizio)}</b>`, x => `<span class="etichette">${Object.entries(x.esiti).map(([e, n]) => etichetta(`${tSe("rilevati.esito." + e, e)} ${n}`, e === "protetto" ? "ok" : e === "bloccato" ? "errore" : "attenzione")).join("")}</span>`, x => `<span class="sotto">${esc(x.ultimo.slice(0, 16))}</span>`])
      + tabella(t("rilevati.connessi"), r.programmi_connessi, [x => nome(x.servizio.nome, x.processo), x => esc(t("rilevati.n_connessioni", {n: x.connessioni})), x => scelta(x.servizio.politica) || etichetta(t("rilevati.locale"))])
      + tabella(t("rilevati.connessioni"), r.connessioni, [x => nome(x.servizio, x.host), x => esc(x.processo), x => esc(t("rilevati.n_connessioni", {n: x.connessioni})), x => scelta(x.politica)])
      + tabella(t("rilevati.dns"), r.dns, [x => nome(x.servizio, x.host), x => esc(x.cosa), x => scelta(x.politica)])
      || `<span class="sfumato">${esc(t("rilevati.rete.niente"))}</span>`) + (r.cache_dns_vuota ? `<p class="aiuto">${esc(t("rilevati.dns_vuoto"))}</p>` : "");
  });
  disegna();
});

// ---- Attività
DISEGNA.attivita = el => {
  el.innerHTML = `<section class="scheda"><div class="tabella"><table><caption class="vh">${esc(t("attivita.titolo"))}</caption><thead><tr>
    ${["ora", "servizio", "esito", "dettagli"].map(c => `<th scope="col">${esc(t(`attivita.colonna.${c}`))}</th>`).join("")}</tr></thead><tbody id="registro"></tbody></table></div></section>`;
  registro();
};
AGGIORNA.attivita = () => registro();
const registro = prova(async () => {
  const righe = await api("/api/registro?n=300"), corpo = $("#registro");
  if (!corpo) return;
  corpo.innerHTML = righe.length ? righe.map(v => {
    const ev = v.evento || "", tono = ev === "mascherata" ? "ok" : /BLOCC|bloccato/.test(ev) ? "errore" : /NON|nessun/.test(ev) ? "attenzione" : "";
    let d = Object.entries(v.sostituzioni || {}).map(([k, n]) => etichetta(`${tipoDato(k)} ${n}`)).join("");
    if (v.ripristinati) d += etichetta(t("attivita.ripristinati", {n: v.ripristinati}));
    if (v.VALORI_IN_CHIARO) d += etichetta(t("attivita.in_chiaro", {n: v.VALORI_IN_CHIARO}), "errore");
    if (v.ms !== undefined) d += etichetta(`${v.ms} ms`);
    const struttura = v.struttura ? `<details><summary>${esc(t("attivita.struttura"))}</summary><code>${esc(JSON.stringify(v.struttura))}</code></details>` : "";
    return `<tr><td class="sotto">${esc((v.ora || "").slice(5, 16))}</td><td>${esc(v.servizio || "")}</td>
      <td>${etichetta(tSe("evento." + ev, ev), tono)}<div class="sotto">${esc(v.percorso || "")}${v.via ? " · " + esc(tSe("via." + v.via, v.via)) : ""}</div></td>
      <td><span class="etichette">${d}</span>${struttura}</td></tr>`;
  }).join("") : `<tr><td colspan="4" class="vuoto">${esc(t("attivita.vuoto"))}</td></tr>`;
});

// ---- Archivio
// Si cerca per segnaposto o per valore vero (la ricerca guarda i valori anche quando restano nascosti), si elimina una voce,
// un gruppo scelto o ciò che non si usa da tempo. I numeri eliminati non vengono riusati.
DISEGNA.archivio = el => {
  const opzioni = (voci, scelta) => voci.map(([v, n]) => `<option value="${esc(v)}"${String(v) === String(scelta) ? " selected" : ""}>${esc(n)}</option>`).join("");
  el.innerHTML = `<section class="scheda">
      <div class="dentro">
        <div class="riga"><input type="search" id="archCerca" class="spazio" placeholder="${esc(t("archivio.cerca"))}" aria-label="${esc(t("archivio.cerca"))}">
          <select id="archTipo" aria-label="${esc(t("archivio.tipo"))}"></select>
          <select id="archOrdine" aria-label="${esc(t("archivio.ordine"))}">${opzioni(["recenti", "usati", "fermi", "tipo"].map(v => [v, t(`archivio.ordine.${v}`)]), "recenti")}</select>
          <label class="riga">${levetta("inChiaro", t("archivio.mostra"))}<span>${esc(t("archivio.mostra"))}</span></label></div>
        <div class="riga"><span class="sfumato piccolo" id="archConta" aria-live="polite"></span><span class="spazio"></span>
          <button class="bottone pericolo" id="archElimina" disabled>${esc(t("archivio.elimina_scelte"))}</button></div>
      </div>
      <div class="tabella"><table><caption class="vh">${esc(t("archivio.titolo"))}</caption><thead><tr>
        <th scope="col"><input type="checkbox" id="archTutte" aria-label="${esc(t("archivio.scegli_tutte"))}"></th>
        ${["segnaposto", "valore", "creato", "usato"].map(c => `<th scope="col">${esc(t(`archivio.colonna.${c}`))}</th>`).join("")}</tr></thead><tbody id="tabArchivio"></tbody></table></div>
    </section>
    <section class="scheda" aria-labelledby="pulTitolo">
      <div class="dentro"><h2 id="pulTitolo">${esc(t("archivio.pulizia"))}</h2><p>${esc(t("archivio.pulizia.sotto"))}</p></div>
      ${riga(t("archivio.pulizia.fermi"), esc(t("archivio.pulizia.fermi.sotto")), `<select id="pulGiorni" aria-label="${esc(t("archivio.pulizia.giorni"))}">${opzioni([30, 90, 180, 365].map(g => [g, t("archivio.giorni", {n: g})]), 90)}</select><button class="bottone" id="pulFermi">${esc(t("archivio.pulizia.elimina"))}</button>`)}
      ${riga(t("archivio.pulizia.da_sola"), esc(t("archivio.pulizia.da_sola.sotto")), `<select id="pulDaSola" aria-label="${esc(t("archivio.pulizia.da_sola"))}">${opzioni([[0, t("archivio.pulizia.mai")], ...[90, 180, 365].map(g => [g, t("archivio.pulizia.dopo", {n: g})])], 0)}</select>`)}
      ${riga(t("archivio.svuota.titolo_breve"), esc(t("archivio.svuota.testo")), `<button class="bottone pericolo" id="svuota">${esc(t("archivio.svuota"))}</button>`)}
    </section>`;
  let attesa;
  const scelte = () => $$("#tabArchivio input:checked").map(x => x.value);
  const aggiornaScelte = () => { const n = scelte().length; $("#archElimina").disabled = !n; $("#archElimina").textContent = n ? t("archivio.elimina_n", {n}) : t("archivio.elimina_scelte"); };
  const leggi = prova(async () => {
    const a = await api("/api/archivio", {in_chiaro: $("#inChiaro").checked, cerca: $("#archCerca").value, etichetta: $("#archTipo").value, ordine: $("#archOrdine").value});
    const tipo = $("#archTipo").value;
    $("#archTipo").innerHTML = opzioni([["", t("archivio.tipo.tutti", {n: num(a.totale)})], ...Object.entries(a.per_tipo).sort((x, y) => y[1] - x[1]).map(([k, n]) => [k, `${tipoDato(k)} (${num(n)})`])], tipo);
    $("#archConta").innerHTML = (a.totale ? esc(t("archivio.conta", {mostrate: num(a.voci.length), trovate: num(a.trovate), totale: num(a.totale)})) : esc(t("archivio.vuoto")))
      + (a.cifrato ? " " + etichetta(t("archivio.cifrato"), "ok") : "");
    $("#tabArchivio").innerHTML = a.voci.length ? a.voci.map(v => `<tr><td><input type="checkbox" value="${esc(v.segnaposto)}" aria-label="${esc(t("archivio.scegli", {segnaposto: v.segnaposto}))}"></td>
        <td><span class="segnaposto">${esc(v.segnaposto)}</span></td><td>${esc(v.valore)}</td><td class="sotto">${esc(v.creato)}</td><td class="sotto">${esc(v.usato)}</td></tr>`).join("")
      : `<tr><td colspan="5" class="vuoto">${esc((a.totale ? t("archivio.nessuna_trovata") : t("archivio.vuoto")))}</td></tr>`;
    $("#archTutte").checked = false;
    $$("#tabArchivio input").forEach(x => x.onchange = aggiornaScelte);
    aggiornaScelte();
  });
  $("#archCerca").oninput = () => { clearTimeout(attesa); attesa = setTimeout(leggi, 250); };
  for (const id of ["archTipo", "archOrdine", "inChiaro"]) $(`#${id}`).onchange = leggi;
  $("#archTutte").onchange = e => { $$("#tabArchivio input").forEach(x => { x.checked = e.target.checked; }); aggiornaScelte(); };
  const elimina = async (dati, titolo) => {
    const quante = (await api("/api/archivio/elimina", {...dati, solo_conta: true})).eliminate;
    if (!quante) { avvisa(t("archivio.elimina.niente")); return; }
    if (!await conferma(titolo, t("archivio.elimina.testo", {n: num(quante)}), t("archivio.elimina.si", {n: num(quante)}))) return;
    const r = await api("/api/archivio/elimina", dati);
    avvisa(t("archivio.eliminate", {n: num(r.eliminate)}));
    leggi(); leggiStato();
  };
  $("#archElimina").onclick = prova(() => elimina({segnaposto: scelte()}, t("archivio.elimina.titolo")));
  $("#pulFermi").onclick = prova(() => elimina({fermi_da_giorni: +$("#pulGiorni").value, etichetta: $("#archTipo").value}, t("archivio.pulizia.titolo", {n: $("#pulGiorni").value})));
  api("/api/impostazioni").then(i => { $("#pulDaSola").value = String(i.archivio_giorni || 0); }).catch(() => {});
  $("#pulDaSola").onchange = prova(e => salva({archivio_giorni: +e.target.value}));
  $("#svuota").onclick = prova(async () => {
    if (!await conferma(t("archivio.svuota.titolo"), t("archivio.svuota.testo"), t("archivio.svuota"))) return;
    await api("/api/archivio/svuota", {}); leggi(); leggiStato();
  });
  leggi();
};

// ------------------------------------------------------------------ 4. avvio

function applicaTema(tema) {
  if (tema === "chiaro" || tema === "scuro") document.documentElement.dataset.tema = tema; else delete document.documentElement.dataset.tema;
  try { localStorage.setItem("tema", tema); } catch { /* memoria del browser non disponibile: pazienza */ }
}
function cambiaVista(avanzata) {
  vista = avanzata ? "avanzata" : "semplice";
  applicaVista();
  api("/api/impostazioni", {vista}).catch(() => {});
  mostra(false);
}

// l'estensione, se c'è in questo browser, si presenta con un messaggio alla pagina
window.addEventListener("message", e => {
  const d = e.data;
  if (e.source !== window || e.origin !== location.origin || !d || d.msp_pii !== "estensione") return;
  estensione = d;
  disegnaEstensione(); canali();
  if (d.appena) avvisa(t(d.ok ? "browser.collegata_ora" : "browser.collegata_senza_risposta"), !d.ok);
});

async function avvia() {
  try { applicaTema(localStorage.getItem("tema") || "auto"); } catch { /* vedi sopra */ }
  const lingue = await api("/api/lingue");
  LINGUA = lingue.attiva;
  document.documentElement.lang = LINGUA;
  const leggi = async codice => (await fetch(`/locales/${codice}.json`)).json();
  [TESTI, RISERVA] = await Promise.all([leggi(LINGUA), LINGUA === "it" ? Promise.resolve({}) : leggi("it")]);
  const i = await api("/api/impostazioni");
  vista = i.vista === "avanzata" ? "avanzata" : "semplice";
  applicaTema(i.tema || "auto");
  disegnaMenu(); applicaVista();
  $("#avanzata").onchange = e => cambiaVista(e.target.checked);
  addEventListener("hashchange", () => mostra());
  mostra(false);
  window.postMessage({msp_pii: "ci sei?"}, location.origin);
  await leggiStato();
  setInterval(() => { leggiStato(); if (aperta.id === "inizio") canali(); }, 3000);
}
avvia().catch(e => { $("#contenuto").textContent = "Omissis: " + e.message; });
