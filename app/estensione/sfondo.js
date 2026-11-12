// Omissis — servizio in background dell'estensione: parla con il programma sul PC (solo
// 127.0.0.1), tiene aggiornate le politiche dei servizi e applica i blocchi.
importScripts('predefiniti.js');

const PORTA = 8765;
const VERSIONE = chrome.runtime.getManifest().version;
let ultimoControllo = 0;

const conf = () => chrome.storage.local.get({token: '', porta: PORTA, sospesa: false, avvisi: true});

async function motore(azione, dati, attesa) {
  const c = await conf();
  if (!c.token) throw new Error('non collegata');
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), attesa || 90000);
  try {
    const r = await fetch(`http://127.0.0.1:${c.porta}/ponte/${azione}`, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': c.token},
      body: JSON.stringify(dati || {}), signal: ctl.signal, cache: 'no-store'});
    if (!r.ok) throw new Error(r.status === 403 ? 'codice non valido' : 'errore ' + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}

// ---------------------------------------------------------------- politiche e blocchi
async function regole(stato) {
  const vecchie = (await chrome.declarativeNetRequest.getDynamicRules()).map(r => r.id);
  const nuove = [];
  let id = 1;
  for (const s of stato.servizi) {
    if (s.politica !== 'blocca') continue;
    if (s.radar) {   // servizio del radar: sui suoi siti non abbiamo accesso, quindi niente pagina di avviso, solo il blocco
      nuove.push({id: id++, priority: 1, condition: {requestDomains: s.domini,
        resourceTypes: ['main_frame', 'sub_frame', 'xmlhttprequest', 'websocket', 'script', 'ping', 'media', 'image', 'font', 'stylesheet', 'other']},
        action: {type: 'block'}});
      continue;
    }
    nuove.push({id: id++, priority: 2, condition: {requestDomains: s.domini, resourceTypes: ['main_frame']},
      action: {type: 'redirect', redirect: {extensionPath: '/bloccato.html?s=' + encodeURIComponent(s.nome) + '&h=' + encodeURIComponent(s.domini[0])}}});
    nuove.push({id: id++, priority: 1, condition: {requestDomains: s.domini,
      resourceTypes: ['sub_frame', 'xmlhttprequest', 'websocket', 'script', 'ping', 'media', 'image', 'font', 'stylesheet', 'other']},
      action: {type: 'block'}});
  }
  await chrome.declarativeNetRequest.updateDynamicRules({removeRuleIds: vecchie, addRules: nuove});
}

// Le frasi nella lingua del browser, lette dal file dell'estensione (qui il browser non le traduce da solo).
let frasi = null;
async function T(chiave) {
  if (!frasi) {
    const leggi = async lingua => (await fetch(chrome.runtime.getURL(`_locales/${lingua}/messages.json`))).json();
    try { frasi = await leggi((chrome.i18n.getUILanguage() || 'en').split('-')[0]); } catch (e) { frasi = await leggi('en'); }
  }
  return (frasi[chiave] || {}).message || chiave;
}

async function segnale() {
  const {token, sospesa, salute} = await chrome.storage.local.get(['token', 'sospesa', 'salute']);
  const guasto = !token || !(salute && salute.ok);
  await chrome.action.setBadgeBackgroundColor({color: guasto ? '#c50f1f' : sospesa ? '#8f8f8f' : '#0a7a33'});
  await chrome.action.setBadgeText({text: guasto ? '!' : sospesa ? 'off' : ''});
  await chrome.action.setTitle({title: await T(!token ? 'icona_non_collegata' : guasto ? 'icona_non_risponde' : sospesa ? 'icona_sospesa' : 'icona_attiva')});
}

async function aggiorna(forza) {
  if (!forza && Date.now() - ultimoControllo < 15000) return;
  ultimoControllo = Date.now();
  let salute;
  try {
    const r = await motore('stato', {versione: VERSIONE}, 5000);
    const nuovo = {servizi: r.servizi, ripristina: !!r.ripristina, blocca_file: !!r.blocca_file, casella: r.casella !== false};
    const {stato} = await chrome.storage.local.get('stato');
    if (JSON.stringify(stato) !== JSON.stringify(nuovo)) await chrome.storage.local.set({stato: nuovo});
    await regole(nuovo);
    salute = {ok: true, quando: Date.now()};
  } catch (e) {
    salute = {ok: false, quando: Date.now(), motivo: String((e && e.message) || e)};
  }
  await chrome.storage.local.set({salute});
  await segnale();
}

