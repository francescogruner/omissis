# -*- coding: utf-8 -*-
"""Il codice dell'estensione portato nella pagina di un servizio DAL PROXY.

Nelle app desktop che accettano la porta di debug (ChatGPT, Copilot, Perplexity) lo porta il connettore. L'app di Claude
la porta la rifiuta, ma usa il proxy e i certificati del sistema: la sua finestra e' la pagina di claude.ai, e passa da
qui. Il proxy mette in cima a quella pagina lo stesso content.js dell'estensione: all'Invio il testo viene sostituito
NELLA CASELLA prima che l'app lo legga, e i valori veri tornano nel testo della pagina. Non dipende dal formato in cui
il messaggio poi parte (dal novembre 2026 claude.ai lo manda in protobuf, vedi wire.py).

Come parlano pagina e programma: content.js chiama chrome.runtime.sendMessage; qui «chrome» e' un guscio che fa una
richiesta allo stesso sito, a un indirizzo che non esiste sul sito vero (/__omissis__/...). Quella richiesta passa dal
proxy, che risponde lui (addon.py) girandola al motore come fa il connettore, e NON la inoltra mai al servizio.

Chi risponde a quell'indirizzo? Il guscio lo chiede ogni volta, SENZA chiave e senza testo, prima di mandare qualcosa:
  - Omissis: si lavora;
  - il sito vero: la finestra non passa piu' da Omissis, cioe' chi usa il computer ha tolto la protezione o chiuso il
    programma. La finestra non deve restare bloccata: la prima volta lo si dice e ci si ferma, poi i messaggi passano
    (senza protezione, come avverte il pannello). Al sito vero non arrivano mai ne' la chiave ne' un testo;
  - nessuno: la rete passa ancora da Omissis ma lui e' fermo (protezione in pausa): nemmeno il sito si raggiunge, e il
    messaggio resta fermo;
  - Omissis, ma non riconosce piu' la pagina (riavviato con un segreto nuovo): va ricaricata la finestra.

La pagina e' del servizio: i suoi script girano nello stesso mondo di questo codice (dal proxy non esiste il «mondo
isolato» dell'estensione). Per questo le chiamate vogliono una chiave che sta solo dentro questo codice, e lo script
si toglie dalla pagina appena parte.
"""
import base64
import hashlib
import json
import re
import urllib.request
from pathlib import Path

import catalog
import i18n
import paths

HERE = Path(__file__).resolve().parent
EXT = HERE / "extension"
PREFIX = "/__omissis__/"
MAX_PAGE = 6_000_000

