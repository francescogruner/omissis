# -*- coding: utf-8 -*-
"""Prova il server MCP facendogli da app: lo lancia, gli parla sull'ingresso/uscita standard come vuole il protocollo
e controlla che all'«assistente» non arrivi mai un dato vero, ne' leggendo i documenti ne' chiedendo il ripristino.

Serve il motore acceso (la protezione attiva). I documenti sono inventati e stanno in una cartella provvisoria, la
sola che il server puo' usare durante la prova; gli appunti di Windows non vengono toccati.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import mcp_server
import paths

HERE = Path(__file__).resolve().parent
TEXT = ("Verbale di assistenza. Giulia Ferraresi (giulia.ferraresi@nevatek.example, cell. 347 5551234) della Nevatek S.r.l. "
        "ha chiesto di spostare l'appuntamento con Aldo Bruschi.")
SENSITIVE = ["Giulia Ferraresi", "giulia.ferraresi@nevatek.example", "347 5551234", "Aldo Bruschi", "Ferraresi", "Bruschi"]
outcomes, seen = [], []


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(f"{'OK    ' if ok else 'ERRORE'} {name}" + (f"   {note}" if note else ""), flush=True)


def reveal(text):
    return sum(s in text for s in SENSITIVE)


class App:
    """Un'app che parla MCP con il server, una riga JSON per messaggio."""

    def __init__(self, folder, port=None):
        env = {**os.environ, "OMISSIS_MCP_FOLDERS": str(folder), "PYTHONUTF8": "1"}
        if port:
            env["OMISSIS_PORT"] = str(port)
        self.p = subprocess.Popen([sys.executable, str(HERE / "mcp_server.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env=env, cwd=HERE)
        self.n = 0

    def raw(self, line):
        self.p.stdin.write(line + b"\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline().decode("utf-8"))

    def ask(self, method, params=None):
        self.n += 1
        return self.raw(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}).encode("utf-8"))

    def notify(self, method):
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}).encode("utf-8") + b"\n")
        self.p.stdin.flush()

    def tool(self, name, **arguments):
        r = self.ask("tools/call", {"name": name, "arguments": arguments})["result"]
        text = "\n".join(c["text"] for c in r["content"])
        seen.append(text)   # tutto cio' che l'assistente vede, per il controllo finale
        return text, r["isError"]

    def close(self):
        self.p.stdin.close()
        return self.p.wait(10)


