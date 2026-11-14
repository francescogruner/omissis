# -*- coding: utf-8 -*-
"""Prova ciò che tocca il desktop di Windows: scorciatoie da tastiera, testo selezionato sostituito sul posto, finestra
per scegliere una cartella.   Richiede la protezione attiva (serve il motore per mascherare).

  .venv\\Scripts\\python.exe e2e_desktop.py

Per la sostituzione sul posto apre per pochi secondi una sua finestrella con un testo inventato e manda i tasti SOLO se
quella finestra è davvero in primo piano: se Windows non glielo concede (schermo bloccato, un altro programma che tiene
il primo piano) quel controllo viene saltato, e detto. Gli appunti vengono rimessi com'erano.
"""
import ctypes
import os
import sys
import tempfile
import threading
import time

import clipboard
import documents
import folders

u32 = ctypes.WinDLL("user32")
u32.FindWindowW.restype = ctypes.c_void_p
u32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
u32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
u32.GetParent.restype = ctypes.c_void_p
u32.GetParent.argtypes = [ctypes.c_void_p]
u32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
u32.GetForegroundWindow.restype = ctypes.c_void_p
TEXT = "Scrivi a Giulia Ferraresi (giulia.ferraresi@nevatek.example, cell. 347 5551234) per confermare l'appuntamento."
outcomes, skipped = [], []


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(("OK    " if ok else "ERRORE ") + name + (f"   {note}" if note else ""))


def skip(name, reason):
    skipped.append(name)
    print(f"SALTATO {name}   ({reason})")


sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- combinazioni
mark("combinazioni: lette e scritte come sui tasti", clipboard.combo("ctrl+alt+m") == (3, ord("M")) and clipboard.combo("Ctrl + Alt + Shift + F22") == (7, 0x85)
      and clipboard.caption("ctrl+alt+m") == "Ctrl+Alt+M")
mark("combinazioni: rifiutate quelle senza Ctrl o Alt, vuote o con due lettere", all(clipboard.combo(x) is None for x in ("", "m", "shift+m", "ctrl+alt", "ctrl+a+b", "ctrl+è")))
mark("impostazioni: le scelte dell'utente sopra le predefinite, vuota = spenta",
      clipboard.choices({"shortcuts": {"mask": "CTRL+ALT+K", "restore": ""}}) == {"replace": "ctrl+alt+s", "mask": "ctrl+alt+k", "restore": ""})

# ---------------------------------------------------------------- scorciatoie registrate con Windows
pressed = []
one = clipboard.Shortcuts({"replace": lambda: pressed.append("replace"), "mask": lambda: pressed.append("mask"), "restore": lambda: pressed.append("restore")})
status = one.configure({"replace": "ctrl+alt+shift+f22", "mask": "ctrl+alt+shift+f21", "restore": ""})
mark("scorciatoie: registrate, quella vuota resta spenta", status["replace"]["active"] and status["mask"]["active"] and not status["restore"]["active"] and not status["restore"]["error"],
      str({k: v["active"] for k, v in status.items()}))
two = clipboard.Shortcuts({"mask": lambda: None})
busy = two.configure({"mask": "ctrl+alt+shift+f22"})
mark("scorciatoie: una combinazione già presa viene dichiarata occupata", not busy["mask"]["active"] and busy["mask"]["error"] == "busy")
mark("scorciatoie: una combinazione non valida viene dichiarata tale", two.configure({"mask": "ctrl+alt"})["mask"]["error"] == "not_valid")
two.stop()
clipboard.press(clipboard.VK_CONTROL, clipboard.VK_MENU, clipboard.VK_SHIFT, 0x85)   # Ctrl+Alt+Maiusc+F22: non la usa nessun programma
end = time.time() + 3
while not pressed and time.time() < end:
    time.sleep(0.05)
if pressed:
    mark("scorciatoie: premuta la combinazione, parte la sua azione (e solo quella)", pressed == ["replace"], str(pressed))
else:
    skip("scorciatoie: premuta la combinazione, parte la sua azione", "Windows non ha consegnato i tasti: schermo bloccato o sessione senza desktop")
status = one.configure({"replace": "", "mask": "ctrl+alt+shift+f22", "restore": ""})
mark("scorciatoie: cambiate senza riavviare", status["mask"]["active"] and not status["replace"]["active"])
# una lettera già presa da un altro programma (qui: da un'altra copia delle scorciatoie) viene sostituita con una libera
free = next((x for x in "qwpoly" if one.configure({"replace": f"ctrl+alt+{x}", "mask": "", "restore": ""})["replace"]["active"]), None)
if free is None:
    skip("scorciatoie: lettera occupata sostituita da una libera", "nessuna lettera di prova libera su questo PC")
