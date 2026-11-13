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
TESTO = "Scrivi a Giulia Ferraresi (giulia.ferraresi@nevatek.example, cell. 347 5551234) per confermare l'appuntamento."
esiti, saltati = [], []


def segna(nome, ok, nota=""):
    esiti.append(bool(ok))
    print(("OK    " if ok else "ERRORE ") + nome + (f"   {nota}" if nota else ""))


def salta(nome, motivo):
    saltati.append(nome)
    print(f"SALTATO {nome}   ({motivo})")


sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- combinazioni
segna("combinazioni: lette e scritte come sui tasti", clipboard.combinazione("ctrl+alt+m") == (3, ord("M")) and clipboard.combinazione("Ctrl + Alt + Shift + F22") == (7, 0x85)
      and clipboard.scritta("ctrl+alt+m") == "Ctrl+Alt+M")
segna("combinazioni: rifiutate quelle senza Ctrl o Alt, vuote o con due lettere", all(clipboard.combinazione(x) is None for x in ("", "m", "shift+m", "ctrl+alt", "ctrl+a+b", "ctrl+è")))
segna("impostazioni: le scelte dell'utente sopra le predefinite, vuota = spenta",
      clipboard.scelte({"scorciatoie": {"maschera": "CTRL+ALT+K", "ripristina": ""}}) == {"sostituisci": "ctrl+alt+s", "maschera": "ctrl+alt+k", "ripristina": ""})

# ---------------------------------------------------------------- scorciatoie registrate con Windows
premute = []
uno = clipboard.Scorciatoie({"sostituisci": lambda: premute.append("sostituisci"), "maschera": lambda: premute.append("maschera"), "ripristina": lambda: premute.append("ripristina")})
stato = uno.imposta({"sostituisci": "ctrl+alt+shift+f22", "maschera": "ctrl+alt+shift+f21", "ripristina": ""})
segna("scorciatoie: registrate, quella vuota resta spenta", stato["sostituisci"]["attiva"] and stato["maschera"]["attiva"] and not stato["ripristina"]["attiva"] and not stato["ripristina"]["errore"],
      str({k: v["attiva"] for k, v in stato.items()}))
due = clipboard.Scorciatoie({"maschera": lambda: None})
occupata = due.imposta({"maschera": "ctrl+alt+shift+f22"})
segna("scorciatoie: una combinazione già presa viene dichiarata occupata", not occupata["maschera"]["attiva"] and occupata["maschera"]["errore"] == "occupata")
segna("scorciatoie: una combinazione non valida viene dichiarata tale", due.imposta({"maschera": "ctrl+alt"})["maschera"]["errore"] == "non_valida")
due.ferma()
clipboard.premi(clipboard.VK_CONTROL, clipboard.VK_MENU, clipboard.VK_SHIFT, 0x85)   # Ctrl+Alt+Maiusc+F22: non la usa nessun programma
fine = time.time() + 3
while not premute and time.time() < fine:
    time.sleep(0.05)
if premute:
    segna("scorciatoie: premuta la combinazione, parte la sua azione (e solo quella)", premute == ["sostituisci"], str(premute))
else:
    salta("scorciatoie: premuta la combinazione, parte la sua azione", "Windows non ha consegnato i tasti: schermo bloccato o sessione senza desktop")
stato = uno.imposta({"sostituisci": "", "maschera": "ctrl+alt+shift+f22", "ripristina": ""})
segna("scorciatoie: cambiate senza riavviare", stato["maschera"]["attiva"] and not stato["sostituisci"]["attiva"])
uno.ferma()

# ---------------------------------------------------------------- testo selezionato, sul posto
prima = clipboard.leggi()
if prima is None and ctypes.windll.user32.CountClipboardFormats() > 0:
    salta("selezione sul posto", "negli appunti c'è qualcosa che non è testo: non lo cancello")
