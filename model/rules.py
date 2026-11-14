# -*- coding: utf-8 -*-
"""Strato a regole di Omissis: formati certi (regex + checksum) e segreti.

rileva(testo) -> [[inizio, fine, etichetta], ...]
Le regole coprono cio' che ha una forma riconoscibile; il resto lo fa il modello.
"""
import re

_HEX = "0-9A-Fa-f"


def _luhn(c):
    s = 0
    for i, ch in enumerate(reversed(c)):
        d = int(ch) * (2 if i % 2 else 1)
        s += d - 9 if d > 9 else d
    return s % 10 == 0


def _piva_ok(c):
    s = sum(int(x) if i % 2 == 0 else (2 * int(x) - 9 if int(x) > 4 else 2 * int(x)) for i, x in enumerate(c[:10]))
    return (10 - s % 10) % 10 == int(c[10]) and c != "0" * 11


def _iban_ok(c):
    c = re.sub(r"[ -]", "", c).upper()
    try:
        return int("".join(str(int(x, 36)) for x in c[4:] + c[:4])) % 97 == 1
    except ValueError:
        return False


def _looks_secret(v):
    return bool(re.search(r"\d|[^\w\s]", v)) or (v != v.lower() and v != v.upper() and v != v.capitalize())


# (etichetta, regex, gruppo, verifica)
RULES = [
    ("SEGRETO", r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", 0, None),
    ("SEGRETO", r"\beyJ[\w-]{10,}\.eyJ[\w-]{10,}\.[\w-]{10,}", 0, None),
    ("SEGRETO", r"\b(?:ghp_|gh[ousr]_|github_pat_|glpat-|npm_|hf_|dop_v1_|AIza|sk-proj-|sk-|xox[baprs]-|(?:pk|sk|rk)_(?:live|test)_)[\w-]{16,}", 0, None),
    ("SEGRETO", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", 0, None),
    ("SEGRETO", r"\bSG\.[\w-]{16,}\.[\w-]{16,}", 0, None),
    ("SEGRETO", r"\b[a-z][a-z0-9+.-]*://[^\s/:@\"']*:[^\s/@\"']+@[^\s\"'<>]+", 0, None),
    ("SEGRETO", r"https://(?:hooks\.slack\.com/services|discord(?:app)?\.com/api/webhooks|api\.telegram\.org/bot)[^\s\"'<>]+", 0, None),
    ("SEGRETO", r"https://[^\s\"'<>]*(?:webhook|[?&](?:token|key|sig|secret)=)[^\s\"'<>]*", 0, None),
    ("SEGRETO", r"(?i)\b(?:Server|Data Source)=[^\n\"']*?\b(?:Password|Pwd)=[^;\s\"']+;?", 0, None),
    ("SEGRETO", r"(?i)\bjdbc:[^\s\"']*password=[^\s\"';]+", 0, None),
    ("SEGRETO", r"\bDefaultEndpointsProtocol=[^\s\"']+", 0, None),
    ("SEGRETO", r"\b(?:\d{6}-){7}\d{6}\b", 0, None),
    ("SEGRETO", r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}|\$6\$[./\w]+\$[./\w]{86}", 0, None),
    ("SEGRETO", rf"\b[{_HEX}]{{32}}:[{_HEX}]{{32}}\b", 0, None),
    ("SEGRETO", r"(?i)\b(?:password|passwd|pwd|psw|passphrase|psksecret|psk|client_secret|secret|token|api[_-]?key|"
                r"access[_-]?key|AccountKey|wpa_passphrase|chiave api)\b[\"']?\s*(?:[:=]|\bè\b)\s*[\"']?([^\s\"';,]{4,})", 1, _looks_secret),
    ("ID_DISPOSITIVO", r"(?i)(?:\bs/n|\bsn|\bs\.n\.|\bserial(?:e|i| number| no)?|\bnumero di serie|\bmatricola|\bmatr\.?|\bservice tag|\bimei|\biccid)"
                       r"\s*(?:n\.|n°|nr\.?)?\s*[:#=.]?\s*([A-Za-z0-9][A-Za-z0-9-]{5,29})(?![A-Za-z0-9])", 1,
     lambda v: sum(ch.isdigit() for ch in v) >= 2),
    ("EMAIL", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", 0, None),
    ("URL", r"\b(?:https?|ftp|sftp)://[^\s<>\"')\]]+", 0,
     lambda v: not re.match(r"https?://(?:[\w-]+\.)*(?:microsoft\.com|microsoftonline\.com|azure\.com|office\.com|google\.com|"
                            r"apple\.com|github\.com|gov\.it|europa\.eu)(?:/[\w./%-]*)?$", v)),
    ("URL", r"\bwww\.[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?:/[^\s<>\"')\]]*)?", 0, None),
    ("IP", r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:/\d{1,2})?(?!\.?\d)", 0,
     lambda v: not v.startswith(("255.", "0.0.0.0", "127.")) and v not in ("8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9")),
    ("IP", rf"(?<![{_HEX}:])(?:(?:[{_HEX}]{{1,4}}:){{7}}[{_HEX}]{{1,4}}|(?:[{_HEX}]{{1,4}}:){{1,6}}:(?:[{_HEX}]{{1,4}}(?::[{_HEX}]{{1,4}}){{0,5}})?)(?![{_HEX}:])", 0, None),
    ("MAC", rf"(?<![{_HEX}:-])(?:[{_HEX}]{{2}}[:-]){{5}}[{_HEX}]{{2}}(?![{_HEX}:-])", 0, None),
    ("MAC", r"(?<![0-9a-f.])(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}(?![0-9a-f.])", 0, None),
    ("ID_CLOUD", rf"(?<![{_HEX}-])[{_HEX}]{{8}}-(?:[{_HEX}]{{4}}-){{3}}[{_HEX}]{{12}}(?![{_HEX}-])", 0, None),
    ("CF", r"(?<![A-Za-z0-9])[A-Za-z]{6}\d{2}[A-EHLMPR-Ta-ehlmpr-t]\d{2}[A-Za-z]\d{3}[A-Za-z](?![A-Za-z0-9])", 0, None),
    ("CF", r"(?<![A-Za-z0-9])[A-Z]{3} [A-Z]{3} \d{2}[A-EHLMPR-T]\d{2} [A-Z]\d{3}[A-Z](?![A-Za-z0-9])", 0, None),
    ("IBAN", r"(?<![A-Za-z0-9])[Ii][Tt]\d{2}[ -]?[A-Za-z](?:[ -]?\d){10}(?:[ -]?[A-Za-z0-9]){12}(?![A-Za-z0-9])", 0, None),
    ("IBAN", r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?(?![A-Za-z0-9])", 0, _iban_ok),
    ("ID_UTENZA", r"\bIT\d{3}E\d{8}\b", 0, None),
    ("PIVA", r"(?<![A-Za-z0-9])(?:IT)?(\d{11})(?![\d])", 0, lambda v: _piva_ok(v[-11:])),
    ("CARTA", r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d])", 0,
     lambda v: 13 <= len(re.sub(r"\D", "", v)) <= 19 and re.sub(r"\D", "", v)[0] in "3456" and _luhn(re.sub(r"\D", "", v))),
    ("TARGA", r"(?<![A-Z0-9])[A-HJ-NPR-TV-Z]{2}[ -]?\d{3}[ -]?[A-HJ-NPR-TV-Z]{2}(?![A-Za-z0-9])", 0, None),
]
_COMP = [(e, re.compile(rx, re.S), g, v) for e, rx, g, v in RULES]


def detect(text):
    found_items = []
    for eti, rx, group, verify in _COMP:
        for m in rx.finditer(text):
            s, e = m.span(group)
            if e > s and (verify is None or verify(text[s:e])):
                found_items.append([s, e, eti])
    # tiene gli span piu' lunghi, scarta quelli contenuti in un altro
    found_items.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out = []
    for s, e, l in found_items:
        if out and s < out[-1][1] and e <= out[-1][1]:
            continue
        out.append([s, e, l])
    return out
