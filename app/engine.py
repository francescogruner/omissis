# -*- coding: utf-8 -*-
"""Motore di pseudonimizzazione: servizio locale che sostituisce i dati sensibili con segnaposto
([PERSONA_1], [EMAIL_3]...) e sa riportarli al valore originale.

Gira con l'ambiente Python del modello (benchmark\\.venv) e ascolta SOLO su 127.0.0.1.
Fa eccezione il server di inferenza in rete (remote.py), spento di serie: se nelle impostazioni c'e' «serve», una
seconda porta risponde in HTTPS agli altri PC dell'organizzazione, e solo con le posizioni dei dati trovati dal modello;
se invece c'e' «engine_url» il modello non viene caricato e il riconoscimento lo fa quel server.
Lo usano il proxy (addon.py) e, in futuro, qualunque altra interfaccia (estensione, gateway API).

  POST /mask  {"testi": [...]}        -> {"testi": [...], "mappa": {segnaposto: valore}, "conteggi": {...}, "ms": n}
  POST /values    {"segnaposto": [...]}   -> {"mappa": {segnaposto: valore}}
  GET  /status                             -> {"modello", "device", "voci"}
  POST /bridge/...                         per l'estensione del browser: vedi bridge.py

Ogni richiesta deve portare l'intestazione X-Token con il contenuto di data\\token.txt.
L'estensione ha un codice suo (data\\token_extension.txt) che apre soltanto /bridge/.
L'archivio (data\\vault.sqlite) contiene i valori reali: non esce mai da questo PC ed e' cifrato con la
protezione dei dati di Windows, legata all'utente (data\\vault_key.bin serve all'indice ed e' protetta allo stesso modo).

Uso:  python engine.py [--model <cartella>] [--port 8765] [--device cpu|cuda]
"""
import argparse
import base64
import collections
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
import paths   # noqa: E402
import sistema   # noqa: E402
import remote   # noqa: E402
import settings   # noqa: E402

DATA = paths.DATA
os.environ.setdefault("OMISSIS_LISTS", str(paths.lists()))   # il modello legge da li' le liste personali
sys.path.insert(0, str(paths.model_folder()))
RX_PLACEHOLDER = re.compile(r"\[([A-Z][A-Z_]{1,22})_(\d{1,7})\]")
RX_LABEL = re.compile(r"[A-Z][A-Z_]{1,22}")
EDGES = " `'\"()[]{}<>.,;:"   # cio' che puo' stare attaccato a un valore senza farne parte


