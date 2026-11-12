# -*- coding: utf-8 -*-
"""Ponte tra il motore e l'estensione del browser.

L'estensione intercetta le richieste DENTRO la pagina (prima che vengano cifrate) e le passa qui:
il lavoro vero lo fanno gli stessi adattatori del proxy (ripristino.py), cosi' c'e' un solo posto
in cui si decide dove sta il testo e come si riscrive una risposta. Gira dentro motore.py.

  POST /ponte/stato       politiche dei servizi (cosa proteggere, registrare, bloccare)
  POST /ponte/richiesta   {url, metodo, tipo, corpo}        -> {azione: passa | sostituisci | blocca, corpo}
  POST /ponte/apri        {url, tipo}                       -> {id} se la risposta va riscritta mentre arriva
  POST /ponte/pezzo       {id, dati (base64), fine}         -> {dati (base64)}
  POST /ponte/intera      {url, tipo, testo}                -> {testo}
  POST /ponte/valori      {segnaposto: [...]}               -> {mappa}   (ripristino nel testo della pagina)
  POST /ponte/visita      {host}                            contatto con un servizio AI (Shadow AI)
  POST /ponte/websocket   {url}                             canale che l'estensione non sa leggere

Stesse regole del proxy: se il modello non risponde la richiesta viene bloccata; nel registro solo
conteggi e struttura.
"""
import base64
import collections
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import catalogo
import impostazioni
import percorsi
import registro
import ripristino as R

MAX_CORPO = 8_000_000
MAX_ALLEGATO = 20_000_000
TIPI_FILE = {".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
             ".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv", ".json": "application/json", ".html": "text/html",
             ".htm": "text/html", ".xml": "application/xml"}


class NonFatto(Exception):
    """Un allegato che non si e' potuto anonimizzare; codice dice perche' (vedi documenti.Errore)."""

    def __init__(self, codice=""):
        super().__init__(codice)
        self.codice = codice
VERSIONE = 1


