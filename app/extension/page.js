// Omissis — parte che gira DENTRO la pagina del servizio (stesso mondo degli script del sito).
// Intercetta le richieste prima che partano: il testo viene mandato al programma sul PC, che
// sostituisce i dati sensibili con segnaposto, e la risposta viene riscritta mentre arriva.
// Regola: se la protezione non risponde, la richiesta NON parte.
(() => {
  'use strict';
  const RX = /\[[A-Z][A-Z_]{1,22}_\d{1,7}\]/;
  const TEXTUAL = /json|text\/|x-www-form-urlencoded|graphql|xml/i;
  const MAX = 8000000;
  let port = null, S = null, n = 0;
  const waits = new Map();
  let withStatus;
  const firstStatus = new Promise(ok => { withStatus = ok; });

  // ---- canale privato con l'estensione: arriva una volta sola, prima di ogni script del sito
  function listen(ev) {
    const d = ev.data;
    if (ev.source !== window || !d || d.__omissis !== 'port' || !ev.ports || !ev.ports.length) return;
    ev.stopImmediatePropagation();
    if (port) return;
    port = ev.ports[0];
    port.onmessage = m => {
      const x = m.data || {};
      if (x.status) { S = x.status; withStatus(); return; }
      const a = waits.get(x.n);
      if (a) { waits.delete(x.n); a(x.r || {}); }
    };
    port.postMessage({hello: true});
  }
  window.addEventListener('message', listen, true);
  // senza estensione che risponde non si puo' proteggere nulla: su questi siti si blocca
  setTimeout(() => { if (!S) { S = {everyone: true, restore: false}; withStatus(); } }, 3000);

  function ask(m, timeout) {
    return new Promise((ok, no) => {
      if (!port) { no(new Error('channel')); return; }
      const k = ++n;
      const t = setTimeout(() => { waits.delete(k); no(new Error('elapsed')); }, timeout || 90000);
      waits.set(k, r => { clearTimeout(t); ok(r); });
      port.postMessage({n: k, m});
    });
  }

  // Dentro un'app desktop la finestra puo' non parlare con il servizio ma con un indirizzo interno dell'app
  // (es. app://-/__codex-api/...), che poi inoltra lei: quelle richieste valgono come dirette al servizio.
  function internal(url) {
    return !!(S && S.host_site) && url.protocol === location.protocol && url.host === location.host;
  }

  function guarded(url) {
    if (!S) return false;
    if (S.everyone) return true;
    if (internal(url)) return S.domains.some(d => S.host_site === d || S.host_site.endsWith('.' + d));
    const h = url.hostname;
    return S.domains.some(d => h === d || h.endsWith('.' + d));
  }

  // l'indirizzo da dichiarare al programma: per le richieste interne, quello del servizio con lo stesso percorso
  function declared(url) {
    return internal(url) ? 'https://' + S.host_site + url.pathname + url.search : url.href;
  }

  // ---- lettura del corpo di una richiesta
  async function read(body, kind) {
    if (body == null) return null;
    if (typeof body === 'string') return {text: body, redo: t => t};
    if (body instanceof URLSearchParams) {
      return {text: body.toString(), kind: kind || 'application/x-www-form-urlencoded', redo: t => new URLSearchParams(t)};
    }
    if (body instanceof FormData) {
      let byte = 0, file = false;
      for (const [, v] of body) if (typeof v !== 'string') { file = true; byte += v.size || 0; }
      return file ? {file: true, byte} : null;
    }
    if (body instanceof Blob) {
      const tb = kind || body.type;
      if (body.size <= MAX && TEXTUAL.test(tb)) {
        return {text: await body.text(), kind: tb, redo: t => new Blob([t], {type: body.type})};
      }
      return {file: true, byte: body.size};
    }
    if (body instanceof ArrayBuffer || ArrayBuffer.isView(body)) {
      if (body.byteLength <= MAX && TEXTUAL.test(kind)) {
        return {text: new TextDecoder().decode(body), redo: t => new TextEncoder().encode(t)};
      }
      return {binary: true, byte: body.byteLength};
    }
    return {binary: true, byte: 0};   // flussi e altro
  }

  // -> {azione: 'passa'} | {azione: 'sostituisci', corpo} | {azione: 'blocca'}
  async function prepare(url, method, kind, body) {
    const l = await read(body, kind);
    if (!l) return {action: 'passthrough'};
    const m = {t: 'request', url: declared(url), method, kind: l.kind || kind || ''};
    if (l.text !== undefined) m.body = l.text;
    else { m.file = !!l.file; m.binary = !!l.binary; m.byte = l.byte; }
    const r = await ask(m);
    if (r.action === 'passthrough') return {action: 'passthrough'};
    if (r.action === 'replace' && typeof r.body === 'string' && l.redo) return {action: 'replace', body: l.redo(r.body)};
    return {action: 'block'};
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

  function inChunks(id) {
    let fault = false;
    return new TransformStream({
      async transform(chunk, ctl) {
        if (fault) { ctl.enqueue(chunk); return; }
        try {
          const r = await ask({t: 'chunk', id, data: a64(chunk)}, 20000);
          if (typeof r.data !== 'string') throw new Error('bridge');
          if (r.data) ctl.enqueue(da64(r.data));
        } catch (e) { fault = true; ctl.enqueue(chunk); }
      },
      async flush(ctl) {
        if (fault) return;
        try {
          const r = await ask({t: 'chunk', id, end: true}, 20000);
          if (r.data) ctl.enqueue(da64(r.data));
        } catch (e) { /* restano i segnaposto */ }
      }
    });
  }

  function inFull(url, kind) {
    let chunks = [], byte = 0, direct = false;
    return new TransformStream({
      transform(p, ctl) {
        if (direct) { ctl.enqueue(p); return; }
        chunks.push(p); byte += p.byteLength;
        if (byte > MAX) { direct = true; for (const x of chunks) ctl.enqueue(x); chunks = []; }
      },
      async flush(ctl) {
        if (direct || !chunks.length) return;
        const everything = new Uint8Array(byte);
        let pos = 0;
        for (const x of chunks) { everything.set(x, pos); pos += x.byteLength; }
        let text;
        try { text = new TextDecoder('utf-8', {fatal: true}).decode(everything); } catch (e) { ctl.enqueue(everything); return; }
        if (!RX.test(text)) { ctl.enqueue(everything); return; }
        try {
          const r = await ask({t: 'whole', url: declared(url), kind, text}, 30000);
          ctl.enqueue(typeof r.text === 'string' ? new TextEncoder().encode(r.text) : everything);
        } catch (e) { ctl.enqueue(everything); }
      }
    });
  }

  async function wrap(resp, url) {
    if (!S.restore || !resp.body || resp.type === 'opaque' || resp.type === 'opaqueredirect' || resp.type === 'error') return resp;
    if (resp.status < 200 || resp.status === 204 || resp.status === 205 || resp.status === 304) return resp;
    const kind = resp.headers.get('content-type') || '';
    if (!/event-stream|json|text\/plain|stream/i.test(kind)) return resp;
    let ts = null;
    if (!/json/i.test(kind) || /stream|ndjson|jsonl/i.test(kind) || /StreamGenerate/.test(url.pathname)) {
      try {
        const r = await ask({t: 'open_up', url: declared(url), kind}, 8000);
        if (r && r.id) ts = inChunks(r.id);
      } catch (e) { return resp; }
    }
    if (!ts) ts = inFull(url, kind);
    const intest = new Headers(resp.headers);
    intest.delete('content-length');
    const new_one = new Response(resp.body.pipeThrough(ts), {status: resp.status, statusText: resp.statusText, headers: intest});
    for (const k of ['url', 'redirected', 'type']) Object.defineProperty(new_one, k, {value: resp[k], enumerable: true});
    return new_one;
  }

  // ---- fetch
  const nativeFetch = window.fetch;
  async function newFetch(io, args) {
    await firstStatus;
    let input = args[0], init = args[1], url, method, fromRequest;
    try {
      fromRequest = input instanceof Request;
      url = new URL(fromRequest ? input.url : String(input), document.baseURI);
      method = String((init && init.method) || (fromRequest ? input.method : 'GET')).toUpperCase();
    } catch (e) { return Reflect.apply(nativeFetch, io, args); }
    if (!guarded(url)) return Reflect.apply(nativeFetch, io, args);
    if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
      let outcome;
      try {
        const intest = new Headers((init && init.headers) || (fromRequest ? input.headers : undefined));
        const kind = intest.get('content-type') || '';
        let body = init && init.body != null ? init.body : null;
        if (body == null && fromRequest && input.body) {
          const copy = input.clone();
          body = TEXTUAL.test(kind) ? await copy.text() : await copy.blob();
        }
        outcome = await prepare(url, method, kind, body);
      } catch (e) { outcome = {action: 'block'}; }
      if (outcome.action === 'block') throw new TypeError('Failed to fetch');
      if (outcome.action === 'replace') {
        if (init && init.body != null) init = Object.assign({}, init, {body: outcome.body});
        else input = new Request(input, {body: outcome.body});
        args = [input, init];
      }
    }
    const resp = await Reflect.apply(nativeFetch, io, args);
    try { return await wrap(resp, url); } catch (e) { return resp; }
  }
  window.fetch = new Proxy(nativeFetch, {apply(_f, io, args) { return newFetch(io, args); }});

  // ---- XMLHttpRequest: si maschera la richiesta; la risposta la sistema l'estensione nel testo della pagina
  const XP = XMLHttpRequest.prototype, info = new WeakMap();
  const xOpen = XP.open, xSend = XP.send, xIntest = XP.setRequestHeader;
  XP.open = new Proxy(xOpen, {apply(f, io, args) {
    try { info.set(io, {method: String(args[0]).toUpperCase(), url: new URL(String(args[1]), document.baseURI), asynchronous: args[2] !== false, kind: ''}); } catch (e) { /* indirizzo non valido: ci pensa il browser */ }
    return Reflect.apply(f, io, args);
  }});
  XP.setRequestHeader = new Proxy(xIntest, {apply(f, io, args) {
    const i = info.get(io);
    if (i && /^content-type$/i.test(String(args[0]))) i.kind = String(args[1]);
    return Reflect.apply(f, io, args);
  }});
  XP.send = new Proxy(xSend, {apply(f, io, args) {
    const i = info.get(io), body = args[0];
    if (!i || body == null || !S || !guarded(i.url) || !/^(POST|PUT|PATCH)$/.test(i.method)) {
      if (i && body != null && !S && /^(POST|PUT|PATCH)$/.test(i.method) && i.asynchronous) {   // stato non ancora arrivato: si aspetta
        firstStatus.then(() => XP.send.call(io, body));
        return undefined;
      }
      return Reflect.apply(f, io, args);
    }
    if (!i.asynchronous) throw new DOMException('Omissis: richiesta sincrona non protetta, bloccata', 'NetworkError');
    const failed = () => { try { io.abort(); } catch (e) { /* gia' chiusa */ } io.dispatchEvent(new ProgressEvent('error')); };
    prepare(i.url, i.method, i.kind, body).then(outcome => {
      if (outcome.action === 'block') failed();
      else Reflect.apply(f, io, [outcome.action === 'replace' ? outcome.body : body]);
    }, failed);
    return undefined;
  }});

  // ---- WebSocket: non coperto, ma viene segnalato nel registro
  const WS = window.WebSocket;
  if (WS) {
    window.WebSocket = new Proxy(WS, {construct(f, args, fresh) {
      try {
        const u = new URL(String(args[0]), document.baseURI);
        if (S && guarded(u)) ask({t: 'websocket', url: u.href.replace(/^ws/, 'http')}, 5000).catch(() => {});
      } catch (e) { /* indirizzo non valido */ }
      return Reflect.construct(f, args, fresh);
    }});
  }
})();
