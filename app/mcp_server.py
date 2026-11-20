# -*- coding: utf-8 -*-
"""Server MCP di Omissis: porta l'anonimizzazione dei documenti DENTRO le app che parlano MCP (Claude Desktop,
Claude Code, Codex, ChatGPT in modalita' sviluppatore, Cursor, Windsurf, Antigravity, VS Code...), usate come
sempre e con il proprio abbonamento. L'app lancia questo programma e gli parla sull'ingresso/uscita standard.

Che cosa fa: l'assistente, invece di leggere un documento, chiede a Omissis di leggerlo. Il file viene aperto su
questo PC, i dati personali sostituiti con i segnaposto ([PERSONA_1], [EMAIL_3]...) e all'assistente arriva solo il
testo gia' anonimizzato. Per riavere i valori veri l'assistente chiede il ripristino: Omissis scrive il risultato in
un file (o negli appunti) e all'assistente torna soltanto DOVE l'ha scritto, mai il contenuto.

Che cosa NON fa: non vede cio' che l'utente scrive nella chat ne' i file allegati a mano (quelli partono in chiaro,
a meno che l'app non sia protetta anche dal connettore o dall'estensione). E' un complemento, non un sostituto.

Garanzie tenute dal codice:
  - nessuno strumento restituisce mai un valore vero preso dall'archivio;
  - si leggono e si scrivono solo le cartelle permesse (di serie Documenti, Desktop e Download; altre con --folder
    o con OMISSIS_MCP_FOLDERS), mai la cartella dei dati di Omissis ne' quella del programma;
  - se il motore non risponde non esce nulla: errore, mai il testo in chiaro.

  python mcp_server.py [--folder <cartella> ...]       il server (lo lancia l'app)
  python mcp_server.py --config                         come registrarlo nelle varie app
  python mcp_server.py --install claude-desktop         lo scrive nella configurazione di Claude Desktop
  python mcp_server.py --uninstall claude-desktop       lo toglie

Solo libreria standard per il protocollo (JSON-RPC su righe, come vuole MCP).
"""
import ctypes
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

import paths
from version import VERSION

HERE = Path(__file__).resolve().parent
NAME = "omissis"
PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]   # versioni di MCP che questo server parla, dalla piu' recente
MAX_BYTES = 60_000_000
STORE_ALIAS = "omissis-python.exe"   # il nome fisso che il pacchetto del Microsoft Store da' all'interprete (vedi costruisci_store.py)
EMPTY = {"resources/list": "resources", "resources/templates/list": "resourceTemplates", "prompts/list": "prompts"}
INSTRUCTIONS = (
    "Omissis keeps personal data on the user's computer. When the user asks you to work on a document that may contain "
    "personal data (names, e-mail addresses, phone numbers, tax codes, IBANs, passwords, host names), call "
    "read_anonymized with its path instead of opening the file yourself: you receive the text with placeholders such as "
    "[PERSONA_1] or [EMAIL_3]. Keep every placeholder exactly as written in your answers and in the files you produce; "
    "the same placeholder always means the same value. Never ask the user for the real values and never try to guess "
    "them. When the user needs the real values back, call restore_text (for a text you wrote) or restore_copy (for a "
    "file): they write the result on the user's computer and return only its location. Do not open restored files.")
