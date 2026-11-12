# -*- coding: utf-8 -*-
"""Anonimizza e ripristina documenti e cartelle intere, per quando l'AI si usa con allegati o con
cartelle di lavoro (Cowork e simili): si da' all'AI la copia anonimizzata, poi si ripristinano i
file che produce.

  python documenti.py anonimizza <file o cartella>     ->  <nome>.anon.<est>   /  <cartella>.anon
  python documenti.py ripristina <file o cartella>     ->  <nome>.ripristinato.<est>  /  <cartella>.ripristinato

Formati: Word (.docx), Excel (.xlsx), PowerPoint (.pptx), testo (.txt .md .csv .json .html .xml .eml...)
PDF e immagini (ne esce un file di testo: le scansioni si leggono con lettura.py). Nei file Office la formattazione resta: il
testo viene sostituito dentro il documento, anche quando un nome e' spezzato tra pezzi con stili
diversi, e comprende intestazioni, pie' di pagina, note, commenti e testo eliminato con le revisioni.
Vengono svuotati anche autore e azienda nelle proprieta' del file.

NON coperti: immagini inserite dentro i documenti, vecchi .doc/.xls,
nomi dei fogli di Excel, numeri nelle celle numeriche, nomi dei file. In una cartella i file non
coperti vengono SALTATI (non copiati), cosi' nella copia anonimizzata non finisce nulla in chiaro.

Richiede il motore acceso (pannello.py oppure avvia.py).
"""
import io
import json
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from lxml import etree

import lettura
import lingue
import percorsi
import ripristino as R

QUI = Path(__file__).resolve().parent
MOTORE = f"http://127.0.0.1:{percorsi.PORTA_MOTORE}"
TESTO = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".xml", ".html", ".htm", ".eml", ".yaml", ".yml", ".ini", ".sql",
         ".rtf", ".srt", ".vtt", ".tex", ".py", ".js", ".ts", ".ps1", ".sh", ".bat", ".cfg", ".conf", ".toml"}
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
# per formato: (parti del pacchetto da leggere, elemento che fa da "paragrafo", elementi che portano il testo)
OFFICE = {
    ".docx": [(r"word/(document|header\d*|footer\d*|footnotes|endnotes|comments\w*)\.xml", f"{{{W}}}p", (f"{{{W}}}t", f"{{{W}}}delText", f"{{{W}}}instrText"))],
    ".pptx": [(r"ppt/(slides/slide\d+|notesSlides/notesSlide\d+|slideMasters/slideMaster\d+|slideLayouts/slideLayout\d+)\.xml", f"{{{A}}}p", (f"{{{A}}}t",)),
              (r"ppt/comments/.+\.xml", None, None)],
    ".xlsx": [(r"xl/sharedStrings\.xml", f"{{{S}}}si", (f"{{{S}}}t",)), (r"xl/worksheets/sheet\d+\.xml", f"{{{S}}}is", (f"{{{S}}}t",)),
              (r"xl/comments\d*\.xml", f"{{{S}}}comment", (f"{{{S}}}t",))],
}
# parti comuni a tutti i formati: grafici (etichette e valori memorizzati) e disegni
COMUNI = [(r"(word|ppt|xl)/(charts/chart\d+|diagrams/data\d+|drawings/drawing\d+)\.xml", None, None)]
PROPRIETA = {"creator", "lastModifiedBy", "Company", "Manager"}
IMMAGINI = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}   # lette con il riconoscimento dei caratteri: ne esce un file di testo
COPERTI = TESTO | set(OFFICE) | {".pdf"} | IMMAGINI


class Errore(Exception):
    pass


def motore(percorso, dati):
    token = (percorsi.DATI / "token.txt").read_text(encoding="utf-8").strip()
    rich = urllib.request.Request(MOTORE + percorso, data=json.dumps(dati).encode("utf-8"),
                                  headers={"Content-Type": "application/json", "X-Token": token})
    try:
        with urllib.request.urlopen(rich, timeout=300) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as ex:
        raise Errore(lingue.t("programma.protezione_non_attiva")) from ex


def applica(segmenti, posizioni):
    """Riporta le sostituzioni [inizio, fine, nuovo] (riferite al testo unito) dentro i singoli pezzi:
    il nuovo testo va nel primo pezzo toccato, gli altri perdono solo i caratteri coperti."""
    out, inizi, n = list(segmenti), [], 0
    for s in segmenti:
        inizi.append(n)
        n += len(s)
    for ini, fine, nuovo in sorted(posizioni, reverse=True):
        i = max(k for k, x in enumerate(inizi) if x <= ini)
        j = max(k for k, x in enumerate(inizi) if x < fine) if fine > ini else i
        if i == j:
            out[i] = out[i][:ini - inizi[i]] + nuovo + out[i][fine - inizi[i]:]
        else:
            out[j] = out[j][fine - inizi[j]:]
            for k in range(i + 1, j):
                out[k] = ""
            out[i] = out[i][:ini - inizi[i]] + nuovo
    return out


