// Omissis — servizio in background dell'estensione: parla con il programma sul PC (solo
// 127.0.0.1), tiene aggiornate le politiche dei servizi e applica i blocchi.
importScripts('defaults.js');

const PORT = 8765;
const VERSION = chrome.runtime.getManifest().version;
const BUILD = globalThis.MSP_BUILD || '';   // l'impronta dei file con cui questa copia e' partita (la scrive build_extension.py)
let lastCheck = 0;

const conf = () => chrome.storage.local.get({token: '', port: PORT, suspended: false, notices: true});

// Il browser e la sua versione: il programma li annota accanto a ogni messaggio protetto, per sapere con quali versioni funziona.
let CLIENT = '';
(async () => {
  try {
    const d = navigator.userAgentData;
    const brands = (d && (await d.getHighEntropyValues(['fullVersionList'])).fullVersionList) || (d && d.brands) || [];
    const m = brands.find(x => !/chromium|not.?a.?brand/i.test(x.brand)) || brands.find(x => /chromium/i.test(x.brand));
    CLIENT = m ? `${m.brand} ${m.version}` : '';
  } catch (e) { /* resta vuoto: il programma lo segna come sconosciuto */ }
})();

async function engine(action, data, timeout) {
  const c = await conf();
  if (!c.token) throw new Error('not_paired');
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeout || 90000);
  try {
    const r = await fetch(`http://127.0.0.1:${c.port}/bridge/${action}`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': c.token},
      body: JSON.stringify({...(data || {}), client: CLIENT}), signal: ctl.signal, cache: 'no-store'});
    if (!r.ok) throw new Error(r.status === 403 ? 'invalid_code' : 'error ' + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}

// Le pagine dei servizi caricano spesso strumenti di statistiche e di registrazione della sessione di altre aziende, che
// leggono la pagina mentre si scrive: prima dell'Invio, quando nella casella ci sono ancora i valori veri (visto dal vivo
// il 17/11/2026: un indirizzo email finito nelle statistiche di Genspark, un nome e un telefono in quelle di Manus).
// Sulle pagine dei servizi protetti queste richieste non partono. Nessuno di questi strumenti serve al servizio per rispondere.
const TRACKERS = ['google-analytics.com', 'analytics.google.com', 'stats.g.doubleclick.net', 'amplitude.com',
  'applicationinsights.azure.com', 'monitor.azure.com', 'clarity.ms', 'hotjar.com', 'hotjar.io', 'fullstory.com',
  'logrocket.io', 'logrocket.com', 'lr-ingest.io', 'lr-ingest.com', 'mixpanel.com', 'segment.io', 'segment.com',
  'posthog.com', 'heapanalytics.com', 'browser-intake-datadoghq.com', 'browser-intake-datadoghq.eu', 'sentry.io',
  'smartlook.com', 'mouseflow.com', 'gator.volces.com', 'alb.reddit.com', 'px.ads.linkedin.com', 'analytics.tiktok.com',
  'bat.bing.com', 'ct.pinterest.com'];
// Le statistiche di Google spesso passano da un indirizzo del sito stesso (visto il 17/11/2026: t.genspark.ai), e cercano da
// sole gli indirizzi email nella pagina, compresi i valori veri che Omissis rimette nei messaggi gia' inviati.
// Si riconoscono dal percorso, uguale su ogni dominio.
const TRACKER_PATHS = ['/g/collect?', '/j/collect?', '/mp/collect?'];

// ---------------------------------------------------------------- politiche e blocchi
// Gli aggiornamenti delle regole vanno uno alla volta: due insieme leggono lo stesso elenco e aggiungono la stessa regola due
// volte, il browser rifiuta e l'estensione si crederebbe scollegata dal programma.
let inLine = Promise.resolve();
function rules(status) {
  const turn = inLine.then(() => applyRules(status));
  inLine = turn.catch(() => {});
  return turn;
}

