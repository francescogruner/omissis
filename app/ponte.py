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
import os
import re
import secrets
import threading
import time
import urllib.parse

import catalogo
import impostazioni
import registro
import ripristino as R

MAX_CORPO = 8_000_000
VERSIONE = 1


class Ponte:
    def __init__(self, motore):
        self.m = motore
        self.reg = registro.Registro()
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
             "valori": self.valori, "visita": self.visita, "websocket": self.websocket}.get(azione)
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
                "casella": bool(imp.get("casella", True)), "servizi": servizi}

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
