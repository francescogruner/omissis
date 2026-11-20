# -*- coding: utf-8 -*-
"""Shadow AI: cosa c'e' di "intelligenza artificiale" su questo PC e verso quali servizi AI parla.

  pc()    programmi e app installati, processi in esecuzione, estensioni del browser e dell'editor,
          comandi da terminale, modelli che girano in locale
  rete()  servizi AI risolti di recente (cache DNS di Windows) e connessioni aperte in questo
          momento, con il programma che le ha aperte

Sola lettura, nessun privilegio di amministratore. La cache DNS e' un'istantanea: mostra cio' che
il PC ha contattato da poco, non uno storico. Lo storico lo tiene il proxy (data\\contacts.sqlite)
per il traffico che gli passa attraverso.      Uso da terminale: python scan.py
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import catalog
import settings
import i18n
import sistema

if sistema.WINDOWS:
    import winreg

HOME = Path.home()
LOCALE, ROAMING = Path(os.environ.get("LOCALAPPDATA", "")), Path(os.environ.get("APPDATA", ""))
MAC_SUPPORT = HOME / "Library" / "Application Support"   # sul Mac i profili dei browser stanno tutti qui


def _ps(command):
    """Esegue un comando PowerShell di sola lettura e restituisce il JSON che produce."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + command + " | ConvertTo-Json -Compress -Depth 3"],
                           capture_output=True, timeout=40, creationflags=sistema.NO_WINDOW)
        data = json.loads(r.stdout.decode("utf-8", errors="replace") or "[]")
        return data if isinstance(data, list) else [data]
    except Exception:   # noqa: BLE001
        return []


def _recognize(name):
    """Servizio o strumento del catalogo a cui corrisponde un nome di programma o processo."""
    for s in catalog.SERVICES:
        if s["app"] and re.search(s["app"], name, re.I):
            return {"id": s["id"], "name": s["name"], "what": i18n.t(f"services.kind.{s['kind']}"), "policy": settings.policy(s),
                    "readable": bool(s["adapter"])}
    for s in catalog.LOCAL:
        if re.search(s["app"], name, re.I):
            return {"id": s["id"], "name": s["name"], "what": i18n.t(f"detected.what.{s['what']}"), "policy": None, "readable": False}
    return None


