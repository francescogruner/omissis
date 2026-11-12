# -*- coding: utf-8 -*-
"""Shadow AI: cosa c'e' di "intelligenza artificiale" su questo PC e verso quali servizi AI parla.

  pc()    programmi e app installati, processi in esecuzione, estensioni del browser e dell'editor,
          comandi da terminale, modelli che girano in locale
  rete()  servizi AI risolti di recente (cache DNS di Windows) e connessioni aperte in questo
          momento, con il programma che le ha aperte

Sola lettura, nessun privilegio di amministratore. La cache DNS e' un'istantanea: mostra cio' che
il PC ha contattato da poco, non uno storico. Lo storico lo tiene il proxy (dati\\contatti.sqlite)
per il traffico che gli passa attraverso.      Uso da terminale: python scansione.py
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import winreg
from pathlib import Path

import catalogo
import impostazioni

CASA = Path.home()
LOCALE, ROAMING = Path(os.environ.get("LOCALAPPDATA", "")), Path(os.environ.get("APPDATA", ""))


def _ps(comando):
    """Esegue un comando PowerShell di sola lettura e restituisce il JSON che produce."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + comando + " | ConvertTo-Json -Compress -Depth 3"],
                           capture_output=True, timeout=40, creationflags=0x08000000)
        dati = json.loads(r.stdout.decode("utf-8", errors="replace") or "[]")
        return dati if isinstance(dati, list) else [dati]
    except Exception:   # noqa: BLE001
        return []


def _riconosci(nome):
    """Servizio o strumento del catalogo a cui corrisponde un nome di programma o processo."""
    for s in catalogo.SERVIZI:
        if s["app"] and re.search(s["app"], nome, re.I):
            return {"id": s["id"], "nome": s["nome"], "cosa": catalogo.TIPI[s["tipo"]], "politica": impostazioni.politica(s),
                    "leggibile": bool(s["adattatore"])}
    for s in catalogo.LOCALI:
        if re.search(s["app"], nome, re.I):
            return {"id": s["id"], "nome": s["nome"], "cosa": s["cosa"], "politica": None, "leggibile": False}
    return None


def programmi():
    trovati = {}
    chiavi = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
              (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
    for radice, percorso in chiavi:
        try:
            k = winreg.OpenKey(radice, percorso)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                with winreg.OpenKey(k, winreg.EnumKey(k, i)) as sk:
                    nome = winreg.QueryValueEx(sk, "DisplayName")[0]
                    try:
                        versione = str(winreg.QueryValueEx(sk, "DisplayVersion")[0])
                    except OSError:
                        versione = ""
            except OSError:
                continue
            r = _riconosci(nome)
            if r:
                trovati[nome] = {"nome": nome, "versione": versione, "origine": "programma", **{"servizio": r}}
    for a in _ps("Get-AppxPackage | Select-Object Name, Version"):
        nome = str(a.get("Name", ""))
        r = _riconosci(nome.replace(".", " "))
        if r and "Runtime" not in nome:
            trovati[nome] = {"nome": nome, "versione": str(a.get("Version", "")), "origine": "app dello Store", "servizio": r}
    return sorted(trovati.values(), key=lambda x: x["nome"].lower())


def processi():
    visti = {}
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, timeout=20, creationflags=0x08000000).stdout
    except Exception:   # noqa: BLE001
        return []
    for riga in out.decode("cp850", errors="replace").splitlines():
        nome = riga.split('","')[0].strip('"')
        r = _riconosci(re.sub(r"\.exe$", "", nome, flags=re.I))
        if r:
            visti.setdefault(nome.lower(), {"nome": nome, "istanze": 0, "servizio": r})["istanze"] += 1
    return sorted(visti.values(), key=lambda x: x["nome"].lower())


def _nome_estensione(cartella, manifesto):
    nome = str(manifesto.get("name", ""))
    m = re.fullmatch(r"__MSG_(.+)__", nome)
    if m:
        for lingua in (manifesto.get("default_locale", "en"), "en", "en_US", "it"):
            f = cartella / "_locales" / lingua / "messages.json"
            if f.exists():
                try:
                    msg = json.loads(f.read_text(encoding="utf-8-sig"))
                    for k, v in msg.items():
                        if k.lower() == m.group(1).lower():
                            return str(v.get("message", nome))
                except (ValueError, OSError):
                    pass
    return nome


