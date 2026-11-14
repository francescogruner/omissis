# -*- coding: utf-8 -*-
"""Prova dell'anonimizzazione dei documenti con file di esempio (dati inventati).

Crea una cartella di esempio con Word, Excel, PowerPoint, testo, CSV, PDF, una scansione e un file non coperto;
la anonimizza, controlla che nei file prodotti non resti nessun valore originale (nemmeno in
intestazioni, testo eliminato con le revisioni, proprieta' del file), che i file si riaprano e
che la formattazione resti; poi ripristina e confronta con gli originali.
Richiede la protezione attiva.   Uso: python e2e_documents.py
"""
import shutil
import sys
import zipfile
from pathlib import Path

import docx
import openpyxl
from docx.shared import Pt
from pptx import Presentation
from pptx.util import Inches

import documents

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent / "data" / "esempi"
ORIGINALS = ["Giulia Ferraresi", "Ferraresi", "Nevatek", "Aldo Bruschi", "aldo.bruschi@nevatek.example", "347 5551234",
             "IT60X0542811101000000123456", "Tramonto!2026", "FRRGLI85M41F205X", "Ottavio Marchesini"]


def create():
    shutil.rmtree(BASE, ignore_errors=True)
    c = BASE / "Pratica"
    (c / "sotto").mkdir(parents=True)
    # --- Word: nome spezzato tra pezzi con stili diversi, tabella, intestazione, pie' di pagina, testo eliminato, proprieta'
    d = docx.Document()
    d.core_properties.author, d.core_properties.last_modified_by = "Ottavio Marchesini", "Ottavio Marchesini"
    d.sections[0].header.paragraphs[0].text = "Studio Nevatek S.r.l. - riservato"
    d.sections[0].footer.paragraphs[0].text = "Referente: Aldo Bruschi, aldo.bruschi@nevatek.example"
    d.add_heading("Verbale di assistenza", 1)
    p = d.add_paragraph("La signora ")
    p.add_run("Giulia ").bold = True
    r = p.add_run("Ferraresi")
    r.italic, r.font.size = True, Pt(14)
    p.add_run(" (codice fiscale FRRGLI85M41F205X) ha chiesto il rimborso sull'IBAN IT60X0542811101000000123456.")
    d.add_paragraph("Per contatti chiamare il 347 5551234. La password provvisoria è Tramonto!2026.")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Cliente", "Referente"
    t.cell(1, 0).text, t.cell(1, 1).text = "Nevatek S.r.l.", "Aldo Bruschi"
    d.save(c / "verbale.docx")
    # testo eliminato con le revisioni: aggiunto a mano nell'XML
    removed = ('<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:del w:id="9" w:author="Ottavio Marchesini" '
                 'w:date="2026-11-01T10:00:00Z"><w:r><w:delText>Bozza inviata per errore a Aldo Bruschi</w:delText></w:r></w:del></w:p>')
    rewrite(c / "verbale.docx", "word/document.xml", lambda x: x.replace(b"<w:sectPr", removed.encode() + b"<w:sectPr", 1))
    # --- Excel: testo nelle celle, numeri, due fogli
    w = openpyxl.Workbook()
    f = w.active
    f.title = "Contatti"
    f.append(["Nome", "Email", "Telefono", "Importo"])
    f.append(["Giulia Ferraresi", "giulia.ferraresi@nevatek.example", "347 5551234", 1250.5])
    f.append(["Aldo Bruschi", "aldo.bruschi@nevatek.example", "0461 555012", 980])
    w.create_sheet("Note").append(["Cliente Nevatek: richiamare Aldo Bruschi entro venerdì"])
    w.save(c / "contatti.xlsx")
    # --- PowerPoint
    pr = Presentation()
    s = pr.slides.add_slide(pr.slide_layouts[1])
    s.shapes.title.text = "Progetto per Nevatek S.r.l."
    s.placeholders[1].text = "Referente: Giulia Ferraresi\nContatto: aldo.bruschi@nevatek.example"
    s.notes_slide.notes_text_frame.text = "Ricordare a Aldo Bruschi la password Tramonto!2026"
    s.shapes.add_textbox(Inches(1), Inches(5), Inches(6), Inches(1)).text_frame.text = "Tel. 347 5551234"
    pr.save(c / "sotto" / "presentazione.pptx")
    # --- testo, CSV, PDF con testo, file non coperto
    (c / "nota.txt").write_text("Chiamato Aldo Bruschi (347 5551234): conferma il bonifico a Giulia Ferraresi.\n", encoding="utf-8")
    (c / "sotto" / "elenco.csv").write_text("nome;email\nGiulia Ferraresi;giulia.ferraresi@nevatek.example\nAldo Bruschi;aldo.bruschi@nevatek.example\n", encoding="utf-8")
    (c / "lettera.pdf").write_bytes(pdf("Gentile Giulia Ferraresi, confermiamo il rimborso. Contatto: aldo.bruschi@nevatek.example"))
    (c / "archivio.zip").write_bytes(b"PK" + bytes(20))
    # --- una scansione: testo disegnato in un'immagine, salvata come PDF senza testo e come immagine
    from PIL import Image, ImageDraw, ImageFont
    sheet = Image.new("RGB", (1654, 2339), "white")
    pen, font = ImageDraw.Draw(sheet), ImageFont.truetype("arial.ttf", 34)
    for i, line in enumerate(["DICHIARAZIONE", "La sottoscritta Giulia Ferraresi, residente a Brescia,", "telefono 347 5551234, email giulia.ferraresi@nevatek.example,",
                              "dichiara di lavorare con Aldo Bruschi presso la Nevatek S.r.l."]):
        pen.text((140, 220 + i * 70), line, fill="black", font=font)
    sheet = sheet.rotate(0.6, fillcolor="white")
    sheet.save(c / "scansione.pdf", "PDF", resolution=200)
    sheet.save(c / "sotto" / "fotografia.png")
    return c