TOOLS = [
    {"name": "omissis_status",
     "title": "Omissis status",
     "description": "Tells whether Omissis is running on this computer and which folders this server may read. Call it first if another tool fails.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "read_anonymized",
     "title": "Read a document, anonymised",
     "description": ("Reads a document on the user's computer and returns its text with personal data replaced by placeholders "
                     "([PERSONA_1], [EMAIL_3]...). Use it INSTEAD of reading the file directly. Formats: Word, Excel, PowerPoint, PDF "
                     "(scans are read with OCR), images containing text, text files. Long documents come in pieces: call again with "
                     "the 'start' value given at the end of the result."),
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["path"], "properties": {
         "path": {"type": "string", "description": "Absolute path of the file."},
         "start": {"type": "integer", "minimum": 0, "description": "Character to start from (default 0)."},
         "max_chars": {"type": "integer", "minimum": 1000, "maximum": 200000, "description": "Maximum characters to return (default 40000)."}}},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "anonymize_copy",
     "title": "Write an anonymised copy",
     "description": ("Writes an anonymised copy of a file (name.anon.ext) or of a whole folder (folder.anon) next to the original, keeping "
                     "the format, and returns where it is. Use it when the user wants a file to attach or to share, or when you will "
                     "work on the files with your own tools: work on the copy, never on the original."),
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["path"], "properties": {
         "path": {"type": "string", "description": "Absolute path of the file or folder."}}},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "restore_copy",
     "title": "Write a copy with the real values",
     "description": ("Takes a file or folder that contains placeholders (for example a document you produced) and writes next to it a "
                     "copy with the real values put back (name.restored.ext). Returns only where the copy is: it contains the user's "
                     "real data, so do not open or read it, just tell the user where to find it."),
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["path"], "properties": {
         "path": {"type": "string", "description": "Absolute path of the file or folder with placeholders."}}},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}},
    {"name": "restore_text",
     "title": "Give the user a text with the real values",
     "description": ("Puts the real values back into a text that contains placeholders (for example your final answer, a letter, an "
                     "e-mail) and hands it to the user WITHOUT showing it to you: by default it is copied to the Windows clipboard, "
                     "ready to paste; with 'save_as' it is written to that new file. Returns only how many placeholders were restored."),
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["text"], "properties": {
         "text": {"type": "string", "description": "The text with placeholders."},
         "save_as": {"type": "string", "description": "Optional: absolute path of a NEW file to write instead of using the clipboard."}}},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}},
]


class Refusal(Exception):
    """Una richiesta che non si esegue: il messaggio va all'assistente (in inglese: lo legge il modello)."""


def say(*a):
    """Sull'uscita standard passa solo il protocollo: il resto va sull'uscita degli errori, e mai un testo dei documenti."""
    print("[omissis-mcp]", *a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------------------------- cartelle permesse

def _known_folders():
    """Documenti, Desktop e Download dell'utente, dove Windows li tiene davvero (anche se spostati su OneDrive)."""
    out = []
    if os.name == "nt":
        class GUID(ctypes.Structure):
            _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]
        for text in ("FDD39AD0-238F-46AF-ADB4-6C85480369C7", "B4BFCC3A-DB2C-424C-B029-7FE99A87C641", "374DE290-123F-4565-9164-39C4925E467B"):
            p = text.split("-")
            tail = bytes.fromhex(p[3] + p[4])
            guid, where = GUID(int(p[0], 16), int(p[1], 16), int(p[2], 16), (ctypes.c_ubyte * 8)(*tail)), ctypes.c_wchar_p()
            try:
                if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(where)) == 0 and where.value:
                    out.append(Path(where.value))
            finally:
                ctypes.windll.ole32.CoTaskMemFree(where)
    return out or [Path.home() / n for n in ("Documents", "Desktop", "Downloads")]


def folders(extra=()):
    """Le cartelle dentro cui si puo' leggere e scrivere. OMISSIS_MCP_FOLDERS (o --folder) sostituisce quelle di serie,
    che sono Documenti, Desktop e Download piu' quelle scritte nelle impostazioni (mcp_folders)."""
    chosen = [x for x in (os.environ.get("OMISSIS_MCP_FOLDERS") or "").split(os.pathsep) if x.strip()] + list(extra)
    out = []
    if not chosen:   # di serie: le tre cartelle dell'utente piu' quelle aggiunte nel pannello (Collegamenti > MCP)
        import settings
        chosen = [str(x) for x in _known_folders()] + [str(x) for x in settings.read().get("mcp_folders") or []]
    for f in [Path(x.strip().strip('"')) for x in chosen]:
        real = Path(os.path.realpath(f))
        if real.is_dir() and real not in out:
            out.append(real)
    return out


def _inside(p, folder):
    return p == folder or folder in p.parents


def allowed(raw, roots, exists=True):
    """Il percorso vero (collegamenti risolti), se sta in una cartella permessa. Altrimenti Refusal."""
    text = str(raw or "").strip().strip('"')
    if not text or not Path(text).is_absolute():
        raise Refusal("Give an absolute path: drive, folders and file name.")
    real = Path(os.path.realpath(os.path.expandvars(text)))
    banned = [Path(os.path.realpath(x)) for x in (paths.DATA, HERE, paths.model_folder())]
    if any(_inside(real, b) for b in banned) or not any(_inside(real, r) for r in roots):
        raise Refusal("That path is outside the folders Omissis may use from here: " + "; ".join(str(r) for r in roots)
                      + ". Ask the user to move the file into one of them, or to add its folder in the Omissis panel (Connections > MCP).")
    if exists and not real.exists():
        raise Refusal("There is no file or folder at that path.")
    return real