def estensioni_browser():
    out = []
    browser = {"Chrome": LOCALE / "Google/Chrome/User Data", "Edge": LOCALE / "Microsoft/Edge/User Data",
               "Brave": LOCALE / "BraveSoftware/Brave-Browser/User Data", "Vivaldi": LOCALE / "Vivaldi/User Data",
               "Opera": ROAMING / "Opera Software/Opera Stable"}
    for nome_b, base in browser.items():
        if not base.exists():
            continue
        for est in list(base.glob("*/Extensions/*")) + list(base.glob("Extensions/*")):
            versioni = sorted([v for v in est.iterdir() if v.is_dir()], reverse=True) if est.is_dir() else []
            if not versioni or not (versioni[0] / "manifest.json").exists():
                continue
            try:
                man = json.loads((versioni[0] / "manifest.json").read_text(encoding="utf-8-sig"))
            except (ValueError, OSError):
                continue
            nome = _nome_estensione(versioni[0], man)
            if catalogo.RX_ESTENSIONE.search(nome):
                profilo = est.parent.parent.name if est.parent.name == "Extensions" and est.parent.parent != base else "predefinito"
                out.append({"browser": nome_b, "profilo": profilo, "nome": nome, "versione": str(man.get("version", "")), "id": est.name,
                            "accesso_a_tutti_i_siti": any(x in ("<all_urls>", "*://*/*", "https://*/*", "http://*/*")
                                                           for x in (man.get("host_permissions") or []) + (man.get("permissions") or [])
                                                           if isinstance(x, str))})
    for prof in (ROAMING / "Mozilla/Firefox/Profiles").glob("*/extensions.json"):
        try:
            for a in json.loads(prof.read_text(encoding="utf-8")).get("addons", []):
                nome = str((a.get("defaultLocale") or {}).get("name", ""))
                if a.get("type") == "extension" and a.get("location") == "app-profile" and catalogo.RX_ESTENSIONE.search(nome):
                    out.append({"browser": "Firefox", "profilo": prof.parent.name, "nome": nome, "versione": str(a.get("version", "")),
                                "id": str(a.get("id", "")), "accesso_a_tutti_i_siti": False})
        except (ValueError, OSError):
            pass
    return sorted(out, key=lambda x: (x["browser"], x["nome"].lower()))


def estensioni_editor():
    out, visti = [], set()
    for editor, cartella in {"VS Code": ".vscode", "Cursor": ".cursor", "Windsurf": ".windsurf", "VS Code Insiders": ".vscode-insiders"}.items():
        for p in (CASA / cartella / "extensions").glob("*/package.json"):
            try:
                man = json.loads(p.read_text(encoding="utf-8-sig"))
            except (ValueError, OSError):
                continue
            nome = str(man.get("displayName") or man.get("name") or "")
            if nome.startswith("%"):
                nome = str(man.get("name", nome))
            chiave = (editor, man.get("publisher"), man.get("name"))
            if chiave not in visti and catalogo.RX_ESTENSIONE.search(f"{nome} {man.get('name', '')}"):
                visti.add(chiave)
                out.append({"editor": editor, "nome": nome, "autore": str(man.get("publisher", "")), "versione": str(man.get("version", ""))})
    return sorted(out, key=lambda x: (x["editor"], x["nome"].lower()))


def comandi():
    return [{"comando": c, "percorso": p} for c in catalogo.RX_CLI if (p := shutil.which(c))]


def _porta_aperta(porta):
    with socket.socket() as s:
        s.settimeout(0.25)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def _peso(cartella, massimo=30000):
    tot, n = 0, 0
    for radice, _, file in os.walk(cartella):
        for f in file:
            try:
                tot += os.path.getsize(os.path.join(radice, f))
            except OSError:
                pass
            n += 1
            if n >= massimo:
                return tot, n, True
    return tot, n, False