class Seal:
    """Cifratura dei valori dell'archivio con la protezione dei dati di Windows (DPAPI): solo l'utente di Windows
    che ha creato l'archivio puo' rileggerlo, anche se il file viene copiato altrove. Non richiede password.
    Sul Mac: AES-GCM con una chiave tenuta nel Portachiavi dell'utente (stesso effetto: il file copiato altrove non
    si legge). Su Linux lo stesso, con il portachiavi del desktop (Secret Service: GNOME Keyring, KWallet, KeePassXC);
    dove il portachiavi non c'e' non cifra, e lo dichiara (attivo = False): resta la cartella dei dati, che puo'
    leggere solo chi usa il computer."""
    PREFIX = "dp1:"
    MAC_PREFIX = "kc1:"

    def __init__(self, folder):
        self.is_active = sys.platform == "win32"
        self._aes = None
        if not self.is_active:   # fuori da Windows: il Portachiavi del Mac (None dove non c'e')
            master = sistema.keychain_secret("vault")
            if master:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
                self._aes, self.is_active, self.PREFIX = AESGCM(master), True, self.MAC_PREFIX
        if self.is_active and self._aes is None:
            import ctypes
            from ctypes import wintypes

            class Block(ctypes.Structure):
                _fields_ = [("n", wintypes.DWORD), ("data", ctypes.c_void_p)]
            self._ct, self._Block = ctypes, Block
            self._crypt, self._kernel = ctypes.windll.crypt32, ctypes.windll.kernel32
            self._kernel.LocalFree.argtypes = [ctypes.c_void_p]
        # chiave per l'indice: serve a ritrovare un valore gia' visto senza tenerlo in chiaro nel file
        f_key = Path(folder) / "vault_key.bin"
        if f_key.exists():
            raw = f_key.read_bytes()
            if not self.is_active and sys.platform.startswith("linux") and len(raw) != 32:
                # l'archivio e' stato cifrato con la chiave del portachiavi, che adesso non risponde: aprirlo lo stesso
                # vorrebbe dire non ritrovare piu' i valori gia' salvati e scriverne di nuovi in chiaro
                raise OSError("l'archivio è cifrato con una chiave custodita nel portachiavi di questo utente, che ora non risponde: "
                              "sblocca il portachiavi (di solito basta accedere al desktop con la password) e riavvia Omissis")
            if not self.is_active:
                self.key = raw
            elif self._aes is not None and len(raw) == 32:
                # chiave scritta in chiaro quando il Portachiavi non c'era (o da una versione senza cifratura): ora si sigilla
                self.key = raw
                f_key.write_bytes(self._close(raw))
            else:
                self.key = self._open_up(raw)
        else:
            self.key = secrets.token_bytes(32)
            f_key.write_bytes(self._close(self.key) if self.is_active else self.key)

    def _dpapi(self, data, encrypt):
        ct = self._ct
        buffer = ct.create_string_buffer(data, len(data))
        enter, exits = self._Block(len(data), ct.cast(buffer, ct.c_void_p)), self._Block()
        func = self._crypt.CryptProtectData if encrypt else self._crypt.CryptUnprotectData
        if not func(ct.byref(enter), None, None, None, None, 0x01, ct.byref(exits)):   # 0x01: mai finestre di richiesta
            raise OSError("la protezione dei dati di Windows ha rifiutato l'operazione (archivio di un altro utente?)")
        try:
            return ct.string_at(exits.data, exits.n)
        finally:
            self._kernel.LocalFree(exits.data)

    def _close(self, data):
        if self._aes is not None:
            nonce = secrets.token_bytes(12)
            return nonce + self._aes.encrypt(nonce, data, None)
        return self._dpapi(data, True)

    def _open_up(self, data):
        if self._aes is not None:
            return self._aes.decrypt(data[:12], data[12:], None)
        return self._dpapi(data, False)

    def encrypt(self, value):
        if not self.is_active:
            return value
        return self.PREFIX + base64.b64encode(self._close(value.encode("utf-8"))).decode("ascii")

    def decrypt(self, saved):
        if not saved.startswith(self.PREFIX):
            return saved   # archivio di una versione precedente, o sistema senza cifratura
        return self._open_up(base64.b64decode(saved[len(self.PREFIX):])).decode("utf-8")

    def index(self, value_normalized):
        return hmac.new(self.key, value_normalized.encode("utf-8"), hashlib.sha256).hexdigest()


