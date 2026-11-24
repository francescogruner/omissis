# -*- coding: utf-8 -*-
"""Scrive la scheda di Omissis per winget, il gestore di pacchetti di Windows, per una versione gia' pubblicata.

La scheda e' fatta di quattro file YAML nella forma che chiede l'archivio pubblico di Microsoft (microsoft/winget-pkgs,
schema 1.28): la versione, l'installer, i testi in inglese (la lingua di base dell'archivio) e quelli in italiano.
Finiscono in <out>/manifests/f/FrancescoGruner/Omissis/<versione>/, cioe' gia' nel posto che hanno nell'archivio.

   python packaging/winget/make_manifest.py --version 0.1.10
          [--installer dist/Omissis-0.1.10-setup.exe | --sha256 <impronta>] [--date 2026-11-23] [--out build/winget]

Senza --installer e senza --sha256 l'impronta e la data si leggono dalla versione pubblicata su GitHub (se GitHub non
dice l'impronta, il file viene scaricato e misurato qui). L'identificativo che Windows da' al programma installato
viene dallo script dell'installer (packaging/windows/omissis.iss), cosi' i due non possono divergere.

Controllo, senza diritti di amministratore:   winget validate --manifest <cartella della versione>
Serve solo la libreria standard di Python.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
REPOSITORY = "francescogruner/omissis"
IDENTIFIER = "FrancescoGruner.Omissis"
SCHEMA = "1.28.0"
# il programma chiede Windows 10 versione 2004 o successiva (vedi i requisiti nel README)
MINIMUM_WINDOWS = "10.0.19041.0"

COMMON = {
    "Publisher": "Francesco Gruner",
    "PublisherSupportUrl": f"https://github.com/{REPOSITORY}/issues",
    "Author": "Francesco Gruner",
    "PackageName": "Omissis",
    "License": "Apache-2.0",
    "LicenseUrl": f"https://github.com/{REPOSITORY}/blob/main/LICENSE",
    "Copyright": "Copyright 2026 Francesco Gruner",
}

LOCALES = {
    "en-US": {
        "PublisherUrl": "https://omissis.eu/en/",
        "PrivacyUrl": "https://omissis.eu/en/privacy/",
        "PackageUrl": "https://omissis.eu/en/",
        "ShortDescription": "Use AI assistants without handing them your personal data. Omissis replaces names, "
                            "addresses, codes and other sensitive values with placeholders before a prompt leaves "
                            "your computer, and puts the real values back into the answer.",
        "Description": (
            "Omissis replaces names, e-mail addresses, phone numbers, tax codes, IBANs, passwords, host names and "
            "other sensitive values with placeholders ([PERSONA_1], [EMAIL_3]…) before a prompt leaves your computer, "
            "and puts the real values back into the answer. You read the real text; the AI service only ever sees "
            "placeholders.",
            "It works in the browser, in the desktop apps of AI assistants and in terminal tools, and it covers "
            "attachments too: Word, Excel, PowerPoint, text, PDF and images with text. You keep using your AI "
            "assistants as you always do, with your own subscriptions: no API keys, no new accounts.",
            "Everything runs on your PC: the detection model, the placeholder vault and the management panel. Nothing "
            "is sent to an Omissis server, because there is none.",
        ),
        "Moniker": "omissis",
        "Tags": ["ai", "anonymization", "data-protection", "gdpr", "llm", "local", "open-source", "pii", "privacy",
                 "pseudonymization"],
        "Documentations": [("Documentation", "https://omissis.eu/en/docs/")],
        "InstallationNotes": "Open Omissis from the Start menu: its panel opens in your browser.",
    },
    "it-IT": {
        "PublisherUrl": "https://omissis.eu/",
        "PrivacyUrl": "https://omissis.eu/privacy/",
        "PackageUrl": "https://omissis.eu/",
        "ShortDescription": "Usa gli assistenti AI senza consegnare i tuoi dati personali. Omissis sostituisce nomi, "
                            "indirizzi, codici e altri dati sensibili con segnaposto prima che il messaggio esca dal "
                            "computer, e rimette i valori veri nella risposta.",
        "Description": (
            "Omissis sostituisce nomi, email, telefoni, codici fiscali, IBAN, password, nomi di dispositivi e altri "
            "dati sensibili con segnaposto ([PERSONA_1], [EMAIL_3]…) prima che il messaggio esca dal computer, e "
            "rimette i valori veri nella risposta. Chi scrive legge il testo vero; il servizio AI vede soltanto "
            "segnaposto.",
            "Funziona nel browser, nelle app desktop degli assistenti AI e negli strumenti da terminale, e vale anche "
            "per gli allegati: Word, Excel, PowerPoint, testo, PDF e immagini con testo. Gli assistenti AI si usano "
            "come sempre, con i propri abbonamenti: niente chiavi API, niente account nuovi.",
            "Tutto gira sul tuo PC: il modello che riconosce i dati, l'archivio dei segnaposto, il pannello. Nulla "
            "viene mandato a un server di Omissis, perché non esiste.",
        ),
        "Tags": ["anonimizzazione", "dati-personali", "gdpr", "ia", "llm", "locale", "open-source", "privacy",
                 "protezione-dei-dati", "pseudonimizzazione"],
        "Documentations": [("Documentazione", "https://omissis.eu/docs/")],
        "InstallationNotes": "Apri Omissis dal menu Start: il suo pannello si apre nel browser.",
    },
}
DEFAULT_LOCALE = "en-US"


def y(value):
    """Un valore YAML su una riga, tra apici quando senza apici verrebbe letto come un'altra cosa."""
    s = str(value)
    risky = (not s or s != s.strip() or s[0] in "[]{}&*!|>'\"%@`#,-?:" or ": " in s or " #" in s or s.endswith(":")
             or re.fullmatch(r"[-+]?(\d[\d_]*)?(\.\d*)?([eE][-+]?\d+)?|true|false|null|yes|no|on|off|~", s, re.I))
    return "'" + s.replace("'", "''") + "'" if risky else s