def rewrite(file, part, f):
    entries = {v.filename: zipfile.ZipFile(file).read(v.filename) for v in zipfile.ZipFile(file).infolist()}
    entries[part] = f(entries[part])
    with zipfile.ZipFile(file, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in entries.items():
            z.writestr(k, v)


def pdf(text):
    """PDF minimo di una pagina con una riga di testo."""
    stream = f"BT /F1 11 Tf 40 760 Td ({text}) Tj ET".encode("latin-1")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, pos = b"%PDF-1.4\n", []
    for i, o in enumerate(objects):
        pos.append(len(out))
        out += b"%d 0 obj\n" % (i + 1) + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % p for p in pos)
    return out + b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % x


def whole_text(file):
    """Tutto cio' che c'e' dentro un file, comprese le parti interne dei file Office."""
    if file.suffix in (".docx", ".xlsx", ".pptx"):
        z = zipfile.ZipFile(file)
        return "\n".join(z.read(v).decode("utf-8", errors="replace") for v in z.namelist() if v.endswith((".xml", ".rels")))
    return file.read_bytes().decode("utf-8", errors="replace")


def visible(file):
    if file.suffix == ".docx":
        d = docx.Document(file)
        cells = [c.text for t in d.tables for r in t.rows for c in r.cells]
        return "\n".join([p.text for p in d.paragraphs] + cells + [d.sections[0].header.paragraphs[0].text, d.sections[0].footer.paragraphs[0].text])
    if file.suffix == ".xlsx":
        return "\n".join(str(c.value) for f in openpyxl.load_workbook(file) for r in f.iter_rows() for c in r if c.value is not None)
    if file.suffix == ".pptx":
        return "\n".join(sh.text_frame.text for s in Presentation(file).slides for sh in list(s.shapes) + list(s.notes_slide.shapes) if sh.has_text_frame)
    return file.read_text(encoding="utf-8")


ok = True


def check(what, outcome, detail=""):
    global ok
    ok &= bool(outcome)
    print(f"{'OK    ' if outcome else 'ERRORE'} {what}" + (f"  {detail}" if detail and not outcome else ""))


folder = create()
r = documents.path(str(folder), "anonymize")
anon = Path(r["destination"])
print(f"anonimizzati {len(r['completed'])} file, saltati {len(r['skipped'])}: {r['counts']}")
check("il file non coperto è saltato e non finisce nella copia", [s["file"] for s in r["skipped"]] == ["archivio.zip"] and not (anon / "archivio.zip").exists())
for name in ("scansione.anon.txt", "sotto/fotografia.anon.txt"):
    read_back = (anon / name).read_text(encoding="utf-8") if (anon / name).exists() else ""
    check(f"{name}: la scansione è stata letta e mascherata", "[PERSONA_" in read_back and "[EMAIL_" in read_back and "dichiara" in read_back, read_back[:80])
for f in sorted(anon.rglob("*.*")):
    remaining = [v for v in ORIGINALS if v in whole_text(f)]
    check(f"{f.relative_to(anon)}: nessun valore originale all'interno", not remaining, str(remaining))
d = docx.Document(anon / "verbale.anon.docx")
par = next(p for p in d.paragraphs if "codice fiscale" in p.text)
check("Word: il file si riapre e gli stili restano (grassetto sul primo pezzo del nome)", par.runs[1].bold and "[PERSONA_" in par.runs[1].text, par.text)
check("Word: autore svuotato nelle proprietà", not d.core_properties.author and not d.core_properties.last_modified_by)
f = openpyxl.load_workbook(anon / "contatti.anon.xlsx")["Contatti"]
check("Excel: il file si riapre, i numeri restano numeri", f["D2"].value == 1250.5 and "[PERSONA_" in str(f["A2"].value), f"{f['A2'].value} {f['D2'].value}")
check("PowerPoint: il file si riapre", "[ORG_" in visible(anon / "sotto" / "presentazione.anon.pptx"))
check("PDF: esce un file di testo mascherato", "[PERSONA_" in (anon / "lettera.anon.txt").read_text(encoding="utf-8"))

r2 = documents.path(str(anon), "restore")
rip = Path(r2["destination"])
print(f"ripristinati {len(r2['completed'])} file: {r2['counts']}")
for name in ("verbale.docx", "contatti.xlsx", "sotto/presentazione.pptx", "nota.txt", "sotto/elenco.csv"):
    p = Path(name)
    orig, returned = folder / p, rip / p.parent / f"{p.stem}.restored{p.suffix}"
    check(f"{name}: dopo il ripristino il testo è uguale all'originale", returned.exists() and visible(orig) == visible(returned),
              "" if not returned.exists() else f"\n   originale: {visible(orig)[:200]!r}\n   tornato:   {visible(returned)[:200]!r}")
print("\nEsempio (Word anonimizzato):", visible(anon / "verbale.anon.docx").replace("\n", " | ")[:420])
sys.exit(0 if ok else 1)