class Vault:
    """Corrispondenza stabile valore <-> segnaposto. Lo stesso valore ha sempre lo stesso segnaposto,
    cosi' una conversazione riaperta giorni dopo si puo' ancora ripristinare. Nel file i valori sono
    cifrati (vedi Sigillo) e l'indice per ritrovarli e' un'impronta con chiave, non il valore.
    Un numero non viene mai riusato: un segnaposto eliminato non torna a indicare un altro valore."""
    ORDERS = {"recent": "created DESC", "used": "used DESC", "idle": "used ASC", "kind": "label, n"}

    def __init__(self, path):
        self.seal = Seal(Path(path).parent)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS entries (label TEXT, n INTEGER, key TEXT, value TEXT, "
                        "created REAL, used REAL, PRIMARY KEY (label, n))")
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS by_key ON entries (label, key)")
        if "used" not in {r[1] for r in self.db.execute("PRAGMA table_info(entries)")}:   # archivio di una versione precedente
            self.db.execute("ALTER TABLE entries ADD COLUMN used REAL")
            self.db.execute("UPDATE entries SET used = created")
        self.db.execute("CREATE TABLE IF NOT EXISTS counters (label TEXT PRIMARY KEY, last INTEGER)")
        self.db.execute("INSERT OR IGNORE INTO counters SELECT label, MAX(n) FROM entries GROUP BY label")
        self.db.commit()
        self.lock = threading.Lock()
        self.read_items = {}   # segnaposto -> valore: evita di decifrare a ogni richiesta
        self.touched, self.written = {}, time.time()   # (etichetta, n) -> ultimo uso, da scrivere ogni tanto
        self.pending = False   # ci sono valori nuovi non ancora scritti sul disco (vedi flush)
        self.converted_ones = self._convert()

    def _convert(self):
        """Un archivio scritto in chiaro da una versione precedente viene cifrato alla prima apertura."""
        if not self.seal.is_active:
            return 0
        lines = self.db.execute("SELECT label, n, value FROM entries WHERE value NOT LIKE ?", (self.seal.PREFIX + "%",)).fetchall()
        if not lines:
            return 0
        with self.db:   # tutto o niente
            for label, n, value in lines:
                self.db.execute("UPDATE entries SET key=?, value=? WHERE label=? AND n=?",
                                (self.seal.index(self.key(value)), self.seal.encrypt(value), label, n))
        self.db.execute("VACUUM")   # toglie dal file anche le vecchie pagine con i valori in chiaro
        return len(lines)

    @staticmethod
    def key(value):
        return re.sub(r"\s+", " ", value).strip().casefold()

    def _touch(self, label, n):
        """Segna l'ultimo uso (con il lucchetto preso). Si scrive sul disco ogni tanto, non a ogni messaggio."""
        self.touched[(label, n)] = time.time()
        if len(self.touched) > 2000 or time.time() - self.written > 120:
            self._write_touched()

    def _write_touched(self):
        if self.touched:
            self.db.executemany("UPDATE entries SET used=? WHERE label=? AND n=?", [(when, e, n) for (e, n), when in self.touched.items()])
            self.db.commit()
            self.touched.clear()
        self.written = time.time()

    def placeholder(self, label, value, commit=True):
        """commit=False: il valore nuovo resta in sospeso finche' non si chiama flush(). Chi maschera un testo scrive
        cosi' sul disco una volta sola per richiesta invece che una per valore (ogni scrittura costa qualche millisecondo)."""
        k = self.seal.index(self.key(value))
        with self.lock:
            r = self.db.execute("SELECT n FROM entries WHERE label=? AND key=?", (label, k)).fetchone()
            if r is None:
                n = self.db.execute("SELECT MAX(COALESCE((SELECT last FROM counters WHERE label=?), 0), "
                                    "COALESCE((SELECT MAX(n) FROM entries WHERE label=?), 0)) + 1", (label, label)).fetchone()[0]
                stamp = time.time()
                self.db.execute("INSERT INTO entries (label, n, key, value, created, used) VALUES (?, ?, ?, ?, ?, ?)",
                                (label, n, k, self.seal.encrypt(value), stamp, stamp))
                self.db.execute("INSERT OR REPLACE INTO counters VALUES (?, ?)", (label, n))
                if commit:
                    self.db.commit()
                else:
                    self.pending = True
                self.read_items[f"[{label}_{n}]"] = value
            else:
                n = r[0]
                self._touch(label, n)
        return f"[{label}_{n}]"

    def flush(self):
        """Scrive sul disco i valori lasciati in sospeso. Va chiamata PRIMA di restituire i segnaposto a chi li ha chiesti:
        un segnaposto uscito dal PC senza il suo valore nell'archivio non si potrebbe piu' ripristinare."""
        with self.lock:
            if self.pending:
                self.db.commit()
                self.pending = False

    def value(self, placeholder):
        m = RX_PLACEHOLDER.fullmatch(placeholder)
        if not m:
            return None
        with self.lock:
            if placeholder in self.read_items:
                self._touch(m.group(1), int(m.group(2)))
                return self.read_items[placeholder]
            r = self.db.execute("SELECT value FROM entries WHERE label=? AND n=?", (m.group(1), int(m.group(2)))).fetchone()
            if r is None:
                return None
            if len(self.read_items) > 50000:
                self.read_items.clear()
            v = self.read_items[placeholder] = self.seal.decrypt(r[0])
            self._touch(m.group(1), int(m.group(2)))
        return v

    def entries(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]

    def listing(self, limit=500, reveal=False, search="", label="", order="recent"):
        """Le voci, al massimo `limite`. cerca: un pezzo del segnaposto o del valore vero (la ricerca guarda i valori veri
        anche quando non vengono mostrati). Senza in_chiaro il valore e' ridotto alla prima lettera e alla lunghezza."""
        search = str(search or "").strip().casefold()
        with self.lock:
            self._write_touched()
            lines = self.db.execute("SELECT label, n, value, created, used FROM entries" + (" WHERE label=?" if label else "")
                                    + " ORDER BY " + self.ORDERS.get(order, self.ORDERS["recent"]), (label,) if label else ()).fetchall()
            by_label = dict(self.db.execute("SELECT label, COUNT(*) FROM entries GROUP BY label").fetchall())
        entries, matches = [], 0
        day = lambda x: time.strftime("%Y-%m-%d %H:%M", time.localtime(x or 0))   # noqa: E731
        for e, n, saved, c, u in lines:
            seg, v = f"[{e}_{n}]", None
            if search and search not in seg.casefold():
                v = self.seal.decrypt(saved)
                if search not in v.casefold():
                    continue
            matches += 1
            if len(entries) < limit:
                v = self.seal.decrypt(saved) if v is None else v
                entries.append({"placeholder": seg, "label": e, "value": v if reveal else (v[:1] + "•" * min(len(v) - 1, 11) if len(v) > 1 else "•"),
                             "created": day(c), "used": day(u or c)})
        return {"by_label": by_label, "entries": entries, "encrypted": self.seal.is_active, "total": sum(by_label.values()), "matches": matches}

    def remove(self, placeholder=(), label="", idle_days=None, count_only=False):
        """Elimina le voci indicate una per una, oppure tutte quelle di un tipo e/o non usate da N giorni.
        solo_conta: dice quante sarebbero, senza toccare nulla. I numeri eliminati non vengono riusati."""
        pairs = [(m.group(1), int(m.group(2))) for s in placeholder if (m := RX_PLACEHOLDER.fullmatch(str(s)))]
        where, values = [], []
        if label:
            where.append("label=?"), values.append(str(label))
        if idle_days is not None:
            where.append("COALESCE(used, created) < ?"), values.append(time.time() - 86400 * max(0.0, float(idle_days)))
        if not pairs and not where:
            return {"removed": 0, "entries": self.entries()}
        with self.lock:
            self._write_touched()
            if pairs:
                n = sum(self.db.execute("SELECT COUNT(*) FROM entries WHERE label=? AND n=?", c).fetchone()[0] for c in pairs)
            else:
                n = self.db.execute("SELECT COUNT(*) FROM entries WHERE " + " AND ".join(where), values).fetchone()[0]
            if n and not count_only:
                if pairs:
                    self.db.executemany("DELETE FROM entries WHERE label=? AND n=?", pairs)
                else:
                    self.db.execute("DELETE FROM entries WHERE " + " AND ".join(where), values)
                self.db.commit()
                self.read_items.clear()
            rest = self.db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        return {"removed": n, "entries": rest}

    def clear(self):
        with self.lock:
            self.touched.clear()
            self.db.execute("DELETE FROM entries")   # i contatori restano: i numeri non ripartono da 1
            self.db.commit()
            self.db.execute("VACUUM")
            self.read_items.clear()


