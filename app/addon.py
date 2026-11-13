# -*- coding: utf-8 -*-
"""Addon di mitmproxy: maschera i dati sensibili nelle richieste ai servizi di chat e li
ripristina nelle risposte, cosi' l'utente vede il testo originale e il servizio solo segnaposto.
Registra inoltre i contatti verso i servizi AI del catalogo (Shadow AI) e applica le politiche
scelte nel pannello: proteggi | registra | blocca | ignora.

Regole di sicurezza:
  - se il motore non risponde la richiesta viene BLOCCATA (503), mai inoltrata in chiaro;
  - nel registro (data\\activity.jsonl) finiscono solo conteggi e nomi dei campi, mai i testi;
  - i file caricati (PDF, immagini) NON vengono mascherati: sono segnalati nel registro e,
    se impostato, bloccati.

Le impostazioni si leggono da data\\settings.json a ogni richiesta (vedi settings.py).
OMISSIS_TEST=1 accetta anche il servizio finto in locale.
"""
import asyncio
import json
import os
import re
import urllib.request
from pathlib import Path

from mitmproxy import http

import catalog
import settings
import paths
import activity
import restore as R
from activity import forma

QUI = Path(__file__).resolve().parent
MOTORE = os.environ.get("OMISSIS_ENGINE_URL", "http://127.0.0.1:8765")
PROVA = os.environ.get("OMISSIS_TEST") == "1"
MAX_CORPO = 8_000_000