// ---------------------------------------------------------------- conteggi per scheda
async function conta(scheda, r) {
  if (!scheda || scheda.id == null) return;
  const chiave = 'c' + scheda.id;
  const c = (await chrome.storage.session.get(chiave))[chiave] || {messaggi: 0, sostituzioni: 0, bloccate: 0};
  if (r.azione === 'sostituisci') { c.messaggi++; c.sostituzioni += r.sostituzioni || 0; }
  else if (r.azione === 'blocca') c.bloccate++;
  else return;
  await chrome.storage.session.set({[chiave]: c});
  if (c.sostituzioni) {
    chrome.action.setBadgeBackgroundColor({tabId: scheda.id, color: '#107a6b'});
    chrome.action.setBadgeText({tabId: scheda.id, text: String(c.sostituzioni)});
  }
}
chrome.tabs.onRemoved.addListener(id => chrome.storage.session.remove('c' + id));

function trova(stato, host) {
  for (const s of (stato && stato.servizi) || []) if (s.domini.some(d => host === d || host.endsWith('.' + d))) return s;
  return null;
}

// ---------------------------------------------------------------- messaggi
// vero se il messaggio viene da una pagina dell'estensione stessa (la finestrella), non da un sito
const interno = mitt => !mitt.tab || String(mitt.url || '').startsWith(chrome.runtime.getURL(''));

async function gestisci(m, mitt) {
  switch (m && m.t) {
    case 'richiesta': {
      const c = await conf();
      if (c.sospesa) return {azione: 'passa'};
      if (!c.token) return {azione: 'blocca', motivo: 'non collegata'};
      let r;
      try { r = await motore('richiesta', m); } catch (e) {
        aggiorna(true);
        r = {azione: 'blocca', motivo: e && e.message === 'codice non valido' ? 'non collegata' : 'motore'};
      }
      conta(mitt.tab, r);
      return r;
    }
    case 'testo': {   // la casella di scrittura: stesse regole di una richiesta
      const c = await conf();
      if (c.sospesa) return {azione: 'passa'};
      if (!c.token) return {azione: 'blocca', motivo: 'non collegata'};
      try { return await motore('testo', m); } catch (e) { return {azione: 'blocca', motivo: 'motore'}; }
    }
    case 'apri': case 'pezzo': case 'intera': case 'valori': case 'websocket':
      return motore(m.t, m, 30000);
    case 'visita':
      await aggiorna(false);
      return motore('visita', {host: String(m.host || '')}, 5000).catch(() => ({}));
    case 'collega': {   // dal pannello del programma (stessa macchina) oppure a mano dalla finestrella
      const daPannello = !!(mitt.tab && mitt.url && /^http:\/\/(127\.0\.0\.1|localhost):8766\//.test(mitt.url));
      if (!daPannello && !interno(mitt)) return {ok: false};
      await chrome.storage.local.set({token: String(m.token || '').trim(), porta: Number(m.porta) || PORTA});
      await aggiorna(true);
      const {salute} = await chrome.storage.local.get('salute');
      return {ok: !!(salute && salute.ok), motivo: salute && salute.motivo, versione: VERSIONE};
    }
    case 'presente': {
      const {token, salute} = await chrome.storage.local.get(['token', 'salute']);
      return {versione: VERSIONE, collegata: !!token, ok: !!(salute && salute.ok)};
    }
    case 'imposta': {
      if (!interno(mitt)) return {};
      const nuove = {};
      if ('sospesa' in m) nuove.sospesa = !!m.sospesa;
      if ('avvisi' in m) nuove.avvisi = !!m.avvisi;
      await chrome.storage.local.set(nuove);
      await segnale();
      return {};
    }
    case 'finestra': {
      if (!interno(mitt)) return {};
      await aggiorna(true);
      const d = await chrome.storage.local.get(['token', 'porta', 'salute', 'stato', 'sospesa', 'avvisi']);
      const [scheda] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
      let host = '';
      try { host = new URL(scheda.url).hostname; } catch (e) { /* scheda senza indirizzo leggibile */ }
      const s = trova(d.stato || MSP_PREDEFINITI, host);
      const chiave = 'c' + (scheda ? scheda.id : '');
      return {versione: VERSIONE, collegata: !!d.token, salute: d.salute || {ok: false}, sospesa: !!d.sospesa, avvisi: d.avvisi !== false,
        ripristina: !!(d.stato && d.stato.ripristina), host, servizio: s && {nome: s.nome, politica: s.politica, leggibile: s.leggibile},
        conteggi: (await chrome.storage.session.get(chiave))[chiave] || null};
    }
    case 'bloccato':
      return motore('visita', {host: String(m.host || '')}, 5000).catch(() => ({}));
  }
  return {};
}

chrome.runtime.onMessage.addListener((m, mitt, rispondi) => {
  gestisci(m, mitt).then(rispondi, () => rispondi(m && m.t === 'richiesta' ? {azione: 'blocca', motivo: 'estensione'} : {}));
  return true;
});

chrome.runtime.onInstalled.addListener(() => { chrome.alarms.create('stato', {periodInMinutes: 1}); aggiorna(true); });
chrome.runtime.onStartup.addListener(() => { chrome.alarms.create('stato', {periodInMinutes: 1}); aggiorna(true); });
chrome.alarms.onAlarm.addListener(a => { if (a.name === 'stato') aggiorna(true); });