# ---------------------------------------------------------------------------------------------- testo dei documenti

def _office_text(name, data):
    """Il testo di un documento Office, letto qui sul PC. E' ancora IN CHIARO: chi lo chiama lo passa subito al motore."""
    est = Path(name).suffix.lower()
    if est == ".docx":
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        d, out = docx.Document(io.BytesIO(data)), []
        for child in d.element.body.iterchildren():
            if child.tag.endswith("}p"):
                out.append(Paragraph(child, d).text)
            elif child.tag.endswith("}tbl"):
                out += [" | ".join(c.text.strip() for c in row.cells) for row in Table(child, d).rows]
        margins = []
        for s in d.sections:
            for part in (s.header, s.footer):
                t = "\n".join(p.text for p in part.paragraphs if p.text.strip())
                if t and t not in margins:
                    margins.append(t)
        return "\n".join(margins + out)
    if est == ".xlsx":
        import openpyxl
        book, out = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True), []
        for sheet in book.worksheets:
            out.append(f"=== {sheet.title} ===")
            for row in sheet.iter_rows(values_only=True):
                if any(v is not None and str(v).strip() for v in row):
                    out.append("\t".join("" if v is None else str(v) for v in row).rstrip("\t"))
        return "\n".join(out)
    from pptx import Presentation
    out = []
    for i, slide in enumerate(Presentation(io.BytesIO(data)).slides, 1):
        out.append(f"--- slide {i} ---")
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                out.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                out += [" | ".join(c.text.strip() for c in row.cells) for row in shape.table.rows]
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None and slide.notes_slide.notes_text_frame.text.strip():
            out.append("[notes] " + slide.notes_slide.notes_text_frame.text)
    return "\n".join(out)


def anonymized_text(name, data):
    """(testo con i segnaposto, conteggi) di un documento. Solleva documents.Error se non si puo' leggere o se il motore e' fermo."""
    import documents
    est = Path(name).suffix.lower()
    if est in documents.OFFICE:
        try:
            plain = _office_text(name, data)
        except Exception as ex:   # noqa: BLE001  (file rovinato o protetto da password)
            raise documents.Error("the document cannot be opened (damaged or password-protected)") from ex
        work = documents.Work("anonymize")
        return work.text(plain), work.counts
    if est in documents.TEXT:
        try:
            plain = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            plain = data.decode("cp1252", errors="replace")
        work = documents.Work("anonymize")
        return work.text(plain), work.counts
    _, fresh, counts = documents.work_on(name, data, "anonymize")   # PDF e immagini: ne esce testo in UTF-8
    return fresh.decode("utf-8", errors="replace"), counts


# ---------------------------------------------------------------------------------------------- gli strumenti