else:
    try:
        import tkinter as tk
        radice = tk.Tk()
        radice.title("Omissis: prova della selezione")
        radice.attributes("-topmost", True)
        casella = tk.Text(radice, width=90, height=5)
        casella.pack()
        casella.insert("1.0", TESTO)
        radice.update()
        finestra = u32.GetParent(radice.winfo_id())
        clipboard.premi(clipboard.VK_MENU)   # un tasto premuto da questo processo: Windows gli concede il primo piano
        u32.SetForegroundWindow(finestra)
        radice.focus_force()
        casella.focus_set()
        casella.tag_add("sel", "1.0", "end-1c")
        for _ in range(20):
            radice.update()
            time.sleep(0.05)
        if u32.GetForegroundWindow() != finestra:
            salta("selezione sul posto", "la finestra di prova non ha ottenuto il primo piano: nessun tasto inviato")
        else:
            esito = {}
            filo = threading.Thread(target=lambda: esito.update(m=clipboard.sostituisci(documents.motore, solo_finestra=finestra)))
            filo.start()
            while filo.is_alive():
                radice.update()
                time.sleep(0.02)
            for _ in range(20):
                radice.update()
                time.sleep(0.03)
            dopo = casella.get("1.0", "end-1c")
            segna("selezione sul posto: il testo selezionato è stato sostituito dalla versione mascherata",
                  "[PERSONA_" in dopo and "[EMAIL_" in dopo and "Ferraresi" not in dopo and "347 5551234" not in dopo and dopo.startswith("Scrivi a "), esito.get("m", ""))
            segna("selezione sul posto: negli appunti resta il testo mascherato, non l'originale", "Ferraresi" not in (clipboard.leggi() or "Ferraresi"))
            casella.tag_remove("sel", "1.0", "end")
            casella.delete("1.0", "end")
            casella.insert("1.0", "Buongiorno, confermo la riunione di domani alle dieci.")
            casella.tag_add("sel", "1.0", "end-1c")
            radice.update()
            filo = threading.Thread(target=lambda: esito.update(m=clipboard.sostituisci(documents.motore, solo_finestra=finestra)))
            filo.start()
            while filo.is_alive():
                radice.update()
                time.sleep(0.02)
            segna("selezione sul posto: senza dati sensibili il testo resta com'era", casella.get("1.0", "end-1c") == "Buongiorno, confermo la riunione di domani alle dieci.", esito.get("m", ""))
        segna("selezione sul posto: in un'altra finestra non parte nulla",
              clipboard.sostituisci(documents.motore, solo_finestra=1) in (clipboard.i18n.t("appunti.sul_posto.finestra_cambiata"), clipboard.i18n.t("appunti.sul_posto.terminale"),
                                                                             clipboard.i18n.t("appunti.sul_posto.tasti_premuti")))
        radice.destroy()
    finally:
        if prima is not None:
            clipboard.scrivi(prima)

# ---------------------------------------------------------------- finestra «Seleziona cartella»
def giro(tasto, titolo, cartella):
    esito = {}
    filo = threading.Thread(target=lambda: esito.update(r=folders.scegli(titolo, cartella, davanti=False)))
    filo.start()
    finestra = None
    for _ in range(100):
        finestra = u32.FindWindowW(None, titolo)
        if finestra:
            break
        time.sleep(0.1)
    if finestra:
        time.sleep(0.8)
        segna_doppia = folders.scegli("x", davanti=False)   # mentre una è aperta, una seconda non si apre
        u32.PostMessageW(finestra, 0x0111, tasto, 0)        # il pulsante di conferma (1) o Annulla (2)
    else:
        segna_doppia = "non provata"
    filo.join(15)
    return finestra, esito.get("r"), segna_doppia, filo.is_alive()


with tempfile.TemporaryDirectory() as cartella:
    finestra, scelta, doppia, viva = giro(1, "Omissis: prova della cartella (conferma)", cartella)
    if not finestra:
        salta("cartella: finestra di Windows", "la finestra non si è aperta: sessione senza desktop")
    else:
        segna("cartella: la finestra di Windows restituisce la cartella scelta", bool(scelta) and os.path.samefile(scelta, cartella) and not viva, scelta or "")
        segna("cartella: una finestra per volta", doppia is None)
        finestra, scelta, _, viva = giro(2, "Omissis: prova della cartella (annulla)", cartella)
        segna("cartella: annullando non restituisce nulla", scelta == "" and not viva)
    segna("cartella: si aprono solo cartelle che esistono", folders.apri(os.path.join(cartella, "non-esiste")) is False)

print(f"\n{sum(esiti)}/{len(esiti)} controlli superati" + (f" · {len(saltati)} saltati" if saltati else ""))
sys.exit(0 if all(esiti) else 1)
