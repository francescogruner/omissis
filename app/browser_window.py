# -*- coding: utf-8 -*-
"""Apre una finestra di Chrome (o Edge) SEPARATA che passa dal proxy, per la prova sul web.

  .venv\\Scripts\\python.exe browser_window.py [indirizzo=https://claude.ai]

Non tocca il browser di tutti i giorni ne' le impostazioni di Windows:
  - profilo a parte in data\\browser_profile (bisogna rifare l'accesso al servizio);
  - il proxy vale solo per questa finestra (--proxy-server);
  - il certificato del proxy viene accettato solo da questa finestra e solo per la sua chiave
    (--ignore-certificate-errors-spki-list), senza installarlo nel sistema.
"""
import base64
import hashlib
import subprocess
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

QUI = Path(__file__).resolve().parent
import settings   # noqa: E402
import i18n         # noqa: E402
import paths       # noqa: E402

CERT = paths.DATI / "ca" / "mitmproxy-ca-cert.pem"
BROWSER = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
           r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]

if not CERT.exists():
    sys.exit(i18n.t("proxy.certificato.non_creato"))
chiave = x509.load_pem_x509_certificate(CERT.read_bytes()).public_key().public_bytes(
    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
impronta = base64.b64encode(hashlib.sha256(chiave).digest()).decode()
exe = next((b for b in BROWSER if Path(b).exists()), None)
if exe is None:
    sys.exit(i18n.t("programma.finestra_senza_browser"))
subprocess.Popen([exe, f"--user-data-dir={paths.DATI / 'browser_profile'}", f"--proxy-server=http://127.0.0.1:{settings.leggi()['porta']}",
                  f"--ignore-certificate-errors-spki-list={impronta}", "--no-first-run", "--no-default-browser-check",
                  sys.argv[1] if len(sys.argv) > 1 else "https://claude.ai"])
print(i18n.t("programma.finestra_aperta", browser=Path(exe).stem))
