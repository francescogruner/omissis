# -*- coding: utf-8 -*-
"""Lettura del testo da scansioni e immagini (riconoscimento dei caratteri), con il motore gia'
presente in Windows 10 e 11: gira su questo PC, non manda nulla fuori e non richiede di scaricare
modelli. Serve la lingua italiana tra quelle di Windows (c'e' se Windows e' in italiano).

  pdf(dati)        -> testo di ogni pagina di un PDF fatto di immagini
  immagine(dati)   -> testo di un'immagine (png, jpg, tif, bmp)

Se i pacchetti winrt non sono installati le funzioni sollevano NonDisponibile.
"""
import asyncio

LATO = 2600   # lato lungo, in punti immagine, a cui si porta una pagina prima di leggerla


class NonDisponibile(Exception):
    pass


def _moduli():
    try:
        from winrt.windows.data.pdf import PdfDocument, PdfPageRenderOptions
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
    except ImportError as ex:
        raise NonDisponibile("la lettura delle scansioni non è installata (pacchetti winrt)") from ex
    motore = OcrEngine.try_create_from_language(Language("it")) or OcrEngine.try_create_from_user_profile_languages()
    if motore is None:
        raise NonDisponibile("in Windows manca la lingua per la lettura dei caratteri (Impostazioni → Lingua → Italiano → Funzionalità)")
    return PdfDocument, PdfPageRenderOptions, BitmapDecoder, DataWriter, InMemoryRandomAccessStream, motore


async def _flusso(dati, DataWriter, InMemoryRandomAccessStream):
    s = InMemoryRandomAccessStream()
    w = DataWriter(s)
    w.write_bytes(dati)
    await w.store_async()
    await w.flush_async()
    w.detach_stream()
    s.seek(0)
    return s


async def _leggi(flusso, BitmapDecoder, motore):
    bitmap = await (await BitmapDecoder.create_async(flusso)).get_software_bitmap_async()
    esito = await motore.recognize_async(bitmap)
    return "\n".join(riga.text for riga in esito.lines)


async def _pdf(dati):
    PdfDocument, PdfPageRenderOptions, BitmapDecoder, DataWriter, InMemoryRandomAccessStream, motore = _moduli()
    documento = await PdfDocument.load_from_stream_async(await _flusso(dati, DataWriter, InMemoryRandomAccessStream))
    pagine = []
    for i in range(documento.page_count):
        pagina = documento.get_page(i)
        scala = LATO / max(pagina.size.width, pagina.size.height, 1)
        opzioni = PdfPageRenderOptions()
        opzioni.destination_width = int(pagina.size.width * scala)
        opzioni.destination_height = int(pagina.size.height * scala)
        uscita = InMemoryRandomAccessStream()
        await pagina.render_to_stream_async(uscita, opzioni)
        uscita.seek(0)
        pagine.append(await _leggi(uscita, BitmapDecoder, motore))
    return pagine


async def _immagine(dati):
    _, _, BitmapDecoder, DataWriter, InMemoryRandomAccessStream, motore = _moduli()
    return await _leggi(await _flusso(dati, DataWriter, InMemoryRandomAccessStream), BitmapDecoder, motore)


def pdf(dati):
    return asyncio.run(_pdf(dati))


def immagine(dati):
    return asyncio.run(_immagine(dati))
