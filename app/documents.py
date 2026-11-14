# -*- coding: utf-8 -*-
"""Anonimizza e ripristina documenti e cartelle intere, per quando l'AI si usa con allegati o con
cartelle di lavoro (Cowork e simili): si da' all'AI la copia anonimizzata, poi si ripristinano i
file che produce.

  python documents.py anonimizza <file o cartella>     ->  <nome>.anon.<est>   /  <cartella>.anon
  python documents.py ripristina <file o cartella>     ->  <nome>.ripristinato.<est>  /  <cartella>.ripristinato

Formati: Word (.docx), Excel (.xlsx), PowerPoint (.pptx), testo (.txt .md .csv .json .html .xml .eml...)
PDF e immagini (ne esce un file di testo: le scansioni si leggono con ocr.py). Nei file Office la formattazione resta: il
testo viene sostituito dentro il documento, anche quando un nome e' spezzato tra pezzi con stili
diversi, e comprende intestazioni, pie' di pagina, note, commenti e testo eliminato con le revisioni.
Vengono svuotati anche autore e azienda nelle proprieta' del file.

NON coperti: immagini inserite dentro i documenti, vecchi .doc/.xls,
nomi dei fogli di Excel, numeri nelle celle numeriche, nomi dei file. In una cartella i file non
coperti vengono SALTATI (non copiati), cosi' nella copia anonimizzata non finisce nulla in chiaro.

Richiede il motore acceso (panel.py oppure start.py).
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

import ocr
import i18n
import paths
import restore as R

HERE = Path(__file__).resolve().parent
ENGINE = f"http://127.0.0.1:{paths.ENGINE_PORT}"
TEXT = {".txt", ".md", ".csv", ".tsv", ".json", ".log", ".xml", ".html", ".htm", ".eml", ".yaml", ".yml", ".ini", ".sql",
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
COMMON = [(r"(word|ppt|xl)/(charts/chart\d+|diagrams/data\d+|drawings/drawing\d+)\.xml", None, None)]
PROPERTIES = {"creator", "lastModifiedBy", "Company", "Manager"}
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}   # lette con il riconoscimento dei caratteri: ne esce un file di testo
COVERED = TEXT | set(OFFICE) | {".pdf"} | IMAGES


class Error(Exception):
    """codice: il perche' in una parola (protezione | senza_testo | formato), per chi deve decidere cosa fare del file."""

    def __init__(self, message, code=""):
        super().__init__(message)
        self.code = code


