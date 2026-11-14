# -*- coding: utf-8 -*-
"""Genera i dati sintetici di addestramento di Omissis: data/train.jsonl e data/dev.jsonl.

Ogni riga: {"testo": ..., "spans": [[inizio, fine, etichetta], ...], "forma": ...}
Non usa ne' i testi ne' i generatori del benchmark.

Uso:  python generate_data.py [n_train=40000] [n_dev=2000]
"""
import collections
import json
import random
import sys
from pathlib import Path
from string import Formatter

import fragments as F
from taxonomy import LABELS
from values import IT, Persona, contesto

SEED = 7301
HERE = Path(__file__).resolve().parent
_FMT = Formatter()
SECTORS = list(F.PROSA)
SECTOR_WEIGHTS = [3 if a in ("msp", "cyber") else 2 if a in ("profilo", "pubblico") else 1 for a in SECTORS]


def fill(model, ctx):
    out, spans, n = [], [], 0
    for lit, field, _, _ in _FMT.parse(model):
        out.append(lit)
        n += len(lit)
        if field is None:
            continue
        o, a = field.split(".")
        val = str(getattr(ctx[o], a)())
        eti = getattr(ctx[o], "ETI", {}).get(a)
        if eti and val.strip():
            spans.append([n, n + len(val), eti])
        out.append(val)
        n += len(val)
    return "".join(out), spans


def merge(parts, sep):
    text, spans = "", []
    for i, (t, sp) in enumerate(parts):
        if i:
            text += sep
        spans += [[s + len(text), e + len(text), l] for s, e, l in sp]
        text += t
    return text, spans


def swap(ctx, r):
    """Stesso ambiente, persona principale diversa."""
    c = dict(ctx)
    c["p"], c["q"] = ctx["q"], ctx["p"]
    c["t"] = IT(r, ctx["a"], c["p"])
    return c


def prose(r, ctx, k=None, sector=None):
    sector = sector or r.choices(SECTORS, SECTOR_WEIGHTS)[0]
    k = k or r.choice([1, 1, 1, 2, 2, 3, 4])
    fr = r.sample(F.PROSA[sector], min(k, len(F.PROSA[sector])))
    for _ in range(r.choice([0, 0, 1, 1, 2])):
        fr.insert(r.randint(0, len(fr)), r.choice(F.NEUTRE))
    return merge([fill(f, ctx if r.random() < .7 else contesto(r)) for f in fr], r.choice([" ", " ", "\n", "\n\n"]))


def module(r, ctx):
    fields = r.sample(F.CAMPI, r.randint(3, 12))
    sep = r.choice([": ", ": ", ": ", " : ", ":", " = ", "=", "\t", " - ", ":  ", " ", ":\n"])
    style = r.choice([str, str, str, str.upper, str.lower])
    lines = [fill(style(r.choice(names)).replace("{", "{{").replace("}", "}}") + sep + val, ctx) for names, val in fields]
    if r.random() < .3:
        lines.insert(0, (r.choice(["DATI ANAGRAFICI", "Scheda cliente", "Dettagli dispositivo", "Device details", "Anagrafica",
                                   "Riepilogo richiesta", "Nuova richiesta dal portale", "Dati del contraente", "Informazioni di sistema",
                                   "Credenziali", "Scheda tecnica"]), []))
    return merge(lines, r.choice(["\n", "\n", "\n", "\n", " ", "  ", " | ", "; ", "", "\n\n", ", "]))


def email(r, ctx, depth=0):
    parts = []
    ogg = r.choice(F.OGGETTI)
    if r.random() < .6:
        parts.append(fill(r.choice(F.INTESTAZIONI).replace("{OGG}", ogg), ctx))
    parts.append(fill(r.choice(F.SALUTI), ctx))
    parts.append(prose(r, ctx, k=r.choice([1, 1, 2, 3])))
    parts.append((r.choice(F.CHIUSE), []))
    if r.random() < .75:
        parts.append(fill(r.choice(F.FIRME).replace("{RUOLO}", r.choice(["{x.ruolo}", "{x.ruolo}", "{x.ruolo}", "{x.ufficio}"])), ctx))
    if r.random() < .3:
        parts.append((r.choice(F.DISCLAIMER), []))
    if depth < 2 and r.random() < .3:
        c2 = swap(ctx, r)
        parts.append(merge([fill(r.choice(F.INTESTAZIONI[:5]).replace("{OGG}", ogg), c2), email(r, c2, depth + 1)], "\n"))
    return merge([p for p in parts if p[0]], r.choice(["\n", "\n", "\n\n", "\n\n", " "]))


def table(r, ctx):
    intest, cells = r.choice(F.TABELLE)
    sep = r.choice(["\t", ";", " | ", ",", "  ", " ", "\t"])
    lines = [(sep.join(intest), [])] if r.random() < .8 else []
    for _ in range(r.randint(2, 8)):
        c = dict(ctx)
        c["p"] = Persona(r, ctx["a"])
        c["t"] = IT(r, ctx["a"], c["p"])
        lines.append(merge([fill(x, c) for x in cells], sep))
    return merge(lines, "\n")


def log(r, ctx):
    return merge([fill(f, ctx) for f in r.sample(F.PROSA["cyber"], r.randint(1, 5))], r.choice(["\n", "\n", "\n\n"]))


def chat(r, ctx):
    pref = r.choice(["", "{p.n}: ", "[{v.ora}] {p.n} {p.c}: ", "{p.nc} ({v.ora}): ", "{v.ora} - {p.n}: "])
    lines = []
    for i, f in enumerate(r.sample(F.CHAT, r.randint(3, 9))):
        c = ctx if i % 2 == 0 else swap(ctx, r)
        lines.append(fill(pref + f, c))
    return merge(lines, "\n")


