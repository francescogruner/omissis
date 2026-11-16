# -*- coding: utf-8 -*-
"""Il comando «omissis-hook»: cio' che i plugin di Omissis per le app AI chiamano prima di mandare un messaggio.

I plugin stanno in un repository pubblico e sono uguali per tutti: non possono sapere dove sta Omissis su un PC. Per
questo chiamano un comando dal nome fisso, «omissis-hook kimi» (o claude, codex, gemini), e Omissis mette quel comando
in una sua cartella, aggiunta al PATH di chi usa il PC. Senza Omissis il comando non esiste, e il plugin non fa nulla.

La cartella (dati di Omissis, sottocartella bin) contiene due file che fanno la stessa cosa, perche' ogni app lancia i
suoi hook con una shell diversa:
  omissis-hook.cmd   per cmd e PowerShell (Kimi, Cursor, Claude Code senza Git Bash)
  omissis-hook       per bash (Claude Code con Git Bash)
Tutti e due chiamano ai_hook.py con il Python di Omissis, dicendogli dove sono i dati e su che porta ascolta il motore.

Il PATH toccato e' solo quello dell'utente (HKCU\\Environment), mai quello del sistema, e solo quando chi usa il PC lo
chiede dal pannello. Le app gia' aperte lo vedono dopo essere state chiuse e riaperte. Nelle prove (OMISSIS_TEST) il
registro di Windows non viene toccato: al suo posto c'e' un file tra i dati di prova.
"""
import ctypes
import os
import sys
from pathlib import Path

import i18n
import paths

HOOK = paths.HERE / "ai_hook.py"
NAME = "omissis-hook"


def folder():
    return paths.DATA / "bin"


def _python():
    """L'interprete con cui gira Omissis, nella sua forma con la console (serve l'errore standard)."""
    exe = Path(sys.executable)
    plain = exe.with_name("python.exe")
    return plain if exe.name.lower() == "pythonw.exe" and plain.exists() else exe


def _files():
    """Il contenuto dei due file: lo stesso comando, scritto per cmd/PowerShell e per bash."""
    python, data, port, language = _python(), paths.DATA, paths.ENGINE_PORT, i18n.active()
    windows = f'"{python}" "{HOOK}" --data "{data}" --port {port} --language {language} %*'
    # un percorso con lettere accentate va letto in UTF-8, altrimenti cmd lo storpia
    page = "" if all(ord(c) < 128 for c in windows) else "chcp 65001 >nul\r\n"
    return {NAME + ".cmd": ("@echo off\r\n" + page + windows + "\r\n").encode("utf-8"),
            NAME: (f'#!/bin/sh\nexec "{python.as_posix()}" "{HOOK.as_posix()}" --data "{data.as_posix()}" --port {port} --language {language} "$@"\n').encode("utf-8")}


def write():
    folder().mkdir(parents=True, exist_ok=True)
    for name, content in _files().items():
        (folder() / name).write_bytes(content)


def ready():
    try:
        return all((folder() / name).read_bytes() == content for name, content in _files().items())
    except OSError:
        return False


# ---- il PATH dell'utente
def _test_note():
    return paths.DATA / "bin" / "path-di-prova.txt"


def _read_path():
    """(valore, tipo) del PATH dell'utente nel registro di Windows."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        try:
            return winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return "", winreg.REG_EXPAND_SZ


def _write_path(value, kind):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "Path", 0, kind, value)
    # dice a Windows che l'ambiente e' cambiato: i programmi aperti DOPO lo vedono subito
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 3000, None)


def _same(a, b):
    return os.path.normcase(os.path.normpath(os.path.expandvars(a.strip().strip('"')))) == os.path.normcase(os.path.normpath(str(b)))


def on_path():
    if os.environ.get("OMISSIS_TEST") == "1":
        return _test_note().exists()
    if os.name != "nt":
        return False
    try:
        return any(_same(p, folder()) for p in _read_path()[0].split(";") if p.strip())
    except OSError:
        return False


def install():
    """Scrive i due file e mette la cartella nel PATH dell'utente. Rifarlo non cambia nulla."""
    write()
    if os.environ.get("OMISSIS_TEST") == "1":
        _test_note().write_text(str(folder()), encoding="utf-8")
    elif os.name == "nt" and not on_path():
        value, kind = _read_path()
        _write_path(";".join([p for p in value.split(";") if p.strip()] + [str(folder())]), kind)
    return state()


def remove():
    """Toglie la cartella dal PATH dell'utente e cancella i due file: i plugin, da quel momento, non fanno piu' nulla."""
    if os.environ.get("OMISSIS_TEST") == "1":
        _test_note().unlink(missing_ok=True)
    elif os.name == "nt" and on_path():
        value, kind = _read_path()
        _write_path(";".join(p for p in value.split(";") if p.strip() and not _same(p, folder())), kind)
    for name in _files():
        (folder() / name).unlink(missing_ok=True)
    return state()


def state():
    return {"ready": ready(), "on_path": on_path(), "folder": str(folder())}