async function applyRules(status) {
  const old_ones = (await chrome.declarativeNetRequest.getDynamicRules()).map(r => r.id);
  const new_ones = [];
  let id = 1;
  const {suspended} = await chrome.storage.local.get('suspended');
  const protectedOnes = status.services.filter(s => s.policy === 'protect' && (s.readable || s.box) && (!suspended || s.locked)).flatMap(s => s.domains);
  if (protectedOnes.length) {
    new_ones.push({id: id++, priority: 1, condition: {requestDomains: TRACKERS, initiatorDomains: protectedOnes,
      resourceTypes: ['xmlhttprequest', 'ping', 'script', 'image', 'websocket', 'sub_frame', 'other']}, action: {type: 'block'}});
    for (const path of TRACKER_PATHS) {
      new_ones.push({id: id++, priority: 1, condition: {urlFilter: path, initiatorDomains: protectedOnes,
        resourceTypes: ['xmlhttprequest', 'ping', 'image', 'other']}, action: {type: 'block'}});
    }
  }
  for (const s of status.services) {
    if (s.policy !== 'block') continue;
    if (s.radar) {   // servizio del radar: sui suoi siti non abbiamo accesso, quindi niente pagina di avviso, solo il blocco
      new_ones.push({id: id++, priority: 1, condition: {requestDomains: s.domains,
        resourceTypes: ['main_frame', 'sub_frame', 'xmlhttprequest', 'websocket', 'script', 'ping', 'media', 'image', 'font', 'stylesheet', 'other']},
        action: {type: 'block'}});
      continue;
    }
    new_ones.push({id: id++, priority: 2, condition: {requestDomains: s.domains, resourceTypes: ['main_frame']},
      action: {type: 'redirect', redirect: {extensionPath: '/blocked.html?s=' + encodeURIComponent(s.name) + '&h=' + encodeURIComponent(s.domains[0])}}});
    new_ones.push({id: id++, priority: 1, condition: {requestDomains: s.domains,
      resourceTypes: ['sub_frame', 'xmlhttprequest', 'websocket', 'script', 'ping', 'media', 'image', 'font', 'stylesheet', 'other']},
      action: {type: 'block'}});
  }
  await chrome.declarativeNetRequest.updateDynamicRules({removeRuleIds: old_ones, addRules: new_ones});
}

// Le frasi nella lingua del browser, lette dal file dell'estensione (qui il browser non le traduce da solo).
let phrases = null;
async function T(key) {
  if (!phrases) {
    const read = async language => (await fetch(chrome.runtime.getURL(`_locales/${language}/messages.json`))).json();
    try { phrases = await read((chrome.i18n.getUILanguage() || 'en').split('-')[0]); } catch (e) { phrases = await read('en'); }
  }
  return (phrases[key] || {}).message || key;
}

async function signal() {
  const {token, suspended, health} = await chrome.storage.local.get(['token', 'suspended', 'health']);
  const fault = !token || !(health && health.ok);
  await chrome.action.setBadgeBackgroundColor({color: fault ? '#c50f1f' : suspended ? '#8f8f8f' : '#0a7a33'});
  await chrome.action.setBadgeText({text: fault ? '!' : suspended ? 'off' : ''});
  await chrome.action.setTitle({title: await T(!token ? 'icon_not_connected' : fault ? 'icon_not_responding' : suspended ? 'suspended_icon' : 'active_icon')});
}

// Caricata da una cartella, l'estensione resta quella che il browser ha letto quel giorno: se il programma si aggiorna e
// nella cartella i file cambiano, qui continua a girare il codice di prima, che il programma nuovo puo' non capire piu'.
// build.json si legge dal disco ogni volta: se porta un'impronta diversa dalla nostra, l'estensione si ricarica da sola.
// Installata da uno store, i file cambiano solo insieme all'estensione e le due impronte restano uguali.
async function outdated() {
  let disk;
  try { disk = await (await fetch(chrome.runtime.getURL('build.json'), {cache: 'no-store'})).json(); } catch (e) { return false; }
  if (!disk || !disk.build || disk.test || disk.build === BUILD) return false;   // alla copia di prova non si passa mai da soli
  const {reloaded} = await chrome.storage.local.get('reloaded');
  if (reloaded === disk.build) return false;   // gia' provato per questi file: niente giro di ricariche
  await chrome.storage.local.set({reloaded: disk.build});
  chrome.runtime.reload();
  return true;
}

async function refresh(force) {
  if (!force && Date.now() - lastCheck < 15000) return;
  lastCheck = Date.now();
  if (await outdated()) return;
  let health;
  try {
    const r = await engine('status', {version: VERSION}, 5000);
    const fresh = {services: r.services, restore: !!r.restore, block_files: !!r.block_files, box: r.box !== false,
      attachments: r.attachments !== false};
    const {status} = await chrome.storage.local.get('status');
    if (JSON.stringify(status) !== JSON.stringify(fresh)) await chrome.storage.local.set({status: fresh});
    await rules(fresh);
    health = {ok: true, when: Date.now()};
  } catch (e) {
    health = {ok: false, when: Date.now(), reason: String((e && e.message) || e)};
  }
  await chrome.storage.local.set({health});
  await signal();
}