def engine(path, data):
    token = (paths.DATA / "token.txt").read_text(encoding="utf-8").strip()
    req = urllib.request.Request(ENGINE + path, data=json.dumps(data).encode("utf-8"),
                                  headers={"Content-Type": "application/json", "X-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as ex:
        raise Error(i18n.t("program.protection_not_active"), "protection") from ex


def apply(segments, positions):
    """Riporta le sostituzioni [inizio, fine, nuovo] (riferite al testo unito) dentro i singoli pezzi:
    il nuovo testo va nel primo pezzo toccato, gli altri perdono solo i caratteri coperti."""
    out, starts, n = list(segments), [], 0
    for s in segments:
        starts.append(n)
        n += len(s)
    for ini, end, fresh in sorted(positions, reverse=True):
        i = max(k for k, x in enumerate(starts) if x <= ini)
        j = max(k for k, x in enumerate(starts) if x < end) if end > ini else i
        if i == j:
            out[i] = out[i][:ini - starts[i]] + fresh + out[i][end - starts[i]:]
        else:
            out[j] = out[j][end - starts[j]:]
            for k in range(i + 1, j):
                out[k] = ""
            out[i] = out[i][:ini - starts[i]] + fresh
    return out


class Work:
    """Una passata di anonimizzazione o di ripristino: raccoglie i conteggi."""

    def __init__(self, action):
        self.action, self.counts, self.cache = action, {}, {}

    def positions(self, texts):
        """Per ogni testo le sostituzioni da fare: [[inizio, fine, nuovo], ...]."""
        if self.action == "anonymize":
            out = []
            for k in range(0, len(texts), 150):
                r = engine("/mask", {"texts": texts[k:k + 150]})
                out += r["positions"]
                for e, n in r["counts"].items():
                    self.counts[e] = self.counts.get(e, 0) + n
            return out
        found_items = [[(m.start(), m.end(), m.group()) for m in R.RX_PLACEHOLDER.finditer(t)] for t in texts]
        missing = sorted({seg for line in found_items for _, _, seg in line} - set(self.cache))
        for k in range(0, len(missing), 500):
            self.cache.update(engine("/values", {"placeholder": missing[k:k + 500]})["mapping"])
        out = []
        for line in found_items:
            good = [[s, e, self.cache[seg]] for s, e, seg in line if seg in self.cache]
            self.counts["restored"] = self.counts.get("restored", 0) + len(good)
            self.counts["unknown"] = self.counts.get("unknown", 0) + len(line) - len(good)
            out.append(good)
        return out

    def text(self, t):
        """Testo semplice, a blocchi di righe per non mandare tutto in un colpo solo."""
        blocks, cur = [], ""
        for line in t.splitlines(keepends=True):
            if len(cur) + len(line) > 3000 and cur:
                blocks.append(cur)
                cur = ""
            cur += line
        blocks.append(cur)
        return "".join("".join(apply([b], p)) for b, p in zip(blocks, self.positions(blocks)))

    def authors(self, root):
        """Nomi di chi ha scritto revisioni e commenti: stanno negli attributi, non nel testo. Non ripristinabili."""
        if self.action != "anonymize":
            return
        for n in root.iter():
            if not isinstance(n.tag, str):
                continue
            locale = etree.QName(n).localname
            for attr in list(n.attrib):
                a = etree.QName(attr).localname
                if a in ("author", "userId", "displayName", "initials") or (a == "name" and locale in ("cmAuthor", "author", "person")):
                    n.set(attr, "A" if a == "initials" else "Autore")
                    self.counts["autori di revisioni e commenti rimossi"] = self.counts.get("autori di revisioni e commenti rimossi", 0) + (a != "initials")
            if locale == "author" and n.text and n.text.strip() and len(n) == 0:   # elenco degli autori dei commenti in Excel
                n.text = "Autore"
                self.counts["autori di revisioni e commenti rimossi"] = self.counts.get("autori di revisioni e commenti rimossi", 0) + 1

    def xml(self, data, paragraph, carriers):
        root = etree.fromstring(data)
        self.authors(root)
        if paragraph is None:   # parte senza struttura nota: ogni nodo di testo per conto suo
            groups = [[n] for n in root.iter() if isinstance(n.tag, str) and n.text and n.text.strip() and len(n) == 0]
        else:                   # ogni pezzo di testo va con il paragrafo piu' vicino che lo contiene (le caselle
            per = {}            # di testo sono paragrafi dentro paragrafi: cosi' nessun pezzo e' trattato due volte)
            for n in root.iter(*carriers):
                if n.text:
                    p = n.getparent()
                    while p is not None and p.tag != paragraph:
                        p = p.getparent()
                    per.setdefault(p, []).append(n)
            groups = list(per.values())
        groups = [g for g in groups if "".join(n.text for n in g).strip()]
        for g, pos in zip(groups, self.positions(["".join(n.text for n in g) for g in groups])):
            if pos:
                for n, fresh in zip(g, apply([n.text for n in g], pos)):
                    n.text = fresh
                    n.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def connections(self, data):
        """Collegamenti verso l'esterno (siti, mailto): se contengono un dato sensibile vengono neutralizzati.
        Non sono ripristinabili: nel documento resta il testo del collegamento, non la sua destinazione."""
        root = etree.fromstring(data)
        external = [n for n in root if n.get("TargetMode") == "External" and n.get("Target")]
        if not external:
            return data
        texts = [urllib.parse.unquote(n.get("Target")) for n in external]
        for n, pos in zip(external, self.positions(texts)):
            if pos:
                n.set("Target", "https://collegamento-rimosso.invalid/")
                self.counts["collegamenti neutralizzati"] = self.counts.get("collegamenti neutralizzati", 0) + 1
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def office(self, data, est):
        inbound_item, output = zipfile.ZipFile(io.BytesIO(data)), io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
            for entry in inbound_item.infolist():
                content = inbound_item.read(entry.filename)
                embedded = re.search(r"/embeddings/[^/]+(\.docx|\.xlsx|\.pptx)$", entry.filename.lower())
                for model, paragraph, carriers in OFFICE[est] + COMMON:
                    if re.fullmatch(model, entry.filename):
                        content = self.xml(content, paragraph, carriers)
                        break
                else:
                    if embedded:                       # un foglio o un documento dentro il documento
                        content = self.office(content, embedded.group(1))
                    elif entry.filename.endswith(".rels") and self.action == "anonymize":
                        content = self.connections(content)
                    elif self.action == "anonymize" and re.fullmatch(
                            r"(word/people|ppt/commentAuthors|ppt/authors|xl/persons/[^/]+|xl/threadedComments/[^/]+)\.xml", entry.filename):
                        root = etree.fromstring(content)
                        self.authors(root)
                        content = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                    if self.action == "anonymize" and entry.filename in ("docProps/core.xml", "docProps/app.xml"):
                        root = etree.fromstring(content)
                        for n in root.iter():
                            if isinstance(n.tag, str) and etree.QName(n).localname in PROPERTIES and n.text:
                                n.text = ""
                                self.counts["proprietà del file svuotate"] = self.counts.get("proprietà del file svuotate", 0) + 1
                        content = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                z.writestr(entry, content)
        return output.getvalue()

    def pdf(self, data):
        from pypdf import PdfReader
        pages = [(p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages]
        if sum(len(p.strip()) for p in pages) < 20:   # scansione: le pagine sono immagini
            pages = self._read_back(lambda: ocr.pdf(data), "PDF senza testo (scansione)")
        return "\n\n".join(f"--- pagina {i + 1} ---\n{self.text(p)}" for i, p in enumerate(pages)).encode("utf-8")

    def image(self, data):
        return self.text(self._read_back(lambda: [ocr.image(data)], "image")[0]).encode("utf-8")

    def _read_back(self, read, what):
        """Testo ricavato con il riconoscimento dei caratteri. Puo' contenere errori di lettura (una I letta come 1),
        quindi il risultato va riletto: lo segnala anche il resoconto."""
        try:
            pages = read()
        except ocr.Unavailable as ex:
            raise Error(f"{what}: {ex}") from ex
        except Exception as ex:   # noqa: BLE001
            raise Error(i18n.t("documents.error.reading", what=what, reason=type(ex).__name__)) from ex
        if sum(len(p.strip()) for p in pages) < 10:
            raise Error(i18n.t("documents.error.without_text", what=what), "without_text")
        self.counts["pages_read"] = self.counts.get("pages_read", 0) + len(pages)   # lette dall'immagine: da rileggere
        return pages


def output_name(name, action):
    """nome.docx -> nome.anon.docx ; nome.anon.docx -> nome.ripristinato.docx ; il PDF diventa testo."""
    p = Path(name)
    base, est = p.stem, p.suffix.lower()
    if action == "restore":
        base = re.sub(r"\.anon$", "", base)
    return f"{base}.{'anon' if action == 'anonymize' else 'restored'}{'.txt' if est == '.pdf' or est in IMAGES else p.suffix}"


def work_on(name, data, action):
    """(nome del file in uscita, contenuto, conteggi). Solleva Errore se il formato non e' coperto."""
    est, work = Path(name).suffix.lower(), Work(action)
    if est in OFFICE:
        try:
            fresh = work.office(data, est)
        except (zipfile.BadZipFile, etree.XMLSyntaxError) as ex:
            raise Error(i18n.t("documents.error.office")) from ex
    elif est == ".pdf":
        if action == "restore":
            raise Error(i18n.t("documents.error.pdf_restoring"))
        fresh = work.pdf(data)
    elif est in IMAGES:
        if action == "restore":
            raise Error(i18n.t("documents.error.image_restoring"))
        fresh = work.image(data)
    elif est in TEXT:
        try:
            text, cod = data.decode("utf-8-sig"), "utf-8"
        except UnicodeDecodeError:
            text, cod = data.decode("cp1252", errors="replace"), "cp1252"
        fresh = work.text(text).encode(cod, errors="replace")
    else:
        raise Error(i18n.t("documents.error.fmt", fmt=est or i18n.t("documents.error.without_extension")), "fmt")
    return output_name(name, action), fresh, work.counts


def work_on_auto(name, data, action="auto"):
    """Come elabora, ma con azione "auto" decide da se': un file che contiene segnaposto presenti nell'archivio
    viene ripristinato, ogni altro anonimizzato. Restituisce (azione fatta, nome in uscita, contenuto, conteggi)."""
    if action == "auto":
        est = Path(name).suffix.lower()
        if est in OFFICE or est in TEXT:
            try:
                output, fresh, counts = work_on(name, data, "restore")
                if counts.get("restored"):
                    return "restore", output, fresh, counts
            except Error:   # illeggibile o protezione ferma: lo dira' il tentativo qui sotto
                pass
        action = "anonymize"
    return (action, *work_on(name, data, action))


def path(where, action):
    """Elabora un file oppure una cartella intera. Restituisce il resoconto, file per file."""
    p = Path(where.strip().strip('"'))
    if not p.exists():
        raise Error(i18n.t("documents.error.path"))
    suffix = ".anon" if action == "anonymize" else ".restored"
    if p.is_file():
        pairs, root = [(p, p.parent / output_name(p.name, action))], p.parent
        destination = pairs[0][1]
    else:
        base = re.sub(r"\.anon$", "", p.name) if action == "restore" else p.name
        destination = root = p.parent / (base + suffix)
        pairs = [(f, root / f.relative_to(p).parent / output_name(f.name, action)) for f in sorted(p.rglob("*")) if f.is_file()]
    completed, skipped, total = [], [], {}
    for origin, output in pairs:
        try:
            if origin.stat().st_size > 60_000_000:
                raise Error(i18n.t("documents.error.large"))
            _, fresh, counts = work_on(origin.name, origin.read_bytes(), action)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(fresh)
            completed.append({"file": str(origin.relative_to(p) if p.is_dir() else origin.name), "output": output.name, "counts": counts})
            for k, n in counts.items():
                total[k] = total.get(k, 0) + n
        except Error as ex:
            skipped.append({"file": str(origin.relative_to(p) if p.is_dir() else origin.name), "reason": str(ex)})
    return {"destination": str(destination), "completed": completed, "skipped": skipped, "counts": total}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3 or sys.argv[1] not in ("anonymize", "restore"):
        sys.exit(__doc__)
    try:
        r = path(sys.argv[2], sys.argv[1])
    except Error as ex:
        sys.exit(str(ex))
    print(f"{len(r['completed'])} file elaborati, {len(r['skipped'])} saltati -> {r['destination']}")
    for f in r["completed"]:
        print(f"  {f['file']} -> {f['output']}  {f['counts']}")
    for f in r["skipped"]:
        print(f"  SALTATO {f['file']}: {f['reason']}")
