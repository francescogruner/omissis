// Omissis — parte dell'estensione accanto alla pagina (mondo isolato: il sito non la vede).
// Fa da tramite tra pagina.js e il programma sul PC, mostra gli avvisi, segnala la visita al
// servizio (Shadow AI) e rimette i valori veri dove nella pagina compare un segnaposto.
(() => {
  'use strict';
  const RX = /\[[A-Z][A-Z_]{1,22}_\d{1,7}\]/g;
  const cima = window.top === window;
  // dentro un'app desktop le finestre hanno un indirizzo interno: il connettore dice a quale servizio appartengono
  const OSPITE = globalThis.MSP_OSPITE || location.hostname;
  const canale = globalThis.mspCanale || null;
  let stato = null, sospesa = false, avvisi = true;

  const invia = m => chrome.runtime.sendMessage(m);
  const viva = () => { try { return !!chrome.runtime.id; } catch (e) { return false; } };

  function politica(host) {
    for (const s of (stato && stato.servizi) || []) {
      if (s.domini.some(d => host === d || host.endsWith('.' + d))) return s.politica === 'proteggi' && !s.leggibile ? 'registra' : s.politica;
    }
    return null;
  }

  function riassunto() {
    const domini = [];
    if (!sospesa) for (const s of (stato && stato.servizi) || []) if (s.politica === 'proteggi' && s.leggibile) domini.push(...s.domini);
    // ospite: solo dentro un'app desktop, il servizio a cui appartengono le sue finestre interne
    return {domini, ripristina: !sospesa && !!(stato && stato.ripristina), ospite: (!sospesa && globalThis.MSP_OSPITE) || ''};
  }

  async function carica() {
    let d = {};
    try { d = await chrome.storage.local.get(['stato', 'sospesa', 'avvisi']); } catch (e) { /* estensione ricaricata */ }
    stato = d.stato || globalThis.MSP_PREDEFINITI;
    sospesa = !!d.sospesa;
    avvisi = d.avvisi !== false;
    if (canale) canale.pronta.then(p => p.postMessage({stato: riassunto()}));
    testoPagina();
  }

  // ---------------------------------------------------------------- avvisi nella pagina
  let ospite = null, ultimo = {testo: '', quando: 0}, chiusura = 0;
  function avviso(testo, grave) {
    const ora = Date.now();
    if (testo === ultimo.testo && ora - ultimo.quando < (grave ? 20000 : 1500)) return;
    ultimo = {testo, quando: ora};
    if (!cima || !document.documentElement) return;
    if (ospite) ospite.remove();
    ospite = document.createElement('div');
    ospite.setAttribute('data-msp-pii', '');
    ospite.style.cssText = 'all:initial;position:fixed;z-index:2147483647;right:16px;bottom:16px;';
    const ombra = ospite.attachShadow({mode: 'closed'});
    const riquadro = document.createElement('div');
    // stesso aspetto del pannello: scuro, bordo sottile, un punto colorato che dice se e' andata bene
    riquadro.style.cssText = 'font:13px/1.45 system-ui,Segoe UI,sans-serif;max-width:340px;padding:10px 14px;border-radius:8px;' +
      'box-shadow:0 8px 30px rgba(0,0,0,.28);color:#ededed;background:#0a0a0a;border:1px solid ' + (grave ? '#ff6369' : '#333');
    riquadro.setAttribute('role', grave ? 'alert' : 'status');
    const punto = document.createElement('span');
    punto.style.cssText = 'display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;background:' + (grave ? '#ff6369' : '#5fc27a');
    const titolo = document.createElement('b');
    titolo.textContent = 'Omissis';
    riquadro.append(punto, titolo, document.createElement('br'), testo);
    ombra.append(riquadro);
    document.documentElement.append(ospite);
    clearTimeout(chiusura);
    const questo = ospite;
    chiusura = setTimeout(() => questo.remove(), grave ? 12000 : 3500);
  }

  // Le frasi: nell'estensione le da' il browser (_locales/<lingua>/messages.json), dentro un'app desktop le porta il
  // connettore (MSP_TESTI). Si leggono tutte subito: quando l'estensione viene aggiornata il browser non le da' piu',
  // ed e' proprio allora che serve dire «ricarica la pagina».
  const T = (chiave, ...valori) => {
    try {
      const portate = globalThis.MSP_TESTI;
      if (portate) return (portate[chiave] || chiave).replace(/\$(\d)/g, (m, n) => valori[n - 1] ?? m);
      return chrome.i18n.getMessage(chiave, valori.map(String)) || chiave;
    } catch (e) { return chiave; }
  };
  const MOTIVI = {motore: T('avviso_motore'), 'non collegata': T('avviso_non_collegata'), file: T('avviso_file'),
    ricarica: T('avviso_ricarica'), estensione: T('avviso_estensione')};
  const FRASI = {uno: T('avviso_uno'), molti: T('avviso_molti', '\u0001'), premi: T('avviso_premi_invio'), casella: T('avviso_casella'),
    allegato_lavoro: T('allegato_lavoro'), allegato_fatto: T('allegato_fatto', '\u0001', '\u0002'), allegato_testo: T('allegato_testo'),
    allegato_bloccato: T('allegato_bloccato', '\u0001')};
  const sostituiti = n => (n === 1 ? FRASI.uno : FRASI.molti.replace('\u0001', n));

  // ---------------------------------------------------------------- allegati
  // Il file che l'utente sceglie, trascina o incolla viene fermato prima che la pagina lo riceva, mandato al programma
  // sul PC e sostituito con la copia anonimizzata (un PDF o un'immagine diventano un file di testo). Come per la casella
  // di scrittura, non dipende da come il sito carica poi il file.
  const ALLEGATO_MAX = globalThis.MSP_OSPITE ? 8e6 : 20e6;   // dentro un'app il passaggio e' piu' stretto
  const nostri = new WeakSet();   // gli eventi che rimettiamo in circolo noi
  // Nella stessa pagina possono esserci due copie di questo codice (una rimasta da prima di un aggiornamento, o estensione e
  // connettore insieme): mentre una consegna le copie dei file lo segna sulla pagina, cosi' l'altra non le ferma di nuovo.
  const SEGNO = 'data-omissis-allegato';
  const nostro = ev => nostri.has(ev) || document.documentElement.hasAttribute(SEGNO);
  const consegna = (bersaglio, e) => { nostri.add(e); document.documentElement.setAttribute(SEGNO, ''); try { bersaglio.dispatchEvent(e); } finally { document.documentElement.removeAttribute(SEGNO); } };
  const allegatiAttivi = () => cima !== null && !sospesa && politica(OSPITE) === 'proteggi' && (!stato || stato.allegati !== false);
  const inB64 = async file => { let s = ''; const u = new Uint8Array(await file.arrayBuffer()); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };
  const daB64 = testo => Uint8Array.from(atob(testo), c => c.charCodeAt(0));

  /** I file da consegnare alla pagina al posto di quelli scelti. null = nessuno deve passare (e l'avviso e' gia' a schermo). */
  async function anonimizzati(file) {
    const pronti = [];
    let sostituiti = 0, dati = 0, convertiti = 0;
    avviso(FRASI.allegato_lavoro, false);
    for (const f of file) {
      let r;
      try { r = await invia(f.size > ALLEGATO_MAX ? {t: 'allegato', host: OSPITE, nome: f.name, byte: f.size} : {t: 'allegato', host: OSPITE, nome: f.name, byte: f.size, dati: await inB64(f)}); }
      catch (e) { r = {azione: 'blocca', motivo: viva() ? 'estensione' : 'ricarica'}; }
      if (r && r.azione === 'sostituisci') {
        pronti.push(new File([daB64(r.dati)], r.nome, {type: r.tipo, lastModified: f.lastModified}));
        sostituiti++; dati += r.sostituzioni || 0; convertiti += r.convertito ? 1 : 0;
      } else if (r && r.azione === 'passa') pronti.push(f);
      else { avviso(r && r.motivo === 'file' ? FRASI.allegato_bloccato.replace('\u0001', f.name) : (MOTIVI[r && r.motivo] || MOTIVI.estensione), true); return null; }
    }
    if (sostituiti && avvisi) avviso(FRASI.allegato_fatto.replace('\u0001', sostituiti).replace('\u0002', dati) + (convertiti ? ' ' + FRASI.allegato_testo : ''), false);
    return pronti;
  }
  const carico = file => { const dt = new DataTransfer(); for (const f of file) dt.items.add(f); return dt; };

  // scelta dal pulsante: «input» e «change» arrivano uno dopo l'altro con i file veri, e vanno fermati tutti e due
  const inLavoro = new WeakSet();
  for (const tipo of ['input', 'change']) {
    window.addEventListener(tipo, ev => {
      const el = ev.target;
      if (nostro(ev) || !(el instanceof HTMLInputElement) || el.type !== 'file') return;
      if (inLavoro.has(el)) { ev.stopImmediatePropagation(); return; }   // il secondo dei due eventi, o una scelta mentre lavoriamo
      if (!el.files || !el.files.length || !allegatiAttivi()) return;
      ev.stopImmediatePropagation();
      inLavoro.add(el);
      const scelti = [...el.files];
      el.value = '';   // finche' la copia non e' pronta la pagina non deve trovare i file veri
      anonimizzati(scelti).then(pronti => {
        if (!pronti || !pronti.length) return;
        el.files = carico(pronti).files;
        for (const t of ['input', 'change']) consegna(el, new Event(t, {bubbles: true}));
      }).finally(() => setTimeout(() => inLavoro.delete(el), 0));
    }, true);
  }

  // trascinamento e incolla: l'evento vero viene fermato e rifatto uguale, con le copie al posto dei file
  function rifai(ev, costruisci) {
    const dt = ev.dataTransfer || ev.clipboardData;
    if (nostro(ev) || !dt || !dt.files || !dt.files.length || !allegatiAttivi()) return;
    ev.preventDefault();
    ev.stopImmediatePropagation();
    const bersaglio = ev.target, testi = {};
    for (const t of ['text/plain', 'text/html']) { const v = dt.getData(t); if (v) testi[t] = v; }
    anonimizzati([...dt.files]).then(pronti => {
      if (!pronti || !pronti.length) return;
      const nuovo = carico(pronti);
      for (const [t, v] of Object.entries(testi)) nuovo.setData(t, v);
      consegna(bersaglio && bersaglio.isConnected ? bersaglio : document.body, costruisci(nuovo));
    });
  }
  window.addEventListener('drop', ev => rifai(ev, dt => new DragEvent('drop', {bubbles: true, cancelable: true, composed: true, dataTransfer: dt,
    clientX: ev.clientX, clientY: ev.clientY, screenX: ev.screenX, screenY: ev.screenY})), true);
  window.addEventListener('paste', ev => rifai(ev, dt => new ClipboardEvent('paste', {bubbles: true, cancelable: true, composed: true, clipboardData: dt})), true);

  // ---------------------------------------------------------------- tramite per pagina.js
  if (canale) {
    canale.pronta.then(p => {
      p.onmessage = async ev => {
        const {n, m} = ev.data || {};
        if (!m) return;
        let r;
        try {
          r = await invia(m);
          if (!r) throw new Error('vuota');
        } catch (e) {
          r = m.t === 'richiesta' ? {azione: 'blocca', motivo: viva() ? 'estensione' : 'ricarica'} : {};
        }
        if (m.t === 'richiesta') {
          if (r.azione === 'blocca') avviso(MOTIVI[r.motivo] || MOTIVI.estensione, true);
          else if (r.azione === 'sostituisci' && avvisi) {
            avviso(sostituiti(r.sostituzioni), false);
          }
        }
        p.postMessage({n, r});
      };
    });
  }

  // ---------------------------------------------------------------- valori veri nel testo della pagina
  // Rete di sicurezza per cio' che non passa da fetch (XMLHttpRequest, WebSocket, testo incollato gia'
  // mascherato): dove nel testo visibile compare un segnaposto conosciuto, mostra il valore.
  const noti = new Map(), coda = new Set();
  let osservatore = null, timer = 0;

  // Alcune pagine scrivono un segnaposto spezzato in piu' pezzi di testo vicini ("[PERSONA" + "_" + "3]").
  const RX_APRE = /\[(?:[A-Z][A-Z_]{0,22}\d{0,7})?$/, RX_INTERO = /^\[[A-Z][A-Z_]{1,22}_\d{1,7}\]/, RX_PARTE = /^\[(?:[A-Z][A-Z_]{0,23}\d{0,7})?$/;
  const bloccoDi = t => (t.parentElement && t.parentElement.closest('p, li, td, th, h1, h2, h3, h4, h5, h6, pre, blockquote, div')) || t.parentElement;

  function unPezzo(t) {
    if (t.data.includes('[')) { coda.add(t); return; }
    if (t.data.length > 40 || !/[\]_\d]/.test(t.data)) return;
    const blocco = bloccoDi(t);   // puo' essere la chiusura di un segnaposto spezzato: si riesamina il pezzo che lo apre
    if (!blocco) return;
    const w = document.createTreeWalker(blocco, NodeFilter.SHOW_TEXT);
    w.currentNode = t;
    for (let p = w.previousNode(), i = 0; p && i < 8; p = w.previousNode(), i++) if (p.data.includes('[')) { coda.add(p); return; }
  }

  function esamina(nodo) {
    if (nodo.nodeType === 3) { unPezzo(nodo); return; }
    if (nodo.nodeType !== 1) return;
    const w = document.createTreeWalker(nodo, NodeFilter.SHOW_TEXT);
    for (let t = w.nextNode(); t; t = w.nextNode()) unPezzo(t);
  }

  // Se il pezzo finisce con l'inizio di un segnaposto e i pezzi seguenti lo completano: {seg, pezzi: [[nodo, da, a], ...]}
  function spezzato(t) {
    const m = RX_APRE.exec(t.data);
    const blocco = m && bloccoDi(t);
    if (!blocco) return null;
    const w = document.createTreeWalker(blocco, NodeFilter.SHOW_TEXT);
    w.currentNode = t;
    let testo = t.data.slice(m.index);
    const pezzi = [[t, m.index, t.data.length]];
    for (let n = w.nextNode(), i = 0; n && i < 8; n = w.nextNode(), i++) {
      const prima = testo.length;
      testo += n.data;
      const intero = RX_INTERO.exec(testo);
      if (intero) { pezzi.push([n, 0, intero[0].length - prima]); return {seg: intero[0], pezzi}; }
      if (!RX_PARTE.test(testo)) return null;
      pezzi.push([n, 0, n.data.length]);
    }
    return null;
  }

  function intoccabile(t) {
    const p = t.parentElement;
    return !p || p.isContentEditable || /^(SCRIPT|STYLE|TEXTAREA|NOSCRIPT|TITLE)$/.test(p.tagName) || !!p.closest('[data-msp-pii]');
  }

  async function svuota() {
    timer = 0;
    const nodi = [...coda].filter(t => t.isConnected);
    coda.clear();
    const ora = Date.now(), servono = new Set();
    for (const t of nodi) {
      const s2 = spezzato(t);
      for (const s of (t.data.match(RX) || []).concat(s2 ? [s2.seg] : [])) {
        const v = noti.get(s);
        if (!v || (v.valore === null && ora - v.quando > 30000)) servono.add(s);
      }
    }
    if (servono.size) {
      let mappa;
      try { mappa = (await invia({t: 'valori', segnaposto: [...servono].slice(0, 500)})).mappa || {}; } catch (e) { return; }
      for (const s of servono) noti.set(s, {valore: typeof mappa[s] === 'string' ? mappa[s] : null, quando: ora});
    }
    for (const t of nodi) {
      if (!t.isConnected || intoccabile(t)) continue;
      const nuovo = t.data.replace(RX, s => { const v = noti.get(s); return v && v.valore !== null ? v.valore : s; });
      if (nuovo !== t.data) t.data = nuovo;
      const s2 = spezzato(t);   // il valore va nel primo pezzo, gli altri perdono la loro parte di segnaposto
      const v2 = s2 && noti.get(s2.seg);
      if (v2 && v2.valore !== null && !s2.pezzi.some(([n]) => intoccabile(n))) {
        s2.pezzi.forEach(([n, da, a], i) => { n.data = i === 0 ? n.data.slice(0, da) + v2.valore : n.data.slice(a); });
      }
    }
  }

  function testoPagina() {
    const pol = politica(OSPITE);
    const attivo = !sospesa && !!(stato && stato.ripristina) && (pol === 'proteggi' || pol === 'registra');
    if (attivo && !osservatore) {
      osservatore = new MutationObserver(lista => {
        for (const r of lista) {
          if (r.type === 'characterData') esamina(r.target);
          else for (const x of r.addedNodes) esamina(x);
        }
        if (coda.size && !timer) timer = setTimeout(svuota, 80);
      });
      osservatore.observe(document, {subtree: true, childList: true, characterData: true});
      if (document.body) { esamina(document.body); if (coda.size && !timer) timer = setTimeout(svuota, 80); }
    } else if (!attivo && osservatore) {
      osservatore.disconnect();
      osservatore = null;
    }
  }

  // ---------------------------------------------------------------- barriera sulla casella di scrittura
  // Alcune app desktop non mandano il messaggio come richiesta della finestra: lo consegnano al proprio processo
  // principale per un canale interno che da qui non si vede. Li' l'unico punto certo e' la casella: all'Invio (o al
  // clic sul pulsante di invio) il testo viene sostituito NELLA CASELLA prima che l'app lo legga; i valori veri
  // tornano poi nel testo della pagina. Dentro le app (MSP_OSPITE) e' l'unica difesa; nel browser e' la prima, perche'
  // non dipende dal formato delle richieste, che i siti cambiano senza preavviso (si spegne dalle impostazioni).
  const CASELLA = true;
  const RX_INVIO = /send|invia|submit|inoltra/i;
  let approvato = null, lavoro = false, ultimaCasella = null, lasciaClic = null;
  const piatto = t => String(t).replace(/\s+/g, ' ').trim();

  function casellaDi(da) {
    const el = da && da.nodeType === 1 ? da : da && da.parentElement;
    if (!el || !el.closest) return null;
    if (el.tagName === 'TEXTAREA') return el;
    return el.closest('[contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]');
  }
  const leggi = el => el.tagName === 'TEXTAREA' ? el.value : el.innerText;

  function scrivi(el, testo) {
    el.focus();
    if (el.tagName === 'TEXTAREA') {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(el, testo);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      return piatto(leggi(el)) === piatto(testo);
    }
    const scegliTutto = () => { const s = getSelection(), r = document.createRange(); r.selectNodeContents(el); s.removeAllRanges(); s.addRange(r); };
    scegliTutto();   // gli editor ricchi accettano un "incolla": conserva gli a capo
    const dt = new DataTransfer();
    dt.setData('text/plain', testo);
    el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
    if (piatto(leggi(el)) === piatto(testo)) return true;
    scegliTutto();
    document.execCommand('insertText', false, testo);
    return piatto(leggi(el)) === piatto(testo);
  }

  function pulsanteInvio(da) {
    const b = da && da.closest ? da.closest('button, [role="button"], input[type="submit"]') : null;
    if (!b || b.closest('[data-msp-pii]')) return null;
    const scritte = [b.getAttribute('aria-label'), b.getAttribute('data-testid'), b.getAttribute('title'), b.id, b.type === 'submit' ? 'submit' : ''].join(' ');
    return RX_INVIO.test(scritte) ? b : null;
  }

  function pulsanteVicino(el) {
    for (let n = el.parentElement, i = 0; n && i < 8; n = n.parentElement, i++) {
      const b = [...n.querySelectorAll('button, [role="button"], input[type="submit"]')].filter(x => pulsanteInvio(x) && !x.disabled);
      if (b.length) return b[b.length - 1];
    }
    return null;
  }

  const casellaAttiva = () => CASELLA && !sospesa && politica(OSPITE) === 'proteggi' && (!!globalThis.MSP_OSPITE || !stato || stato.casella !== false);
  const giaApprovato = (el, testo) => !!approvato && approvato.el === el && approvato.testo === piatto(testo);

  function spedisci(el, come, pulsante) {
    if (come === 'pulsante' && pulsante && pulsante.isConnected) { lasciaClic = pulsante; pulsante.click(); return; }
    for (const tipo of ['keydown', 'keypress', 'keyup']) {
      el.dispatchEvent(new KeyboardEvent(tipo, {key: 'Enter', code: 'Enter', bubbles: true, cancelable: true, composed: true}));
    }
    setTimeout(() => {   // l'app non ha reagito al tasto simulato: si prova con il suo pulsante di invio
      if (!el.isConnected || !piatto(leggi(el)) || !giaApprovato(el, leggi(el))) return;
      const b = pulsanteVicino(el);
      if (b) { lasciaClic = b; b.click(); } else avviso(FRASI.premi, false);
    }, 450);
  }

  async function elabora(el, testo, come, pulsante) {
    if (lavoro) return;
    lavoro = true;
    try {
      let r = null;
      try { r = await invia({t: 'testo', host: OSPITE, testo}); } catch (e) { r = {azione: 'blocca', motivo: viva() ? 'estensione' : 'ricarica'}; }
      if (!r || (r.azione !== 'passa' && r.azione !== 'sostituisci')) { avviso(MOTIVI[r && r.motivo] || MOTIVI.estensione, true); return; }
      let pronto = testo;
      if (r.azione === 'sostituisci') {
        if (!scrivi(el, r.testo)) { avviso(FRASI.casella, true); return; }
        pronto = r.testo;
        if (avvisi) avviso(sostituiti(r.sostituzioni), false);
        await new Promise(ok => setTimeout(ok, 80));   // l'app deve accorgersi del testo nuovo
      }
      approvato = {el, testo: piatto(pronto)};
      spedisci(el, come, pulsante);
    } finally { lavoro = false; }
  }

  if (CASELLA) {
    window.addEventListener('focusin', ev => { const el = casellaDi(ev.target); if (el) ultimaCasella = el; }, true);
    window.addEventListener('keydown', ev => {
      if (ev.key !== 'Enter' || ev.shiftKey || ev.ctrlKey || ev.altKey || ev.metaKey || ev.isComposing || !ev.isTrusted || !casellaAttiva()) return;
      const el = casellaDi(ev.target);
      if (!el) return;
      const testo = leggi(el);
      if (!piatto(testo) || giaApprovato(el, testo)) return;
      ev.preventDefault();
      ev.stopImmediatePropagation();
      elabora(el, testo, 'tasto', null);
    }, true);
    window.addEventListener('click', ev => {
      if (!casellaAttiva()) return;
      const b = pulsanteInvio(ev.target);
      if (!b) return;
      if (lasciaClic === b) { lasciaClic = null; return; }
      // la casella giusta: l'ultima in cui si e' scritto, altrimenti la piu' vicina al pulsante che contiene del testo
      let el = ultimaCasella && ultimaCasella.isConnected && piatto(leggi(ultimaCasella)) ? ultimaCasella : null;
      for (let n = b.parentElement, i = 0; n && i < 8 && !el; n = n.parentElement, i++) {
        el = [...n.querySelectorAll('textarea, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]')].find(x => piatto(leggi(x))) || null;
      }
      if (!el) return;
      const testo = leggi(el);
      if (!piatto(testo) || giaApprovato(el, testo)) return;
      ev.preventDefault();
      ev.stopImmediatePropagation();
      elabora(el, testo, 'pulsante', b);
    }, true);
  }

  // ---------------------------------------------------------------- avvio
  try {
    chrome.storage.onChanged.addListener((c, area) => { if (area === 'local' && (c.stato || c.sospesa || c.avvisi)) carica(); });
  } catch (e) { /* estensione ricaricata */ }
  carica();
  if (cima) invia({t: 'visita', host: OSPITE}).catch(() => {});
})();