def motore(percorso, dati):
    token = (paths.DATI / "token.txt").read_text(encoding="utf-8").strip()
    rich = urllib.request.Request(MOTORE + percorso, data=json.dumps(dati).encode("utf-8"),
                                  headers={"Content-Type": "application/json", "X-Token": token})
    with urllib.request.urlopen(rich, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


class MspPii:
    def __init__(self):
        self.valori = {}        # segnaposto -> valore (cache; i valori restano in memoria e nell'archivio del motore)
        self.assenti = set()
        self.originali = {}     # valore -> segnaposto, per accorgersi di un valore che esce in chiaro altrove
        self.reg = activity.Registro()

    # ---------------------------------------------------------------- utilita'
    def scrivi(self, **voce):
        voce = self.reg.scrivi(**voce)
        extra = ", ".join(f"{k} {v}" for k, v in (voce.get("sostituzioni") or {}).items())
        if "ripristinati" in voce:
            extra = f"{voce['ripristinati']} segnaposto riportati al valore originale"
        if "VALORI_IN_CHIARO" in voce:
            extra += f" | ATTENZIONE: {voce['VALORI_IN_CHIARO']} valori già mascherati compaiono in chiaro"
        print(f"{voce['ora'][11:]}  {voce.get('servizio', ''):14} {voce.get('evento', '')}  {voce.get('percorso', '')[:60]}  {extra}", flush=True)

    def contatto(self, servizio, host, esito):
        self.reg.contatto(servizio["id"], host, esito)

    def precarica(self, segnaposto):
        mancanti = [s for s in set(segnaposto) if s not in self.valori and s not in self.assenti]
        if mancanti:
            try:
                trovati = motore("/values", {"segnaposto": mancanti})["mappa"]
            except Exception:   # noqa: BLE001  (senza motore i segnaposto restano tali: nessun danno)
                return
            self.valori.update(trovati)
            self.assenti.update(s for s in mancanti if s not in trovati)

    def cerca(self, segnaposto):
        if segnaposto not in self.valori and segnaposto not in self.assenti:
            self.precarica([segnaposto])
        return self.valori.get(segnaposto)

    @staticmethod
    def percorso(flow):
        return activity.percorso_pulito(flow.request.path)

    def adattatore(self, flow):
        """(adattatore, nome del servizio) per una richiesta da proteggere, altrimenti (None, None)."""
        host = flow.request.pretty_host
        s = catalog.trova(host)
        if s is not None:
            if s["adattatore"] and settings.politica(s) == "proteggi":
                return R.CLASSI[s["adattatore"]](), s["id"]
            return None, None
        if PROVA and host in ("127.0.0.1", "localhost"):
            ad = R.di_prova(flow.request.path)
            return ad, (ad.nome if ad else None)
        return None, None

    async def maschera(self, testi):
        esito = await asyncio.to_thread(motore, "/mask", {"testi": testi})
        self.valori.update(esito["mappa"])
        for seg, val in esito["mappa"].items():
            if len(val) >= 5:
                self.originali[val] = seg
        while len(self.originali) > 20000:
            self.originali.pop(next(iter(self.originali)))
        return esito

    # ---------------------------------------------------------------- contatti verso i servizi AI
    def http_connect(self, flow: http.HTTPFlow):
        s = catalog.trova(flow.request.host)
        if s is None:
            return
        pol = settings.politica(s)
        if pol == "ignora":
            return
        if pol == "blocca":
            flow.response = http.Response.make(403, f"Omissis: {s['nome']} è bloccato dalle impostazioni".encode("utf-8"),
                                               {"content-type": "text/plain; charset=utf-8"})
            self.contatto(s, flow.request.host, "bloccato")
            return
        self.contatto(s, flow.request.host, "protetto" if pol == "proteggi" and s["adattatore"] else "non protetto")

    # ---------------------------------------------------------------- richiesta
    async def request(self, flow: http.HTTPFlow):
        ad, servizio = self.adattatore(flow)
        if ad is None:
            return
        flow.metadata["msp"], flow.metadata["msp_servizio"] = ad, servizio
        imp = settings.leggi()
        rq = flow.request
        if rq.method not in ("POST", "PUT", "PATCH") or not rq.raw_content:
            return
        tipo = rq.headers.get("content-type", "")
        voce = {"servizio": servizio, "metodo": rq.method, "percorso": self.percorso(flow), "byte": len(rq.raw_content),
                "cliente": activity.cliente_da_ua(rq.headers.get("User-Agent", ""))}
        if "multipart/" in tipo or "octet-stream" in tipo or re.search(r"(?i)upload|/files?(/|$)", rq.path):
            if imp["blocca_file"]:
                flow.response = http.Response.make(403, b'{"error":"Omissis: caricamento di file bloccato"}',
                                                   {"content-type": "application/json"})
            self.scrivi(**voce, evento="file bloccato" if imp["blocca_file"] else "file NON mascherato")
            return
        if len(rq.raw_content) > MAX_CORPO:
            return
        aperta = ad.richiesta(rq.path, tipo, rq.get_text(strict=False) or "")
        if aperta is None:
            return
        rif, ricomponi, corpo = aperta
        rif = [(c, k) for c, k in rif if c[k].strip()]
        if rif:
            try:
                esito = await self.maschera([c[k] for c, k in rif])
            except Exception as ex:   # noqa: BLE001
                flow.response = http.Response.make(
                    503, json.dumps({"error": {"type": "msp_pii", "message": "Omissis: motore di protezione non raggiungibile, "
                                                                           "richiesta bloccata per non inviare dati in chiaro"}}),
                    {"content-type": "application/json"})
                self.scrivi(**voce, evento="BLOCCATA: motore non raggiungibile", errore=type(ex).__name__)
                return
            for (c, k), nuovo in zip(rif, esito["testi"]):
                c[k] = nuovo
            rq.set_text(ricomponi())
            rq.headers["accept-encoding"] = "identity"   # la risposta in streaming deve arrivare non compressa
            voce.update(evento="mascherata", campi=len(rif), caratteri=sum(len(t) for t in esito["testi"]),
                        sostituzioni=esito["conteggi"], ms=esito["ms"])
        else:
            voce.update(evento="nessun campo di testo riconosciuto", struttura=forma(corpo))
        # controllo di tenuta: un valore gia' mascherato compare in chiaro in questa richiesta?
        testo = rq.get_text(strict=False) or ""
        fuori = sum(1 for v in self.originali if v in testo)
        if fuori:
            voce["VALORI_IN_CHIARO"] = fuori
            voce.setdefault("struttura", forma(corpo))
        self.scrivi(**voce)

    # ---------------------------------------------------------------- risposta
    def responseheaders(self, flow: http.HTTPFlow):
        ad = flow.metadata.get("msp")
        if ad is None or not settings.leggi()["ripristina"]:
            return
        rs = flow.response
        if ad.in_streaming(rs.headers.get("content-type", ""), flow.request.path) and \
                rs.headers.get("content-encoding", "identity") == "identity":
            flusso = ad.flusso(self.cerca, self.precarica)
            flow.metadata["msp_flusso"] = flusso
            rs.stream = flusso

    def response(self, flow: http.HTTPFlow):
        ad = flow.metadata.get("msp")
        if ad is None or not settings.leggi()["ripristina"]:
            return
        rs, servizio = flow.response, flow.metadata.get("msp_servizio")
        flusso = flow.metadata.get("msp_flusso")
        if flusso is not None:
            if flusso.ripristinati:
                self.scrivi(servizio=servizio, percorso=self.percorso(flow), evento="risposta in streaming", ripristinati=flusso.ripristinati)
            return
        tipo = rs.headers.get("content-type", "")
        if not rs.raw_content or len(rs.raw_content) > MAX_CORPO or not any(x in tipo for x in ("json", "event-stream", "text/plain")):
            return
        testo = rs.get_text(strict=False) or ""
        trovati = [m.group() for m in R.RX_SEGNAPOSTO.finditer(testo)]
        if not trovati:
            return
        self.precarica(trovati)
        rs.set_text(ad.intera(tipo, testo, self.cerca))
        self.scrivi(servizio=servizio, percorso=self.percorso(flow), evento="risposta", ripristinati=len(trovati))

    # ---------------------------------------------------------------- websocket (es. Copilot)
    def websocket_message(self, flow: http.HTTPFlow):
        ad = flow.metadata.get("msp")
        msg = flow.websocket.messages[-1]
        if ad is None or not msg.is_text:
            return
        servizio = flow.metadata.get("msp_servizio")
        try:
            oggetto = json.loads(msg.content.decode("utf-8"))
        except ValueError:
            oggetto = None
        if msg.from_client:
            rif = [(c, k) for c, k in ad.campi(flow.request.path, oggetto) if c[k].strip()] if oggetto is not None else []
            if not rif:
                if len(msg.content) > 200:
                    self.scrivi(servizio=servizio, percorso=self.percorso(flow), evento="messaggio websocket: nessun campo di testo riconosciuto",
                                byte=len(msg.content), struttura=forma(oggetto) if oggetto is not None else "non JSON")
                return
            try:
                esito = motore("/mask", {"testi": [c[k] for c, k in rif]})
            except Exception as ex:   # noqa: BLE001
                msg.drop()
                self.scrivi(servizio=servizio, percorso=self.percorso(flow), evento="BLOCCATO messaggio websocket: motore non raggiungibile",
                            errore=type(ex).__name__)
                return
            self.valori.update(esito["mappa"])
            for (c, k), nuovo in zip(rif, esito["testi"]):
                c[k] = nuovo
            msg.content = json.dumps(oggetto, ensure_ascii=False).encode("utf-8")
            self.scrivi(servizio=servizio, percorso=self.percorso(flow), evento="mascherata", campi=len(rif), via="websocket",
                        sostituzioni=esito["conteggi"], ms=esito["ms"])
        elif settings.leggi()["ripristina"] and (b"[" in msg.content or flow.metadata.get("msp_ws_pendenti")):
            foglie = flow.metadata.setdefault("msp_ws", R.Foglie(self.cerca))
            self.precarica([m.group() for m in R.RX_SEGNAPOSTO.finditer(msg.content.decode("utf-8", errors="replace"))])
            if oggetto is None:
                msg.content = R.ripristina(msg.content.decode("utf-8", errors="replace"), self.cerca).encode("utf-8")
            else:
                foglie.cambiato = False
                nuovo = foglie.applica(oggetto)
                if foglie.cambiato:
                    msg.content = json.dumps(nuovo, ensure_ascii=False).encode("utf-8")
            flow.metadata["msp_ws_pendenti"] = foglie.pendenti


addons = [MspPii()]