class Engine:
    def __init__(self, model, device=None):
        cfg = settings.read()
        self.remote = remote.configured(cfg)
        if self.remote:   # il modello lo ha un server della rete: qui restano regole, elenchi, segnaposto e archivio
            self.det = remote.detector(cfg)
        else:
            from inference import Detector
            self.det = Detector(model, device=device)
        self.vault = Vault(DATA / "vault.sqlite")
        self.lock = threading.Lock()                # un'inferenza per volta
        self.cache = collections.OrderedDict()           # testo gia' visto -> span (le cronologie si ripetono)
        self.profile()

    def profile(self):
        """Le categorie che il modello conosce ma che di serie restano in chiaro (date, professioni, dati particolari...):
        accende quelle scelte nelle impostazioni («categorie»). Restituisce cosa c'e' e cosa e' acceso."""
        known = list(self.det.off_model)
        enabled = [e for e in settings.read().get("categories") or [] if e in known]
        off = [e for e in known if e not in enabled]
        if off != self.det.off:
            with self.lock:
                self.det.configure_off(off)
                self.cache.clear()
        return {"known": known, "enabled": enabled}

    def _span(self, texts):
        keys = [hashlib.sha256(t.encode("utf-8")).digest() for t in texts]
        new_items = [i for i, k in enumerate(keys) if k not in self.cache]
        if new_items:
            with self.lock:
                for i, sp in zip(new_items, self.det.many([texts[i] for i in new_items], complete=True)):
                    self.cache[keys[i]] = sp
            while len(self.cache) > 4000:
                self.cache.popitem(last=False)
        return [self.cache[k] for k in keys]

    def detect(self, texts, on=()):
        """Per un altro PC della rete (remote.py): solo cio' che trova il modello. Niente regole ne' elenchi, che ogni PC
        applica da se', e niente archivio: i segnaposto e i valori veri nascono e restano sul PC che ha chiesto.
        on: le categorie in piu' accese su quel PC; valgono per questa richiesta e basta."""
        t0 = time.perf_counter()
        wanted = sorted(e for e in self.det.off_model if e not in set(on))
        with self.lock:
            mine = list(self.det.off)
            try:
                if wanted != mine:
                    self.det.configure_off(wanted)
                spans = self.det.many(texts)
            finally:
                if wanted != mine:
                    self.det.configure_off(mine)
        return {"spans": spans, "ms": round((time.perf_counter() - t0) * 1000)}

    @staticmethod
    def _merge(spans):
        """Span ordinati e senza sovrapposizioni (vince il primo, esteso fino alla fine del piu' lungo)."""
        out = []
        for s, e, l in sorted(spans, key=lambda x: (x[0], -x[1])):
            if out and s < out[-1][1]:
                out[-1][1] = max(out[-1][1], e)
            else:
                out.append([s, e, l])
        return out

    def mask(self, texts, exclude=(), never=(), also=None, keep=True):
        """keep=False: una prova con dati d'esempio. I segnaposto valgono solo per questa risposta e nell'archivio non entra nulla.
        escludi: etichette da NON sostituire in questa chiamata (es. quelle tecniche nel contesto di un agente).
        mai: termini da non sostituire in questa chiamata (es. i nomi degli strumenti dichiarati da un agente).
        anche: {termine: etichetta} da sostituire comunque, ovunque compaiano (le correzioni fatte a mano nel pannello)."""
        # i gruppi di dati che chi usa il PC ha spento nelle impostazioni valgono per ogni strada (browser, app, terminale,
        # documenti, MCP): tutte passano da qui. Cio' che e' stato scelto a mano («anche», liste personali) resta comunque.
        exclude = set(exclude) | settings.labels_off()
        never = {str(x).strip(EDGES).casefold() for x in never}   # stessa pulizia dei bordi usata sotto: «Nevatek S.r.l.» finisce con un punto
        also = {str(v).strip(): (str(l) if RX_LABEL.fullmatch(str(l)) else "ELENCO") for v, l in (also or {}).items() if str(v).strip()}
        t0 = time.perf_counter()
        # i segnaposto gia' presenti non si toccano: mascherare due volte lo stesso testo deve dare lo stesso testo
        # (succede con un testo incollato gia' mascherato e con il secondo controllo fatto prima dell'invio)
        busy = [[(m.start(), m.end()) for m in RX_PLACEHOLDER.finditer(t)] if "[" in t else [] for t in texts]

        def free(spans, i):
            return [sp for sp in spans if sp[2] not in exclude and not any(sp[0] < e and s < sp[1] for s, e in busy[i])
                    and (not never or texts[i][sp[0]:sp[1]].strip(EDGES).casefold() not in never)
                    # la casella generica di un'azienda (info@, amministrazione@...) non e' un dato personale: resta in chiaro
                    and not (sp[2] == "EMAIL" and settings.role_mailbox(texts[i][sp[0]:sp[1]]))]
        by_text = [free(self._merge(sp), i) for i, sp in enumerate(self._span(texts))]
        # un valore riconosciuto in un testo va coperto anche dove ricompare negli altri (es. nella
        # cronologia), anche se li' il modello non lo ha segnalato
        well_known = {}
        for t, sp in zip(texts, by_text):
            for s, e, l in sp:
                v = t[s:e]
                if len(v) >= 4 and any(c.isalnum() for c in v):
                    well_known.setdefault(v, l)
        if well_known:
            rx = re.compile("|".join(re.escape(v) for v in sorted(well_known, key=len, reverse=True)))
            for i, t in enumerate(texts):
                extra = [[m.start(), m.end(), well_known[m.group()]] for m in rx.finditer(t)
                         if not any(s < m.end() and m.start() < e for s, e, _ in by_text[i])]
                if extra:
                    by_text[i] = free(self._merge(by_text[i] + extra), i)
        if also:   # scelti a mano: vincono su cio' che ha trovato il modello negli stessi punti
            by_term = {v.casefold(): l for v, l in also.items()}
            rx = re.compile("|".join(re.escape(v) for v in sorted(also, key=len, reverse=True)), re.I)
            for i, t in enumerate(texts):
                forced = [[m.start(), m.end(), by_term.get(m.group().casefold(), "ELENCO")] for m in rx.finditer(t)
                           if not any(m.start() < e and s < m.end() for s, e in busy[i])]
                if forced:
                    by_text[i] = sorted(forced + [sp for sp in by_text[i] if not any(sp[0] < f[1] and f[0] < sp[1] for f in forced)])
        mapping, counts, exited, positions = {}, collections.Counter(), [], []
        example, numbers = {}, collections.Counter()   # keep=False: segnaposto di questa risposta soltanto

        def placeholder(label, value):
            if keep:
                return self.vault.placeholder(label, value, commit=False)
            k = (label, Vault.key(value))
            if k not in example:
                numbers[label] += 1
                example[k] = f"[{label}_{numbers[label]}]"
            return example[k]
        try:
            for t, sp in zip(texts, by_text):
                chunks, pos, where = [], 0, []
                for s, e, l in sp:
                    seg = placeholder(l, t[s:e])
                    mapping.setdefault(seg, t[s:e])
                    counts[l] += 1
                    chunks += [t[pos:s], seg]
                    where.append([s, e, seg])
                    pos = e
                exited.append("".join(chunks) + t[pos:])
                positions.append(where)
        finally:
            self.vault.flush()   # una scrittura sola per tutta la richiesta, e comunque prima di rispondere
        # "posizioni": per ogni testo, [inizio, fine, segnaposto] riferiti al testo ORIGINALE (serve ai documenti,
        # dove la sostituzione va riportata dentro pezzi di testo con formattazioni diverse)
        return {"texts": exited, "positions": positions, "mapping": mapping, "counts": dict(counts),
                "ms": round((time.perf_counter() - t0) * 1000)}

    def values(self, placeholder):
        return {"mapping": {s: v for s in placeholder if (v := self.vault.value(s)) is not None}}


