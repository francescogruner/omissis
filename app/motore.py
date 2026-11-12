# -*- coding: utf-8 -*-
"""Motore di pseudonimizzazione: servizio locale che sostituisce i dati sensibili con segnaposto
([PERSONA_1], [EMAIL_3]...) e sa riportarli al valore originale.

Gira con l'ambiente Python del modello (benchmark\\.venv) e ascolta SOLO su 127.0.0.1.
Lo usano il proxy (addon.py) e, in futuro, qualunque altra interfaccia (estensione, gateway API).

  POST /maschera  {"testi": [...]}        -> {"testi": [...], "mappa": {segnaposto: valore}, "conteggi": {...}, "ms": n}
  POST /valori    {"segnaposto": [...]}   -> {"mappa": {segnaposto: valore}}
  GET  /stato                             -> {"modello", "device", "voci"}
  POST /ponte/...                         per l'estensione del browser: vedi ponte.py

Ogni richiesta deve portare l'intestazione X-Token con il contenuto di dati\\token.txt.
L'estensione ha un codice suo (dati\\token_estensione.txt) che apre soltanto /ponte/.
L'archivio (dati\\archivio.sqlite) contiene i valori reali: non esce mai da questo PC ed e' cifrato con la
protezione dei dati di Windows, legata all'utente (dati\\chiave_archivio.bin serve all'indice ed e' protetta allo stesso modo).

Uso:  python motore.py [--modello <cartella>] [--porta 8765] [--device cpu|cuda]
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

QUI = Path(__file__).resolve().parent
import percorsi   # noqa: E402

DATI = percorsi.DATI
os.environ.setdefault("OMISSIS_LISTE", str(percorsi.liste()))   # il modello legge da li' le liste personali
sys.path.insert(0, str(percorsi.cartella_modello()))
RX_SEGNAPOSTO = re.compile(r"\[([A-Z][A-Z_]{1,22})_(\d{1,7})\]")


class Sigillo:
    """Cifratura dei valori dell'archivio con la protezione dei dati di Windows (DPAPI): solo l'utente di Windows
    che ha creato l'archivio puo' rileggerlo, anche se il file viene copiato altrove. Non richiede password.
    Fuori da Windows non cifra (e lo dichiara: attivo = False)."""
    PREFISSO = "dp1:"

    def __init__(self, cartella):
        self.attivo = sys.platform == "win32"
        if self.attivo:
            import ctypes
            from ctypes import wintypes

            class Blocco(ctypes.Structure):
                _fields_ = [("n", wintypes.DWORD), ("dati", ctypes.c_void_p)]
            self._ct, self._Blocco = ctypes, Blocco
            self._crypt, self._kernel = ctypes.windll.crypt32, ctypes.windll.kernel32
            self._kernel.LocalFree.argtypes = [ctypes.c_void_p]
        # chiave per l'indice: serve a ritrovare un valore gia' visto senza tenerlo in chiaro nel file
        f_chiave = Path(cartella) / "chiave_archivio.bin"
        if f_chiave.exists():
            self.chiave = self._apri(f_chiave.read_bytes()) if self.attivo else f_chiave.read_bytes()
        else:
            self.chiave = secrets.token_bytes(32)
            f_chiave.write_bytes(self._chiudi(self.chiave) if self.attivo else self.chiave)

    def _dpapi(self, dati, cifra):
        ct = self._ct
        tampone = ct.create_string_buffer(dati, len(dati))
        entra, esce = self._Blocco(len(dati), ct.cast(tampone, ct.c_void_p)), self._Blocco()
        funzione = self._crypt.CryptProtectData if cifra else self._crypt.CryptUnprotectData
        if not funzione(ct.byref(entra), None, None, None, None, 0x01, ct.byref(esce)):   # 0x01: mai finestre di richiesta
            raise OSError("la protezione dei dati di Windows ha rifiutato l'operazione (archivio di un altro utente?)")
        try:
            return ct.string_at(esce.dati, esce.n)
        finally:
            self._kernel.LocalFree(esce.dati)

    def _chiudi(self, dati):
        return self._dpapi(dati, True)

    def _apri(self, dati):
        return self._dpapi(dati, False)

    def cifra(self, valore):
        if not self.attivo:
            return valore
        return self.PREFISSO + base64.b64encode(self._chiudi(valore.encode("utf-8"))).decode("ascii")

    def decifra(self, salvato):
        if not salvato.startswith(self.PREFISSO):
            return salvato   # archivio di una versione precedente, o sistema senza cifratura
        return self._apri(base64.b64decode(salvato[len(self.PREFISSO):])).decode("utf-8")

    def indice(self, valore_normalizzato):
        return hmac.new(self.chiave, valore_normalizzato.encode("utf-8"), hashlib.sha256).hexdigest()


class Archivio:
    """Corrispondenza stabile valore <-> segnaposto. Lo stesso valore ha sempre lo stesso segnaposto,
    cosi' una conversazione riaperta giorni dopo si puo' ancora ripristinare. Nel file i valori sono
    cifrati (vedi Sigillo) e l'indice per ritrovarli e' un'impronta con chiave, non il valore."""

    def __init__(self, percorso):
        self.sigillo = Sigillo(Path(percorso).parent)
        self.db = sqlite3.connect(percorso, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS voci (etichetta TEXT, n INTEGER, chiave TEXT, valore TEXT, "
                        "creato REAL, PRIMARY KEY (etichetta, n))")
        self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS per_chiave ON voci (etichetta, chiave)")
        self.lucchetto = threading.Lock()
        self.letti = {}   # segnaposto -> valore: evita di decifrare a ogni richiesta
        self.convertiti = self._converti()

    def _converti(self):
        """Un archivio scritto in chiaro da una versione precedente viene cifrato alla prima apertura."""
        if not self.sigillo.attivo:
            return 0
        righe = self.db.execute("SELECT etichetta, n, valore FROM voci WHERE valore NOT LIKE ?", (Sigillo.PREFISSO + "%",)).fetchall()
        if not righe:
            return 0
        with self.db:   # tutto o niente
            for etichetta, n, valore in righe:
                self.db.execute("UPDATE voci SET chiave=?, valore=? WHERE etichetta=? AND n=?",
                                (self.sigillo.indice(self.chiave(valore)), self.sigillo.cifra(valore), etichetta, n))
        self.db.execute("VACUUM")   # toglie dal file anche le vecchie pagine con i valori in chiaro
        return len(righe)

    @staticmethod
    def chiave(valore):
        return re.sub(r"\s+", " ", valore).strip().casefold()

    def segnaposto(self, etichetta, valore):
        k = self.sigillo.indice(self.chiave(valore))
        with self.lucchetto:
            r = self.db.execute("SELECT n FROM voci WHERE etichetta=? AND chiave=?", (etichetta, k)).fetchone()
            if r is None:
                n = self.db.execute("SELECT COALESCE(MAX(n), 0) + 1 FROM voci WHERE etichetta=?", (etichetta,)).fetchone()[0]
                self.db.execute("INSERT INTO voci VALUES (?, ?, ?, ?, ?)", (etichetta, n, k, self.sigillo.cifra(valore), time.time()))
                self.db.commit()
                self.letti[f"[{etichetta}_{n}]"] = valore
            else:
                n = r[0]
        return f"[{etichetta}_{n}]"

    def valore(self, segnaposto):
        m = RX_SEGNAPOSTO.fullmatch(segnaposto)
        if not m:
            return None
        with self.lucchetto:
            if segnaposto in self.letti:
                return self.letti[segnaposto]
            r = self.db.execute("SELECT valore FROM voci WHERE etichetta=? AND n=?", (m.group(1), int(m.group(2)))).fetchone()
            if r is None:
                return None
            if len(self.letti) > 50000:
                self.letti.clear()
            v = self.letti[segnaposto] = self.sigillo.decifra(r[0])
        return v

    def voci(self):
        with self.lucchetto:
            return self.db.execute("SELECT COUNT(*) FROM voci").fetchone()[0]

    def elenco(self, limite=500, in_chiaro=False):
        """Voci piu' recenti. Senza in_chiaro il valore e' ridotto alla prima lettera e alla lunghezza."""
        with self.lucchetto:
            righe = self.db.execute("SELECT etichetta, n, valore, creato FROM voci ORDER BY creato DESC LIMIT ?", (limite,)).fetchall()
            per_tipo = dict(self.db.execute("SELECT etichetta, COUNT(*) FROM voci GROUP BY etichetta").fetchall())
        voci = []
        for e, n, salvato, c in righe:
            v = self.sigillo.decifra(salvato)
            voci.append({"segnaposto": f"[{e}_{n}]", "etichetta": e, "valore": v if in_chiaro else v[:1] + "•" * min(len(v) - 1, 11),
                         "creato": time.strftime("%Y-%m-%d %H:%M", time.localtime(c))})
        return {"per_tipo": per_tipo, "voci": voci, "cifrato": self.sigillo.attivo}

    def svuota(self):
        with self.lucchetto:
            self.db.execute("DELETE FROM voci")
            self.db.commit()
            self.db.execute("VACUUM")
            self.letti.clear()


class Motore:
    def __init__(self, modello, device=None):
        from inferenza import Rilevatore
        self.ril = Rilevatore(modello, device=device)
        self.archivio = Archivio(DATI / "archivio.sqlite")
        self.lucchetto = threading.Lock()                # un'inferenza per volta
        self.cache = collections.OrderedDict()           # testo gia' visto -> span (le cronologie si ripetono)

    def _span(self, testi):
        chiavi = [hashlib.sha256(t.encode("utf-8")).digest() for t in testi]
        nuovi = [i for i, k in enumerate(chiavi) if k not in self.cache]
        if nuovi:
            with self.lucchetto:
                for i, sp in zip(nuovi, self.ril.molti([testi[i] for i in nuovi], completo=True)):
                    self.cache[chiavi[i]] = sp
            while len(self.cache) > 4000:
                self.cache.popitem(last=False)
        return [self.cache[k] for k in chiavi]

    @staticmethod
    def _unisci(spans):
        """Span ordinati e senza sovrapposizioni (vince il primo, esteso fino alla fine del piu' lungo)."""
        out = []
        for s, e, l in sorted(spans, key=lambda x: (x[0], -x[1])):
            if out and s < out[-1][1]:
                out[-1][1] = max(out[-1][1], e)
            else:
                out.append([s, e, l])
        return out

    def maschera(self, testi, escludi=(), mai=()):
        """escludi: etichette da NON sostituire in questa chiamata (es. quelle tecniche nel contesto di un agente).
        mai: termini da non sostituire in questa chiamata (es. i nomi degli strumenti dichiarati da un agente)."""
        mai = {str(x).casefold() for x in mai}
        t0 = time.perf_counter()
        # i segnaposto gia' presenti non si toccano: mascherare due volte lo stesso testo deve dare lo stesso testo
        # (succede con un testo incollato gia' mascherato e con il secondo controllo fatto prima dell'invio)
        occupati = [[(m.start(), m.end()) for m in RX_SEGNAPOSTO.finditer(t)] if "[" in t else [] for t in testi]

        def liberi(spans, i):
            return [sp for sp in spans if sp[2] not in escludi and not any(sp[0] < e and s < sp[1] for s, e in occupati[i])
                    and (not mai or testi[i][sp[0]:sp[1]].strip(" `'\"()[]{}<>.,;:").casefold() not in mai)]
        per_testo = [liberi(self._unisci(sp), i) for i, sp in enumerate(self._span(testi))]
        # un valore riconosciuto in un testo va coperto anche dove ricompare negli altri (es. nella
        # cronologia), anche se li' il modello non lo ha segnalato
        noti = {}
        for t, sp in zip(testi, per_testo):
            for s, e, l in sp:
                v = t[s:e]
                if len(v) >= 4 and any(c.isalnum() for c in v):
                    noti.setdefault(v, l)
        if noti:
            rx = re.compile("|".join(re.escape(v) for v in sorted(noti, key=len, reverse=True)))
            for i, t in enumerate(testi):
                extra = [[m.start(), m.end(), noti[m.group()]] for m in rx.finditer(t)
                         if not any(s < m.end() and m.start() < e for s, e, _ in per_testo[i])]
                if extra:
                    per_testo[i] = liberi(self._unisci(per_testo[i] + extra), i)
        mappa, conteggi, usciti, posizioni = {}, collections.Counter(), [], []
        for t, sp in zip(testi, per_testo):
            pezzi, pos, dove = [], 0, []
            for s, e, l in sp:
                seg = self.archivio.segnaposto(l, t[s:e])
                mappa.setdefault(seg, t[s:e])
                conteggi[l] += 1
                pezzi += [t[pos:s], seg]
                dove.append([s, e, seg])
                pos = e
            usciti.append("".join(pezzi) + t[pos:])
            posizioni.append(dove)
        # "posizioni": per ogni testo, [inizio, fine, segnaposto] riferiti al testo ORIGINALE (serve ai documenti,
        # dove la sostituzione va riportata dentro pezzi di testo con formattazioni diverse)
        return {"testi": usciti, "posizioni": posizioni, "mappa": mappa, "conteggi": dict(conteggi),
                "ms": round((time.perf_counter() - t0) * 1000)}

    def valori(self, segnaposto):
        return {"mappa": {s: v for s in segnaposto if (v := self.archivio.valore(s)) is not None}}


def servi(motore, porta, token, token_estensione, ponte):
    class Gestore(BaseHTTPRequestHandler):
        def log_message(self, *a):   # niente righe di log con i percorsi
            pass

        def _rispondi(self, codice, oggetto):
            corpo = json.dumps(oggetto, ensure_ascii=False).encode("utf-8")
            self.send_response(codice)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self._estensione()
            self.end_headers()
            self.wfile.write(corpo)

        def _estensione(self):
            """Le estensioni del browser possono chiamare il motore (serve comunque il codice)."""
            origine = self.headers.get("Origin", "")
            if origine.startswith(("chrome-extension://", "moz-extension://")):
                self.send_header("Access-Control-Allow-Origin", origine)
                self.send_header("Vary", "Origin")
                if self.headers.get("Access-Control-Request-Private-Network"):
                    self.send_header("Access-Control-Allow-Private-Network", "true")

        def _autorizzato(self):
            if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
                self._rispondi(403, {"errore": "host non ammesso"})
                return False
            dato = self.headers.get("X-Token", "")
            if secrets.compare_digest(dato, token) or \
                    (self.path.startswith("/ponte/") and secrets.compare_digest(dato, token_estensione)):
                return True
            self._rispondi(403, {"errore": "token mancante o errato"})
            return False

        def do_OPTIONS(self):
            self.send_response(204)
            self._estensione()
            self.send_header("Access-Control-Allow-Headers", "content-type, x-token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if self.path == "/stato" and self._autorizzato():
                self._rispondi(200, {"modello": str(motore.ril.mod.name_or_path), "device": motore.ril.device,
                                     "soglia": motore.ril.soglia, "voci": motore.archivio.voci(),
                                     "archivio_cifrato": motore.archivio.sigillo.attivo})

        def do_POST(self):
            if not self._autorizzato():
                return
            try:
                dati = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                if self.path.startswith("/ponte/"):
                    esito = ponte.gestisci(self.path[7:], dati if isinstance(dati, dict) else {})
                    self._rispondi(404 if esito is None else 200, {"errore": "percorso sconosciuto"} if esito is None else esito)
                elif self.path == "/maschera":
                    self._rispondi(200, motore.maschera([str(t) for t in dati["testi"]], {str(e) for e in dati.get("escludi") or []}, dati.get("mai") or ()))
                elif self.path == "/valori":
                    self._rispondi(200, motore.valori([str(s) for s in dati["segnaposto"]]))
                elif self.path == "/archivio":
                    self._rispondi(200, motore.archivio.elenco(int(dati.get("limite", 500)), bool(dati.get("in_chiaro"))))
                elif self.path == "/archivio/svuota":
                    motore.archivio.svuota()
                    self._rispondi(200, {"voci": 0})
                elif self.path == "/liste":   # il pannello ha cambiato liste\mai.txt o liste\sempre.txt
                    with motore.lucchetto:
                        motore.ril.imposta_liste()
                        motore.cache.clear()
                    self._rispondi(200, {"mai": len(motore.ril.mai), "sempre": motore.ril.rx_sempre is not None})
                else:
                    self._rispondi(404, {"errore": "percorso sconosciuto"})
            except Exception as ex:   # noqa: BLE001  (il chiamante deve sapere che NON e' stato mascherato nulla)
                self._rispondi(500, {"errore": type(ex).__name__})

    class Servizio(ThreadingHTTPServer):
        allow_reuse_address = False   # su Windows, altrimenti, due copie potrebbero aprire la stessa porta senza errore

    Servizio(("127.0.0.1", porta), Gestore).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modello", default=str(percorsi.modello(percorsi.MODELLO_PREDEFINITO)))
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--device", default=None)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    DATI.mkdir(parents=True, exist_ok=True)
    f_token, f_estensione = DATI / "token.txt", DATI / "token_estensione.txt"
    for f in (f_token, f_estensione):
        if not f.exists():
            f.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    m = Motore(a.modello, a.device)
    m.maschera(["riscaldamento"])
    print(f"motore pronto su http://127.0.0.1:{a.porta} | modello {Path(a.modello).name} | {m.ril.device} | voci in archivio: {m.archivio.voci()}")
    from ponte import Ponte
    servi(m, a.porta, f_token.read_text(encoding="utf-8").strip(), f_estensione.read_text(encoding="utf-8").strip(), Ponte(m))
