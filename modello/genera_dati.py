# -*- coding: utf-8 -*-
"""Genera i dati sintetici di addestramento di msp-pii: dati/train.jsonl e dati/dev.jsonl.

Ogni riga: {"testo": ..., "spans": [[inizio, fine, etichetta], ...], "forma": ...}
Non usa ne' i testi ne' i generatori del benchmark.

Uso:  python genera_dati.py [n_train=40000] [n_dev=2000]
"""
import collections
import json
import random
import sys
from pathlib import Path
from string import Formatter

import frammenti as F
from tassonomia import ETICHETTE
from valori import IT, Persona, contesto

SEME = 7301
QUI = Path(__file__).resolve().parent
_FMT = Formatter()
AMBITI = list(F.PROSA)
PESI_AMBITI = [3 if a in ("msp", "cyber") else 1 for a in AMBITI]


def riempi(modello, ctx):
    out, spans, n = [], [], 0
    for lit, campo, _, _ in _FMT.parse(modello):
        out.append(lit)
        n += len(lit)
        if campo is None:
            continue
        o, a = campo.split(".")
        val = str(getattr(ctx[o], a)())
        eti = getattr(ctx[o], "ETI", {}).get(a)
        if eti and val.strip():
            spans.append([n, n + len(val), eti])
        out.append(val)
        n += len(val)
    return "".join(out), spans


def unisci(parti, sep):
    testo, spans = "", []
    for i, (t, sp) in enumerate(parti):
        if i:
            testo += sep
        spans += [[s + len(testo), e + len(testo), l] for s, e, l in sp]
        testo += t
    return testo, spans


def scambia(ctx, r):
    """Stesso ambiente, persona principale diversa."""
    c = dict(ctx)
    c["p"], c["q"] = ctx["q"], ctx["p"]
    c["t"] = IT(r, ctx["a"], c["p"])
    return c


def prosa(r, ctx, k=None, ambito=None):
    ambito = ambito or r.choices(AMBITI, PESI_AMBITI)[0]
    k = k or r.choice([1, 1, 1, 2, 2, 3, 4])
    fr = r.sample(F.PROSA[ambito], min(k, len(F.PROSA[ambito])))
    for _ in range(r.choice([0, 0, 1, 1, 2])):
        fr.insert(r.randint(0, len(fr)), r.choice(F.NEUTRE))
    return unisci([riempi(f, ctx if r.random() < .7 else contesto(r)) for f in fr], r.choice([" ", " ", "\n", "\n\n"]))


def modulo(r, ctx):
    campi = r.sample(F.CAMPI, r.randint(3, 12))
    sep = r.choice([": ", ": ", ": ", " : ", ":", " = ", "=", "\t", " - ", ":  ", " ", ":\n"])
    stile = r.choice([str, str, str, str.upper, str.lower])
    righe = [riempi(stile(r.choice(nomi)).replace("{", "{{").replace("}", "}}") + sep + val, ctx) for nomi, val in campi]
    if r.random() < .3:
        righe.insert(0, (r.choice(["DATI ANAGRAFICI", "Scheda cliente", "Dettagli dispositivo", "Device details", "Anagrafica",
                                   "Riepilogo richiesta", "Nuova richiesta dal portale", "Dati del contraente", "Informazioni di sistema",
                                   "Credenziali", "Scheda tecnica"]), []))
    return unisci(righe, r.choice(["\n", "\n", "\n", "\n", " ", "  ", " | ", "; ", "", "\n\n", ", "]))


def email(r, ctx, profondita=0):
    parti = []
    ogg = r.choice(F.OGGETTI)
    if r.random() < .6:
        parti.append(riempi(r.choice(F.INTESTAZIONI).replace("{OGG}", ogg), ctx))
    parti.append(riempi(r.choice(F.SALUTI), ctx))
    parti.append(prosa(r, ctx, k=r.choice([1, 1, 2, 3])))
    parti.append((r.choice(F.CHIUSE), []))
    if r.random() < .75:
        parti.append(riempi(r.choice(F.FIRME).replace("{RUOLO}", r.choice(F.RUOLI)), ctx))
    if r.random() < .3:
        parti.append((r.choice(F.DISCLAIMER), []))
    if profondita < 2 and r.random() < .3:
        c2 = scambia(ctx, r)
        parti.append(unisci([riempi(r.choice(F.INTESTAZIONI[:5]).replace("{OGG}", ogg), c2), email(r, c2, profondita + 1)], "\n"))
    return unisci([p for p in parti if p[0]], r.choice(["\n", "\n", "\n\n", "\n\n", " "]))


def tabella(r, ctx):
    intest, celle = r.choice(F.TABELLE)
    sep = r.choice(["\t", ";", " | ", ",", "  ", " ", "\t"])
    righe = [(sep.join(intest), [])] if r.random() < .8 else []
    for _ in range(r.randint(2, 8)):
        c = dict(ctx)
        c["p"] = Persona(r, ctx["a"])
        c["t"] = IT(r, ctx["a"], c["p"])
        righe.append(unisci([riempi(x, c) for x in celle], sep))
    return unisci(righe, "\n")


def log(r, ctx):
    return unisci([riempi(f, ctx) for f in r.sample(F.PROSA["cyber"], r.randint(1, 5))], r.choice(["\n", "\n", "\n\n"]))


def chat(r, ctx):
    pref = r.choice(["", "{p.n}: ", "[{v.ora}] {p.n} {p.c}: ", "{p.nc} ({v.ora}): ", "{v.ora} - {p.n}: "])
    righe = []
    for i, f in enumerate(r.sample(F.CHAT, r.randint(3, 9))):
        c = ctx if i % 2 == 0 else scambia(ctx, r)
        righe.append(riempi(pref + f, c))
    return unisci(righe, "\n")