def serve(engine, port, token, extension_token, bridge):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):   # niente righe di log con i percorsi
            pass

        def _respond(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._extension()
            self.end_headers()
            self.wfile.write(body)

        def _extension(self):
            """Le estensioni del browser possono chiamare il motore (serve comunque il codice)."""
            origin = self.headers.get("Origin", "")
            if origin.startswith(("chrome-extension://", "moz-extension://")):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                if self.headers.get("Access-Control-Request-Private-Network"):
                    self.send_header("Access-Control-Allow-Private-Network", "true")

        def _authorized(self):
            if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
                self._respond(403, {"error": "host non ammesso"})
                return False
            data_item = self.headers.get("X-Token", "")
            if secrets.compare_digest(data_item, token) or \
                    (self.path.startswith("/bridge/") and secrets.compare_digest(data_item, extension_token)):
                return True
            self._respond(403, {"error": "token mancante o errato"})
            return False

        def do_OPTIONS(self):
            self.send_response(204)
            self._extension()
            self.send_header("Access-Control-Allow-Headers", "content-type, x-token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if self.path in ("/status", "/st" + "ato") and self._authorized():
                self._respond(200, {"model": str(engine.det.mod.name_or_path), "device": engine.det.device,
                                     "threshold": engine.det.threshold, "entries": engine.vault.entries(),
                                     "vault_encrypted": engine.vault.seal.is_active,
                                     "remote": dict(engine.det.state) if engine.remote else None, "shared": remote.shared()})

        def do_POST(self):
            if not self._authorized():
                return
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                if self.path.startswith("/bridge/"):
                    outcome = bridge.handle(self.path[len("/bridge/"):], data if isinstance(data, dict) else {})
                    self._respond(404 if outcome is None else 200, {"error": "percorso sconosciuto"} if outcome is None else outcome)
                elif self.path == "/mask":
                    self._respond(200, engine.mask([str(t) for t in data["texts"]], {str(e) for e in data.get("exclude") or []}, data.get("never") or (),
                                                           data.get("also") if isinstance(data.get("also"), dict) else None, keep=not data.get("demo")))
                elif self.path == "/values":
                    self._respond(200, engine.values([str(s) for s in data["placeholder"]]))
                elif self.path == "/vault":
                    self._respond(200, engine.vault.listing(int(data.get("limit", 500)), bool(data.get("reveal")), str(data.get("search") or ""),
                                                               str(data.get("label") or ""), str(data.get("order") or "recent")))
                elif self.path == "/vault/delete":
                    days = data.get("idle_days")
                    self._respond(200, engine.vault.remove([str(s) for s in data.get("placeholder") or []], str(data.get("label") or ""),
                                                                None if days is None else float(days), bool(data.get("count_only"))))
                elif self.path == "/vault/clear":
                    engine.vault.clear()
                    self._respond(200, {"entries": 0})
                elif self.path == "/profile":   # il pannello ha cambiato le categorie accese, o chiede quali sono
                    self._respond(200, engine.profile())
                elif self.path == "/lists":   # il pannello ha cambiato lists\never.txt o lists\always.txt
                    with engine.lock:
                        engine.det.configure_lists()
                        engine.cache.clear()
                    self._respond(200, {"never": len(engine.det.never), "always": engine.det.rx_always is not None})
                else:
                    self._respond(404, {"error": "percorso sconosciuto"})
            except Exception as ex:   # noqa: BLE001  (il chiamante deve sapere che NON e' stato mascherato nulla)
                self._respond(500, {"error": type(ex).__name__})

    class Service(ThreadingHTTPServer):
        # su Windows, altrimenti, due copie potrebbero aprire la stessa porta senza errore; sul Mac e su Linux serve
        # invece a ripartire subito dopo una chiusura (li' due servizi sulla stessa porta non si aprono comunque)
        allow_reuse_address = sys.platform != "win32"

    Service(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", dest="model", default=str(paths.model(paths.default_model())))
    ap.add_argument("--port", dest="port", type=int, default=8765)
    ap.add_argument("--device", default=None)
    a = ap.parse_args()
    sistema.follow_parent()   # avviato dal pannello, si chiude con lui: non resta mai acceso da solo a tenere la porta
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    DATA.mkdir(parents=True, exist_ok=True)
    f_token, f_extension = DATA / "token.txt", DATA / "token_extension.txt"
    for f in (f_token, f_extension):
        if not f.exists():
            f.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    m = Engine(a.model, a.device)
    try:
        m.mask(["warmup"])
    except remote.Failure:   # il server della rete non risponde adesso: il motore parte lo stesso, e il pannello lo dice
        pass
    cfg = settings.read()
    if cfg.get("serve") and not m.remote:   # presta il modello agli altri PC: certificato e chiave li ha preparati il pannello
        folder = DATA / "server"
        try:
            access = (folder / "access.txt").read_text(encoding="utf-8").strip()
            threading.Thread(target=remote.share, args=(m, int(cfg["serve_port"]), access, folder / "cert.pem", folder / "key.pem"), daemon=True).start()
        except OSError:
            pass
    print(f"motore pronto su http://127.0.0.1:{a.port} | modello {Path(a.model).name} | {m.det.device} | voci in archivio: {m.vault.entries()}")
    from bridge import Bridge
    serve(m, a.port, f_token.read_text(encoding="utf-8").strip(), f_extension.read_text(encoding="utf-8").strip(), Bridge(m))
