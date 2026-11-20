# -*- coding: utf-8 -*-
"""Prova le impostazioni imposte dall'amministratore e il riepilogo per la console centrale, con dati inventati.
Non ha bisogno di nulla acceso e non tocca ne' i dati veri ne' le chiavi di sistema del registro.

  python e2e_central.py

Al posto della console c'e' un piccolo servizio finto su questo PC, che registra cio' che riceve.
"""
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ok = True


def check(what, outcome, note=""):
    global ok
    ok &= bool(outcome)
    print(f"{'OK    ' if outcome else 'ERRORE'} {what}" + (f"   {note}" if note else ""))


RECEIVED, ELSEWHERE, SEEN = [], [], []


def own_certificate(folder):
    """Un certificato fatto da se', come quello di una console in rete locale. Restituisce (contesto per il servizio, impronta)."""
    import datetime
    import hashlib
    import ssl
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    who = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Console di prova")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(who).issuer_name(who).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    Path(folder, "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    Path(folder, "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(Path(folder, "cert.pem")), str(Path(folder, "key.pem")))
    return context, hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


class FakeConsole(BaseHTTPRequestHandler):
    answer = 200

    def log_message(self, *a):
        pass

    def do_POST(self):
        SEEN.append(self.path)
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/elsewhere/api/v1/report" or self.path.startswith("/stolen"):
            ELSEWHERE.append(self.headers.get("Authorization"))
        code = FakeConsole.answer if self.headers.get("Authorization") == "Bearer chiave-di-prova" else 401
        if code == 200:
            RECEIVED.append((self.path, json.loads(body.decode("utf-8"))))
        self.send_response(code)
        if code == 302:
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/stolen")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")


