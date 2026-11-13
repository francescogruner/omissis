# -*- coding: utf-8 -*-
"""Builds the training set of version 2: our synthetic Italian documents plus the public datasets
converted by external_data.py, under one label set.   Writes data/train.jsonl, data/dev.jsonl and
data/schema.json.

  python build_train.py [--first-pass <model of a first training round>] [--privy 40000]

The sources do not annotate the same things: one labels job titles but not honorifics, another the
opposite, ours labels host names and none of the public ones does. Telling the network that an
unlabelled honorific is "nothing" would teach it to miss honorifics. So every text carries the name
of its source ("dom") and train.py does not penalise a label that the source could not have given:

  - a label annotated by the source: its absence is a real "nothing";
  - a label the source does not annotate: left open, no penalty either way. gretel annotates a
    different handful of labels in each document, so there everything is open: it only gives examples
    of what something is, never of what it is not;
  - our own documents are generated, so we know everything that is in them: they are closed for all
    the labels, and they are what keeps a new label (occupation, place...) from being seen in a
    company name or a host name. The few things our templates write as plain words (a "dott." before
    a name, a date inside a sentence) are found by a model of a first training round ("forse") and
    left open.

The sources added later are less even, and each one enters with its own rule (see the tables below the imports):
a source annotated by a language model (finance) is believed only where the model of version 1 sees something too,
and what that model sees and the source does not label is left open; sources that annotate by hand only what
matters to them (tab) or under thousands of free-form types (urchade) only give examples of what something is.

Long public documents are cut at line or sentence ends so that nothing is lost to the 512-token
limit, and some single sentences are added, because that is how short messages look in real use.
"""
import argparse
import collections
import json
import random
import re
import sys
from pathlib import Path

from inference import Rilevatore
from taxonomy import ETICHETTE, SPENTE

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
EXTERNAL = ("ai4privacy", "nemotron", "gretel", "privy", "mapa", "finance", "nym", "tab", "urchade")
# mapa and tab: few texts, but the only real (not synthetic) ones, written and annotated by people
REPEAT = {"mapa": 3, "tab": 3}
# sources that only say what something is, never what is not: every label is left open
ONLY_EXAMPLES = {"gretel", "tab", "urchade"}
# labels that a source does annotate, but not everywhere: mapa only the family names; nym and finance only the dates
# and addresses that are personal data in the document, not the ones the text is made of
LEFT_OPEN = {"mapa": {"PERSONA"}, "nym": {"DATA", "ORA", "EMAIL", "URL"}, "finance": {"DATA", "ORA"}}
# finance was labelled by a language model: a quarter of its "names" are words like "the Employee". A person or a company
# of the source is kept only where the model of version 1 sees something too; elsewhere the place is left open
CHECKED = {"finance": {"PERSONA", "ORG"}}
# ... and it does not label the examples that the text gives by itself (an IBAN in a form, a tax code in a table): where the
# model of version 1 sees one of these labels and the source has nothing, the place is left open instead of "nothing"
TRUSTED = {"finance": {"PERSONA", "INDIRIZZO", "TELEFONO", "CITTA", "CF", "IBAN", "EMAIL", "CARTA", "DOC_ID", "IP", "DATA_NASCITA"}}
# A capitalised name in the middle of a sentence ("... an invoice from Harlow Brothers for ..."): in the public texts it
# may be a company that nobody labelled, and the model of version 1, trained on Italian, does not see most of them.
# Taking them as "nothing" was what made the fifth round miss customers' names in real texts. So they are left open
# for ORG. What stays "nothing" is what the text shape itself says is not a name: headings, field names ("Audit:",
# "Consent"), words at the start of a line or of a sentence, lowercase words.
MID_SENTENCE = re.compile(r"\b[a-zà-ÿ]+[,;]? ((?>(?:[A-ZÀ-Ý][\w&.'’-]*)(?: (?:(?:of|and|de|di|del|della|des|du|van|von|der|the|&) )?[A-ZÀ-Ý][\w&.'’-]*)*))"
                          r"(?!\s*[:=])")
CUT = re.compile(r"\n+|(?<=[.!?;])\s+")
LIMIT = 1700     # characters: about 450 tokens


