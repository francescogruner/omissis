# -*- coding: utf-8 -*-
"""Controlla i file delle lingue (pannello\\lingue\\*.json) e dice cosa non torna.

  python controlla_lingue.py

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

QUI = Path(__file__).resolve().parent
LINGUE = QUI / "pannello" / "lingue"
RX_GRAFFE = re.compile(r"\{(\w+)\}")
# t("chiave") e tSe("prefisso." + x) nel codice della pagina; lingue.t("chiave") e t(f"prefisso.{x}") nel programma
RX_USO = re.compile(r"""\b(?:t|tn|tSe|lingue\.t)\(\s*(f?)(["'`])((?:(?!\2).)+)\2""")


def usi():
    """Le chiavi scritte per intero e, per quelle composte al momento, l'espressione che le riconosce."""
    intere, composte = set(), set()
    for f in [QUI / "pannello" / "app.js", *QUI.glob("*.py")]:
        if f.name == Path(__file__).name:
            continue
        testo = f.read_text(encoding="utf-8")
        for m in RX_USO.finditer(testo):
            chiave, coda = m.group(3), testo[m.end():m.end() + 3]
            variabile = "${" in chiave or (m.group(1) and "{" in chiave) or coda.lstrip().startswith("+")
            if not variabile:
                intere.add(chiave)
                continue
            modello = re.sub(r"\\\$\\\{[^}]*\\\}|\\\{[^}]*\\\}", ".+", re.escape(chiave))
            composte.add(re.compile(modello + (".+" if coda.lstrip().startswith("+") else "") + "$"))
    return intere, composte


def estensione():
    """Le frasi dell'estensione (estensione\\_locales\\<lingua>\\messages.json, il formato dei browser): stesse chiavi,
    stessi segnaposto ($1), e ogni chiave usata nei file dell'estensione deve esistere."""
    cartella = QUI / "estensione"
    file = {f.parent.name: json.loads(f.read_text(encoding="utf-8")) for f in sorted((cartella / "_locales").glob("*/messages.json"))}
    rif, problemi = file["it"], 0
    for codice, voci in file.items():
        mancano, in_piu = sorted(set(rif) - set(voci)), sorted(set(voci) - set(rif))
        diversi = sorted(k for k in set(rif) & set(voci) if set(re.findall(r"\$\d", rif[k]["message"])) != set(re.findall(r"\$\d", voci[k]["message"])))
        print(f"estensione {codice}: {len(voci)} frasi" + ("" if mancano or in_piu or diversi else " · completa"))
        for titolo, elenco in (("mancano", mancano), ("in più", in_piu), ("segnaposto diversi", diversi)):
            if elenco:
                problemi += len(elenco)
                print(f"   {titolo}: " + ", ".join(elenco))
    usate = set()
    for f in [*cartella.glob("*.js"), *cartella.glob("*.html"), QUI / "genera_estensione.py"]:
        testo = f.read_text(encoding="utf-8")
        usate |= set(re.findall(r"""\bT\(\s*['"]([a-z_]+)['"]""", testo)) | set(re.findall(r"""data-(?:t|nome)=["']([a-z_]+)["']""", testo))
        usate |= set(re.findall(r"__MSG_([a-z_]+)__", testo))
        usate |= {k for k in rif if f"'{k}'" in testo or f'"{k}"' in testo}   # anche dentro una scelta: T(guasto ? 'a' : 'b')
    composte = {k for k in rif if k.startswith(("stato_", "politica_"))}   # T('stato_' + stato), T('politica_' + pol)
    inesistenti = sorted(k for k in usate if k not in rif and not k.endswith("_"))
    inutilizzate = sorted(set(rif) - usate - composte)
    if inesistenti:
        problemi += len(inesistenti)
        print("   usate nell'estensione ma assenti dai file:", ", ".join(inesistenti))
    if inutilizzate:
        print("   frasi che l'estensione non usa più:", ", ".join(inutilizzate))
    return problemi


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    file = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted(LINGUE.glob("*.json"))}
    rif = file["it"]
    problemi = 0
    for codice, voci in file.items():
        mancano, in_piu = sorted(set(rif) - set(voci)), sorted(set(voci) - set(rif))
        graffe = sorted(k for k in set(rif) & set(voci) if set(RX_GRAFFE.findall(rif[k])) != set(RX_GRAFFE.findall(voci[k])))
        print(f"{codice} ({voci.get('_lingua', '?')}): {len(voci) - 1} frasi" + ("" if mancano or in_piu or graffe else " · completa"))
        for titolo, elenco in (("mancano", mancano), ("in più", in_piu), ("parole tra graffe diverse", graffe)):
            if elenco:
                problemi += len(elenco)
                print(f"   {titolo}: " + ", ".join(elenco[:12]) + (f" … (+{len(elenco) - 12})" if len(elenco) > 12 else ""))
    intere, composte = usi()
    inesistenti = sorted(k for k in intere if k not in rif)
    senza_riscontro = sorted(c.pattern for c in composte if not any(c.match(k) for k in rif))
    inutilizzate = sorted(k for k in rif if not k.startswith("_") and k not in intere and not any(c.match(k) for c in composte))
    if inesistenti:
        problemi += len(inesistenti)
        print("usate nel codice ma assenti dai file:", ", ".join(inesistenti))
    if senza_riscontro:
        problemi += len(senza_riscontro)
        print("chiavi composte nel codice che non trovano nessuna frase:", ", ".join(senza_riscontro))
    if inutilizzate:
        print(f"frasi che il codice non usa più ({len(inutilizzate)}):", ", ".join(inutilizzate[:20]) + (" …" if len(inutilizzate) > 20 else ""))
    problemi += estensione()
    print("tutto a posto" if not problemi else f"{problemi} cose da sistemare")
    sys.exit(1 if problemi else 0)


if __name__ == "__main__":
    main()