# «chrome» per content.js: messaggi al programma con una richiesta allo stesso sito, che il proxy ferma e a cui risponde
SHELL = r"""
const chrome = (() => {
  const listeners = [], data = {status: __STATUS__, suspended: false, notices: true};
  const headers = {'content-type': 'application/json', 'x-omissis-key': __KEY__};
  const plain = {credentials: 'omit', cache: 'no-store'};
  // here: risponde Omissis | gone: risponde il sito vero (protezione tolta o programma chiuso) | down: non risponde
  // nessuno (Omissis fermo, la rete passa ancora da lui) | stale: Omissis non riconosce piu' questa pagina
  let state = 'here', agreed = false, probed = 0;
  const who = async sure => {
    if (!sure && state === 'gone' && Date.now() - probed < 20000) return state;   // il sito vero non va disturbato di continuo
    let now;
    try { now = (await __fetch(__PREFIX__ + 'here', plain)).headers.get('x-omissis') === '1' ? (state === 'stale' ? 'stale' : 'here') : 'gone'; }
    catch (e) { now = 'down'; }
    probed = Date.now();
    if (now === 'here' && state !== 'here') agreed = false;   // Omissis e' tornato: si ricomincia a proteggere
    state = now;
    return now;
  };
  const ask = async (where, init) => {
    const r = await __fetch(__PREFIX__ + where, {...plain, headers, ...init});
    if (r.headers.get('x-omissis') !== '1') { state = 'gone'; throw new Error('omissis'); }
    if (!r.ok) { if (r.status === 403) state = 'stale'; throw new Error('omissis'); }
    return r.json();
  };
  // «ci sono»: il proxy annota che il codice gira davvero dentro questo programma, con la sua versione
  (async () => { if (await who(true) === 'here') ask('status', {method: 'GET', headers: {...headers, 'x-omissis-hello': '1'}}).catch(() => {}); })();
  setInterval(async () => {
    if (await who(false) !== 'here') return;
    try {
      const fresh = await ask('status', {method: 'GET'});
      if (fresh && fresh.services && JSON.stringify(fresh) !== JSON.stringify(data.status)) {
        data.status = fresh;
        for (const f of listeners) f({status: {newValue: fresh}}, 'local');
      }
    } catch (e) { /* il programma e' fermo: al prossimo messaggio lo si vede */ }
  }, 15000);
  const message = async m => {
    const carries = !!m && (m.t === 'text' || m.t === 'attachment' || m.t === 'request');
    if (await who(carries) === 'here') {
      try { return await ask('call', {method: 'POST', body: JSON.stringify({m})}); }
      catch (e) { if (state === 'here') state = 'down'; }
    }
    if (!carries) return {};
    if (state === 'gone') {   // la prima volta lo si dice e ci si ferma; poi il messaggio passa, senza protezione
      if (agreed) return {action: 'passthrough'};
      agreed = true;
      return {action: 'block', reason: 'gone'};
    }
    return {action: 'block', reason: state === 'stale' ? 'reload' : 'engine'};
  };
  return {
    runtime: {id: 'omissis-proxy', sendMessage: message},
    storage: {local: {get: async () => ({...data})}, onChanged: {addListener: f => { listeners.push(f); }}}
  };
})();
"""

RX_HEAD = re.compile(r"(?is)<head\b[^>]*>")
RX_START = re.compile(r"(?is)<html\b[^>]*>|<!doctype[^>]*>")
RX_NONCE = re.compile(r"""(?is)<script\b[^>]*?\snonce=["']([^"']+)["']""")
RX_GUARDED = re.compile(r"(?i)'(?:nonce|sha256|sha384|sha512)-")


def key():
    """La chiave che il codice nella pagina deve presentare: ricavata dal segreto dell'estensione, uguale da un avvio
    all'altro (una pagina rimasta aperta continua a funzionare) e mai scritta altrove."""
    secret = (paths.DATA / "token_extension.txt").read_text(encoding="utf-8").strip()
    return hashlib.sha256(("pagina:" + secret).encode("utf-8")).hexdigest()[:32]