def read(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pieces(text, spans, limit=LIMIT):
    """Cuts a long text at line or sentence ends that fall outside every span. Returns [(text, spans)]."""
    if len(text) <= limit:
        return [(text, spans)]
    spans = sorted(spans)
    ends = [m.end() for m in CUT.finditer(text) if not any(s < m.end() < e or s < m.start() < e for s, e, _ in spans)]
    out, start = [], 0
    while len(text) - start > limit:
        usable = [e for e in ends if start < e <= start + limit]
        end = usable[-1] if usable else start + limit
        if not usable and any(s < end < e for s, e, _ in spans):      # no clean cut: move past the span
            end = next(e for s, e, _ in spans if s < end < e)
        out.append((start, end))
        start = end
    out.append((start, len(text)))
    return [(text[a:b], [[s - a, e - a, l] for s, e, l in spans if a <= s and e <= b]) for a, b in out if text[a:b].strip()]


def one_sentence(r, text, spans):
    """A single line or sentence of the text (20-300 characters) with its spans, or None."""
    cuts = [0] + [m.end() for m in CUT.finditer(text)] + [len(text)]
    for _ in range(6):
        i = r.randrange(len(cuts) - 1)
        a, b = cuts[i], cuts[i + 1]
        if 20 <= b - a <= 300 and not any(s < a < e or s < b < e for s, e, _ in spans):
            return text[a:b].strip("\n"), [[s - a, e - a, l] for s, e, l in spans if a <= s and e <= b and e - a <= len(text[a:b].strip("\n"))]
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--first-pass", dest="first", default="",
                    help="model of a first round: in our documents it marks the new labels written as plain words, which are then left open")
    ap.add_argument("--teacher", default="", help="model of version 1: in the public texts it marks where a company name may be (see below)")
    ap.add_argument("--privy", type=int, default=100000, help="how many privy texts to keep")
    ap.add_argument("--dev-external", type=int, default=400, help="texts per public source kept aside for data/dev.jsonl")
    a = ap.parse_args()
    r = random.Random(97)

    # generate_data.py writes our part as train.jsonl and dev.jsonl; this script replaces them with the merged sets and
    # keeps our part aside (ours_*.jsonl), so that it can be run again without regenerating
    for name in ("train", "dev"):
        with open(DATA / f"{name}.jsonl", encoding="utf-8") as f:
            fresh = '"dom"' not in f.readline()
        if fresh:
            (DATA / f"ours_{name}.jsonl").write_bytes((DATA / f"{name}.jsonl").read_bytes())
    ours, dev = read(DATA / "ours_train.jsonl"), read(DATA / "ours_dev.jsonl")
    schema = {"ours": list(ETICHETTE)}
    held = [{"testo": d["testo"], "spans": d["spans"], "dom": "ours"} for d in dev if d.get("dom", "ours") == "ours"]
    rows, opened = [], 0
    guesses = Rilevatore(a.first, mai=[], sempre=[], regole=False, noti=False, spente=[]).molti([d["testo"] for d in ours]) if a.first else [[]] * len(ours)
    for d, guess in zip(ours, guesses):
        maybe = [[s, e, l] for s, e, l in guess if l in SPENTE and not any(s < e2 and s2 < e for s2, e2, _ in d["spans"])]
        opened += len(maybe)
        rows.append({"testo": d["testo"], "spans": d["spans"], "dom": "ours", **({"forse": maybe} if maybe else {})})
    print(f"ours: {len(ours):,} texts, closed for all {len(ETICHETTE)} labels; {opened:,} places left open where a new label is written as plain words")
    teacher = Rilevatore(a.teacher, mai=[], sempre=[]) if a.teacher else None
    for name in EXTERNAL:
        docs = read(DATA / "external" / f"{name}.jsonl")
        r.shuffle(docs)
        if name == "privy":
            docs = docs[:a.privy + a.dev_external]
        aside = min(a.dev_external, len(docs) // 20)
        counts = collections.Counter(l for d in docs for _, _, l in d["spans"])
        counts.update(l for d in docs for _, _, l in d.get("anche", []))
        # mapa labels family names but not given names: for people it only says what is one, never what is not
        left_open = LEFT_OPEN.get(name, set())
        schema[name] = [] if name in ONLY_EXAMPLES else sorted(l for l, n in counts.items() if n >= 50 and l not in left_open)
        # Company names need both things at once. Every public source calls "company" something different and leaves most
        # organisations unlabelled: taken as they are, they teach to miss a customer's name written without "S.r.l.".
        # Left completely open, nothing says that an English heading ("Audit", "Consent") is not a company. So in the
        # public texts a company is "nothing" everywhere EXCEPT where the model of version 1, which follows our own
        # rule for companies, sees one: there it stays open.
        if teacher is not None:
            schema[name] = sorted(set(schema[name]) | {"ORG"})
        parts = []
        for i, d in enumerate(docs):
            # an alternative label of the source ("anche") stays allowed on the same span ("forse")
            alt = {(s, e): l for s, e, l in d.get("anche", [])}
            marked = [[s, e, l + ("|" + alt[(s, e)] if (s, e) in alt else "")] for s, e, l in d["spans"]]
            # places that the source leaves open ("?" + label) or declares empty ("!") travel with the spans through the cuts
            marked += [[s, e, "?" + l] for s, e, l in d.get("aperti", [])] + [[s, e, "!"] for s, e in d.get("nulla", [])]
            parts += [(i < aside, t, sp) for t, sp in pieces(d["testo"], marked)]
            if i >= aside and len(d["testo"]) > 400 and r.random() < .35:
                single = one_sentence(r, d["testo"], marked)
                if single:
                    parts.append((False, *single))
        seen = teacher.molti([t for _, t, _ in parts], completo=True) if teacher is not None else [[]] * len(parts)
        companies = doubted = shaped = 0
        checked, trusted = CHECKED.get(name, set()), TRUSTED.get(name, set()) | {"ORG"}
        for (is_dev, text, sp), guess in zip(parts, seen):
            maybe = [[s, e, l.split("|")[1]] for s, e, l in sp if "|" in l] + [[s, e, l[1:]] for s, e, l in sp if l[0] == "?"]
            taken = [[s, e, l] for s, e, l in sp if l[0] != "?"]          # labelled, or declared empty
            sp = [[s, e, l.split("|")[0]] for s, e, l in sp if l[0] not in "?!"]
            if teacher is not None and checked:
                unseen = [x for x in sp if x[2] in checked and not any(x[0] < e2 and s2 < x[1] for s2, e2, _ in guess)]
                doubted += len(unseen)
                maybe += unseen
                sp = [x for x in sp if x not in unseen]
            also = [[s, e, l] for s, e, l in guess if l in trusted and (l == "ORG" or e - s >= 5)
                    and not any(s < e2 and s2 < e for s2, e2, _ in taken)]
            companies += len(also)
            if teacher is not None:
                names = [[m.start(1), m.end(1), "ORG"] for m in MID_SENTENCE.finditer(text)]
                names = [x for x in names if not any(x[0] < e2 and s2 < x[1] for s2, e2, _ in taken + also)]
                shaped += len(names)
                also += names
            maybe = sorted(maybe + also)
            row = {"testo": text, "spans": sp, "dom": name, **({"forse": maybe} if maybe else {})}
            if is_dev:
                held.append(row)
            else:
                rows += [row] * REPEAT.get(name, 1)
        print(f"{name}: {len(docs):,} documents -> {len(parts):,} texts; closed for {len(schema[name])} labels, open for the other "
              f"{len(ETICHETTE) - len(schema[name])}; {companies:,} places left open where the model of version 1 sees a company"
              + (" or one of the labels it is trusted for" if name in TRUSTED else "")
              + f", {shaped:,} more for a capitalised name in the middle of a sentence"
              + (f"; {doubted:,} people and companies of the source not believed" if doubted else ""))
    r.shuffle(rows)
    for name, data in (("train.jsonl", rows), ("dev.jsonl", held)):
        with (DATA / name).open("w", encoding="utf-8") as f:
            for d in data:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
    (DATA / "schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=1), encoding="utf-8")
    by_source = collections.Counter(d["dom"] for d in rows)
    labels = collections.Counter(l for d in rows for _, _, l in d["spans"])
    print(f"\ntrain.jsonl: {len(rows):,} texts {dict(by_source)}\ndev.jsonl: {len(held):,} texts")
    print("entities:", dict(labels.most_common()))


if __name__ == "__main__":
    main()