def neutro(r, ctx):
    return unisci([riempi(f, ctx) for f in r.sample(F.NEUTRE, r.randint(1, 6))], r.choice([" ", "\n", "\n", "\n\n", " | "]))


def breve(r, ctx):
    nomi, val = r.choice(F.CAMPI)
    return riempi(r.choice(["{V}", "{V}", "{N} {V}", "{N}: {V}", "chiamare {V}", "vedi {V}", "{V} grazie", "rif. {V}", "{V} - {p.x}",
                            "{p.x} {V}", "{a.x} / {V}", "x {p.n}: {V}"]).replace("{N}", r.choice(nomi).lower()).replace("{V}", val), ctx)


def misto(r, ctx):
    return unisci([riempi(r.choice(F.OGGETTI), ctx), prosa(r, ctx, ambito=r.choice(["msp", "msp", "cyber"])), modulo(r, ctx)],
                  r.choice(["\n", "\n\n", " "]))


FORME = [(prosa, 28), (email, 17), (modulo, 14), (tabella, 6), (log, 9), (chat, 5), (neutro, 13), (breve, 4), (misto, 4)]
CONTORNO = ["{v.titolo}", "{v.titolo}", "{v.sep}", "{v.invisibile}", "{v.sigla}: {v.titolo}", "{v.ticket}", "{v.titolo} {v.ticket}",
            "{v.simbolo} {v.titolo}", "R: {v.titolo}", "I: {v.titolo} {v.sigla}", "[{v.sigla}] {v.titolo}"]


def trasforma(testo, spans, f):
    """Applica f(i, carattere, dentro_uno_span) -> stringa e ricalcola gli span."""
    dentro = [False] * (len(testo) + 1)
    for s, e, _ in spans:
        for i in range(s, e):
            dentro[i] = True
    pos, out = [0] * (len(testo) + 1), []
    n = 0
    for i, ch in enumerate(testo):
        pos[i] = n
        x = f(i, ch, dentro[i])
        out.append(x)
        n += len(x)
    pos[len(testo)] = n
    return "".join(out), [[pos[s], pos[e], l] for s, e, l in spans]


def rumore(r, testo, spans):
    f = r.random()
    if f < .04 and len(testo.upper()) == len(testo):
        testo = testo.upper()
    elif f < .09 and len(testo.lower()) == len(testo):
        testo = testo.lower()
    elif f < .15:   # parole incollate, come dopo la rimozione dell'HTML
        testo, spans = trasforma(testo, spans, lambda i, ch, d: "" if ch == "\n" and not d else ch)
    elif f < .25:
        testo, spans = trasforma(testo, spans, lambda i, ch, d: "\r\n" if ch == "\n" else ch)
    elif f < .30:
        testo, spans = trasforma(testo, spans, lambda i, ch, d: "  " if ch == " " and not d and r.random() < .15 else ch)
    if r.random() < .12:   # singole entita' in maiuscolo o minuscolo
        car = list(testo)
        for s, e, l in spans:
            if l in ("PERSONA", "ORG", "CITTA", "INDIRIZZO", "HOSTNAME", "CF", "EMAIL") and r.random() < .5:
                nuovo = testo[s:e].upper() if r.random() < .5 else testo[s:e].lower()
                if len(nuovo) == e - s:
                    car[s:e] = nuovo
        testo = "".join(car)
    return testo, spans


def documento(r):
    forma = r.choices([f for f, _ in FORME], [p for _, p in FORME])[0]
    ctx = contesto(r)
    parti = [forma(r, ctx)]
    if r.random() < .15:   # titolo, separatore o riferimento prima del testo
        parti.insert(0, riempi(r.choice(CONTORNO), ctx))
    if r.random() < .22:   # oggetto del ticket come prima riga (i ticket sono "oggetto + a capo + testo")
        testo, spans = unisci([riempi(r.choice(F.OGGETTI), ctx), unisci(parti, "\n")], "\n")
        parti = [(testo, spans)]
    if r.random() < .08:   # ... o dopo
        parti.append(riempi(r.choice(CONTORNO + F.DISCLAIMER), ctx))
    testo, spans = unisci(parti, r.choice(["\n", "\n", "\n\n", " ", " - "]))
    testo, spans = rumore(r, testo, spans)
    pulito = []
    for s, e, l in sorted(spans):
        while s < e and testo[s].isspace():
            s += 1
        while e > s and testo[e - 1].isspace():
            e -= 1
        if s < e:
            assert l in ETICHETTE, l
            assert not pulito or pulito[-1][1] <= s, "span sovrapposti"
            pulito.append([s, e, l])
    return {"testo": testo, "spans": pulito, "forma": forma.__name__}


def scrivi(nome, n, seme):
    r = random.Random(seme)
    conta, forme, car = collections.Counter(), collections.Counter(), 0
    (QUI / "dati").mkdir(exist_ok=True)
    with (QUI / "dati" / nome).open("w", encoding="utf-8") as f:
        for _ in range(n):
            d = documento(r)
            conta.update(l for _, _, l in d["spans"])
            forme[d["forma"]] += 1
            car += len(d["testo"])
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"{nome}: {n} testi, {car / n:.0f} caratteri medi, {sum(conta.values())} entità")
    print("  forme:", dict(forme.most_common()))
    print("  entità:", dict(conta.most_common()))
    return d


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    n_train = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
    n_dev = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    scrivi("train.jsonl", n_train, SEME)
    scrivi("dev.jsonl", n_dev, SEME + 1)
    r = random.Random(5)
    for _ in range(4):
        d = documento(r)
        print(f"\n--- {d['forma']} ---\n{d['testo'][:500]}\n  ->", [(d["testo"][s:e][:30], l) for s, e, l in d["spans"]][:14])
