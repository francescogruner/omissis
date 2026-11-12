// Omissis — parte che gira DENTRO la pagina del servizio (stesso mondo degli script del sito).
// Intercetta le richieste prima che partano: il testo viene mandato al programma sul PC, che
// sostituisce i dati sensibili con segnaposto, e la risposta viene riscritta mentre arriva.
// Regola: se la protezione non risponde, la richiesta NON parte.
(() => {
  'use strict';
  const RX = /\[[A-Z][A-Z_]{1,22}_\d{1,7}\]/;
  const TESTUALE = /json|text\/|x-www-form-urlencoded|graphql|xml/i;
  const MAX = 8000000;
  let porta = null, S = null, n = 0;
  const attese = new Map();
  let conStato;
  const primoStato = new Promise(ok => { conStato = ok; });

  // ---- canale privato con l'estensione: arriva una volta sola, prima di ogni script del sito
  function ascolta(ev) {
    const d = ev.data;
    if (ev.source !== window || !d || d.__msp_pii !== 'porta' || !ev.ports || !ev.ports.length) return;
    ev.stopImmediatePropagation();
    if (porta) return;
    porta = ev.ports[0];
    porta.onmessage = m => {
      const x = m.data || {};
      if (x.stato) { S = x.stato; conStato(); return; }
      const a = attese.get(x.n);
      if (a) { attese.delete(x.n); a(x.r || {}); }
    };
    porta.postMessage({eccomi: true});
  }
  window.addEventListener('message', ascolta, true);
  // senza estensione che risponde non si puo' proteggere nulla: su questi siti si blocca
  setTimeout(() => { if (!S) { S = {tutti: true, ripristina: false}; conStato(); } }, 3000);

  function chiedi(m, attesa) {
    return new Promise((ok, no) => {
      if (!porta) { no(new Error('canale')); return; }
      const k = ++n;
      const t = setTimeout(() => { attese.delete(k); no(new Error('tempo')); }, attesa || 90000);
      attese.set(k, r => { clearTimeout(t); ok(r); });
      porta.postMessage({n: k, m});
    });
  }

  // Dentro un'app desktop la finestra puo' non parlare con il servizio ma con un indirizzo interno dell'app
  // (es. app://-/__codex-api/...), che poi inoltra lei: quelle richieste valgono come dirette al servizio.
  function interna(url) {
    return !!(S && S.ospite) && url.protocol === location.protocol && url.host === location.host;
  }

  function protetto(url) {
    if (!S) return false;
    if (S.tutti) return true;
    if (interna(url)) return S.domini.some(d => S.ospite === d || S.ospite.endsWith('.' + d));
    const h = url.hostname;
    return S.domini.some(d => h === d || h.endsWith('.' + d));
  }

  // l'indirizzo da dichiarare al programma: per le richieste interne, quello del servizio con lo stesso percorso
  function dichiarato(url) {
    return interna(url) ? 'https://' + S.ospite + url.pathname + url.search : url.href;
  }

  // ---- lettura del corpo di una richiesta
  async function leggi(corpo, tipo) {
    if (corpo == null) return null;
    if (typeof corpo === 'string') return {testo: corpo, rifai: t => t};
    if (corpo instanceof URLSearchParams) {
      return {testo: corpo.toString(), tipo: tipo || 'application/x-www-form-urlencoded', rifai: t => new URLSearchParams(t)};
    }
    if (corpo instanceof FormData) {
      let byte = 0, file = false;
      for (const [, v] of corpo) if (typeof v !== 'string') { file = true; byte += v.size || 0; }
      return file ? {file: true, byte} : null;
    }
    if (corpo instanceof Blob) {
      const tb = tipo || corpo.type;
      if (corpo.size <= MAX && TESTUALE.test(tb)) {
        return {testo: await corpo.text(), tipo: tb, rifai: t => new Blob([t], {type: corpo.type})};
      }
      return {file: true, byte: corpo.size};
    }
    if (corpo instanceof ArrayBuffer || ArrayBuffer.isView(corpo)) {
      if (corpo.byteLength <= MAX && TESTUALE.test(tipo)) {
        return {testo: new TextDecoder().decode(corpo), rifai: t => new TextEncoder().encode(t)};
      }
      return {binario: true, byte: corpo.byteLength};
    }
    return {binario: true, byte: 0};   // flussi e altro
  }

  // -> {azione: 'passa'} | {azione: 'sostituisci', corpo} | {azione: 'blocca'}
  async function prepara(url, metodo, tipo, corpo) {
    const l = await leggi(corpo, tipo);
    if (!l) return {azione: 'passa'};
    const m = {t: 'richiesta', url: dichiarato(url), metodo, tipo: l.tipo || tipo || ''};
    if (l.testo !== undefined) m.corpo = l.testo;
    else { m.file = !!l.file; m.binario = !!l.binario; m.byte = l.byte; }
    const r = await chiedi(m);
    if (r.azione === 'passa') return {azione: 'passa'};
    if (r.azione === 'sostituisci' && typeof r.corpo === 'string' && l.rifai) return {azione: 'sostituisci', corpo: l.rifai(r.corpo)};
    return {azione: 'blocca'};
  }

  // ---- risposta: riscrittura mentre arriva
  function a64(u8) {
    let s = '';
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s);
  }
  function da64(t) {
    const s = atob(t), u8 = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) u8[i] = s.charCodeAt(i);
    return u8;
  }

  function aPezzi(id) {
    let guasto = false;
    return new TransformStream({
      async transform(pezzo, ctl) {
        if (guasto) { ctl.enqueue(pezzo); return; }
        try {
          const r = await chiedi({t: 'pezzo', id, dati: a64(pezzo)}, 20000);
          if (typeof r.dati !== 'string') throw new Error('ponte');
          if (r.dati) ctl.enqueue(da64(r.dati));
        } catch (e) { guasto = true; ctl.enqueue(pezzo); }
      },
      async flush(ctl) {
        if (guasto) return;
        try {
          const r = await chiedi({t: 'pezzo', id, fine: true}, 20000);
          if (r.dati) ctl.enqueue(da64(r.dati));
        } catch (e) { /* restano i segnaposto */ }
      }
    });
  }

  function perIntero(url, tipo) {
    let pezzi = [], byte = 0, diretto = false;
    return new TransformStream({
      transform(p, ctl) {
        if (diretto) { ctl.enqueue(p); return; }
        pezzi.push(p); byte += p.byteLength;
        if (byte > MAX) { diretto = true; for (const x of pezzi) ctl.enqueue(x); pezzi = []; }
      },
      async flush(ctl) {
        if (diretto || !pezzi.length) return;
        const tutto = new Uint8Array(byte);
        let pos = 0;
        for (const x of pezzi) { tutto.set(x, pos); pos += x.byteLength; }
        let testo;
        try { testo = new TextDecoder('utf-8', {fatal: true}).decode(tutto); } catch (e) { ctl.enqueue(tutto); return; }
        if (!RX.test(testo)) { ctl.enqueue(tutto); return; }
        try {
          const r = await chiedi({t: 'intera', url: dichiarato(url), tipo, testo}, 30000);
          ctl.enqueue(typeof r.testo === 'string' ? new TextEncoder().encode(r.testo) : tutto);
        } catch (e) { ctl.enqueue(tutto); }
      }
    });
  }

  async function avvolgi(risp, url) {
    if (!S.ripristina || !risp.body || risp.type === 'opaque' || risp.type === 'opaqueredirect' || risp.type === 'error') return risp;
    if (risp.status < 200 || risp.status === 204 || risp.status === 205 || risp.status === 304) return risp;
    const tipo = risp.headers.get('content-type') || '';
    if (!/event-stream|json|text\/plain|stream/i.test(tipo)) return risp;
    let ts = null;
    if (!/json/i.test(tipo) || /stream|ndjson|jsonl/i.test(tipo) || /StreamGenerate/.test(url.pathname)) {
      try {
        const r = await chiedi({t: 'apri', url: dichiarato(url), tipo}, 8000);
        if (r && r.id) ts = aPezzi(r.id);
      } catch (e) { return risp; }
    }
    if (!ts) ts = perIntero(url, tipo);
    const intest = new Headers(risp.headers);
    intest.delete('content-length');
    const nuova = new Response(risp.body.pipeThrough(ts), {status: risp.status, statusText: risp.statusText, headers: intest});
    for (const k of ['url', 'redirected', 'type']) Object.defineProperty(nuova, k, {value: risp[k], enumerable: true});
    return nuova;
  }

  // ---- fetch
  const fetchNativo = window.fetch;
  async function nuovoFetch(io, args) {
    await primoStato;
    let input = args[0], init = args[1], url, metodo, daRichiesta;
    try {
      daRichiesta = input instanceof Request;
      url = new URL(daRichiesta ? input.url : String(input), document.baseURI);
      metodo = String((init && init.method) || (daRichiesta ? input.method : 'GET')).toUpperCase();
    } catch (e) { return Reflect.apply(fetchNativo, io, args); }
    if (!protetto(url)) return Reflect.apply(fetchNativo, io, args);
    if (metodo === 'POST' || metodo === 'PUT' || metodo === 'PATCH') {
      let esito;
      try {
        const intest = new Headers((init && init.headers) || (daRichiesta ? input.headers : undefined));
        const tipo = intest.get('content-type') || '';
        let corpo = init && init.body != null ? init.body : null;
        if (corpo == null && daRichiesta && input.body) {
          const copia = input.clone();
          corpo = TESTUALE.test(tipo) ? await copia.text() : await copia.blob();
        }
        esito = await prepara(url, metodo, tipo, corpo);
      } catch (e) { esito = {azione: 'blocca'}; }
      if (esito.azione === 'blocca') throw new TypeError('Failed to fetch');
      if (esito.azione === 'sostituisci') {
        if (init && init.body != null) init = Object.assign({}, init, {body: esito.corpo});
        else input = new Request(input, {body: esito.corpo});
        args = [input, init];
      }
    }
    const risp = await Reflect.apply(fetchNativo, io, args);
    try { return await avvolgi(risp, url); } catch (e) { return risp; }
  }
  window.fetch = new Proxy(fetchNativo, {apply(_f, io, args) { return nuovoFetch(io, args); }});

  // ---- XMLHttpRequest: si maschera la richiesta; la risposta la sistema l'estensione nel testo della pagina
  const XP = XMLHttpRequest.prototype, info = new WeakMap();
  const xOpen = XP.open, xSend = XP.send, xIntest = XP.setRequestHeader;
  XP.open = new Proxy(xOpen, {apply(f, io, args) {
    try { info.set(io, {metodo: String(args[0]).toUpperCase(), url: new URL(String(args[1]), document.baseURI), asinc: args[2] !== false, tipo: ''}); } catch (e) { /* indirizzo non valido: ci pensa il browser */ }
    return Reflect.apply(f, io, args);
  }});
  XP.setRequestHeader = new Proxy(xIntest, {apply(f, io, args) {
    const i = info.get(io);
    if (i && /^content-type$/i.test(String(args[0]))) i.tipo = String(args[1]);
    return Reflect.apply(f, io, args);
  }});
  XP.send = new Proxy(xSend, {apply(f, io, args) {
    const i = info.get(io), corpo = args[0];
    if (!i || corpo == null || !S || !protetto(i.url) || !/^(POST|PUT|PATCH)$/.test(i.metodo)) {
      if (i && corpo != null && !S && /^(POST|PUT|PATCH)$/.test(i.metodo) && i.asinc) {   // stato non ancora arrivato: si aspetta
        primoStato.then(() => XP.send.call(io, corpo));
        return undefined;
      }
      return Reflect.apply(f, io, args);
    }
    if (!i.asinc) throw new DOMException('Omissis: richiesta sincrona non protetta, bloccata', 'NetworkError');
    const fallita = () => { try { io.abort(); } catch (e) { /* gia' chiusa */ } io.dispatchEvent(new ProgressEvent('error')); };
    prepara(i.url, i.metodo, i.tipo, corpo).then(esito => {
      if (esito.azione === 'blocca') fallita();
      else Reflect.apply(f, io, [esito.azione === 'sostituisci' ? esito.corpo : corpo]);
    }, fallita);
    return undefined;
  }});

  // ---- WebSocket: non coperto, ma viene segnalato nel registro
  const WS = window.WebSocket;
  if (WS) {
    window.WebSocket = new Proxy(WS, {construct(f, args, nuovo) {
      try {
        const u = new URL(String(args[0]), document.baseURI);
        if (S && protetto(u)) chiedi({t: 'websocket', url: u.href.replace(/^ws/, 'http')}, 5000).catch(() => {});
      } catch (e) { /* indirizzo non valido */ }
      return Reflect.construct(f, args, nuovo);
    }});
  }
})();