def product_code():
    """L'identificativo con cui Windows registra il programma installato: l'AppId dell'installer piu' «_is1»."""
    text = (ROOT / "packaging" / "windows" / "omissis.iss").read_text(encoding="utf-8")
    found = re.search(r"(?m)^AppId=\{(\{[0-9A-Fa-f-]{36}\})\s*$", text)
    if not found:
        sys.exit("AppId non trovato in packaging/windows/omissis.iss")
    return found.group(1).upper() + "_is1"


def fetch(url, binary=False):
    request = urllib.request.Request(url, headers={"User-Agent": "omissis-winget-manifest",
                                                   "Accept": "application/octet-stream" if binary else "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        request.add_header("Authorization", "Bearer " + token)
    return urllib.request.urlopen(request, timeout=120)


def published(version, name):
    """Impronta SHA-256 e data dell'installer pubblicato su GitHub per questa versione."""
    with fetch(f"https://api.github.com/repos/{REPOSITORY}/releases/tags/v{version}") as answer:
        release = json.load(answer)
    asset = next((a for a in release.get("assets", []) if a["name"] == name), None)
    if not asset:
        sys.exit(f"nella versione v{version} pubblicata su GitHub non c'e' {name}")
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:"):
        return digest[7:], release["published_at"][:10]
    total = hashlib.sha256()
    with fetch(asset["browser_download_url"], binary=True) as answer:
        for piece in iter(lambda: answer.read(1 << 20), b""):
            total.update(piece)
    return total.hexdigest(), release["published_at"][:10]


def of_file(path):
    total = hashlib.sha256()
    with open(path, "rb") as f:
        for piece in iter(lambda: f.read(1 << 20), b""):
            total.update(piece)
    return total.hexdigest()


def head(kind, version):
    return [f"# yaml-language-server: $schema=https://aka.ms/winget-manifest.{kind}.{SCHEMA}.schema.json", "",
            f"PackageIdentifier: {IDENTIFIER}", f"PackageVersion: {y(version)}"]


def tail(kind):
    return [f"ManifestType: {kind}", f"ManifestVersion: {SCHEMA}", ""]


def version_file(version):
    return head("version", version) + [f"DefaultLocale: {DEFAULT_LOCALE}"] + tail("version")


def installer_file(version, sha256, date, name):
    return head("installer", version) + [
        f"MinimumOSVersion: {MINIMUM_WINDOWS}",
        "InstallerType: inno",
        "Scope: user",
        "InstallModes:", "- interactive", "- silent", "- silentWithProgress",
        # in un aggiornamento l'installer chiude Omissis: con questa opzione alla fine lo riapre, senza aprire il browser
        "InstallerSwitches:", "  Upgrade: /RIAVVIA=1",
        "UpgradeBehavior: install",
        f"ProductCode: {y(product_code())}",
        f"ReleaseDate: {date}",
        "Installers:",
        "- Architecture: x64",
        f"  InstallerUrl: https://github.com/{REPOSITORY}/releases/download/v{version}/{name}",
        f"  InstallerSha256: {sha256.upper()}",
    ] + tail("installer")


def locale_file(version, locale):
    texts = LOCALES[locale]
    default = locale == DEFAULT_LOCALE
    kind = "defaultLocale" if default else "locale"
    rows = head(kind, version) + [f"PackageLocale: {locale}"]
    for key in ("Publisher", "PublisherUrl", "PublisherSupportUrl", "PrivacyUrl", "Author", "PackageName", "PackageUrl",
                "License", "LicenseUrl", "Copyright", "ShortDescription"):
        rows.append(f"{key}: {y(texts.get(key, COMMON.get(key)))}")
    rows.append("Description: |-")
    for i, paragraph in enumerate(texts["Description"]):
        rows += ([""] if i else []) + ["  " + paragraph]
    if default:
        rows.append(f"Moniker: {y(texts['Moniker'])}")
    rows += ["Tags:"] + [f"- {y(tag)}" for tag in texts["Tags"]]
    rows.append(f"ReleaseNotesUrl: https://github.com/{REPOSITORY}/releases/tag/v{version}")
    rows.append(f"InstallationNotes: {y(texts['InstallationNotes'])}")
    rows.append("Documentations:")
    for label, url in texts["Documentations"]:
        rows += [f"- DocumentLabel: {y(label)}", f"  DocumentUrl: {url}"]
    return rows + tail(kind)


def main():
    parser = argparse.ArgumentParser(description="Scrive la scheda di Omissis per winget.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--installer", help="l'installer pubblicato, per misurarne l'impronta")
    parser.add_argument("--sha256", help="l'impronta SHA-256 dell'installer pubblicato")
    parser.add_argument("--date", help="la data di pubblicazione (AAAA-MM-GG)")
    parser.add_argument("--out", default=str(ROOT / "build" / "winget"))
    a = parser.parse_args()
    if not re.fullmatch(r"\d+(\.\d+){1,3}", a.version):
        sys.exit("la versione e' fatta di soli numeri e punti, per esempio 0.1.10")
    name = f"Omissis-{a.version}-setup.exe"
    sha256, date = a.sha256, a.date
    if a.installer:
        sha256 = of_file(a.installer)
    if not sha256 or not date:
        found = published(a.version, name)
        sha256, date = sha256 or found[0], date or found[1]
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", sha256) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        sys.exit("impronta o data non valide")
    folder = Path(a.out) / "manifests" / IDENTIFIER[0].lower() / Path(*IDENTIFIER.split(".")) / a.version
    folder.mkdir(parents=True, exist_ok=True)
    files = {f"{IDENTIFIER}.yaml": version_file(a.version),
             f"{IDENTIFIER}.installer.yaml": installer_file(a.version, sha256, date, name)}
    for locale in LOCALES:
        files[f"{IDENTIFIER}.locale.{locale}.yaml"] = locale_file(a.version, locale)
    for old in folder.glob("*.yaml"):
        old.unlink()
    for file, rows in files.items():
        (folder / file).write_bytes("\n".join(rows).encode("utf-8"))
    print(folder)


if __name__ == "__main__":
    main()