sys.stdout.reconfigure(encoding="utf-8")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    os.environ["OMISSIS_DATA"] = folder
    imposed_file = Path(folder) / "imposte.json"
    os.environ["OMISSIS_MANAGED_FILE"] = str(imposed_file)
    import central   # dopo aver scelto la cartella dei dati: le impostazioni di questo PC non vengono toccate
    import managed
    import settings

    def impose(data):
        imposed_file.write_text(json.dumps(data), encoding="utf-8") if data is not None else imposed_file.unlink(missing_ok=True)
        managed.read(fresh=True)

    # ---- che cosa si sostituisce di serie, e i profili
    start = settings.read()
    check("di serie: sostituiti persone, identificativi, pagamenti e dati informatici; in chiaro solo i nomi delle aziende, e non è «protezione ridotta»",
          start["groups_off"] == ["organizations"] and start["categories"] == [] and settings.profile_of() == "standard" and settings.reduced() == []
          and settings.labels_off() == {"ORG"} and settings.reduced({"groups_off": ["organizations", "it"]}) == ["it"], f"{start['groups_off']} {settings.profile_of()}")
    names = {}
    for name, wanted in settings.PROFILES.items():
        after = settings.write({**settings.read(), **{k: list(v) for k, v in wanted.items()}})
        names[name] = (settings.profile_of(), settings.reduced(), sorted(after["groups_off"]), len(after["categories"]))
    settings.write({**settings.read(), "groups_off": ["organizations"], "categories": ["SALUTE"]})
    odd = settings.profile_of()
    settings.write({**settings.read(), "groups_off": ["organizations"], "categories": []})
    check("i quattro profili, dal meno al più stretto: nessuno spegne un gruppo acceso di serie; scelte fatte voce per voce risultano «personalizzato»",
          names == {"standard": ("standard", [], ["organizations"], 0), "confidential": ("confidential", [], [], 0), "special": ("special", [], [], 5),
                    "maximum": ("maximum", [], [], 13)} and odd == "custom", f"{names} {odd}")
    impose({"profile": "special"})
    fixed, cannot = settings.read(), settings.write({**settings.read(), "groups_off": ["organizations", "it"], "categories": []})
    check("un profilo imposto da chi amministra il PC fissa gruppi e categorie: chi usa il PC non li cambia e non riduce la protezione",
          fixed["groups_off"] == [] and fixed["categories"] == sorted(settings.SPECIAL) and settings.locked()["keys"] == ["categories", "groups_off", "profile"]
          and cannot["groups_off"] == [] and cannot["categories"] == sorted(settings.SPECIAL), str(settings.locked()))
    impose({"profile": "maximum", "groups_off": ["organizations"]})
    mixed = settings.read()
    impose({"profile": "inventato"})
    unknown = (settings.read()["groups_off"], settings.locked()["keys"])
    impose(None)
    check("una voce scritta a mano dall'amministratore vince sul profilo; un profilo che non esiste non impone nulla",
          mixed["groups_off"] == ["organizations"] and len(mixed["categories"]) == 13 and unknown == (["organizations"], []) and settings.read()["categories"] == [], f"{mixed['groups_off']} {unknown}")

    # ---- impostazioni imposte
    check("senza vincoli: nulla è bloccato", settings.locked() == {"keys": [], "policies": [], "console": []})
    check("primo avvio: la configurazione guidata viene proposta, ma non durante le prove automatiche",
          settings.first_run() and not settings.first_run(test=True))
    settings.write({**settings.read(), "updates": "notify", "policies": {"deepseek": "record", "chatgpt": "record"}, "groups_off": ["it"]})
    impose({"updates": "never", "policies": {"deepseek": "block"}, "groups_off": [], "restore": 0, "vault_days": "molti", "inventata": 1,
            "mcp_folders": "non un elenco"})
    cfg = settings.read()
    check("le scelte imposte vincono su quelle dell'utente", cfg["updates"] == "never" and cfg["groups_off"] == [] and cfg["restore"] is False,
          f"{cfg['updates']} {cfg['groups_off']} {cfg['restore']}")
    check("regole: imposto solo il servizio scritto, gli altri restano dell'utente", cfg["policies"] == {"deepseek": "block", "chatgpt": "record"}, str(cfg["policies"]))
    # dalla 0.1.4 la guida si propone anche ai PC gestiti (salta i passi gia' decisi); la toglie solo onboarded imposto
    check("PC con impostazioni imposte: la configurazione guidata viene proposta, se onboarded non è imposto", settings.first_run())
    check("un valore scritto male o un nome sconosciuto non impone nulla",
          settings.locked() == {"keys": ["groups_off", "restore", "updates"], "policies": ["deepseek"], "console": []}, str(settings.locked()))
    after = settings.write({**settings.read(), "updates": "automatic", "groups_off": ["payments"], "policies": {**cfg["policies"], "deepseek": "ignore", "chatgpt": "block"},
                            "theme": "dark"})
    check("salvare non scavalca un vincolo, ma cambia il resto", after["updates"] == "never" and after["groups_off"] == [] and after["theme"] == "dark"
          and after["policies"] == {"deepseek": "block", "chatgpt": "block"}, str(after["policies"]))
    own = json.loads((Path(folder) / "settings.json").read_text(encoding="utf-8"))
    check("nel file dell'utente restano le SUE scelte, non quelle imposte", own["updates"] == "notify" and own["groups_off"] == ["it"]
          and own["policies"] == {"deepseek": "record", "chatgpt": "block"}, f"{own['updates']} {own['groups_off']} {own['policies']}")
    impose(None)
    cfg = settings.read()
    check("tolto il vincolo tornano le scelte dell'utente", cfg["updates"] == "notify" and cfg["groups_off"] == ["it"] and cfg["policies"]["deepseek"] == "record"
          and cfg["restore"] is True and settings.locked()["keys"] == [])
    # ---- regole mandate dalla console: valgono solo se il PC ha scelto di accettarle, e solo quelle ammesse
    answer = json.dumps({"ok": True, "rules_version": 4, "rules": {
        "policies": {"deepseek": "block", "non-esiste": "block", "claude": "spegni"}, "block_files": True, "updates": "never", "groups_off": [],
        "engine_url": "https://altrove.example", "console_url": "https://altrove.example", "gateway_upstreams": {"openai": "https://altrove.example"},
        "console_names": False, "console_rules": False, "mcp_folders": ["C:\\"]}}).encode("utf-8")
    settings.write({**settings.read(), "console_url": "https://console.example", "console_key": "omk_prova"})
    central.receive(settings.read(), answer)
    check("regole dalla console: di serie il PC non le accetta e non le conserva",
          not settings.CONSOLE_FILE.exists() and settings.read()["block_files"] is False and settings.locked()["console"] == [] and central.summary("active")["rules_accept"] is False)
    settings.write({**settings.read(), "console_rules": True})
    central.receive(settings.read(), answer)
    cfg, lock = settings.read(), settings.locked()
    check("accettate, valgono quelle ammesse: servizi, file, aggiornamenti, protezione ridotta", cfg["block_files"] is True and cfg["updates"] == "never" and cfg["groups_off"] == []
          and cfg["policies"] == {"deepseek": "block", "chatgpt": "block"}, f"{cfg['block_files']} {cfg['updates']} {cfg['groups_off']} {cfg['policies']}")
    check("la console non sposta indirizzi, cartelle, nome nel riepilogo, né la scelta di accettarla", cfg["engine_url"] == "" and cfg["console_url"] == "https://console.example"
          and cfg["gateway_upstreams"] == {} and cfg["console_names"] is True and cfg["console_rules"] is True and cfg["mcp_folders"] == [])
    check("nel pannello risultano bloccate, e si sa che vengono dalla console", lock == {"keys": ["block_files", "groups_off", "updates"], "policies": ["deepseek"],
                                                                                         "console": ["block_files", "groups_off", "updates", "policies.deepseek"]}, str(lock))
    check("il riepilogo dice alla console quale versione delle regole è in vigore", central.summary("active")["rules_accept"] is True
          and central.summary("active")["rules_version"] == 4 and central.state()["rules"]["count"] == 4 and central.STATE["again"] is True, str(central.state()["rules"]))
    tried = settings.write({**settings.read(), "block_files": False, "updates": "automatic"})
    check("chi usa il PC non le scavalca dal pannello", tried["block_files"] is True and tried["updates"] == "never")
    impose({"updates": "automatic", "policies": {"deepseek": "ignore"}})
    cfg = settings.read()
    check("dove dicono cose diverse vince l'amministratore del PC", cfg["updates"] == "automatic" and cfg["policies"]["deepseek"] == "ignore" and cfg["block_files"] is True
          and settings.locked()["console"] == ["block_files", "groups_off"], str(settings.locked()))
    impose({"console_rules": 0})
    check("l'amministratore del PC può vietare le regole della console", settings.read()["block_files"] is False and settings.locked() == {"keys": ["console_rules"], "policies": [], "console": []})
    impose(None)
    central.receive(settings.read(), b"non json")
    central.receive(settings.read(), json.dumps({"ok": True}).encode("utf-8"))
    check("una risposta rotta, o di una console che non parla di regole, lascia quelle che c'erano", settings.read()["block_files"] is True and settings.console_file()["version"] == 4)
    central.receive(settings.read(), json.dumps({"ok": True, "rules": {}, "rules_version": 5}).encode("utf-8"))
    check("quando la console toglie le regole tornano le scelte dell'utente", settings.read()["block_files"] is False and settings.read()["updates"] == "notify"
          and settings.locked()["console"] == [] and central.summary("active")["rules_version"] == 5)
    free = settings.read()["always_on"] is False and settings.write({**settings.read(), "always_on": True})["always_on"] is True
    settings.write({**settings.read(), "always_on": False})
    central.receive(settings.read(), json.dumps({"ok": True, "rules": {"always_on": True}, "rules_version": 6}).encode("utf-8"))
    check("la console può stabilire che la protezione non si spenga, e chi usa il PC non lo toglie", free and settings.read()["always_on"] is True
          and settings.locked()["console"] == ["always_on"] and settings.write({**settings.read(), "always_on": False})["always_on"] is True, str(settings.locked()))
    impose({"always_on": 0})
    check("anche su questo vince l'amministratore del PC", settings.read()["always_on"] is False and settings.locked()["console"] == []
          and settings.locked()["keys"] == ["always_on"])
    impose(None)
    central.receive(settings.read(), json.dumps({"ok": True, "rules": {"profile": "confidential"}, "rules_version": 7}).encode("utf-8"))
    by_console = (settings.read()["groups_off"], settings.read()["categories"], settings.locked()["console"], settings.write({**settings.read(), "groups_off": ["organizations"]})["groups_off"])
    impose({"profile": "standard"})
    over = settings.read()["groups_off"]
    impose(None)
    check("la console può imporre un profilo dei dati (qui: anche i nomi delle aziende); il profilo dell'amministratore del PC vince sul suo",
          by_console == ([], [], ["profile"], []) and over == ["organizations"], f"{by_console} {over}")
    central.receive(settings.read(), answer)
    settings.write({**settings.read(), "console_url": "https://altra-console.example"})
    check("collegato a un'altra console, le regole della prima non restano in vigore", settings.read()["block_files"] is False and settings.locked()["console"] == []
          and central.summary("active")["rules_version"] == 0)
    settings.write({**settings.read(), "console_url": "", "console_key": "", "console_rules": False})
    settings.CONSOLE_FILE.unlink(missing_ok=True)
    central.STATE["again"] = False
    again = settings.first_run()
    settings.write({**settings.read(), "onboarded": "si"})   # solo un vero «vista» la chiude, non un valore qualsiasi
    still = settings.first_run()
    settings.write({**settings.read(), "onboarded": True})
    check("configurazione guidata: vista una volta non torna più", again and still and not settings.first_run())

    # ---- lettura dal registro: una chiave di prova tra quelle dell'utente, tolta alla fine
    if sys.platform == "win32":
        import winreg
        key = rf"Software\OmissisProva{os.getpid()}"
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as k:
                winreg.SetValueEx(k, "updates", 0, winreg.REG_SZ, "never")
                winreg.SetValueEx(k, "restore", 0, winreg.REG_DWORD, 0)
                winreg.SetValueEx(k, "vault_days", 0, winreg.REG_DWORD, 30)
                winreg.SetValueEx(k, "policies", 0, winreg.REG_SZ, '{"deepseek": "block"}')
                winreg.SetValueEx(k, "groups_off", 0, winreg.REG_MULTI_SZ, ["it", "records"])
                winreg.SetValueEx(k, "console_names", 0, winreg.REG_SZ, "false")
            read = managed.from_registry(winreg.HKEY_CURRENT_USER, key)
            check("registro: testo, numero, JSON ed elenco letti nella forma giusta",
                  read == {"updates": "never", "restore": 0, "vault_days": 30, "policies": {"deepseek": "block"}, "groups_off": ["it", "records"],
                           "console_names": False}, str(read))
        finally:
            winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, key, winreg.KEY_WOW64_64KEY)
        check("registro: una chiave che non esiste non impone nulla", managed.from_registry(winreg.HKEY_CURRENT_USER, key) == {})
    else:
        print("SALTATO lettura dal registro: solo su Windows")

    # ---- il riepilogo: da un registro delle attività inventato
    today, old = time.strftime("%Y-%m-%d"), time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * 60))
    rows = [{"stamp": f"{today} 09:00:00", "event": "masked", "service": "chatgpt", "replacements": {"PERSONA": 2, "EMAIL": 1}},
            {"stamp": f"{today} 09:05:00", "event": "masked", "service": "claude", "replacements": {"IBAN": 1}},
            {"stamp": f"{today} 09:06:00", "event": "masked", "service": "claude", "replacements": {}},
            {"stamp": f"{today} 09:07:00", "event": "blocked_policy", "service": "deepseek"},
            {"stamp": f"{today} 09:08:00", "event": "masked", "service": "chatgpt", "replacements": {"<b>finta</b>": 3, "PERSONA": "tanti"}},
            {"stamp": f"{old} 09:00:00", "event": "masked", "service": "chatgpt", "replacements": {"PERSONA": 50}}]
    (Path(folder) / "activity.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\nriga rotta\n", encoding="utf-8")
    d = central.days()
    check("giorni: richieste, valori per tipo, servizi e richieste fermate di oggi",
          d == [{"day": today, "requests": 2, "blocked": 1, "replacements": {"PERSONA": 2, "EMAIL": 1, "IBAN": 1}, "services": {"chatgpt": 1, "claude": 1}}], str(d))
    s = central.summary("active")
    allowed = {"v", "device", "sent", "version", "channel", "os", "protection", "model", "updates", "groups_off", "managed", "days", "tools", "computer", "user",
               "rules_accept", "rules_version"}   # se questo PC accetta le regole della console, e quale versione ha in vigore
    check("riepilogo: solo le voci previste", set(s) == allowed, str(sorted(set(s) ^ allowed)))
    check("l'identificativo del PC è a caso e resta lo stesso", len(s["device"]) == 32 and central.summary("active")["device"] == s["device"]
          and s["device"] not in (os.environ.get("COMPUTERNAME", "?").lower(), ""))
    settings.write({**settings.read(), "console_names": False})
    s = central.summary("active")
    check("senza nomi: né computer né utente nel riepilogo", "computer" not in s and "user" not in s)
    settings.write({**settings.read(), "console_names": True})

    # ---- l'invio
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeConsole)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    check("senza indirizzo e chiave non parte nulla", central.send("active")["configured"] is False and not RECEIVED)
    cfg = settings.write({**settings.read(), "console_url": "http://console.example.test", "console_key": "chiave-di-prova"})
    check("un indirizzo non https fuori da questo PC viene rifiutato", cfg["console_url"] == "" and not central.configured())
    settings.write({**settings.read(), "console_url": base + "/", "console_key": "chiave-di-prova"})
    st = central.send("active")
    check("invio riuscito: stato aggiornato", st["configured"] and st["error"] == "" and st["last"] and len(RECEIVED) == 1, str(st))
    path, body = RECEIVED[-1] if RECEIVED else ("", {})
    check("arriva all'indirizzo giusto con i conteggi di oggi", path == "/api/v1/report" and body.get("days") == d and body.get("protection") == "active")
    check("nel riepilogo inviato non c'è la chiave di collegamento", "chiave-di-prova" not in json.dumps(body))
    settings.write({**settings.read(), "console_key": "chiave-sbagliata"})
    check("chiave rifiutata dalla console: lo stato lo dice", central.send("active")["error"] == "http_401" and len(RECEIVED) == 1)
    settings.write({**settings.read(), "console_key": "chiave-di-prova"})
    FakeConsole.answer = 302
    st = central.send("active")
    check("un rinvio verso un altro indirizzo non viene seguito: la chiave non va altrove", st["error"] == "http_302" and not ELSEWHERE, f"{st['error']} {ELSEWHERE}")
    FakeConsole.answer = 200
    server.shutdown()
    server.server_close()
    check("console spenta: errore, il programma non si ferma", central.send("active")["error"] == "unreachable")
    # ---- una console in rete locale: certificato fatto da se', riconosciuto dall'impronta
    try:
        context, pin = own_certificate(folder)
    except ImportError:
        context = None
        print("SALTATO console con certificato proprio: manca la libreria cryptography")
    if context is not None:
        local = ThreadingHTTPServer(("127.0.0.1", 0), FakeConsole)
        local.socket = context.wrap_socket(local.socket, server_side=True)
        threading.Thread(target=local.serve_forever, daemon=True).start()
        address, before = f"https://127.0.0.1:{local.server_port}", (len(SEEN), len(RECEIVED))
        settings.write({**settings.read(), "console_url": address, "console_key": "chiave-di-prova", "console_pin": ""})
        check("certificato fatto da sé, senza impronta: rifiutato, e alla console non arriva nulla",
              central.send("active")["error"] == "certificate" and (len(SEEN), len(RECEIVED)) == before, central.STATE["error"])
        settings.write({**settings.read(), "console_pin": "0" * 64})
        check("impronta sbagliata: rifiutato prima di mandare la chiave", central.send("active")["error"] == "certificate" and (len(SEEN), len(RECEIVED)) == before
              and central.state()["pinned"], central.STATE["error"])
        cfg = settings.write({**settings.read(), "console_pin": "SHA256:" + ":".join(pin[i:i + 2].upper() for i in range(0, 64, 2))})
        st = central.send("active")
        check("impronta giusta (scritta anche con i due punti): il riepilogo arriva", cfg["console_pin"] == pin and st["error"] == "" and len(RECEIVED) == before[1] + 1
              and RECEIVED[-1][0] == "/api/v1/report", str(st["error"]))
        check("un'impronta scritta male non vale come impronta", settings.write({**settings.read(), "console_pin": "non-è-un'impronta"})["console_pin"] == "")
        local.shutdown()
        local.server_close()
    settings.write({**settings.read(), "console_pin": ""})
    impose({"console_url": "https://console.example.test", "console_key": "chiave-di-prova"})
    check("console imposta dall'amministratore: lo stato dice che è bloccata", central.state()["managed"] and central.state()["host"] == "console.example.test")
    impose(None)

print("\nTUTTO BENE" if ok else "\nQUALCOSA NON VA")
sys.exit(0 if ok else 1)