def neutral(r, ctx):
    return merge([fill(f, ctx) for f in r.sample(F.NEUTRE, r.randint(1, 6))], r.choice([" ", "\n", "\n", "\n\n", " | "]))


def brief(r, ctx):
    names, val = r.choice(F.CAMPI)
    return fill(r.choice(["{V}", "{V}", "{N} {V}", "{N}: {V}", "chiamare {V}", "vedi {V}", "{V} grazie", "rif. {V}", "{V} - {p.x}",
                            "{p.x} {V}", "{a.x} / {V}", "x {p.n}: {V}"]).replace("{N}", r.choice(names).lower()).replace("{V}", val), ctx)


def mixed(r, ctx):
    return merge([fill(r.choice(F.OGGETTI), ctx), prose(r, ctx, sector=r.choice(["msp", "msp", "cyber"])), module(r, ctx)],
                  r.choice(["\n", "\n\n", " "]))


SHAPES = [(prose, 28), (email, 17), (module, 14), (table, 6), (log, 9), (chat, 5), (neutral, 13), (brief, 4), (mixed, 4)]
# il nome della forma scritto nei dati: resta quello di sempre, i dati gia' generati lo usano
SHAPE_NAME = {prose: "prosa", email: "email", module: "modulo", table: "tabella", log: "log", chat: "chat", neutral: "neutro",
              brief: "breve", mixed: "misto"}
SURROUND = ["{v.titolo}", "{v.titolo}", "{v.sep}", "{v.invisibile}", "{v.sigla}: {v.titolo}", "{v.ticket}", "{v.titolo} {v.ticket}",
            "{v.simbolo} {v.titolo}", "R: {v.titolo}", "I: {v.titolo} {v.sigla}", "[{v.sigla}] {v.titolo}"]


def transform(text, spans, f):
    """Applica f(i, carattere, dentro_uno_span) -> stringa e ricalcola gli span."""
    inside = [False] * (len(text) + 1)
    for s, e, _ in spans:
        for i in range(s, e):
            inside[i] = True
    pos, out = [0] * (len(text) + 1), []
    n = 0
    for i, ch in enumerate(text):
        pos[i] = n
        x = f(i, ch, inside[i])
        out.append(x)
        n += len(x)
    pos[len(text)] = n
    return "".join(out), [[pos[s], pos[e], l] for s, e, l in spans]


def noise(r, text, spans):
    f = r.random()
    if f < .04 and len(text.upper()) == len(text):
        text = text.upper()
    elif f < .09 and len(text.lower()) == len(text):
        text = text.lower()
    elif f < .15:   # parole incollate, come dopo la rimozione dell'HTML
        text, spans = transform(text, spans, lambda i, ch, d: "" if ch == "\n" and not d else ch)
    elif f < .25:
        text, spans = transform(text, spans, lambda i, ch, d: "\r\n" if ch == "\n" else ch)
    elif f < .30:
        text, spans = transform(text, spans, lambda i, ch, d: "  " if ch == " " and not d and r.random() < .15 else ch)
    if r.random() < .12:   # singole entita' in maiuscolo o minuscolo
        car = list(text)
        for s, e, l in spans:
            if l in ("PERSONA", "ORG", "CITTA", "INDIRIZZO", "HOSTNAME", "CF", "EMAIL") and r.random() < .5:
                fresh = text[s:e].upper() if r.random() < .5 else text[s:e].lower()
                if len(fresh) == e - s:
                    car[s:e] = fresh
        text = "".join(car)
    return text, spans


def document(r):
    shape = r.choices([f for f, _ in SHAPES], [p for _, p in SHAPES])[0]
    ctx = contesto(r)
    parts = [shape(r, ctx)]
    if r.random() < .15:   # titolo, separatore o riferimento prima del testo
        parts.insert(0, fill(r.choice(SURROUND), ctx))
    if r.random() < .22:   # oggetto del ticket come prima riga (i ticket sono "oggetto + a capo + testo")
        text, spans = merge([fill(r.choice(F.OGGETTI), ctx), merge(parts, "\n")], "\n")
        parts = [(text, spans)]
    if r.random() < .08:   # ... o dopo
        parts.append(fill(r.choice(SURROUND + F.DISCLAIMER), ctx))
    text, spans = merge(parts, r.choice(["\n", "\n", "\n\n", " ", " - "]))
    text, spans = noise(r, text, spans)
    clean = []
    for s, e, l in sorted(spans):
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if s < e:
            assert l in LABELS, l
            assert not clean or clean[-1][1] <= s, "span sovrapposti"
            clean.append([s, e, l])
    return {"testo": text, "spans": clean, "forma": SHAPE_NAME[shape]}


def write(nome, n, seed):
    r = random.Random(seed)
    count, shapes, car = collections.Counter(), collections.Counter(), 0
    (HERE / "data").mkdir(exist_ok=True)
    with (HERE / "data" / nome).open("w", encoding="utf-8") as f:
        for _ in range(n):
            d = document(r)
            count.update(l for _, _, l in d["spans"])
            shapes[d["forma"]] += 1
            car += len(d["testo"])
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"{nome}: {n} testi, {car / n:.0f} caratteri medi, {sum(count.values())} entità")
    print("  forme:", dict(shapes.most_common()))
    print("  entità:", dict(count.most_common()))
    return d


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    n_train = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
    n_dev = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    write("train.jsonl", n_train, SEED)
    write("dev.jsonl", n_dev, SEED + 1)
    r = random.Random(5)
    for _ in range(4):
        d = document(r)
        print(f"\n--- {d['forma']} ---\n{d['testo'][:500]}\n  ->", [(d["testo"][s:e][:30], l) for s, e, l in d["spans"]][:14])