class Server:
    def __init__(self, extra_folders=()):
        self.roots = folders(extra_folders)
        self.client = ""
        self.read = {}      # (percorso, modificato, dimensione) -> (testo anonimizzato, conteggi): per dare i documenti lunghi a pezzi
        self.log = None

    def record(self, tool, counts):
        """Una riga nel registro del programma: solo conteggi, come per le altre strade."""
        try:
            import activity
            self.log = self.log or activity.Log()
            self.log.write(service="mcp", via="mcp", method="document", client=self.client[:60], path=tool, event="masked" if tool != "restore" else "response_restored",
                           replacements={k: v for k, v in counts.items() if isinstance(v, int) and k.isupper()}, restored=counts.get("restored", 0))
        except Exception as ex:   # noqa: BLE001  (il registro non deve mai fermare il lavoro)
            say("registro non scritto:", type(ex).__name__)

    @staticmethod
    def _counts(counts):
        data = {k: v for k, v in counts.items() if k.isupper()}
        return ", ".join(f"{k} {v}" for k, v in sorted(data.items(), key=lambda x: -x[1])) or "none"

    def omissis_status(self, a):
        import documents
        token = paths.DATA / "token.txt"
        import urllib.request
        req = urllib.request.Request(documents.ENGINE + "/status", headers={"X-Token": token.read_text(encoding="utf-8").strip()})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                s = json.loads(r.read().decode("utf-8"))
        except OSError as ex:
            raise Refusal("Omissis is not running: ask the user to start it (Omissis icon, or the panel) and try again. Nothing was read.") from ex
        return (f"Omissis {VERSION} is running (model {Path(str(s.get('model'))).name} on {s.get('device')}). "
                f"Folders this server may use: {'; '.join(str(r) for r in self.roots) or 'none'}.")

    def read_anonymized(self, a):
        p = allowed(a.get("path"), self.roots)
        if not p.is_file():
            raise Refusal("That is a folder: give the path of one file, or use anonymize_copy for the whole folder.")
        st = p.stat()
        if st.st_size > MAX_BYTES:
            raise Refusal("The file is larger than 60 MB.")
        key = (str(p), st.st_mtime_ns, st.st_size)
        if key not in self.read:
            text, counts = anonymized_text(p.name, p.read_bytes())
            if len(self.read) >= 8:
                self.read.pop(next(iter(self.read)))
            self.read[key] = (text, counts)
            self.record("read_anonymized", counts)
        text, counts = self.read[key]
        start = max(0, int(a.get("start") or 0))
        size = min(200000, max(1000, int(a.get("max_chars") or 40000)))
        piece, end = text[start:start + size], min(len(text), start + size)
        note = f"[Omissis: values replaced: {self._counts(counts)}. Characters {start}-{end} of {len(text)}."
        note += f" More text follows: call read_anonymized again with start={end}.]" if end < len(text) else " End of document.]"
        if counts.get("pages_read"):
            note += f" [{counts['pages_read']} page(s) were read from images with OCR: some characters may be misread.]"
        return piece + "\n\n" + note

    def _copy(self, a, action):
        import documents
        p = allowed(a.get("path"), self.roots)
        suffix = ".anon" if action == "anonymize" else ".restored"
        target = p.parent / (documents.output_name(p.name, action) if p.is_file() else (p.name.removesuffix(".anon") if action == "restore" else p.name) + suffix)
        allowed(str(target), self.roots, exists=False)
        r = documents.path(str(p), action)
        self.record(action, r["counts"])
        lines = [f"{len(r['completed'])} file(s) written to: {r['destination']}"]
        if action == "anonymize":
            lines.append(f"Values replaced: {self._counts(r['counts'])}.")
            lines += [f"  {f['file']} -> {f['output']}" for f in r["completed"][:40]]
        else:
            lines.append(f"Placeholders restored: {r['counts'].get('restored', 0)}; unknown to this computer: {r['counts'].get('unknown', 0)}.")
            lines.append("The copy contains the user's real data: do not open it, tell the user where it is.")
        if r["skipped"]:
            lines.append(f"{len(r['skipped'])} file(s) skipped (not copied): " + "; ".join(f"{f['file']}: {f['reason']}" for f in r["skipped"][:20]))
        return "\n".join(lines)

    def anonymize_copy(self, a):
        return self._copy(a, "anonymize")

    def restore_copy(self, a):
        return self._copy(a, "restore")

    def restore_text(self, a):
        import documents
        text = str(a.get("text") or "")
        if not text.strip():
            raise Refusal("The text is empty.")
        work = documents.Work("restore")
        restored = work.text(text)
        done, unknown = work.counts.get("restored", 0), work.counts.get("unknown", 0)
        if not done:
            raise Refusal("No placeholder known to this computer was found in the text, so nothing was written." if unknown or "[" in text
                          else "The text contains no placeholders: there is nothing to restore.")
        if a.get("save_as"):
            target = allowed(a["save_as"], self.roots, exists=False)
            if target.exists():
                raise Refusal("A file with that name already exists: choose a new name.")
            if not target.parent.is_dir():
                raise Refusal("The folder of 'save_as' does not exist.")
            target.write_text(restored, encoding="utf-8")
            where = f"written to {target}. Do not open it: tell the user where it is"
        else:
            import clipboard
            if not clipboard.write(restored):
                raise Refusal("The clipboard is busy: try again, or pass 'save_as' with the path of a new file.")
            where = "copied to the user's clipboard: tell the user to paste it with Ctrl+V"
        self.record("restore", work.counts)
        return f"{done} placeholder(s) restored" + (f", {unknown} unknown left as they were" if unknown else "") + f"; the text with the real values was {where}."

    def call(self, name, arguments):
        """(testo, errore?) per tools/call. Qualunque intoppo diventa un messaggio, mai un testo in chiaro."""
        import documents
        if name not in {t["name"] for t in TOOLS}:
            return f"Unknown tool: {name}", True
        if not (paths.DATA / "token.txt").exists():
            return "Omissis has never been started on this computer: ask the user to start it. Nothing was read.", True
        try:
            return getattr(self, name)(arguments if isinstance(arguments, dict) else {}), False
        except Refusal as ex:
            return str(ex), True
        except documents.Error as ex:
            if ex.code == "protection":
                return "Omissis is not running: ask the user to start it (Omissis icon, or the panel) and try again. Nothing was read.", True
            return f"Omissis could not process it: {ex}", True
        except Exception as ex:   # noqa: BLE001
            say("errore in", name, type(ex).__name__)
            return f"Omissis failed ({type(ex).__name__}). Nothing was returned.", True

    # ------------------------------------------------------------------------------------------ protocollo

    def answer(self, msg):
        """La risposta a un messaggio JSON-RPC, oppure None se e' una notifica."""
        method, ident = msg.get("method"), msg.get("id")
        if ident is None or method is None:   # notifica, oppure risposta a una richiesta nostra (non ne facciamo)
            return None
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if method == "initialize":
            wanted = params.get("protocolVersion")
            self.client = " ".join(str(x) for x in ((params.get("clientInfo") or {}).get("name"), (params.get("clientInfo") or {}).get("version")) if x)
            result = {"protocolVersion": wanted if wanted in PROTOCOLS else PROTOCOLS[0], "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": NAME, "title": "Omissis", "version": VERSION}, "instructions": INSTRUCTIONS}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            text, failed = self.call(params.get("name"), params.get("arguments"))
            result = {"content": [{"type": "text", "text": text}], "isError": failed}
        elif method in EMPTY:   # non li dichiariamo, ma qualche app li chiede lo stesso
            result = {EMPTY[method]: []}
        else:
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    def serve(self, source=None, sink=None):
        source, sink = source or sys.stdin.buffer, sink or sys.stdout.buffer
        say(f"avviato · cartelle: {'; '.join(str(r) for r in self.roots) or 'nessuna'}")
        while True:
            line = source.readline()
            if not line:
                return
            if not line.strip():
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except ValueError:
                answers = [{"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}]
            else:
                answers = [r for m in (msg if isinstance(msg, list) else [msg]) if isinstance(m, dict) and (r := self.answer(m)) is not None]
            for r in answers:
                sink.write(json.dumps(r, ensure_ascii=False).encode("utf-8") + b"\n")
                sink.flush()


# ---------------------------------------------------------------------------------------------- registrazione nelle app

def command():
    """Il comando con cui un'app lancia questo server: l'interprete con la finestra di testo (serve l'uscita standard)."""
    if (paths.INSTALLED or {}).get("channel") == "store":
        # La copia arrivata dal Microsoft Store sta in una cartella di sistema il cui nome cambia a ogni versione. Windows
        # le da' un nome fisso da chiamare da fuori (lo dichiara il pacchetto): il programma parte dentro il pacchetto,
        # quindi vede gli stessi dati del pannello, e il modulo si trova da solo senza scriverne il percorso.
        return str(Path(os.environ.get("LOCALAPPDATA") or "") / "Microsoft" / "WindowsApps" / STORE_ALIAS), ["-m", "mcp_server"]
    py = Path(sys.executable)
    # il pannello gira con un interprete senza finestra (pythonw.exe; nella copia installata si chiama Omissis.exe), che non
    # ha ingresso e uscita standard: per il server serve quello normale, che gli sta accanto
    if py.name.lower() != "python.exe" and py.with_name("python.exe").exists():
        py = py.with_name("python.exe")
    return str(py), [str(HERE / "mcp_server.py")]


def snippets():
    """Che cosa incollare, app per app."""
    cmd, args = command()
    entry = {"command": cmd, "args": args}
    toml = lambda s: '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'   # noqa: E731
    return {"json": json.dumps({"mcpServers": {NAME: entry}}, indent=2),
            "claude_code": f'claude mcp add --scope user {NAME} -- "{cmd}" ' + " ".join(f'"{x}"' for x in args),
            "codex": f"[mcp_servers.{NAME}]\ncommand = {toml(cmd)}\nargs = [{', '.join(toml(x) for x in args)}]"}


def claude_desktop_file():
    """Dove Claude Desktop tiene la configurazione: nella copia arrivata dallo Store sta dentro la cartella del pacchetto."""
    if sys.platform == "darwin":
        folder = Path.home() / "Library" / "Application Support" / "Claude"
        return folder / "claude_desktop_config.json" if folder.is_dir() else None
    local, roaming = Path(os.environ.get("LOCALAPPDATA") or ""), Path(os.environ.get("APPDATA") or "")
    packaged = sorted(local.glob("Packages/*Claude_*/LocalCache/Roaming/Claude")) if str(local) not in ("", ".") else []
    # Una copia di Omissis arrivata dal Microsoft Store scrive nelle cartelle dei dati dell'utente solo in una copia
    # privata: la configurazione di un Claude Desktop installato alla vecchia maniera non la raggiungerebbe (vedi by_hand).
    usable = packaged if (paths.INSTALLED or {}).get("channel") == "store" else [*packaged, roaming / "Claude"]
    for folder in usable:
        if folder.is_dir():
            return folder / "claude_desktop_config.json"
    return None


def claude_desktop_by_hand():
    """Claude Desktop c'e', ma da questa copia di Omissis (Microsoft Store) la sua configurazione non si puo' scrivere:
    le righe vanno incollate a mano."""
    roaming = Path(os.environ.get("APPDATA") or "")
    return (paths.INSTALLED or {}).get("channel") == "store" and claude_desktop_file() is None and str(roaming) not in ("", ".") \
        and (roaming / "Claude").is_dir()


def _read_config(file):
    if not file.exists() or not file.read_text(encoding="utf-8-sig").strip():
        return {}
    data = json.loads(file.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        raise ValueError("forma inattesa")
    return data


def claude_desktop_state(file=None):
    """{"installed": l'app c'e', "registered": Omissis e' nella sua configurazione, "current": e punta a questa copia}."""
    file = file or claude_desktop_file()
    if file is None:
        return {"installed": False, "registered": False, "current": False, "by_hand": claude_desktop_by_hand()}
    try:
        entry = _read_config(file).get("mcpServers", {}).get(NAME)
    except (OSError, ValueError):
        entry = None
    cmd, args = command()
    return {"installed": True, "registered": entry is not None, "by_hand": False,
            "current": isinstance(entry, dict) and entry.get("command") == cmd and entry.get("args") == args}


def claude_desktop_install(file=None, remove=False):
    """Aggiunge (o toglie) Omissis tra i server MCP di Claude Desktop, senza toccare il resto. Prima di cambiare un file
    esistente ne tiene una copia accanto (.omissis-backup). Un file che non si legge non viene toccato: ValueError."""
    file = file or claude_desktop_file()
    if file is None:
        raise ValueError("Claude Desktop non è installato")
    data = _read_config(file)   # ValueError se non e' JSON valido: meglio fermarsi che rovinare la configurazione dell'utente
    servers = data.setdefault("mcpServers", {})
    if remove:
        if NAME not in servers:
            return False
        del servers[NAME]
        if not servers:
            del data["mcpServers"]
    else:
        cmd, args = command()
        if servers.get(NAME) == {"command": cmd, "args": args}:
            return False
        servers[NAME] = {"command": cmd, "args": args}
    if file.exists():
        shutil.copy2(file, file.with_name(file.name + ".omissis-backup"))
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--config"]:
        sys.stdout.reconfigure(encoding="utf-8")
        s = snippets()
        print("Claude Desktop, Cursor, Windsurf, Antigravity, VS Code (file di configurazione MCP):\n" + s["json"])
        print("\nClaude Code:\n" + s["claude_code"])
        print("\nCodex (~/.codex/config.toml):\n" + s["codex"])
    elif a[:1] in (["--install"], ["--uninstall"]) and a[1:] == ["claude-desktop"]:
        sys.stdout.reconfigure(encoding="utf-8")
        try:
            changed = claude_desktop_install(remove=a[0] == "--uninstall")
        except (OSError, ValueError) as ex:
            sys.exit(f"non fatto: {ex}")
        print(("fatto" if changed else "era già così") + f": {claude_desktop_file()} · chiudi del tutto e riapri Claude Desktop")
    else:
        extra = [a[i + 1] for i, x in enumerate(a[:-1]) if x == "--folder"]
        started = time.time()
        try:
            Server(extra).serve()
        except KeyboardInterrupt:
            pass
        say(f"chiuso dopo {time.time() - started:.0f} s")