else:
    three = clipboard.Shortcuts({"replace": lambda: None, "mask": lambda: None, "restore": lambda: None})
    in_use, changed = clipboard.system(three, {"replace": "", "mask": f"ctrl+alt+{free}", "restore": "ctrl+alt+shift+f20"})
    mark("scorciatoie: lettera occupata sostituita da una libera, le altre restano", list(changed) == ["mask"] and changed["mask"][0] == f"ctrl+alt+{free}"
          and in_use["mask"] != f"ctrl+alt+{free}" and three.status["mask"]["active"] and in_use["restore"] == "ctrl+alt+shift+f20" and in_use["replace"] == "",
          f"{clipboard.caption(changed.get('mask', ('', ''))[0])} → {clipboard.caption(in_use['mask'])}")
    three.stop()
one.stop()

# ---------------------------------------------------------------- testo selezionato, sul posto
before = clipboard.read()
if before is None and ctypes.windll.user32.CountClipboardFormats() > 0:
    skip("selezione sul posto", "negli appunti c'è qualcosa che non è testo: non lo cancello")
else:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title("Omissis: prova della selezione")
        root.attributes("-topmost", True)
        box = tk.Text(root, width=90, height=5)
        box.pack()
        box.insert("1.0", TEXT)
        root.update()
        win = u32.GetParent(root.winfo_id())
        clipboard.press(clipboard.VK_MENU)   # un tasto premuto da questo processo: Windows gli concede il primo piano
        u32.SetForegroundWindow(win)
        root.focus_force()
        box.focus_set()
        box.tag_add("sel", "1.0", "end-1c")
        for _ in range(20):
            root.update()
            time.sleep(0.05)
        if u32.GetForegroundWindow() != win:
            skip("selezione sul posto", "la finestra di prova non ha ottenuto il primo piano: nessun tasto inviato")
        else:
            outcome = {}
            thread = threading.Thread(target=lambda: outcome.update(m=clipboard.replace(documents.engine, only_window=win)))
            thread.start()
            while thread.is_alive():
                root.update()
                time.sleep(0.02)
            for _ in range(20):
                root.update()
                time.sleep(0.03)
            after = box.get("1.0", "end-1c")
            mark("selezione sul posto: il testo selezionato è stato sostituito dalla versione mascherata",
                  "[PERSONA_" in after and "[EMAIL_" in after and "Ferraresi" not in after and "347 5551234" not in after and after.startswith("Scrivi a "), outcome.get("m", ""))
            mark("selezione sul posto: negli appunti resta il testo mascherato, non l'originale", "Ferraresi" not in (clipboard.read() or "Ferraresi"))
            box.tag_remove("sel", "1.0", "end")
            box.delete("1.0", "end")
            box.insert("1.0", "Buongiorno, confermo la riunione di domani alle dieci.")
            box.tag_add("sel", "1.0", "end-1c")
            root.update()
            thread = threading.Thread(target=lambda: outcome.update(m=clipboard.replace(documents.engine, only_window=win)))
            thread.start()
            while thread.is_alive():
                root.update()
                time.sleep(0.02)
            mark("selezione sul posto: senza dati sensibili il testo resta com'era", box.get("1.0", "end-1c") == "Buongiorno, confermo la riunione di domani alle dieci.", outcome.get("m", ""))
        mark("selezione sul posto: in un'altra finestra non parte nulla",
              clipboard.replace(documents.engine, only_window=1) in (clipboard.i18n.t("clipboard.in_place.window_changed"), clipboard.i18n.t("clipboard.in_place.terminal"),
                                                                             clipboard.i18n.t("clipboard.in_place.keystrokes_pressed")))
        root.destroy()
    finally:
        if before is not None:
            clipboard.write(before)

# ---------------------------------------------------------------- finestra «Seleziona cartella»
def lap(keystroke, title, folder):
    outcome = {}
    thread = threading.Thread(target=lambda: outcome.update(r=folders.choose(title, folder, front=False)))
    thread.start()
    win = None
    for _ in range(100):
        win = u32.FindWindowW(None, title)
        if win:
            break
        time.sleep(0.1)
    if win:
        time.sleep(0.8)
        mark_double = folders.choose("x", front=False)   # mentre una è aperta, una seconda non si apre
        u32.PostMessageW(win, 0x0111, keystroke, 0)        # il pulsante di conferma (1) o Annulla (2)
    else:
        mark_double = "non provata"
    thread.join(15)
    return win, outcome.get("r"), mark_double, thread.is_alive()


with tempfile.TemporaryDirectory() as folder:
    win, choice, double, alive = lap(1, "Omissis: prova della cartella (conferma)", folder)
    if not win:
        skip("cartella: finestra di Windows", "la finestra non si è aperta: sessione senza desktop")
    else:
        mark("cartella: la finestra di Windows restituisce la cartella scelta", bool(choice) and os.path.samefile(choice, folder) and not alive, choice or "")
        mark("cartella: una finestra per volta", double is None)
        win, choice, _, alive = lap(2, "Omissis: prova della cartella (annulla)", folder)
        mark("cartella: annullando non restituisce nulla", choice == "" and not alive)
    mark("cartella: si aprono solo cartelle che esistono", folders.open_up(os.path.join(folder, "non-esiste")) is False)

print(f"\n{sum(outcomes)}/{len(outcomes)} controlli superati" + (f" · {len(skipped)} saltati" if skipped else ""))
sys.exit(0 if all(outcomes) else 1)