class Lavoro:
    """Una passata di anonimizzazione o di ripristino: raccoglie i conteggi."""

    def __init__(self, azione):
        self.azione, self.conteggi, self.cache = azione, {}, {}

    def posizioni(self, testi):
        """Per ogni testo le sostituzioni da fare: [[inizio, fine, nuovo], ...]."""
        if self.azione == "anonimizza":
            out = []
            for k in range(0, len(testi), 150):
                r = motore("/maschera", {"testi": testi[k:k + 150]})
                out += r["posizioni"]
                for e, n in r["conteggi"].items():
                    self.conteggi[e] = self.conteggi.get(e, 0) + n
            return out
        trovati = [[(m.start(), m.end(), m.group()) for m in R.RX_SEGNAPOSTO.finditer(t)] for t in testi]
        mancanti = sorted({seg for riga in trovati for _, _, seg in riga} - set(self.cache))
        for k in range(0, len(mancanti), 500):
            self.cache.update(motore("/valori", {"segnaposto": mancanti[k:k + 500]})["mappa"])
        out = []
        for riga in trovati:
            buoni = [[s, e, self.cache[seg]] for s, e, seg in riga if seg in self.cache]
            self.conteggi["ripristinati"] = self.conteggi.get("ripristinati", 0) + len(buoni)
            self.conteggi["sconosciuti"] = self.conteggi.get("sconosciuti", 0) + len(riga) - len(buoni)
            out.append(buoni)
        return out

    def testo(self, t):
        """Testo semplice, a blocchi di righe per non mandare tutto in un colpo solo."""
        blocchi, cur = [], ""
        for riga in t.splitlines(keepends=True):
            if len(cur) + len(riga) > 3000 and cur:
                blocchi.append(cur)
                cur = ""
            cur += riga
        blocchi.append(cur)
        return "".join("".join(applica([b], p)) for b, p in zip(blocchi, self.posizioni(blocchi)))

    def autori(self, radice):
        """Nomi di chi ha scritto revisioni e commenti: stanno negli attributi, non nel testo. Non ripristinabili."""
        if self.azione != "anonimizza":
            return
        for n in radice.iter():
            if not isinstance(n.tag, str):
                continue
            locale = etree.QName(n).localname
            for attr in list(n.attrib):
                a = etree.QName(attr).localname
                if a in ("author", "userId", "displayName", "initials") or (a == "name" and locale in ("cmAuthor", "author", "person")):
                    n.set(attr, "A" if a == "initials" else "Autore")
                    self.conteggi["autori di revisioni e commenti rimossi"] = self.conteggi.get("autori di revisioni e commenti rimossi", 0) + (a != "initials")
            if locale == "author" and n.text and n.text.strip() and len(n) == 0:   # elenco degli autori dei commenti in Excel
                n.text = "Autore"
                self.conteggi["autori di revisioni e commenti rimossi"] = self.conteggi.get("autori di revisioni e commenti rimossi", 0) + 1

    def xml(self, dati, paragrafo, portatori):
        radice = etree.fromstring(dati)
        self.autori(radice)
        if paragrafo is None:   # parte senza struttura nota: ogni nodo di testo per conto suo
            gruppi = [[n] for n in radice.iter() if isinstance(n.tag, str) and n.text and n.text.strip() and len(n) == 0]
        else:                   # ogni pezzo di testo va con il paragrafo piu' vicino che lo contiene (le caselle
            per = {}            # di testo sono paragrafi dentro paragrafi: cosi' nessun pezzo e' trattato due volte)
            for n in radice.iter(*portatori):
                if n.text:
                    p = n.getparent()
                    while p is not None and p.tag != paragrafo:
                        p = p.getparent()
                    per.setdefault(p, []).append(n)
            gruppi = list(per.values())
        gruppi = [g for g in gruppi if "".join(n.text for n in g).strip()]
        for g, pos in zip(gruppi, self.posizioni(["".join(n.text for n in g) for g in gruppi])):
            if pos:
                for n, nuovo in zip(g, applica([n.text for n in g], pos)):
                    n.text = nuovo
                    n.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return etree.tostring(radice, xml_declaration=True, encoding="UTF-8", standalone=True)

    def collegamenti(self, dati):
        """Collegamenti verso l'esterno (siti, mailto): se contengono un dato sensibile vengono neutralizzati.
        Non sono ripristinabili: nel documento resta il testo del collegamento, non la sua destinazione."""
        radice = etree.fromstring(dati)
        esterni = [n for n in radice if n.get("TargetMode") == "External" and n.get("Target")]
        if not esterni:
            return dati
        testi = [urllib.parse.unquote(n.get("Target")) for n in esterni]
        for n, pos in zip(esterni, self.posizioni(testi)):
            if pos:
                n.set("Target", "https://collegamento-rimosso.invalid/")
                self.conteggi["collegamenti neutralizzati"] = self.conteggi.get("collegamenti neutralizzati", 0) + 1
        return etree.tostring(radice, xml_declaration=True, encoding="UTF-8", standalone=True)

    def office(self, dati, est):
        entrata, uscita = zipfile.ZipFile(io.BytesIO(dati)), io.BytesIO()
        with zipfile.ZipFile(uscita, "w", zipfile.ZIP_DEFLATED) as z:
            for voce in entrata.infolist():
                contenuto = entrata.read(voce.filename)
                incorporato = re.search(r"/embeddings/[^/]+(\.docx|\.xlsx|\.pptx)$", voce.filename.lower())
                for modello, paragrafo, portatori in OFFICE[est] + COMUNI:
                    if re.fullmatch(modello, voce.filename):
                        contenuto = self.xml(contenuto, paragrafo, portatori)
                        break
                else:
                    if incorporato:                       # un foglio o un documento dentro il documento
                        contenuto = self.office(contenuto, incorporato.group(1))
                    elif voce.filename.endswith(".rels") and self.azione == "anonimizza":
                        contenuto = self.collegamenti(contenuto)
                    elif self.azione == "anonimizza" and re.fullmatch(
                            r"(word/people|ppt/commentAuthors|ppt/authors|xl/persons/[^/]+|xl/threadedComments/[^/]+)\.xml", voce.filename):
                        radice = etree.fromstring(contenuto)
                        self.autori(radice)
                        contenuto = etree.tostring(radice, xml_declaration=True, encoding="UTF-8", standalone=True)
                    if self.azione == "anonimizza" and voce.filename in ("docProps/core.xml", "docProps/app.xml"):
                        radice = etree.fromstring(contenuto)
                        for n in radice.iter():
                            if isinstance(n.tag, str) and etree.QName(n).localname in PROPRIETA and n.text:
                                n.text = ""
                                self.conteggi["proprietà del file svuotate"] = self.conteggi.get("proprietà del file svuotate", 0) + 1
                        contenuto = etree.tostring(radice, xml_declaration=True, encoding="UTF-8", standalone=True)
                z.writestr(voce, contenuto)
        return uscita.getvalue()

    def pdf(self, dati):
        from pypdf import PdfReader
        pagine = [(p.extract_text() or "") for p in PdfReader(io.BytesIO(dati)).pages]
        if sum(len(p.strip()) for p in pagine) < 20:   # scansione: le pagine sono immagini
            pagine = self._letto(lambda: lettura.pdf(dati), "PDF senza testo (scansione)")
        return "\n\n".join(f"--- pagina {i + 1} ---\n{self.testo(p)}" for i, p in enumerate(pagine)).encode("utf-8")

    def immagine(self, dati):
        return self.testo(self._letto(lambda: [lettura.immagine(dati)], "immagine")[0]).encode("utf-8")

    def _letto(self, leggi, cosa):
        """Testo ricavato con il riconoscimento dei caratteri. Puo' contenere errori di lettura (una I letta come 1),
        quindi il risultato va riletto: lo segnala anche il resoconto."""
        try:
            pagine = leggi()
        except lettura.NonDisponibile as ex:
            raise Errore(f"{cosa}: {ex}") from ex
        except Exception as ex:   # noqa: BLE001
            raise Errore(lingue.t("documenti.errore.lettura", cosa=cosa, motivo=type(ex).__name__)) from ex
        if sum(len(p.strip()) for p in pagine) < 10:
            raise Errore(lingue.t("documenti.errore.senza_testo", cosa=cosa))
        self.conteggi["pagine_lette"] = self.conteggi.get("pagine_lette", 0) + len(pagine)   # lette dall'immagine: da rileggere
        return pagine


