# -*- coding: utf-8 -*-
"""Lettura del testo da scansioni e immagini (riconoscimento dei caratteri), con il motore gia'
presente nel sistema: gira su questo computer, non manda nulla fuori e non richiede di scaricare
modelli.

  Windows 10 e 11   il motore di Windows (pacchetti winrt). Serve la lingua italiana tra quelle di Windows
                    (c'e' se Windows e' in italiano)
  Mac               il riconoscimento del testo di macOS (Vision), lo stesso di «Testo attivo»; le pagine dei PDF le
                    disegna Quartz. Serve il pacchetto pyobjc-framework-Vision, che viaggia dentro l'app
  Linux             Tesseract, se è installato con la lingua italiana (pacchetti tesseract-ocr e tesseract-ocr-ita); le
                    pagine dei PDF le disegna pdftoppm (pacchetto poppler-utils, di serie in quasi tutti i desktop)

  pdf(dati)        -> testo di ogni pagina di un PDF fatto di immagini
  immagine(dati)   -> testo di un'immagine (png, jpg, tif, bmp)

Se manca cio' che serve le funzioni sollevano Unavailable.
"""
import asyncio
import sys

SIDE = 2600   # lato lungo, in punti immagine, a cui si porta una pagina prima di leggerla
MAC = sys.platform == "darwin"
LINUX = sys.platform.startswith("linux")
TESSERACT = ["ita", "eng", "fra", "deu", "spa"]   # su Linux: quelle installate tra queste
LANGUAGES = ["it-IT", "en-US", "fr-FR", "de-DE", "es-ES"]   # sul Mac: quelle che Vision conosce tra queste, in quest'ordine


class Unavailable(Exception):
    pass


def _modules():
    try:
        from winrt.windows.data.pdf import PdfDocument, PdfPageRenderOptions
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
    except ImportError as ex:
        raise Unavailable("la lettura delle scansioni non è installata (pacchetti winrt)") from ex
    engine = OcrEngine.try_create_from_language(Language("it")) or OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise Unavailable("in Windows manca la lingua per la lettura dei caratteri (Impostazioni → Lingua → Italiano → Funzionalità)")
    return PdfDocument, PdfPageRenderOptions, BitmapDecoder, DataWriter, InMemoryRandomAccessStream, engine


async def _stream(data, DataWriter, InMemoryRandomAccessStream):
    s = InMemoryRandomAccessStream()
    w = DataWriter(s)
    w.write_bytes(data)
    await w.store_async()
    await w.flush_async()
    w.detach_stream()
    s.seek(0)
    return s


async def _read(stream, BitmapDecoder, engine):
    bitmap = await (await BitmapDecoder.create_async(stream)).get_software_bitmap_async()
    outcome = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in outcome.lines)


async def _pdf(data):
    PdfDocument, PdfPageRenderOptions, BitmapDecoder, DataWriter, InMemoryRandomAccessStream, engine = _modules()
    document = await PdfDocument.load_from_stream_async(await _stream(data, DataWriter, InMemoryRandomAccessStream))
    pages = []
    for i in range(document.page_count):
        page = document.get_page(i)
        scale = SIDE / max(page.size.width, page.size.height, 1)
        options = PdfPageRenderOptions()
        options.destination_width = int(page.size.width * scale)
        options.destination_height = int(page.size.height * scale)
        output = InMemoryRandomAccessStream()
        await page.render_to_stream_async(output, options)
        output.seek(0)
        pages.append(await _read(output, BitmapDecoder, engine))
    return pages


async def _image(data):
    _, _, BitmapDecoder, DataWriter, InMemoryRandomAccessStream, engine = _modules()
    return await _read(await _stream(data, DataWriter, InMemoryRandomAccessStream), BitmapDecoder, engine)


# ------------------------------------------------------------------ Mac (Vision e Quartz)

def _mac_modules():
    try:
        import Quartz
        import Vision
    except ImportError as ex:
        raise Unavailable("la lettura delle scansioni non è installata (pyobjc-framework-Vision)") from ex
    return Quartz, Vision


def _mac_read(cg_image, Vision):
    """Il testo di un'immagine di Quartz, riga per riga."""
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    try:   # le lingue che questo macOS sa leggere, tra quelle che servono
        known, _ = request.supportedRecognitionLanguagesAndReturnError_(None)
        wanted = [code for code in LANGUAGES if code in list(known or [])]
        if wanted:
            request.setRecognitionLanguages_(wanted)
    except Exception:   # noqa: BLE001  (macOS piu' vecchio: restano le lingue di serie)
        pass
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
    done, error = handler.performRequests_error_([request], None)
    if not done:
        raise RuntimeError(str(error) if error is not None else "Vision")
    lines = []
    for found in request.results() or []:   # nell'ordine di lettura, come le consegna Vision
        best = found.topCandidates_(1)
        if best:
            lines.append(str(best[0].string()))
    return "\n".join(lines)