def documents_in(folder):
    import docx
    import openpyxl
    from pptx import Presentation
    from pptx.util import Inches
    (folder / "verbale.txt").write_text(TEXT, encoding="utf-8")
    (folder / "lungo.txt").write_text("\n".join([TEXT] * 60), encoding="utf-8")
    d = docx.Document()
    d.sections[0].header.paragraphs[0].text = "Riservato - Nevatek S.r.l. - referente Aldo Bruschi"
    d.add_paragraph(TEXT)
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Referente", "Giulia Ferraresi"
    d.save(folder / "verbale.docx")
    w = openpyxl.Workbook()
    w.active.title = "Contatti"
    w.active.append(["Nome", "E-mail", "Telefono"])
    w.active.append(["Giulia Ferraresi", "giulia.ferraresi@nevatek.example", "347 5551234"])
    w.active.append(["Aldo Bruschi", "aldo.bruschi@nevatek.example", 3475551299])   # un telefono scritto come numero
    w.save(folder / "contatti.xlsx")
    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[5])
    s.shapes.title.text = "Incontro con Giulia Ferraresi"
    s.shapes.add_textbox(Inches(1), Inches(2), Inches(6), Inches(1)).text_frame.text = "Scrivere a giulia.ferraresi@nevatek.example"
    s.notes_slide.notes_text_frame.text = "Richiamare Aldo Bruschi al 347 5551234"
    p.save(folder / "incontro.pptx")
    (folder / "cartella").mkdir()
    (folder / "cartella" / "uno.txt").write_text(TEXT, encoding="utf-8")
    (folder / "cartella" / "due.md").write_text("# Nota\n" + TEXT, encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    log = paths.DATA / "activity.jsonl"
    lines_before = len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as outside:
        folder = Path(os.path.realpath(tmp))
        documents_in(folder)
        (Path(outside) / "fuori.txt").write_text(TEXT, encoding="utf-8")
        app = App(folder)

        # --- protocollo
        r = app.ask("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "prova-mcp", "version": "1.0"}})["result"]
        mark("avvio: versione del protocollo, nome e istruzioni per l'assistente", r["protocolVersion"] == "2025-06-18" and r["serverInfo"]["name"] == "omissis"
             and "read_anonymized" in r["instructions"] and "tools" in r["capabilities"])
        app.notify("notifications/initialized")
        mark("una notifica non riceve risposta, il controllo di vita sì", app.ask("ping") == {"jsonrpc": "2.0", "id": app.n, "result": {}})
        tools = {t["name"]: t for t in app.ask("tools/list")["result"]["tools"]}
        mark("elenco degli strumenti, ciascuno con descrizione e schema", set(tools) == {"omissis_status", "read_anonymized", "anonymize_copy", "restore_copy", "restore_text"}
             and all(t["description"] and t["inputSchema"]["type"] == "object" for t in tools.values()), ", ".join(sorted(tools)))
        mark("metodo sconosciuto e riga che non è JSON: errore, il server resta in piedi", app.ask("non/esiste")["error"]["code"] == -32601
             and app.raw(b"{non json")["error"]["code"] == -32700 and "result" in app.ask("ping"))
        altra = App(folder)
        mark("una versione del protocollo sconosciuta riceve la più recente che il server parla",
             altra.ask("initialize", {"protocolVersion": "2099-01-01", "capabilities": {}})["result"]["protocolVersion"] == mcp_server.PROTOCOLS[0])
        mark("chiusa l'app, il server si chiude da solo", altra.close() == 0)

        # --- lettura anonimizzata
        text, failed = app.tool("omissis_status")
        mark("stato: Omissis acceso e cartelle permesse", not failed and "is running" in text and str(folder) in text, text[:90])
        text, failed = app.tool("read_anonymized", path=str(folder / "verbale.txt"))
        mark("testo: all'assistente arrivano i segnaposto, nessun dato vero", not failed and reveal(text) == 0 and "[PERSONA_" in text and "[EMAIL_" in text
             and "Verbale di assistenza" in text and "End of document" in text, text[:110].replace("\n", " "))
        text, failed = app.tool("read_anonymized", path=str(folder / "verbale.docx"))
        mark("Word: corpo, tabella e intestazione, nessun dato vero", not failed and reveal(text) == 0 and "Referente | [PERSONA_" in text and "Riservato" in text)
        text, failed = app.tool("read_anonymized", path=str(folder / "contatti.xlsx"))
        mark("Excel: righe e colonne, anche il telefono scritto come numero", not failed and reveal(text) == 0 and "3475551299" not in text
             and "Nome\tE-mail\tTelefono" in text and "=== Contatti ===" in text, text.splitlines()[2][:80])
        text, failed = app.tool("read_anonymized", path=str(folder / "incontro.pptx"))
        mark("PowerPoint: titolo, caselle di testo e note", not failed and reveal(text) == 0 and "--- slide 1 ---" in text and "[notes]" in text and "[EMAIL_" in text)
        first, _ = app.tool("read_anonymized", path=str(folder / "lungo.txt"), max_chars=3000)
        whole, start = "", 0
        for _ in range(20):
            piece, failed = app.tool("read_anonymized", path=str(folder / "lungo.txt"), start=start, max_chars=3000)
            body, note = piece.rsplit("\n\n[Omissis:", 1)
            whole += body
            start += len(body)
            if "End of document" in note:
                break
        mark("documento lungo: arriva a pezzi e i pezzi ricompongono tutto", "call read_anonymized again with start=3000" in first and reveal(whole) == 0
             and whole.count("Verbale di assistenza") == 60 and whole.count("[EMAIL_") == 60, f"{len(whole)} caratteri")

        # --- limiti: cartelle, percorsi
        text, failed = app.tool("read_anonymized", path=str(Path(outside) / "fuori.txt"))
        mark("un file fuori dalle cartelle permesse non viene letto", failed and reveal(text) == 0 and "outside the folders" in text)
        text, failed = app.tool("read_anonymized", path=str(paths.DATA / "token.txt"))
        text2, failed2 = app.tool("read_anonymized", path="verbale.txt")
        text3, failed3 = app.tool("read_anonymized", path=str(folder / "cartella" / ".." / ".." / Path(outside).name / "fuori.txt"))
        mark("né i dati di Omissis, né un percorso relativo, né uno che esce con «..»", failed and failed2 and failed3 and "absolute path" in text2 and reveal(text3) == 0)
        text, failed = app.tool("read_anonymized", path=str(folder / "non-esiste.txt"))
        text2, failed2 = app.tool("read_anonymized", path=str(folder / "cartella"))
        text3, failed3 = app.tool("non_esiste")
        mark("file che non c'è, cartella al posto del file, strumento sconosciuto: errore chiaro", failed and failed2 and failed3 and "no file" in text and "folder" in text2)

        # --- copie anonimizzate
        text, failed = app.tool("anonymize_copy", path=str(folder / "verbale.docx"))
        copy = folder / "verbale.anon.docx"
        mark("copia anonimizzata di un file, nello stesso formato", not failed and copy.exists() and str(copy) in text and reveal(text) == 0
             and reveal(mcp_server._office_text(copy.name, copy.read_bytes())) == 0, text.splitlines()[1][:80])
        text, failed = app.tool("anonymize_copy", path=str(folder / "cartella"))
        inside = sorted(f.name for f in (folder / "cartella.anon").glob("*")) if (folder / "cartella.anon").is_dir() else []
        mark("copia anonimizzata di una cartella intera", not failed and inside == ["due.anon.md", "uno.anon.txt"]
             and all(reveal(f.read_text(encoding="utf-8")) == 0 for f in (folder / "cartella.anon").glob("*")), ", ".join(inside))

        # --- ripristino: i valori veri tornano sul PC, mai all'assistente
        masked = (folder / "cartella.anon" / "uno.anon.txt").read_text(encoding="utf-8")
        text, failed = app.tool("restore_text", text="Gentile " + masked, save_as=str(folder / "risposta.txt"))
        written = (folder / "risposta.txt").read_text(encoding="utf-8") if (folder / "risposta.txt").exists() else ""
        mark("ripristino di un testo: scritto in un file, all'assistente solo il conto", not failed and written == "Gentile " + TEXT and reveal(text) == 0
             and "placeholder(s) restored" in text, text[:70])
        text, failed = app.tool("restore_text", text=masked, save_as=str(folder / "risposta.txt"))
        text2, failed2 = app.tool("restore_text", text=masked, save_as=str(Path(outside) / "risposta.txt"))
        text3, failed3 = app.tool("restore_text", text="Nessun segnaposto qui.", save_as=str(folder / "vuoto.txt"))
        text4, failed4 = app.tool("restore_text", text="Scrivi a [PERSONA_999999].", save_as=str(folder / "ignoto.txt"))
        mark("non si sovrascrive, non si scrive fuori, non si scrive se non c'è nulla da ripristinare", failed and failed2 and failed3 and failed4
             and "already exists" in text and not (Path(outside) / "risposta.txt").exists() and not (folder / "vuoto.txt").exists() and not (folder / "ignoto.txt").exists())
        text, failed = app.tool("restore_copy", path=str(folder / "cartella.anon" / "uno.anon.txt"))
        back = folder / "cartella.anon" / "uno.restored.txt"
        mark("ripristino di un file: la copia ha i valori veri, la risposta no", not failed and back.exists() and back.read_text(encoding="utf-8") == TEXT
             and reveal(text) == 0 and "do not open it" in text)

        # --- motore spento: nessun testo, mai
        off = App(folder, port=paths.ENGINE_PORT + 190)
        off.ask("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
        text, failed = off.tool("read_anonymized", path=str(folder / "verbale.txt"))
        text2, failed2 = off.tool("omissis_status")
        text3, failed3 = off.tool("restore_text", text=masked, save_as=str(folder / "spento.txt"))
        mark("con Omissis spento non esce nulla: errore, non il testo in chiaro", failed and failed2 and failed3 and reveal(text) == 0 and "not running" in text
             and not (folder / "spento.txt").exists())
        off.close()

        mark("in tutta la prova l'assistente non ha mai visto un dato vero", sum(reveal(t) for t in seen) == 0, f"{len(seen)} risposte degli strumenti")
        app.close()
        fresh = log.read_text(encoding="utf-8").splitlines()[lines_before:] if log.exists() else []
        mine = [json.loads(x) for x in fresh if '"via": "mcp"' in x]
        mark("registro: righe con i soli conteggi e il nome dell'app", len(mine) >= 6 and all(m["client"] == "prova-mcp 1.0" for m in mine)
             and any(sum(m["replacements"].values()) > 0 for m in mine) and reveal("\n".join(fresh)) == 0, f"{len(mine)} righe")

        # --- registrazione in Claude Desktop (su un file di prova, non su quello vero)
        cfg = folder / "claude_desktop_config.json"
        cfg.write_text(json.dumps({"mcpServers": {"altro": {"command": "x"}}, "preferences": {"tema": "scuro"}}), encoding="utf-8")
        changed = mcp_server.claude_desktop_install(cfg)
        data = json.loads(cfg.read_text(encoding="utf-8"))
        state = mcp_server.claude_desktop_state(cfg)
        mark("Claude Desktop: Omissis aggiunto senza toccare il resto, con una copia del file di prima", changed and data["mcpServers"]["altro"] == {"command": "x"}
             and data["preferences"] == {"tema": "scuro"} and data["mcpServers"]["omissis"]["args"] == [str(HERE / "mcp_server.py")]
             and state == {"installed": True, "registered": True, "current": True} and cfg.with_name(cfg.name + ".omissis-backup").exists()
             and not mcp_server.claude_desktop_install(cfg))
        removed = mcp_server.claude_desktop_install(cfg, remove=True)
        data = json.loads(cfg.read_text(encoding="utf-8"))
        mark("Claude Desktop: tolto, il resto rimane", removed and data == {"mcpServers": {"altro": {"command": "x"}}, "preferences": {"tema": "scuro"}}
             and not mcp_server.claude_desktop_state(cfg)["registered"])
        cfg.write_text("{ non è JSON", encoding="utf-8")
        try:
            mcp_server.claude_desktop_install(cfg)
            refused = False
        except ValueError:
            refused = True
        mark("una configurazione che non si legge non viene toccata", refused and cfg.read_text(encoding="utf-8") == "{ non è JSON")
        fresh_cfg = folder / "nuovo" / "claude_desktop_config.json"
        fresh_cfg.parent.mkdir()
        s = mcp_server.snippets()
        mark("configurazione che non esiste ancora: creata; testi da incollare per le altre app", mcp_server.claude_desktop_install(fresh_cfg)
             and json.loads(fresh_cfg.read_text(encoding="utf-8"))["mcpServers"]["omissis"]["command"].lower().endswith("python.exe")
             and json.loads(s["json"])["mcpServers"]["omissis"]["args"] and "claude mcp add" in s["claude_code"] and "[mcp_servers.omissis]" in s["codex"])
    print(f"\n{'TUTTO OK' if all(outcomes) else 'ERRORI'}: {sum(outcomes)}/{len(outcomes)} controlli")
    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