def nome_uscita(nome, azione):
    """nome.docx -> nome.anon.docx ; nome.anon.docx -> nome.ripristinato.docx ; il PDF diventa testo."""
    p = Path(nome)
    base, est = p.stem, p.suffix.lower()
    if azione == "ripristina":
        base = re.sub(r"\.anon$", "", base)
    return f"{base}.{'anon' if azione == 'anonimizza' else 'ripristinato'}{'.txt' if est == '.pdf' or est in IMMAGINI else p.suffix}"


def elabora(nome, dati, azione):
    """(nome del file in uscita, contenuto, conteggi). Solleva Errore se il formato non e' coperto."""
    est, lavoro = Path(nome).suffix.lower(), Lavoro(azione)
    if est in OFFICE:
        try:
            nuovo = lavoro.office(dati, est)
        except (zipfile.BadZipFile, etree.XMLSyntaxError) as ex:
            raise Errore(lingue.t("documenti.errore.office")) from ex
    elif est == ".pdf":
        if azione == "ripristina":
            raise Errore(lingue.t("documenti.errore.pdf_ripristino"))
        nuovo = lavoro.pdf(dati)
    elif est in IMMAGINI:
        if azione == "ripristina":
            raise Errore(lingue.t("documenti.errore.immagine_ripristino"))
        nuovo = lavoro.immagine(dati)
    elif est in TESTO:
        try:
            testo, cod = dati.decode("utf-8-sig"), "utf-8"
        except UnicodeDecodeError:
            testo, cod = dati.decode("cp1252", errors="replace"), "cp1252"
        nuovo = lavoro.testo(testo).encode(cod, errors="replace")
    else:
        raise Errore(lingue.t("documenti.errore.formato", formato=est or lingue.t("documenti.errore.senza_estensione")))
    return nome_uscita(nome, azione), nuovo, lavoro.conteggi