def modelli_locali():
    out = []
    for s in catalogo.LOCALI:
        for porta in s["porte"]:
            if _porta_aperta(porta):
                out.append({"nome": s["nome"], "cosa": f"servizio in ascolto sulla porta {porta}", "gb": None})
    for nome, cartella in {"Modelli di Ollama": CASA / ".ollama/models", "Modelli di LM Studio": CASA / ".lmstudio/models",
                           "Modelli scaricati da Hugging Face": CASA / ".cache/huggingface/hub"}.items():
        if cartella.exists():
            peso, n, troncato = _peso(cartella)
            if n:
                out.append({"nome": nome, "cosa": str(cartella), "gb": round(peso / 1e9, 1), "parziale": troncato})
    return out


def pc():
    t0 = time.time()
    r = {"programmi": programmi(), "processi": processi(), "estensioni_browser": estensioni_browser(),
         "estensioni_editor": estensioni_editor(), "comandi": comandi(), "locali": modelli_locali()}
    r["quando"], r["secondi"] = time.strftime("%Y-%m-%d %H:%M:%S"), round(time.time() - t0, 1)
    return r


def rete():
    """Servizi AI nella cache DNS e connessioni aperte adesso, con il programma che le ha aperte."""
    dns, ip_servizio = {}, {}
    for v in _ps("Get-DnsClientCache | Select-Object Entry, Data"):
        host = str(v.get("Entry") or "")
        s = catalogo.trova(host)
        if s is None:
            continue
        dns.setdefault((s["id"], host), {"servizio": s["nome"], "id": s["id"], "host": host, "cosa": catalogo.TIPI[s["tipo"]],
                                         "politica": impostazioni.politica(s), "leggibile": bool(s["adattatore"])})
        if re.fullmatch(r"[0-9a-fA-F:.]+", str(v.get("Data") or "")):
            ip_servizio[str(v["Data"])] = (s, host)
    conn, programmi_ai = {}, {}
    righe = _ps("$p = @{}; Get-Process | ForEach-Object { $p[[int]$_.Id] = $_.ProcessName }; "
                "Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | "
                "Where-Object { $_.RemoteAddress -notmatch '^(127\\.|::1|0\\.0\\.0\\.0|::)$' -and $_.RemoteAddress -notmatch '^127\\.' } | "
                "Select-Object RemoteAddress, @{n='Processo';e={$p[[int]$_.OwningProcess]}}")
    for c in righe:
        processo = str(c.get("Processo") or "?")
        trovato = ip_servizio.get(str(c.get("RemoteAddress")))
        if trovato:   # attribuzione certa: l'indirizzo viene dalla cache DNS
            s, host = trovato
            conn.setdefault((s["id"], processo), {"servizio": s["nome"], "id": s["id"], "host": host, "processo": processo,
                                                  "connessioni": 0, "politica": impostazioni.politica(s)})["connessioni"] += 1
        r = _riconosci(processo)
        if r:         # programma AI con connessioni verso l'esterno (non si sa verso quale indirizzo di preciso)
            programmi_ai.setdefault(processo, {"processo": processo, "servizio": r, "connessioni": 0})["connessioni"] += 1
    return {"quando": time.strftime("%Y-%m-%d %H:%M:%S"), "cache_dns_vuota": not dns and not ip_servizio,
            "dns": sorted(dns.values(), key=lambda x: x["servizio"].lower()),
            "connessioni": sorted(conn.values(), key=lambda x: x["servizio"].lower()),
            "programmi_connessi": sorted(programmi_ai.values(), key=lambda x: x["processo"].lower())}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, r = pc(), rete()
    print(f"PC ({p['secondi']} s): {len(p['programmi'])} programmi, {len(p['processi'])} processi, {len(p['estensioni_browser'])} estensioni del browser, "
          f"{len(p['estensioni_editor'])} estensioni dell'editor, {len(p['comandi'])} comandi, {len(p['locali'])} voci in locale")
    print(f"Rete: {len(r['dns'])} host AI nella cache DNS, {len(r['connessioni'])} connessioni attribuite, "
          f"{len(r['programmi_connessi'])} programmi AI con connessioni aperte")
    if "--tutto" in sys.argv:
        print(json.dumps({"pc": p, "rete": r}, ensure_ascii=False, indent=1))