def programs():
    found_items = {}
    if not sistema.WINDOWS:   # sul Mac le app in /Applications; su Linux (solo prove) niente
        for name, version in sistema.mac_applications():
            r = _recognize(name)
            if r:
                found_items[name] = {"name": name, "version": version, "origin": i18n.t("detected.origin.program"), "service": r}
        return sorted(found_items.values(), key=lambda x: x["name"].lower())
    keys = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
              (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
    for root, path in keys:
        try:
            k = winreg.OpenKey(root, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                with winreg.OpenKey(k, winreg.EnumKey(k, i)) as sk:
                    name = winreg.QueryValueEx(sk, "DisplayName")[0]
                    try:
                        version = str(winreg.QueryValueEx(sk, "DisplayVersion")[0])
                    except OSError:
                        version = ""
            except OSError:
                continue
            r = _recognize(name)
            if r:
                found_items[name] = {"name": name, "version": version, "origin": i18n.t("detected.origin.program"), **{"service": r}}
    for a in _ps("Get-AppxPackage | Select-Object Name, Version"):
        name = str(a.get("Name", ""))
        r = _recognize(name.replace(".", " "))
        if r and "Runtime" not in name:
            found_items[name] = {"name": name, "version": str(a.get("Version", "")), "origin": i18n.t("detected.origin.store"), "service": r}
    return sorted(found_items.values(), key=lambda x: x["name"].lower())


def processes():
    sightings = {}
    if not sistema.WINDOWS:
        for name, _ in sistema.running_names():
            r = _recognize(name)
            if r:
                sightings.setdefault(name, {"name": name, "instances": 0, "service": r})["instances"] += 1
        return sorted(sightings.values(), key=lambda x: x["name"].lower())
    try:
        out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, timeout=20, creationflags=0x08000000).stdout
    except Exception:   # noqa: BLE001
        return []
    for line in out.decode("cp850", errors="replace").splitlines():
        name = line.split('","')[0].strip('"')
        r = _recognize(re.sub(r"\.exe$", "", name, flags=re.I))
        if r:
            sightings.setdefault(name.lower(), {"name": name, "instances": 0, "service": r})["instances"] += 1
    return sorted(sightings.values(), key=lambda x: x["name"].lower())


def _extension_name(folder, manifest):
    name = str(manifest.get("name", ""))
    m = re.fullmatch(r"__MSG_(.+)__", name)
    if m:
        for language in (manifest.get("default_locale", "en"), "en", "en_US", "it"):
            f = folder / "_locales" / language / "messages.json"
            if f.exists():
                try:
                    msg = json.loads(f.read_text(encoding="utf-8-sig"))
                    for k, v in msg.items():
                        if k.lower() == m.group(1).lower():
                            return str(v.get("message", name))
                except (ValueError, OSError):
                    pass
    return name


def browser_extensions():
    out = []
    browser = {"Chrome": LOCALE / "Google/Chrome/User Data", "Edge": LOCALE / "Microsoft/Edge/User Data",
               "Brave": LOCALE / "BraveSoftware/Brave-Browser/User Data", "Vivaldi": LOCALE / "Vivaldi/User Data",
               "Opera": ROAMING / "Opera Software/Opera Stable"}
    if sistema.MAC:
        browser = {"Chrome": MAC_SUPPORT / "Google/Chrome", "Edge": MAC_SUPPORT / "Microsoft Edge",
                   "Brave": MAC_SUPPORT / "BraveSoftware/Brave-Browser", "Vivaldi": MAC_SUPPORT / "Vivaldi",
                   "Arc": MAC_SUPPORT / "Arc/User Data", "Opera": MAC_SUPPORT / "com.operasoftware.Opera"}
    for name_b, base in browser.items():
        if not base.exists():
            continue
        for est in list(base.glob("*/Extensions/*")) + list(base.glob("Extensions/*")):
            versions = sorted([v for v in est.iterdir() if v.is_dir()], reverse=True) if est.is_dir() else []
            if not versions or not (versions[0] / "manifest.json").exists():
                continue
            try:
                man = json.loads((versions[0] / "manifest.json").read_text(encoding="utf-8-sig"))
            except (ValueError, OSError):
                continue
            name = _extension_name(versions[0], man)
            if catalog.RX_EXTENSION.search(name):
                profile = est.parent.parent.name if est.parent.name == "Extensions" and est.parent.parent != base else "default"
                out.append({"browser": name_b, "profile": profile, "name": name, "version": str(man.get("version", "")), "id": est.name,
                            "all_sites_access": any(x in ("<all_urls>", "*://*/*", "https://*/*", "http://*/*")
                                                           for x in (man.get("host_permissions") or []) + (man.get("permissions") or [])
                                                           if isinstance(x, str))})
    for prof in ((MAC_SUPPORT / "Firefox/Profiles") if sistema.MAC else (ROAMING / "Mozilla/Firefox/Profiles")).glob("*/extensions.json"):
        try:
            for a in json.loads(prof.read_text(encoding="utf-8")).get("addons", []):
                name = str((a.get("defaultLocale") or {}).get("name", ""))
                if a.get("type") == "extension" and a.get("location") == "app-profile" and catalog.RX_EXTENSION.search(name):
                    out.append({"browser": "Firefox", "profile": prof.parent.name, "name": name, "version": str(a.get("version", "")),
                                "id": str(a.get("id", "")), "all_sites_access": False})
        except (ValueError, OSError):
            pass
    return sorted(out, key=lambda x: (x["browser"], x["name"].lower()))


def editor_extensions():
    out, sightings = [], set()
    for editor, folder in {"VS Code": ".vscode", "Cursor": ".cursor", "Windsurf": ".windsurf", "VS Code Insiders": ".vscode-insiders"}.items():
        for p in (HOME / folder / "extensions").glob("*/package.json"):
            try:
                man = json.loads(p.read_text(encoding="utf-8-sig"))
            except (ValueError, OSError):
                continue
            name = str(man.get("displayName") or man.get("name") or "")
            if name.startswith("%"):
                name = str(man.get("name", name))
            key = (editor, man.get("publisher"), man.get("name"))
            if key not in sightings and catalog.RX_EXTENSION.search(f"{name} {man.get('name', '')}"):
                sightings.add(key)
                out.append({"editor": editor, "name": name, "author": str(man.get("publisher", "")), "version": str(man.get("version", ""))})
    return sorted(out, key=lambda x: (x["editor"], x["name"].lower()))


def commands():
    return [{"command": c, "path": p} for c in catalog.RX_CLI if (p := sistema.which(c))]


def _opened_port(port):
    with socket.socket() as s:
        s.settimeout(0.25)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _weight(folder, maximum=30000):
    tot, n = 0, 0
    for root, _, file in os.walk(folder):
        for f in file:
            try:
                tot += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
            n += 1
            if n >= maximum:
                return tot, n, True
    return tot, n, False


def local_models():
    out = []
    for s in catalog.LOCAL:
        for port in s["ports"]:
            if _opened_port(port):
                out.append({"name": s["name"], "what": i18n.t("detected.listening", port=port), "gb": None, "port": port})
    for name, folder in {"Modelli di Ollama": HOME / ".ollama/models", "Modelli di LM Studio": HOME / ".lmstudio/models",
                           "Modelli scaricati da Hugging Face": HOME / ".cache/huggingface/hub"}.items():
        if folder.exists():
            weight, n, truncated = _weight(folder)
            if n:
                out.append({"name": name, "what": str(folder), "gb": round(weight / 1e9, 1), "partial": truncated})
    return out


def pc():
    t0 = time.time()
    r = {"programs": programs(), "processes": processes(), "browser_extensions": browser_extensions(),
         "editor_extensions": editor_extensions(), "commands": commands(), "local": local_models()}
    r["when"], r["seconds"] = time.strftime("%Y-%m-%d %H:%M:%S"), round(time.time() - t0, 1)
    return r


def network():
    """Servizi AI nella cache DNS e connessioni aperte adesso, con il programma che le ha aperte."""
    dns, ip_service = {}, {}
    if not sistema.WINDOWS:   # la cache DNS e le connessioni con il programma si leggono cosi' solo su Windows
        return {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "dns_cache_empty": True, "dns": [], "links": [], "connected_programs": []}
    for v in _ps("Get-DnsClientCache | Select-Object Entry, Data"):
        host = str(v.get("Entry") or "")
        s = catalog.find(host)
        if s is None:
            continue
        dns.setdefault((s["id"], host), {"service": s["name"], "id": s["id"], "host": host, "what": i18n.t(f"services.kind.{s['kind']}"),
                                         "policy": settings.policy(s), "readable": bool(s["adapter"])})
        if re.fullmatch(r"[0-9a-fA-F:.]+", str(v.get("Data") or "")):
            ip_service[str(v["Data"])] = (s, host)
    conn, programs_ai = {}, {}
    lines = _ps("$p = @{}; Get-Process | ForEach-Object { $p[[int]$_.Id] = $_.ProcessName }; "
                "Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | "
                "Where-Object { $_.RemoteAddress -notmatch '^(127\\.|::1|0\\.0\\.0\\.0|::)$' -and $_.RemoteAddress -notmatch '^127\\.' } | "
                "Select-Object RemoteAddress, @{n='Processo';e={$p[[int]$_.OwningProcess]}}")
    for c in lines:
        process = str(c.get("Processo") or "?")
        found = ip_service.get(str(c.get("RemoteAddress")))
        if found:   # attribuzione certa: l'indirizzo viene dalla cache DNS
            s, host = found
            conn.setdefault((s["id"], process), {"service": s["name"], "id": s["id"], "host": host, "process": process,
                                                  "links": 0, "policy": settings.policy(s)})["links"] += 1
        r = _recognize(process)
        if r:         # programma AI con connessioni verso l'esterno (non si sa verso quale indirizzo di preciso)
            programs_ai.setdefault(process, {"process": process, "service": r, "links": 0})["links"] += 1
    return {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "dns_cache_empty": not dns and not ip_service,
            "dns": sorted(dns.values(), key=lambda x: x["service"].lower()),
            "links": sorted(conn.values(), key=lambda x: x["service"].lower()),
            "connected_programs": sorted(programs_ai.values(), key=lambda x: x["process"].lower())}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p, r = pc(), network()
    print(f"PC ({p['seconds']} s): {len(p['programs'])} programmi, {len(p['processes'])} processi, {len(p['browser_extensions'])} estensioni del browser, "
          f"{len(p['editor_extensions'])} estensioni dell'editor, {len(p['commands'])} comandi, {len(p['local'])} voci in locale")
    print(f"Rete: {len(r['dns'])} host AI nella cache DNS, {len(r['links'])} connessioni attribuite, "
          f"{len(r['connected_programs'])} programmi AI con connessioni aperte")
    if "--all" in sys.argv:
        print(json.dumps({"pc": p, "network": r}, ensure_ascii=False, indent=1))
