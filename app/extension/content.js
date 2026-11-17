// Omissis — parte dell'estensione accanto alla pagina (mondo isolato: il sito non la vede).
// Fa da tramite tra page.js e il programma sul PC, mostra gli avvisi, segnala la visita al
// servizio (Shadow AI) e rimette i valori veri dove nella pagina compare un segnaposto.
(() => {
  'use strict';
  const RX = /\[[A-Z][A-Z_]{1,22}_\d{1,7}\]/g;
  const topmost = window.top === window;
  // dentro un'app desktop le finestre hanno un indirizzo interno: il connettore dice a quale servizio appartengono
  const HOST_SITE = globalThis.MSP_HOST_SITE || location.hostname;
  const channel = globalThis.mspChannel || null;
  let status = null, suspended = false, notices = true;

  const send = m => chrome.runtime.sendMessage(m);
  const alive = () => { try { return !!chrome.runtime.id; } catch (e) { return false; } };

  function policy(host) {
    for (const s of (status && status.services) || []) {
      if (s.domains.some(d => host === d || host.endsWith('.' + d))) return s.policy === 'protect' && !s.readable ? 'record' : s.policy;
    }
    return null;
  }

  // la regola di questo servizio e' imposta da chi amministra il PC? Li' la sospensione scelta dalla finestrella non vale
  function fixed(host) {
    for (const s of (status && status.services) || []) if (s.domains.some(d => host === d || host.endsWith('.' + d))) return !!s.locked;
    return false;
  }

  function summary() {
    const domains = [];
    for (const s of (status && status.services) || []) if (s.policy === 'protect' && s.readable && (!suspended || s.locked)) domains.push(...s.domains);
    // ospite: solo dentro un'app desktop, il servizio a cui appartengono le sue finestre interne
    return {domains, restore: !suspended && !!(status && status.restore), host_site: (!suspended && globalThis.MSP_HOST_SITE) || ''};
  }

  async function load() {
    let d = {};
    try { d = await chrome.storage.local.get(['status', 'suspended', 'notices']); } catch (e) { /* estensione ricaricata */ }
    status = d.status || globalThis.MSP_DEFAULTS;
    suspended = !!d.suspended && !fixed(HOST_SITE);
    notices = d.notices !== false;
    if (channel) channel.ready.then(p => p.postMessage({status: summary()}));
    pageText();
  }

  // ---------------------------------------------------------------- avvisi nella pagina
  let host_site = null, last = {text: '', when: 0}, closing = 0;
  function notice(text, serious) {
    const stamp = Date.now();
    if (text === last.text && stamp - last.when < (serious ? 20000 : 1500)) return;
    last = {text, when: stamp};
    if (!topmost || !document.documentElement) return;
    if (host_site) host_site.remove();
    host_site = document.createElement('div');
    host_site.setAttribute('data-omissis', '');
    host_site.style.cssText = 'all:initial;position:fixed;z-index:2147483647;right:16px;bottom:16px;';
    const shadow = host_site.attachShadow({mode: 'closed'});
    const tile = document.createElement('div');
    // stesso aspetto del pannello: scuro, bordo sottile, un punto colorato che dice se e' andata bene
    tile.style.cssText = 'font:13px/1.45 system-ui,Segoe UI,sans-serif;max-width:340px;padding:10px 14px;border-radius:8px;' +
      'box-shadow:0 8px 30px rgba(0,0,0,.28);color:#ededed;background:#0a0a0a;border:1px solid ' + (serious ? '#ff6369' : '#333');
    tile.setAttribute('role', serious ? 'alert' : 'status');
    const point = document.createElement('span');
    point.style.cssText = 'display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;background:' + (serious ? '#ff6369' : '#5fc27a');
    const title = document.createElement('b');
    title.textContent = 'Omissis';
    tile.append(point, title, document.createElement('br'), text);
    shadow.append(tile);
    document.documentElement.append(host_site);
    clearTimeout(closing);
    const this_one = host_site;
    closing = setTimeout(() => this_one.remove(), serious ? 12000 : 3500);
  }

  // Le frasi: nell'estensione le da' il browser (_locales/<lingua>/messages.json), dentro un'app desktop le porta il
  // connettore (MSP_TESTI). Si leggono tutte subito: quando l'estensione viene aggiornata il browser non le da' piu',
  // ed e' proprio allora che serve dire «ricarica la pagina».
  const T = (key, ...values) => {
    try {
      const carried = globalThis.MSP_TEXTS;
      if (carried) return (carried[key] || key).replace(/\$(\d)/g, (m, n) => values[n - 1] ?? m);
      return chrome.i18n.getMessage(key, values.map(String)) || key;
    } catch (e) { return key; }
  };
  const REASONS = {engine: T('engine_notice'), 'not_paired': T('notice_not_connected'), file: T('file_notice'),
    reload: T('reload_notice'), extension: T('extension_notice')};
  const PHRASES = {one: T('one_notice'), many: T('many_notice', '\u0001'), press: T('notice_press_enter'), box: T('box_notice'),
    attachment_work: T('attachment_work'), attachment_done: T('attachment_done', '\u0001', '\u0002'), attachment_text: T('attachment_text'),
    attachment_blocked: T('attachment_blocked', '\u0001')};
  const replaced = n => (n === 1 ? PHRASES.one : PHRASES.many.replace('\u0001', n));

  // ---------------------------------------------------------------- allegati
  // Il file che l'utente sceglie, trascina o incolla viene fermato prima che la pagina lo riceva, mandato al programma
  // sul PC e sostituito con la copia anonimizzata (un PDF o un'immagine diventano un file di testo). Come per la casella
  // di scrittura, non dipende da come il sito carica poi il file.
  const ATTACHMENT_MAX = globalThis.MSP_HOST_SITE ? 8e6 : 20e6;   // dentro un'app il passaggio e' piu' stretto
  const ours = new WeakSet();   // gli eventi che rimettiamo in circolo noi
  // Nella stessa pagina possono esserci due copie di questo codice (una rimasta da prima di un aggiornamento, o estensione e
  // connettore insieme): mentre una consegna le copie dei file lo segna sulla pagina, cosi' l'altra non le ferma di nuovo.
  const SIGN = 'data-omissis-attachment';
  const our_own = ev => ours.has(ev) || document.documentElement.hasAttribute(SIGN);
  const deliver = (target, e) => { ours.add(e); document.documentElement.setAttribute(SIGN, ''); try { target.dispatchEvent(e); } finally { document.documentElement.removeAttribute(SIGN); } };
  const activeAttachments = () => topmost !== null && !suspended && policy(HOST_SITE) === 'protect' && (!status || status.attachments !== false);
  const inB64 = async file => { let s = ''; const u = new Uint8Array(await file.arrayBuffer()); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };
  const daB64 = text => Uint8Array.from(atob(text), c => c.charCodeAt(0));

  /** I file da consegnare alla pagina al posto di quelli scelti. null = nessuno deve passare (e l'avviso e' gia' a schermo). */
  async function anonymized(file) {
    const ready_ones = [];
    let replaced = 0, data = 0, converted_ones = 0;
    notice(PHRASES.attachment_work, false);
    for (const f of file) {
      let r;
      try { r = await send(f.size > ATTACHMENT_MAX ? {t: 'attachment', host: HOST_SITE, name: f.name, byte: f.size} : {t: 'attachment', host: HOST_SITE, name: f.name, byte: f.size, data: await inB64(f)}); }
      catch (e) { r = {action: 'block', reason: alive() ? 'extension' : 'reload'}; }
      if (r && r.action === 'replace') {
        ready_ones.push(new File([daB64(r.data)], r.name, {type: r.kind, lastModified: f.lastModified}));
        replaced++; data += r.replacements || 0; converted_ones += r.converted ? 1 : 0;
      } else if (r && r.action === 'passthrough') ready_ones.push(f);
      else { notice(r && r.reason === 'file' ? PHRASES.attachment_blocked.replace('\u0001', f.name) : (REASONS[r && r.reason] || REASONS.extension), true); return null; }
    }
    if (replaced && notices) notice(PHRASES.attachment_done.replace('\u0001', replaced).replace('\u0002', data) + (converted_ones ? ' ' + PHRASES.attachment_text : ''), false);
    return ready_ones;
  }
  const loading = file => { const dt = new DataTransfer(); for (const f of file) dt.items.add(f); return dt; };

  // scelta dal pulsante: «input» e «change» arrivano uno dopo l'altro con i file veri, e vanno fermati tutti e due
  const inWork = new WeakSet();
  for (const kind of ['input', 'change']) {
    window.addEventListener(kind, ev => {
      const el = ev.target;
      if (our_own(ev) || !(el instanceof HTMLInputElement) || el.type !== 'file') return;
      if (inWork.has(el)) { ev.stopImmediatePropagation(); return; }   // il secondo dei due eventi, o una scelta mentre lavoriamo
      if (!el.files || !el.files.length || !activeAttachments()) return;
      ev.stopImmediatePropagation();
      inWork.add(el);
      const chosen = [...el.files];
      el.value = '';   // finche' la copia non e' pronta la pagina non deve trovare i file veri
      anonymized(chosen).then(ready_ones => {
        if (!ready_ones || !ready_ones.length) return;
        el.files = loading(ready_ones).files;
        for (const t of ['input', 'change']) deliver(el, new Event(t, {bubbles: true}));
      }).finally(() => setTimeout(() => inWork.delete(el), 0));
    }, true);
  }

  // trascinamento e incolla: l'evento vero viene fermato e rifatto uguale, con le copie al posto dei file
  function redo(ev, build) {
    const dt = ev.dataTransfer || ev.clipboardData;
    if (our_own(ev) || !dt || !dt.files || !dt.files.length || !activeAttachments()) return;
    ev.preventDefault();
    ev.stopImmediatePropagation();
    const target = ev.target, texts = {};
    for (const t of ['text/plain', 'text/html']) { const v = dt.getData(t); if (v) texts[t] = v; }
    anonymized([...dt.files]).then(ready_ones => {
      if (!ready_ones || !ready_ones.length) return;
      const fresh = loading(ready_ones);
      for (const [t, v] of Object.entries(texts)) fresh.setData(t, v);
      deliver(target && target.isConnected ? target : document.body, build(fresh));
    });
  }
  window.addEventListener('drop', ev => redo(ev, dt => new DragEvent('drop', {bubbles: true, cancelable: true, composed: true, dataTransfer: dt,
    clientX: ev.clientX, clientY: ev.clientY, screenX: ev.screenX, screenY: ev.screenY})), true);
  window.addEventListener('paste', ev => redo(ev, dt => new ClipboardEvent('paste', {bubbles: true, cancelable: true, composed: true, clipboardData: dt})), true);

  // ---------------------------------------------------------------- tramite per page.js
  if (channel) {
    channel.ready.then(p => {
      p.onmessage = async ev => {
        const {n, m} = ev.data || {};
        if (!m) return;
        let r;
        try {
          r = await send(m);
          if (!r) throw new Error('empty');
        } catch (e) {
          r = m.t === 'request' ? {action: 'block', reason: alive() ? 'extension' : 'reload'} : {};
        }
        if (m.t === 'request') {
          if (r.action === 'block') notice(REASONS[r.reason] || REASONS.extension, true);
          else if (r.action === 'replace' && notices) {
            notice(replaced(r.replacements), false);
          }
        }
        p.postMessage({n, r});
      };
    });
  }

  // ---------------------------------------------------------------- valori veri nel testo della pagina
  // Rete di sicurezza per cio' che non passa da fetch (XMLHttpRequest, WebSocket, testo incollato gia'
  // mascherato): dove nel testo visibile compare un segnaposto conosciuto, mostra il valore.
  const well_known = new Map(), queue = new Set();
  let observer = null, timer = 0;

  // Alcune pagine scrivono un segnaposto spezzato in piu' pezzi di testo vicini ("[PERSONA" + "_" + "3]").
  const RX_OPENS = /\[(?:[A-Z][A-Z_]{0,22}\d{0,7})?$/, RX_WHOLE = /^\[[A-Z][A-Z_]{1,22}_\d{1,7}\]/, RX_PART = /^\[(?:[A-Z][A-Z_]{0,23}\d{0,7})?$/;
  const blockOf = t => (t.parentElement && t.parentElement.closest('p, li, td, th, h1, h2, h3, h4, h5, h6, pre, blockquote, div')) || t.parentElement;

  function aChunk(t) {
    if (t.data.includes('[')) { queue.add(t); return; }
    if (t.data.length > 40 || !/[\]_\d]/.test(t.data)) return;
    const block = blockOf(t);   // puo' essere la chiusura di un segnaposto spezzato: si riesamina il pezzo che lo apre
    if (!block) return;
    const w = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    w.currentNode = t;
    for (let p = w.previousNode(), i = 0; p && i < 8; p = w.previousNode(), i++) if (p.data.includes('[')) { queue.add(p); return; }
  }

  function examine(node) {
    if (node.nodeType === 3) { aChunk(node); return; }
    if (node.nodeType !== 1) return;
    const w = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    for (let t = w.nextNode(); t; t = w.nextNode()) aChunk(t);
  }

  // Se il pezzo finisce con l'inizio di un segnaposto e i pezzi seguenti lo completano: {seg, pezzi: [[nodo, da, a], ...]}
  function split(t) {
    const m = RX_OPENS.exec(t.data);
    const block = m && blockOf(t);
    if (!block) return null;
    const w = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    w.currentNode = t;
    let text = t.data.slice(m.index);
    const chunks = [[t, m.index, t.data.length]];
    for (let n = w.nextNode(), i = 0; n && i < 8; n = w.nextNode(), i++) {
      const before = text.length;
      text += n.data;
      const entire = RX_WHOLE.exec(text);
      if (entire) { chunks.push([n, 0, entire[0].length - before]); return {seg: entire[0], chunks}; }
      if (!RX_PART.test(text)) return null;
      chunks.push([n, 0, n.data.length]);
    }
    return null;
  }

  function untouchable(t) {
    const p = t.parentElement;
    return !p || p.isContentEditable || /^(SCRIPT|STYLE|TEXTAREA|NOSCRIPT|TITLE)$/.test(p.tagName) || !!p.closest('[data-omissis]');
  }

  async function clear() {
    timer = 0;
    const nodes = [...queue].filter(t => t.isConnected);
    queue.clear();
    const stamp = Date.now(), needed = new Set();
    for (const t of nodes) {
      const s2 = split(t);
      for (const s of (t.data.match(RX) || []).concat(s2 ? [s2.seg] : [])) {
        const v = well_known.get(s);
        if (!v || (v.value === null && stamp - v.when > 30000)) needed.add(s);
      }
    }
    if (needed.size) {
      let mapping;
      try { mapping = (await send({t: 'values', placeholder: [...needed].slice(0, 500)})).mapping || {}; } catch (e) { return; }
      for (const s of needed) well_known.set(s, {value: typeof mapping[s] === 'string' ? mapping[s] : null, when: stamp});
    }
    for (const t of nodes) {
      if (!t.isConnected || untouchable(t)) continue;
      const fresh = t.data.replace(RX, s => { const v = well_known.get(s); return v && v.value !== null ? v.value : s; });
      if (fresh !== t.data) t.data = fresh;
      const s2 = split(t);   // il valore va nel primo pezzo, gli altri perdono la loro parte di segnaposto
      const v2 = s2 && well_known.get(s2.seg);
      if (v2 && v2.value !== null && !s2.chunks.some(([n]) => untouchable(n))) {
        s2.chunks.forEach(([n, da, a], i) => { n.data = i === 0 ? n.data.slice(0, da) + v2.value : n.data.slice(a); });
      }
    }
  }

  function pageText() {
    const pol = policy(HOST_SITE);
    const is_active = !suspended && !!(status && status.restore) && (pol === 'protect' || pol === 'record');
    if (is_active && !observer) {
      observer = new MutationObserver(list_name => {
        for (const r of list_name) {
          if (r.type === 'characterData') examine(r.target);
          else for (const x of r.addedNodes) examine(x);
        }
        if (queue.size && !timer) timer = setTimeout(clear, 80);
      });
      observer.observe(document, {subtree: true, childList: true, characterData: true});
      if (document.body) { examine(document.body); if (queue.size && !timer) timer = setTimeout(clear, 80); }
    } else if (!is_active && observer) {
      observer.disconnect();
      observer = null;
    }
  }

  // ---------------------------------------------------------------- barriera sulla casella di scrittura
  // Alcune app desktop non mandano il messaggio come richiesta della finestra: lo consegnano al proprio processo
  // principale per un canale interno che da qui non si vede. Li' l'unico punto certo e' la casella: all'Invio (o al
  // clic sul pulsante di invio) il testo viene sostituito NELLA CASELLA prima che l'app lo legga; i valori veri
  // tornano poi nel testo della pagina. Dentro le app (MSP_OSPITE) e' l'unica difesa; nel browser e' la prima, perche'
  // non dipende dal formato delle richieste, che i siti cambiano senza preavviso (si spegne dalle impostazioni).
  const BOX = true;
  const RX_SENDING = /send|invia|submit|inoltra/i;
  let approved = null, work = false, latestBox = null, leaveClick = null;
  const flat = t => String(t).replace(/\s+/g, ' ').trim();

  function boxOf(da) {
    const el = da && da.nodeType === 1 ? da : da && da.parentElement;
    if (!el || !el.closest) return null;
    if (el.tagName === 'TEXTAREA') return el;
    return el.closest('[contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]');
  }
  const read = el => el.tagName === 'TEXTAREA' ? el.value : el.innerText;

  async function write(el, text) {
    el.focus();
    if (el.tagName === 'TEXTAREA') {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(el, text);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      return flat(read(el)) === flat(text);
    }
    const pause = ms => new Promise(ok => setTimeout(ok, ms));
    const same = () => flat(read(el)) === flat(text);
    // Gli editor ricchi tengono una selezione loro e la aggiornano quando il browser dice che e' cambiata: va detto, e va
    // lasciato loro un istante. Senza, il testo nuovo finisce in fondo a quello vecchio invece di prenderne il posto
    // (visto dal vivo su Perplexity il 17/11/2026: nella casella restavano l'originale e la versione protetta).
    const chooseAll = async () => {
      const s = getSelection(), r = document.createRange();
      r.selectNodeContents(el); s.removeAllRanges(); s.addRange(r);
      document.dispatchEvent(new Event('selectionchange'));
      await pause(40);
    };
    await chooseAll();   // gli editor ricchi accettano un "incolla": conserva gli a capo
    const dt = new DataTransfer();
    dt.setData('text/plain', text);
    el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
    await pause(30);
    if (same()) return true;
    await chooseAll();
    document.execCommand('insertText', false, text);
    await pause(30);
    if (same()) return true;
    // ultima via: svuotare la casella e scriverci da capo. Se nemmeno cosi' torna, il messaggio non parte (lo dice chi chiama)
    await chooseAll();
    document.execCommand('delete');
    await pause(30);
    document.execCommand('insertText', false, text);
    await pause(30);
    return same();
  }

  function sendButton(da) {
    const b = da && da.closest ? da.closest('button, [role="button"], input[type="submit"]') : null;
    if (!b || b.closest('[data-omissis]')) return null;
    const captions = [b.getAttribute('aria-label'), b.getAttribute('data-testid'), b.getAttribute('title'), b.id, b.type === 'submit' ? 'submit' : ''].join(' ');
    return RX_SENDING.test(captions) ? b : null;
  }

  function nearbyButton(el) {
    for (let n = el.parentElement, i = 0; n && i < 8; n = n.parentElement, i++) {
      const b = [...n.querySelectorAll('button, [role="button"], input[type="submit"]')].filter(x => sendButton(x) && !x.disabled);
      if (b.length) return b[b.length - 1];
    }
    return null;
  }

  const activeBox = () => BOX && !suspended && policy(HOST_SITE) === 'protect' && (!!globalThis.MSP_HOST_SITE || !status || status.box !== false);
  const alreadyApproved = (el, text) => !!approved && approved.el === el && approved.text === flat(text);

  function dispatch(el, how, button) {
    if (how === 'button' && button && button.isConnected) { leaveClick = button; button.click(); return; }
    for (const kind of ['keydown', 'keypress', 'keyup']) {
      el.dispatchEvent(new KeyboardEvent(kind, {key: 'Enter', code: 'Enter', bubbles: true, cancelable: true, composed: true}));
    }
    setTimeout(() => {   // l'app non ha reagito al tasto simulato: si prova con il suo pulsante di invio
      if (!el.isConnected || !flat(read(el)) || !alreadyApproved(el, read(el))) return;
      const b = nearbyButton(el);
      if (b) { leaveClick = b; b.click(); } else notice(PHRASES.press, false);
    }, 450);
  }

  async function work_on(el, text, how, button) {
    if (work) return;
    work = true;
    try {
      let r = null;
      try { r = await send({t: 'text', host: HOST_SITE, text}); } catch (e) { r = {action: 'block', reason: alive() ? 'extension' : 'reload'}; }
      if (!r || (r.action !== 'passthrough' && r.action !== 'replace')) { notice(REASONS[r && r.reason] || REASONS.extension, true); return; }
      let ready_now = text;
      if (r.action === 'replace') {
        if (!await write(el, r.text)) { notice(PHRASES.box, true); return; }
        ready_now = r.text;
        if (notices) notice(replaced(r.replacements), false);
        await new Promise(ok => setTimeout(ok, 80));   // l'app deve accorgersi del testo nuovo
      }
      approved = {el, text: flat(ready_now)};
      dispatch(el, how, button);
    } finally { work = false; }
  }

  if (BOX) {
    window.addEventListener('focusin', ev => { const el = boxOf(ev.target); if (el) latestBox = el; }, true);
    window.addEventListener('keydown', ev => {
      if (ev.key !== 'Enter' || ev.shiftKey || ev.ctrlKey || ev.altKey || ev.metaKey || ev.isComposing || !ev.isTrusted || !activeBox()) return;
      const el = boxOf(ev.target);
      if (!el) return;
      const text = read(el);
      if (!flat(text) || alreadyApproved(el, text)) return;
      ev.preventDefault();
      ev.stopImmediatePropagation();
      work_on(el, text, 'keystroke', null);
    }, true);
    window.addEventListener('click', ev => {
      if (!activeBox()) return;
      const b = sendButton(ev.target);
      if (!b) return;
      if (leaveClick === b) { leaveClick = null; return; }
      // la casella giusta: l'ultima in cui si e' scritto, altrimenti la piu' vicina al pulsante che contiene del testo
      let el = latestBox && latestBox.isConnected && flat(read(latestBox)) ? latestBox : null;
      for (let n = b.parentElement, i = 0; n && i < 8 && !el; n = n.parentElement, i++) {
        el = [...n.querySelectorAll('textarea, [contenteditable=""], [contenteditable="true"], [contenteditable="plaintext-only"]')].find(x => flat(read(x))) || null;
      }
      if (!el) return;
      const text = read(el);
      if (!flat(text) || alreadyApproved(el, text)) return;
      ev.preventDefault();
      ev.stopImmediatePropagation();
      work_on(el, text, 'button', b);
    }, true);
  }

  // ---------------------------------------------------------------- avvio
  try {
    chrome.storage.onChanged.addListener((c, area) => { if (area === 'local' && (c.status || c.suspended || c.notices)) load(); });
  } catch (e) { /* estensione ricaricata */ }
  load();
  if (topmost) send({t: 'visit', host: HOST_SITE}).catch(() => {});
})();