def _mac_image(data):
    Quartz, Vision = _mac_modules()
    from Foundation import NSData
    source = Quartz.CGImageSourceCreateWithData(NSData.dataWithBytes_length_(data, len(data)), None)
    picture = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None) if source is not None else None
    if picture is None:
        raise RuntimeError("immagine non leggibile")
    return _mac_read(picture, Vision)


def _mac_pdf(data):
    Quartz, Vision = _mac_modules()
    from Foundation import NSData
    document = Quartz.CGPDFDocumentCreateWithProvider(Quartz.CGDataProviderCreateWithCFData(NSData.dataWithBytes_length_(data, len(data))))
    if document is None:
        raise RuntimeError("PDF non leggibile")
    pages = []
    for i in range(1, Quartz.CGPDFDocumentGetNumberOfPages(document) + 1):
        page = Quartz.CGPDFDocumentGetPage(document, i)
        box = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
        turned = Quartz.CGPDFPageGetRotationAngle(page) % 180 == 90   # pagina girata di un quarto: larghezza e altezza si scambiano
        width, height = (box.size.height, box.size.width) if turned else (box.size.width, box.size.height)
        scale = SIDE / max(width, height, 1)
        w, h = max(1, int(width * scale)), max(1, int(height * scale))
        context = Quartz.CGBitmapContextCreate(None, w, h, 8, 0, Quartz.CGColorSpaceCreateDeviceRGB(), Quartz.kCGImageAlphaPremultipliedLast)
        Quartz.CGContextSetRGBFillColor(context, 1, 1, 1, 1)
        Quartz.CGContextFillRect(context, Quartz.CGRectMake(0, 0, w, h))
        Quartz.CGContextScaleCTM(context, scale, scale)
        Quartz.CGContextConcatCTM(context, Quartz.CGPDFPageGetDrawingTransform(page, Quartz.kCGPDFMediaBox, Quartz.CGRectMake(0, 0, width, height), 0, True))
        Quartz.CGContextDrawPDFPage(context, page)
        pages.append(_mac_read(Quartz.CGBitmapContextCreateImage(context), Vision))
    return pages


# ------------------------------------------------------------------ Linux (Tesseract e pdftoppm)

def _tesseract():
    """Il comando di Tesseract e le lingue da usare, o Unavailable se manca qualcosa."""
    import shutil
    import subprocess
    exe = shutil.which("tesseract")
    if not exe:
        raise Unavailable("la lettura delle scansioni su Linux usa Tesseract, che qui non è installato (pacchetti tesseract-ocr e tesseract-ocr-ita)")
    try:
        r = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise Unavailable("Tesseract non risponde") from ex
    known = set((r.stdout + r.stderr).split())
    wanted = [code for code in TESSERACT if code in known]
    if not wanted:
        raise Unavailable("a Tesseract manca la lingua per leggere i caratteri (pacchetto tesseract-ocr-ita)")
    return exe, "+".join(wanted)


def _linux_read(exe, languages, source, data=None):
    import subprocess
    r = subprocess.run([exe, source, "stdout", "-l", languages], input=data, capture_output=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", errors="replace").strip()[-200:] or "tesseract")
    return r.stdout.decode("utf-8", errors="replace").strip()


def _linux_image(data):
    exe, languages = _tesseract()
    return _linux_read(exe, languages, "stdin", data)


def _linux_pdf(data):
    """Ogni pagina diventa un'immagine in una cartella temporanea (leggibile solo da chi usa il computer, cancellata
    subito dopo) e Tesseract la legge."""
    import re
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path
    exe, languages = _tesseract()
    draw = shutil.which("pdftoppm")
    if not draw:
        raise Unavailable("per leggere i PDF fatti di immagini su Linux serve pdftoppm (pacchetto poppler-utils)")
    with tempfile.TemporaryDirectory(prefix="omissis-ocr-") as folder:
        source = Path(folder) / "in.pdf"
        source.write_bytes(data)
        r = subprocess.run([draw, "-png", "-scale-to", str(SIDE), str(source), str(Path(folder) / "p")], capture_output=True, timeout=900)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", errors="replace").strip()[-200:] or "pdftoppm")
        pages = sorted(Path(folder).glob("p-*.png"), key=lambda p: int(re.search(r"(\d+)\.png$", p.name).group(1)))
        return [_linux_read(exe, languages, str(p)) for p in pages]


def pdf(data):
    return _mac_pdf(data) if MAC else _linux_pdf(data) if LINUX else asyncio.run(_pdf(data))


def image(data):
    return _mac_image(data) if MAC else _linux_image(data) if LINUX else asyncio.run(_image(data))