class Ponte:
    def __init__(self, motore):
        self.m = motore
        self.reg = registro.Registro()
        self.allegati_recenti = collections.deque(maxlen=40)   # (quando, servizio, peso) delle copie anonimizzate consegnate
        try:   # le librerie per leggere i documenti ci sono solo dove il programma e' un pacchetto unico: si guarda una volta
            import documenti
            self.documenti = documenti
        except ImportError:
            self.documenti = None
        self.prova = os.environ.get("MSP_PROVA") == "1"
        self.flussi = {}        # id -> [flusso, servizio, percorso, ultimo uso]
        self.originali = {}     # valore -> segnaposto, per accorgersi di un valore che esce in chiaro altrove
        self.lucchetto = threading.Lock()

    # ---------------------------------------------------------------- utilita'
    @staticmethod
    def _via(dati):
        return "app desktop" if dati.get("via") == "app" else "estensione"

    def _servizio(self, url):
        """(adattatore, id del servizio, host, percorso) per un indirizzo; adattatore None = non si tocca."""
        u = urllib.parse.urlsplit(str(url))
        host, percorso = (u.hostname or "").lower(), u.path + ("?" + u.query if u.query else "")
        s = catalogo.trova(host)
        if s is not None:
            protetto = s["adattatore"] and impostazioni.politica(s) == "proteggi"
            return (R.CLASSI[s["adattatore"]]() if protetto else None), s["id"], host, percorso
        if self.prova and host in ("localhost", "127.0.0.1"):
            ad = R.di_prova(percorso)
            return ad, (ad.nome if ad else None), host, percorso
        return None, None, host, percorso

    def gestisci(self, azione, dati):
        f = {"stato": self.stato, "richiesta": self.richiesta, "testo": self.testo, "apri": self.apri, "pezzo": self.pezzo, "intera": self.intera,
             "valori": self.valori, "visita": self.visita, "websocket": self.websocket, "allegato": self.allegato}.get(azione)
        return None if f is None else f(dati)

    # ---------------------------------------------------------------- politiche
    def stato(self, dati):
        imp = impostazioni.leggi()
        # del radar all'estensione interessano solo i servizi da bloccare: degli altri non puo' fare nulla
        servizi = [{"id": s["id"], "nome": s["nome"], "domini": s["domini"], "politica": impostazioni.politica(s, imp),
                    "leggibile": bool(s["adattatore"]), **({"radar": True} if s["radar"] else {})}
                   for s in catalogo.SERVIZI if not s["radar"] or impostazioni.politica(s, imp) == "blocca"]
        if self.prova:
            servizi.append({"id": "prova", "nome": "Servizio finto", "domini": ["localhost"], "politica": "proteggi", "leggibile": True})
        return {"versione": VERSIONE, "ripristina": bool(imp["ripristina"]), "blocca_file": bool(imp["blocca_file"]),
                "casella": bool(imp.get("casella", True)), "allegati": bool(imp.get("allegati", True)), "servizi": servizi}

    def visita(self, dati):
        host = str(dati.get("host", "")).lower()
        s = catalogo.trova(host)
        if s is None:
            return {}
        pol = impostazioni.politica(s)
        if pol != "ignora":
            self.reg.contatto(s["id"], host, "bloccato" if pol == "blocca" else
                              "protetto" if pol == "proteggi" and s["adattatore"] else "non protetto")
        return {"servizio": s["id"], "politica": pol}

    def websocket(self, dati):
        ad, servizio, _, percorso = self._servizio(dati.get("url", ""))
        if ad is not None:
            self.reg.scrivi(servizio=servizio, via=self._via(dati), percorso=registro.percorso_pulito(percorso),
                            evento="canale websocket NON coperto")
        return {}

    # ---------------------------------------------------------------- richiesta
    def richiesta(self, dati):
        ad, servizio, _, percorso = self._servizio(dati.get("url", ""))
        if ad is None:
            return {"azione": "passa"}
        imp = impostazioni.leggi()
        tipo, corpo = str(dati.get("tipo") or ""), dati.get("corpo")
        # "rete": secondo controllo fatto dal connettore subito prima dell'invio. Di norma la pagina ha gia' sostituito
        # tutto: nel registro va solo cio' che questo controllo ha dovuto sostituire o bloccare.
        rete = bool(dati.get("rete"))
        voce = {"servizio": servizio, "via": self._via(dati), "metodo": str(dati.get("metodo", "POST")),
                "percorso": registro.percorso_pulito(percorso),
                "byte": len(corpo.encode("utf-8")) if isinstance(corpo, str) else int(dati.get("byte") or 0)}
        if dati.get("file") or "multipart/" in tipo or "octet-stream" in tipo or re.search(r"(?i)upload|/files?(/|$)", percorso):
            if self._gia_anonimizzato(servizio, voce["byte"]):   # e' la copia che abbiamo appena preparato noi: puo' partire
                return {"azione": "passa"}
            if not rete or imp["blocca_file"]:
                self.reg.scrivi(**voce, evento="file bloccato" if imp["blocca_file"] else "file NON mascherato")
            return {"azione": "blocca", "motivo": "file"} if imp["blocca_file"] else {"azione": "passa"}
        if not isinstance(corpo, str):
            if voce["byte"] > 200 and not rete:
                self.reg.scrivi(**voce, evento="corpo non testuale: NON letto")
            return {"azione": "passa"}
        if not corpo or len(corpo) > MAX_CORPO:
            return {"azione": "passa"}
        if "json" not in tipo and "x-www-form-urlencoded" not in tipo and corpo.lstrip()[:1] in ("{", "["):
            tipo = "application/json"   # molte pagine mandano JSON senza dichiararlo
        aperta = ad.richiesta(percorso, tipo, corpo)
        if aperta is None:
            return {"azione": "passa"}
        rif, ricomponi, interpretato = aperta
        rif = [(c, k) for c, k in rif if c[k].strip()]
        esito_ext = {"azione": "passa"}
        if rif:
            originali = [c[k] for c, k in rif]
            try:
                esito = self.m.maschera(originali)
            except Exception as ex:   # noqa: BLE001  (mai inoltrare in chiaro)
                self.reg.scrivi(**voce, evento="BLOCCATA: il modello non ha risposto", errore=type(ex).__name__)
                return {"azione": "blocca", "motivo": "motore"}
            with self.lucchetto:
                for seg, val in esito["mappa"].items():
                    if len(val) >= 5:
                        self.originali[val] = seg
                while len(self.originali) > 20000:
                    self.originali.pop(next(iter(self.originali)))
            voce.update(evento="mascherata", campi=len(rif), caratteri=sum(len(t) for t in esito["testi"]),
                        sostituzioni=esito["conteggi"], ms=esito["ms"])
            if esito["testi"] != originali:   # se non c'e' nulla da sostituire la richiesta resta com'e'
                for (c, k), nuovo in zip(rif, esito["testi"]):
                    c[k] = nuovo
                corpo = ricomponi()
                esito_ext = {"azione": "sostituisci", "corpo": corpo, "sostituzioni": sum(esito["conteggi"].values())}
        else:
            voce.update(evento="nessun campo di testo riconosciuto", struttura=registro.forma(interpretato))
        with self.lucchetto:
            fuori = sum(1 for v in self.originali if v in corpo)
        if fuori:
            voce["VALORI_IN_CHIARO"] = fuori
            voce.setdefault("struttura", registro.forma(interpretato))
        if rete:
            if esito_ext["azione"] != "sostituisci" and not fuori:
                return esito_ext
            voce["strato"] = "rete"   # la pagina non l'aveva fatto: l'ha fermato il controllo prima dell'invio
        self.reg.scrivi(**voce)
        return esito_ext

    def testo(self, dati):
        """Il testo della casella di scrittura, sostituito prima che l'app lo legga (dove le richieste non si vedono)."""
        host, t = str(dati.get("host", "")).lower(), dati.get("testo")
        ad, servizio, _, _ = self._servizio(f"https://{host}/generico/casella")
        if ad is None or not isinstance(t, str) or not t.strip():
            return {"azione": "passa"}
        voce = {"servizio": servizio, "via": self._via(dati), "metodo": "casella", "percorso": "(casella di scrittura)", "byte": len(t.encode("utf-8"))}
        try:
            esito = self.m.maschera([t])
        except Exception as ex:   # noqa: BLE001  (mai lasciar partire in chiaro)
            self.reg.scrivi(**voce, evento="BLOCCATA: il modello non ha risposto", errore=type(ex).__name__)
            return {"azione": "blocca", "motivo": "motore"}
        self.reg.scrivi(**voce, evento="mascherata", campi=1, caratteri=len(esito["testi"][0]), sostituzioni=esito["conteggi"], ms=esito["ms"])
        if esito["testi"][0] == t:
            return {"azione": "passa"}
        return {"azione": "sostituisci", "testo": esito["testi"][0], "sostituzioni": sum(esito["conteggi"].values())}

    # ---------------------------------------------------------------- allegati
    def _gia_anonimizzato(self, servizio, peso):
        """Il caricamento che sta partendo e' fatto di copie appena anonimizzate? Si riconoscono dal peso: quello di una
        copia, o la somma delle ultime (piu' file nello stesso invio)."""
        ora, somma = time.time(), 0
        for quando, di, byte in reversed(self.allegati_recenti):
            if ora - quando > 180:
                break
            if di == servizio:
                somma += byte
                if peso in (byte, somma):
                    return True
        return False

    def _anonimizza_file(self, nome, grezzo):
        """(nome nuovo, contenuto, conteggi). Leggere Word, Excel, PDF e immagini e' un lavoro del programma di gestione:
        se questo processo ne ha le librerie lo fa da se', altrimenti lo chiede al pannello sullo stesso PC."""
        documenti = self.documenti
        if documenti is not None:
            try:
                return documenti.elabora(nome, grezzo, "anonimizza")
            except documenti.Errore as ex:
                raise NonFatto(ex.codice) from None
        token = (percorsi.DATI / "token.txt").read_text(encoding="utf-8").strip()
        rich = urllib.request.Request(f"http://127.0.0.1:{percorsi.PORTA_PANNELLO}/interno/allegato",
                                      data=json.dumps({"nome": nome, "dati": base64.b64encode(grezzo).decode("ascii")}).encode("utf-8"),
                                      headers={"Content-Type": "application/json", "X-Token": token})
        try:
            with urllib.request.urlopen(rich, timeout=300) as r:
                d = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as ex:
            try:
                codice = json.loads(ex.read().decode("utf-8")).get("codice", "")
            except ValueError:
                codice = ""
            raise NonFatto(codice) from None
        except (urllib.error.URLError, OSError, ValueError):
            raise NonFatto("pannello") from None
        return d["nome"], base64.b64decode(d["dati"]), d["conteggi"]

    def allegato(self, dati):
        """Un file che l'utente sta per allegare a un messaggio (scelto, trascinato o incollato): la pagina ricevera' la copia
        anonimizzata. Cio' che non si riesce ad anonimizzare segue la scelta «blocca i file»; un'immagine o un PDF senza
        testo non ha nulla da sostituire e passa; se la protezione non risponde non parte nulla."""
        ad, servizio, _, _ = self._servizio(f"https://{str(dati.get('host', '')).lower()}/generico/casella")
        if ad is None:
            return {"azione": "passa"}
        imp = impostazioni.leggi()
        nome = Path(str(dati.get("nome") or "file")).name[:200]
        est = Path(nome).suffix.lower()
        voce = {"servizio": servizio, "via": self._via(dati), "metodo": "allegato", "percorso": f"(allegato {est or 'senza estensione'})",
                "byte": int(dati.get("byte") or 0)}

        def non_anonimizzato():
            self.reg.scrivi(**voce, evento="file bloccato" if imp["blocca_file"] else "file NON mascherato")
            return {"azione": "blocca", "motivo": "file"} if imp["blocca_file"] else {"azione": "passa"}

        if not imp.get("allegati", True):
            return non_anonimizzato()
        try:
            grezzo = base64.b64decode(dati.get("dati") or "")
        except ValueError:
            grezzo = b""
        if not grezzo or len(grezzo) > MAX_ALLEGATO:
            return non_anonimizzato()
        voce["byte"] = len(grezzo)
        inizio = time.time()
        try:
            nuovo_nome, nuovo, conteggi = self._anonimizza_file(nome, grezzo)
        except NonFatto as ex:
            if ex.codice == "senza_testo":
                self.reg.scrivi(**voce, evento="allegato senza testo: passato")
                return {"azione": "passa"}
            if ex.codice == "protezione":
                self.reg.scrivi(**voce, evento="BLOCCATA: motore non raggiungibile")
                return {"azione": "blocca", "motivo": "motore"}
            return non_anonimizzato()
        except Exception as ex:   # noqa: BLE001  (un file che manda in errore la lettura non deve partire in chiaro per sbaglio)
            voce["errore"] = type(ex).__name__
            return non_anonimizzato()
        self.allegati_recenti.append((time.time(), servizio, len(nuovo)))
        sostituzioni = {k: n for k, n in conteggi.items() if k != "pagine_lette" and n}
        self.reg.scrivi(**voce, evento="allegato mascherato", sostituzioni=sostituzioni, ms=round((time.time() - inizio) * 1000))
        nuova_est = Path(nuovo_nome).suffix.lower()
        return {"azione": "sostituisci", "nome": nuovo_nome, "tipo": TIPI_FILE.get(nuova_est, "application/octet-stream"),
                "dati": base64.b64encode(nuovo).decode("ascii"), "sostituzioni": sum(sostituzioni.values()), "convertito": nuova_est != est}

    # ---------------------------------------------------------------- risposta
    def apri(self, dati):
        if not impostazioni.leggi()["ripristina"]:
            return {"id": None}
        ad, servizio, _, percorso = self._servizio(dati.get("url", ""))
        if ad is None or not ad.in_streaming(str(dati.get("tipo") or ""), percorso):
            return {"id": None}
        ident, ora = secrets.token_hex(8), time.time()
        with self.lucchetto:
            for k in [k for k, v in self.flussi.items() if ora - v[3] > 1800]:   # risposte interrotte a meta'
                del self.flussi[k]
            self.flussi[ident] = [ad.flusso(self.m.archivio.valore), servizio, registro.percorso_pulito(percorso), ora, self._via(dati)]
        return {"id": ident}

    def pezzo(self, dati):
        ident, fine = str(dati.get("id", "")), bool(dati.get("fine"))
        with self.lucchetto:
            voce = self.flussi.pop(ident, None) if fine else self.flussi.get(ident)
        if voce is None:   # flusso sconosciuto: i dati tornano come sono (restano i segnaposto, nessun danno)
            return {"dati": dati.get("dati") or "", "perso": True}
        flusso, servizio, percorso, _, via = voce
        voce[3] = time.time()
        grezzo = base64.b64decode(dati.get("dati") or "")
        out = b"".join(flusso(grezzo)) if grezzo else b""
        if fine:
            out += b"".join(flusso(b""))
            if flusso.ripristinati:
                self.reg.scrivi(servizio=servizio, via=via, percorso=percorso, evento="risposta in streaming",
                                ripristinati=flusso.ripristinati)
        return {"dati": base64.b64encode(out).decode("ascii")}

    def intera(self, dati):
        testo = dati.get("testo")
        if not isinstance(testo, str) or not impostazioni.leggi()["ripristina"]:
            return {}
        ad, servizio, _, percorso = self._servizio(dati.get("url", ""))
        trovati = len(R.RX_SEGNAPOSTO.findall(testo))
        if ad is None or not trovati or len(testo) > MAX_CORPO:
            return {}
        nuovo = ad.intera(str(dati.get("tipo") or ""), testo, self.m.archivio.valore)
        rimasti = len(R.RX_SEGNAPOSTO.findall(nuovo))
        if trovati > rimasti:
            self.reg.scrivi(servizio=servizio, via=self._via(dati), percorso=registro.percorso_pulito(percorso), evento="risposta",
                            ripristinati=trovati - rimasti)
        return {"testo": nuovo}

    def valori(self, dati):
        if not impostazioni.leggi()["ripristina"]:
            return {"mappa": {}}
        return self.m.valori([str(s) for s in (dati.get("segnaposto") or [])[:500]])