def elabora_auto(nome, dati, azione="auto"):
    """Come elabora, ma con azione "auto" decide da se': un file che contiene segnaposto presenti nell'archivio
    viene ripristinato, ogni altro anonimizzato. Restituisce (azione fatta, nome in uscita, contenuto, conteggi)."""
    if azione == "auto":
        est = Path(nome).suffix.lower()
        if est in OFFICE or est in TESTO:
            try:
                uscita, nuovo, conteggi = elabora(nome, dati, "ripristina")
                if conteggi.get("ripristinati"):
                    return "ripristina", uscita, nuovo, conteggi
            except Errore:   # illeggibile o protezione ferma: lo dira' il tentativo qui sotto
                pass
        azione = "anonimizza"
    return (azione, *elabora(nome, dati, azione))


def percorso(dove, azione):
    """Elabora un file oppure una cartella intera. Restituisce il resoconto, file per file."""
    p = Path(dove.strip().strip('"'))
    if not p.exists():
        raise Errore(lingue.t("documenti.errore.percorso"))
    suffisso = ".anon" if azione == "anonimizza" else ".ripristinato"
    if p.is_file():
        coppie, radice = [(p, p.parent / nome_uscita(p.name, azione))], p.parent
        destinazione = coppie[0][1]
    else:
        base = re.sub(r"\.anon$", "", p.name) if azione == "ripristina" else p.name
        destinazione = radice = p.parent / (base + suffisso)
        coppie = [(f, radice / f.relative_to(p).parent / nome_uscita(f.name, azione)) for f in sorted(p.rglob("*")) if f.is_file()]
    fatti, saltati, totale = [], [], {}
    for origine, uscita in coppie:
        try:
            if origine.stat().st_size > 60_000_000:
                raise Errore(lingue.t("documenti.errore.grande"))
            _, nuovo, conteggi = elabora(origine.name, origine.read_bytes(), azione)
            uscita.parent.mkdir(parents=True, exist_ok=True)
            uscita.write_bytes(nuovo)
            fatti.append({"file": str(origine.relative_to(p) if p.is_dir() else origine.name), "uscita": uscita.name, "conteggi": conteggi})
            for k, n in conteggi.items():
                totale[k] = totale.get(k, 0) + n
        except Errore as ex:
            saltati.append({"file": str(origine.relative_to(p) if p.is_dir() else origine.name), "motivo": str(ex)})
    return {"destinazione": str(destinazione), "fatti": fatti, "saltati": saltati, "conteggi": totale}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3 or sys.argv[1] not in ("anonimizza", "ripristina"):
        sys.exit(__doc__)
    try:
        r = percorso(sys.argv[2], sys.argv[1])
    except Errore as ex:
        sys.exit(str(ex))
    print(f"{len(r['fatti'])} file elaborati, {len(r['saltati'])} saltati -> {r['destinazione']}")
    for f in r["fatti"]:
        print(f"  {f['file']} -> {f['uscita']}  {f['conteggi']}")
    for f in r["saltati"]:
        print(f"  SALTATO {f['file']}: {f['motivo']}")
