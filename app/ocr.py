# -*- coding: utf-8 -*-
"""Lettura del testo da scansioni e immagini (riconoscimento dei caratteri), con il motore gia'
presente in Windows 10 e 11: gira su questo PC, non manda nulla fuori e non richiede di scaricare
modelli. Serve la lingua italiana tra quelle di Windows (c'e' se Windows e' in italiano).

  pdf(dati)        -> testo di ogni pagina di un PDF fatto di immagini
  immagine(dati)   -> testo di un'immagine (png, jpg, tif, bmp)

Se i pacchetti winrt non sono installati le funzioni sollevano NonDisponibile.
"""
import asyncio

SIDE = 2600   # lato lungo, in punti immagine, a cui si porta una pagina prima di leggerla


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


def pdf(data):
    return asyncio.run(_pdf(data))


def image(data):
    return asyncio.run(_image(data))