// ---------------------------------------------------------------- conteggi per scheda
async function count(card, r) {
  if (!card || card.id == null) return;
  const key = 'c' + card.id;
  const c = (await chrome.storage.session.get(key))[key] || {messages: 0, replacements: 0, blocked: 0};
  if (r.action === 'replace') { c.messages++; c.replacements += r.replacements || 0; }
  else if (r.action === 'block') c.blocked++;
  else return;
  await chrome.storage.session.set({[key]: c});
  if (c.replacements) {
    chrome.action.setBadgeBackgroundColor({tabId: card.id, color: '#107a6b'});
    chrome.action.setBadgeText({tabId: card.id, text: String(c.replacements)});
  }
}
chrome.tabs.onRemoved.addListener(id => chrome.storage.session.remove('c' + id));

function find(status, host) {
  for (const s of (status && status.services) || []) if (s.domains.some(d => host === d || host.endsWith('.' + d))) return s;
  return null;
}

// La sospensione scelta dalla finestrella non vale sui servizi la cui regola e' imposta da chi amministra il PC:
// si guarda il servizio a cui va la richiesta e quello della pagina che la fa.
async function paused(c, m, sender) {
  if (!c.suspended) return false;
  const {status} = await chrome.storage.local.get('status');
  const hosts = m && m.host ? [String(m.host)] : [];
  for (const u of [m && m.url, sender && sender.tab && sender.tab.url]) { try { hosts.push(new URL(u).hostname); } catch (e) { /* senza indirizzo */ } }
  return !hosts.some(h => { const s = find(status || MSP_DEFAULTS, h); return !!(s && s.locked); });
}

// ---------------------------------------------------------------- messaggi
// vero se il messaggio viene da una pagina dell'estensione stessa (la finestrella), non da un sito
const internal = sender => !sender.tab || String(sender.url || '').startsWith(chrome.runtime.getURL(''));