def bridge(engine, action, data, client, timeout=90):
    token = (paths.DATA / "token_extension.txt").read_text(encoding="utf-8").strip()
    req = urllib.request.Request(f"{engine}/bridge/{action}", data=json.dumps({**data, "via": "app", "client": client}).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-Token": token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def status(engine, client, test=False):
    """Le regole dei servizi dal motore; se non risponde, quelle di partenza (e i messaggi verranno fermati)."""
    try:
        r = bridge(engine, "status", {}, client, 5)
        return {"services": r["services"], "restore": bool(r["restore"]), "block_files": bool(r["block_files"])}
    except Exception:   # noqa: BLE001
        services = [{"id": s["id"], "name": s["name"], "domains": s["domains"], "policy": catalog.default_policy(s),
                     "readable": bool(s["adapter"]), **({"box": True} if s["box"] else {}), **catalog.page(s["id"])}
                    for s in catalog.SERVICES if not s["radar"]]
        if test:
            services.append({"id": "test", "name": "Servizio finto", "domains": ["localhost"], "policy": "protect", "readable": True,
                             **catalog.page("test")})
        return {"services": services, "restore": True, "block_files": False}


def handle(engine, m, client):
    """Lo stesso lavoro che nell'estensione fa background.js e nelle altre app il connettore."""
    m = m if isinstance(m, dict) else {}
    t = m.get("t")
    if t in ("request", "text", "attachment"):
        try:
            return bridge(engine, t, m, client, 300 if t == "attachment" else 90)
        except Exception:   # noqa: BLE001  (mai lasciar partire in chiaro)
            return {"action": "block", "reason": "engine"}
    if t in ("open_up", "chunk", "whole", "values", "websocket"):
        try:
            return bridge(engine, t, m, client, 30)
        except Exception:   # noqa: BLE001  (restano i segnaposto)
            return {}
    if t == "visit":
        try:
            return bridge(engine, "visit", {"host": str(m.get("host", ""))}, client, 5)
        except Exception:   # noqa: BLE001
            return {}
    if t == "type":   # digitare davvero lo sa fare solo il connettore: la pagina usa le sue strade
        return {"ok": False}
    return {}


def source(state):
    """Lo script da mettere in cima alla pagina: il guscio e content.js, in una funzione sola."""
    language = i18n.active() if (EXT / "_locales" / i18n.active() / "messages.json").exists() else "en"
    phrases = {k: v["message"] for k, v in json.loads((EXT / "_locales" / language / "messages.json").read_text(encoding="utf-8")).items()}
    domains = [d for s in state["services"] for d in s["domains"]]
    shell = (SHELL.replace("__STATUS__", json.dumps(state, ensure_ascii=False)).replace("__KEY__", json.dumps(key()))
             .replace("__PREFIX__", json.dumps(PREFIX)))
    return ("(() => {\n"
            "const __fetch = window.fetch.bind(window);\n"   # quello vero: questo script gira prima di quelli del sito
            "try { if (document.currentScript) document.currentScript.remove(); } catch (e) { /* resta li' */ }\n"
            "const __h = location.hostname;\n"
            f"if (!{json.dumps(domains)}.some(d => __h === d || __h.endsWith('.' + d))) return;\n"
            f"globalThis.MSP_TEXTS = {json.dumps(phrases, ensure_ascii=False)};\n"
            "globalThis.MSP_PAGE_WORLD = true;\n"   # questo codice gira nel mondo della pagina: puo' sistemare cio' che va negli appunti
            + shell + (EXT / "content.js").read_text(encoding="utf-8") + "\n})();")


def inject(html, script):
    """(pagina con lo script in cima, impronta dello script per la Content-Security-Policy)."""
    code = script.replace("</script", "<\\/script").replace("<!--", "<\\!--")
    nonce = RX_NONCE.search(html)
    tag = "<script" + (f' nonce="{nonce.group(1)}"' if nonce else "") + ">" + code + "</script>"
    m = RX_HEAD.search(html) or RX_START.search(html)
    at = m.end() if m else 0
    return html[:at] + tag + html[at:], base64.b64encode(hashlib.sha256(code.encode("utf-8")).digest()).decode("ascii")


def allow(policy, digest):
    """Una Content-Security-Policy che lascia girare anche il nostro script: la sua impronta va tra le sorgenti ammesse.
    Dove la regola ammette gia' ogni script scritto nella pagina ('unsafe-inline' senza nonce ne' impronte) non si tocca:
    aggiungere un'impronta spegnerebbe proprio quel permesso."""
    parts = [p.strip() for p in policy.split(";") if p.strip()]
    names = [p.split()[0].lower() for p in parts]
    targets = [n for n in ("script-src", "script-src-elem") if n in names] or (["default-src"] if "default-src" in names else [])
    for i, p in enumerate(parts):
        if names[i] in targets and not ("'unsafe-inline'" in p.lower() and not RX_GUARDED.search(p)):
            parts[i] = p + f" 'sha256-{digest}'"
    return "; ".join(parts)
