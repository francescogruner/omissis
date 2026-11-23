# -*- coding: utf-8 -*-
"""Protobuf letto e riscritto senza conoscerne lo schema.

Serve al proxy per le chiamate che un servizio manda in formato binario invece che in JSON: dal novembre 2026 claude.ai
(sito e app) manda cosi' i messaggi, con il protocollo Connect (ConversationService/PerformAction). Di un messaggio
protobuf si riconoscono, senza schema, i campi e il loro tipo; di ogni campo «a lunghezza» si capisce se dentro c'e' un
altro messaggio, un testo o dei byte. Bastano tre cose:

  shape(dati)             la forma, per il registro: numeri dei campi, tipi e lunghezze, MAI i valori
  texts(dati)             i testi contenuti, nell'ordine in cui compaiono
  rebuild(dati, cambi)    lo stesso messaggio con alcuni testi sostituiti (le lunghezze si rifanno da sole)

Cio' che non cambia resta byte per byte com'era. Dove un pezzo si puo' leggere sia come messaggio sia come testo vale
questa regola: e' un messaggio se si legge per intero come tale e contiene byte di controllo, non e' testo valido o
comincia con l'etichetta del campo 1 (un a capo); altrimenti, se e' testo senza caratteri di controllo, e' un testo.
"""

MAX_DEPTH = 12


def _varint(data, i):
    value, shift = 0, 0
    while True:
        b = data[i]
        i += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, i
        shift += 7
        if shift > 63:
            raise ValueError("varint")


def _encode(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def fields(data):
    """[(numero, tipo, inizio del campo, inizio del valore, fine)] oppure None se i byte non sono un messaggio protobuf."""
    out, i, n = [], 0, len(data)
    try:
        while i < n:
            start = i
            key, i = _varint(data, i)
            number, kind = key >> 3, key & 7
            if not 0 < number < 20000:
                return None
            if kind == 0:
                _, end = _varint(data, i)
            elif kind == 1:
                end = i + 8
            elif kind == 5:
                end = i + 4
            elif kind == 2:
                size, i = _varint(data, i)
                end = i + size
            else:
                return None
            if end > n:
                return None
            out.append((number, kind, start, i, end))
            i = end
    except (IndexError, ValueError):
        return None
    return out


def _text(piece):
    """Il pezzo come testo, se e' testo valido senza caratteri di controllo; altrimenti None."""
    try:
        s = bytes(piece).decode("utf-8")
    except UnicodeDecodeError:
        return None
    return None if any(ord(c) < 32 and c not in "\n\r\t" for c in s) else s


def _inside(piece, depth):
    """Che cosa c'e' in un campo a lunghezza: ("message", campi) | ("text", testo) | ("bytes", None)."""
    text = _text(piece)
    inner = fields(piece) if len(piece) > 1 and depth < MAX_DEPTH else None
    if inner is not None and (text is None or piece[:1] == b"\n" or any(b < 32 and b not in (9, 10, 13) for b in piece)):
        return "message", inner
    if text is not None:
        return "text", text
    return ("message", inner) if inner is not None else ("bytes", None)


def shape(data, depth=0):
    """La forma di un messaggio: {numero del campo: tipo}, con i messaggi annidati; un campo ripetuto e' [tipo, "xN"].
    None se i byte non sono protobuf."""
    listing = fields(data)
    if listing is None:
        return None
    out = {}
    for number, kind, _, start, end in listing:
        if kind == 2:
            what, inner = _inside(data[start:end], depth)
            form = shape(data[start:end], depth + 1) if what == "message" else None
            what = form if form is not None else f"{'str' if what == 'text' else 'bytes'}{end - start}"
        else:
            what = {0: "int", 1: "fixed64", 5: "fixed32"}[kind]
        name = str(number)
        if name not in out:
            if len(out) >= 40:
                break
            out[name] = what
        elif isinstance(out[name], list):
            out[name][1] = f"x{int(out[name][1][1:]) + 1}"
        else:
            out[name] = [out[name], "x2"]
    return out


def texts(data, depth=0, out=None):
    """I testi contenuti nel messaggio, nell'ordine in cui compaiono. None se i byte non sono protobuf."""
    listing = fields(data)
    if listing is None:
        return None
    out = [] if out is None else out
    for _, kind, _, start, end in listing:
        if kind != 2 or end == start:
            continue
        what, inner = _inside(data[start:end], depth)
        if what == "message":
            texts(data[start:end], depth + 1, out)
        elif what == "text":
            out.append(inner)
    return out


def places(data, depth=0, path="", out=None):
    """[(posto, testo)]: per ogni testo i numeri dei campi che ci portano («2.1.1»). Serve al registro per dire DOVE stava
    cio' che e' stato sostituito, senza dire che cosa. None se i byte non sono protobuf."""
    listing = fields(data)
    if listing is None:
        return None
    out = [] if out is None else out
    for number, kind, _, start, end in listing:
        if kind != 2 or end == start:
            continue
        here = f"{path}.{number}" if path else str(number)
        what, inner = _inside(data[start:end], depth)
        if what == "message":
            places(data[start:end], depth + 1, here, out)
        elif what == "text":
            out.append((here, inner))
    return out


def rebuild(data, changes, depth=0):
    """Il messaggio con i testi di `changes` ({testo com'era: testo nuovo}) sostituiti. Il resto resta byte per byte."""
    listing = fields(data)
    if listing is None:
        return bytes(data)
    out = bytearray()
    for number, kind, begin, start, end in listing:
        piece = fresh = bytes(data[start:end])
        if kind == 2 and end > start:
            what, inner = _inside(piece, depth)
            if what == "message":
                fresh = rebuild(piece, changes, depth + 1)
            elif what == "text" and inner in changes:
                fresh = changes[inner].encode("utf-8")
        if fresh == piece:
            out += data[begin:end]
        else:
            out += _encode(number << 3 | 2) + _encode(len(fresh)) + fresh
    return bytes(out)


def prose(text):
    """Un testo che puo' essere stato scritto da una persona (e va fatto vedere al motore): ha degli spazi o una
    chiocciola. Identificativi, date e nomi di modello restano fuori: il motore non deve poterli toccare."""
    t = text.strip()
    return len(t) >= 3 and ("@" in t or any(c.isspace() for c in t))


def unwrap(body, kind, coding=""):
    """(busta?, messaggio) di una chiamata Connect. Le chiamate semplici (application/proto) non hanno busta; quelle a
    flusso (application/connect+proto) si': un byte di segni e quattro di lunghezza. (False, None) se non si legge."""
    if "connect+" not in kind:
        return False, bytes(body)
    if len(body) < 5 or 5 + int.from_bytes(body[1:5], "big") != len(body):
        return False, None   # piu' buste, o non e' una busta
    message = bytes(body[5:])
    if body[0] & 1:   # messaggio compresso dentro la busta
        if coding.strip().lower() != "gzip":
            return False, None
        import gzip
        try:
            message = gzip.decompress(message)
        except (OSError, EOFError):
            return False, None
    return True, message


def wrap(enveloped, message):
    """Il corpo da mandare: il messaggio com'e', oppure dentro una busta Connect non compressa."""
    return (b"\x00" + len(message).to_bytes(4, "big") + message) if enveloped else message
