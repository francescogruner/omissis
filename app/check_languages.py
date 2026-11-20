# -*- coding: utf-8 -*-
"""Controlla i file delle lingue (panel\\locales\\*.json) e dice cosa non torna.

  python check_languages.py

Per ogni lingua, rispetto all'italiano che fa da riferimento: chiavi che mancano, chiavi in piu',
parole tra graffe diverse (es. {n}). Poi, rispetto al codice: chiavi usate che non esistono in
nessun file, e chiavi che nessuno usa piu'. Esce con errore se manca qualcosa di necessario.

Per tradurre in una lingua nuova: copiare it.json con il codice della lingua (de.json, fr.json...),
tradurre i valori, cambiare "_lingua" e rilanciare questo controllo.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANGUAGES = HERE / "panel" / "locales"
RX_BRACES = re.compile(r"\{(\w+)\}")
# t("chiave") e tSe("prefisso." + x) nel codice della pagina; lingue.t("chiave") e t(f"prefisso.{x}") nel programma
RX_USE = re.compile(r"""\b(?:t|tn|tSe|lingue\.t)\(\s*(f?)(["'`])((?:(?!\2).)+)\2""")


def uses():
    """Le chiavi scritte per intero e, per quelle composte al momento, l'espressione che le riconosce."""
    whole, compound = set(), set()
    for f in [HERE / "panel" / "app.js", *HERE.glob("*.py")]:
        if f.name == Path(__file__).name:
            continue
        text = f.read_text(encoding="utf-8")
        for m in RX_USE.finditer(text):
            key, queue = m.group(3), text[m.end():m.end() + 3]
            variable = "${" in key or (m.group(1) and "{" in key) or queue.lstrip().startswith("+")
            if not variable:
                whole.add(key)
                continue
            model = re.sub(r"\\\$\\\{[^}]*\\\}|\\\{[^}]*\\\}", ".+", re.escape(key))
            compound.add(re.compile(model + (".+" if queue.lstrip().startswith("+") else "") + "$"))
    return whole, compound


def extension():
    """Le frasi dell'estensione (extension\\_locales\\<lingua>\\messages.json, il formato dei browser): stesse chiavi,
    stessi segnaposto ($1), e ogni chiave usata nei file dell'estensione deve esistere."""
    folder = HERE / "extension"
    file = {f.parent.name: json.loads(f.read_text(encoding="utf-8")) for f in sorted((folder / "_locales").glob("*/messages.json"))}
    ref, problems = file["it"], 0
    for code, entries in file.items():
        missing, extra = sorted(set(ref) - set(entries)), sorted(set(entries) - set(ref))
        different = sorted(k for k in set(ref) & set(entries) if set(re.findall(r"\$\d", ref[k]["message"])) != set(re.findall(r"\$\d", entries[k]["message"])))
        print(f"estensione {code}: {len(entries)} frasi" + ("" if missing or extra or different else " · completa"))
        for title, listing in (("missing", missing), ("in più", extra), ("segnaposto diversi", different)):
            if listing:
                problems += len(listing)
                print(f"   {title}: " + ", ".join(listing))
    used = set()
    for f in [*folder.glob("*.js"), *folder.glob("*.html"), HERE / "build_extension.py"]:
        text = f.read_text(encoding="utf-8")
        used |= set(re.findall(r"""\bT\(\s*['"]([a-z_]+)['"]""", text)) | set(re.findall(r"""data-(?:t|nome)=["']([a-z_]+)["']""", text))
        used |= set(re.findall(r"__MSG_([a-z_]+)__", text))
        used |= {k for k in ref if f"'{k}'" in text or f'"{k}"' in text}   # anche dentro una scelta: T(guasto ? 'a' : 'b')
    compound = {k for k in ref if k.startswith(("status_", "policy_"))}   # T('stato_' + stato), T('politica_' + pol)
    nonexistent = sorted(k for k in used if k not in ref and not k.endswith("_"))
    unused = sorted(set(ref) - used - compound)
    if nonexistent:
        problems += len(nonexistent)
        print("   usate nell'estensione ma assenti dai file:", ", ".join(nonexistent))
    if unused:
        print("   frasi che l'estensione non usa più:", ", ".join(unused))
    return problems


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    file = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(LANGUAGES.glob("*.json"))}
    ref = file["it"]
    problems = 0
    for code, entries in file.items():
        missing, extra = sorted(set(ref) - set(entries)), sorted(set(entries) - set(ref))
        braces = sorted(k for k in set(ref) & set(entries) if set(RX_BRACES.findall(ref[k])) != set(RX_BRACES.findall(entries[k])))
        print(f"{code} ({entries.get('_language', '?')}): {len(entries) - 1} frasi" + ("" if missing or extra or braces else " · completa"))
        for title, listing in (("missing", missing), ("in più", extra), ("parole tra graffe diverse", braces)):
            if listing:
                problems += len(listing)
                print(f"   {title}: " + ", ".join(listing[:12]) + (f" … (+{len(listing) - 12})" if len(listing) > 12 else ""))
    whole, compound = uses()
    nonexistent = sorted(k for k in whole if k not in ref)
    without_feedback = sorted(c.pattern for c in compound if not any(c.match(k) for k in ref))
    # «chiave.mac» e' la variante per Mac di «chiave»: la sceglie t() da sola, quindi e' usata se lo e' la sua base
    base = lambda k: k[:-4] if k.endswith(".mac") else k   # noqa: E731
    unused = sorted(k for k in ref if not k.startswith("_") and base(k) not in whole and not any(c.match(base(k)) for c in compound))
    if nonexistent:
        problems += len(nonexistent)
        print("usate nel codice ma assenti dai file:", ", ".join(nonexistent))
    if without_feedback:
        problems += len(without_feedback)
        print("chiavi composte nel codice che non trovano nessuna frase:", ", ".join(without_feedback))
    if unused:
        print(f"frasi che il codice non usa più ({len(unused)}):", ", ".join(unused[:20]) + (" …" if len(unused) > 20 else ""))
    problems += extension()
    print("tutto a posto" if not problems else f"{problems} cose da sistemare")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