async function handle(m, sender) {
  switch (m && m.t) {
    case 'request': {
      const c = await conf();
      if (await paused(c, m, sender)) return {action: 'passthrough'};
      if (!c.token) return {action: 'block', reason: 'not_paired'};
      let r;
      try { r = await engine('request', m); } catch (e) {
        refresh(true);
        r = {action: 'block', reason: e && e.message === 'invalid_code' ? 'not_paired' : 'engine'};
      }
      count(sender.tab, r);
      return r;
    }
    case 'text': {   // la casella di scrittura: stesse regole di una richiesta
      const c = await conf();
      if (await paused(c, m, sender)) return {action: 'passthrough'};
      if (!c.token) return {action: 'block', reason: 'not_paired'};
      try { return await engine('text', m); } catch (e) { return {action: 'block', reason: 'engine'}; }
    }
    case 'attachment': {   // un file che sta per essere allegato: torna la copia anonimizzata
      const c = await conf();
      if (await paused(c, m, sender)) return {action: 'passthrough'};
      if (!c.token) return {action: 'block', reason: 'not_paired'};
      try {
        const r = await engine('attachment', m, 300000);
        if (r.action === 'replace') count(sender.tab, {action: 'replace', replacements: r.replacements});
        return r;
      } catch (e) { return {action: 'block', reason: 'engine'}; }
    }
    case 'open_up': case 'chunk': case 'whole': case 'values': case 'websocket':
      return engine(m.t, m, 30000);
    case 'visit':
      await refresh(false);
      return engine('visit', {host: String(m.host || '')}, 5000).catch(() => ({}));
    case 'connect': {   // dal pannello del programma (stessa macchina) oppure a mano dalla finestrella
      const fromPanel = !!(sender.tab && sender.url && /^http:\/\/(127\.0\.0\.1|localhost):8766\//.test(sender.url));
      if (!fromPanel && !internal(sender)) return {ok: false};
      await chrome.storage.local.set({token: String(m.token || '').trim(), port: Number(m.port) || PORT});
      await refresh(true);
      const {health} = await chrome.storage.local.get('health');
      return {ok: !!(health && health.ok), reason: health && health.reason, version: VERSION};
    }
    case 'present': {
      await refresh(false);   // chi chiede (il pannello, la pagina di benvenuto) vuole lo stato di adesso, non quello di un minuto fa
      const {token, health} = await chrome.storage.local.get(['token', 'health']);
      return {version: VERSION, build: BUILD, connected: !!token, ok: !!(health && health.ok)};
    }
    case 'configure': {
      if (!internal(sender)) return {};
      const new_ones = {};
      if ('suspended' in m) new_ones.suspended = !!m.suspended;
      if ('notices' in m) new_ones.notices = !!m.notices;
      await chrome.storage.local.set(new_ones);
      if ('suspended' in m) refresh(true);   // le statistiche dei siti tornano libere solo mentre la protezione e' sospesa
      await signal();
      return {};
    }
    case 'win': {
      if (!internal(sender)) return {};
      await refresh(true);
      const d = await chrome.storage.local.get(['token', 'port', 'health', 'status', 'suspended', 'notices']);
      const [card] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
      let host = '';
      try { host = new URL(card.url).hostname; } catch (e) { /* scheda senza indirizzo leggibile */ }
      const s = find(d.status || MSP_DEFAULTS, host);
      const key = 'c' + (card ? card.id : '');
      return {version: VERSION, build: BUILD, connected: !!d.token, health: d.health || {ok: false}, suspended: !!d.suspended, notices: d.notices !== false,
        restore: !!(d.status && d.status.restore), host, service: s && {name: s.name, policy: s.policy, readable: s.readable, box: !!s.box, locked: !!s.locked},
        counts: (await chrome.storage.session.get(key))[key] || null};
    }
    case 'blocked':
      return engine('visit', {host: String(m.host || '')}, 5000).catch(() => ({}));
  }
  return {};
}

chrome.runtime.onMessage.addListener((m, sender, respond) => {
  handle(m, sender).then(respond, () => respond(m && m.t === 'request' ? {action: 'block', reason: 'extension'} : {}));
  return true;
});

// Appena installata, una pagina dice che cosa manca perche' funzioni: il collegamento al programma sul PC. Una volta sola,
// non dopo una ricarica o un aggiornamento, e mai dalla copia di prova.
async function greet(details) {
  if (!details || details.reason !== 'install') return false;
  const {token, welcomed} = await chrome.storage.local.get(['token', 'welcomed']);
  if (token || welcomed) return false;
  try { if ((await (await fetch(chrome.runtime.getURL('build.json'), {cache: 'no-store'})).json()).test) return false; } catch (e) { /* senza impronta si saluta lo stesso */ }
  await chrome.storage.local.set({welcomed: true});
  await chrome.tabs.create({url: chrome.runtime.getURL('welcome.html')});
  return true;
}

// Le schede aperte prima che l'estensione si accendesse (appena installata, o riaccesa) non hanno la protezione: il
// browser la mette solo nelle pagine caricate dopo. Visto dal vivo il 17/11/2026: su una scheda cosi' il messaggio e'
// partito in chiaro. Una volta per ogni accensione, la protezione viene messa nelle schede dei servizi che non l'hanno.
// Dove c'e' una copia vecchia (estensione aggiornata) non si aggiunge nulla: quella copia blocca e chiede di ricaricare.
async function cover() {
  try {
    if ((await chrome.storage.session.get('covered')).covered) return;
    await chrome.storage.session.set({covered: true});
    const matches = chrome.runtime.getManifest().content_scripts[0].matches;
    for (const card of await chrome.tabs.query({url: matches})) {
      try {
        const target = {tabId: card.id, allFrames: true};
        const [probe] = await chrome.scripting.executeScript({target: {tabId: card.id}, func: () => !!globalThis.MSP_COPY});
        if (probe && probe.result) continue;
        await chrome.scripting.executeScript({target, files: ['page.js'], world: 'MAIN', injectImmediately: true});
        await chrome.scripting.executeScript({target, files: ['defaults.js', 'channel.js', 'content.js'], injectImmediately: true});
      } catch (e) { /* scheda chiusa nel frattempo, o pagina del browser */ }
    }
    for (const card of await chrome.tabs.query({url: chrome.runtime.getManifest().content_scripts[2].matches})) {
      try {
        const [probe] = await chrome.scripting.executeScript({target: {tabId: card.id}, func: () => !!globalThis.MSP_COPY});
        if (probe && probe.result) continue;
        await chrome.scripting.executeScript({target: {tabId: card.id}, files: ['defaults.js', 'content.js'], injectImmediately: true});
      } catch (e) { /* scheda chiusa nel frattempo, o pagina del browser */ }
    }
  } catch (e) { /* senza il permesso: le schede si proteggono alla prossima ricarica */ }
}
cover();

chrome.runtime.onInstalled.addListener(details => { chrome.alarms.create('status', {periodInMinutes: 1}); refresh(true); greet(details); });
chrome.runtime.onStartup.addListener(() => { chrome.alarms.create('status', {periodInMinutes: 1}); refresh(true); });
chrome.alarms.onAlarm.addListener(a => { if (a.name === 'status') refresh(true); });
