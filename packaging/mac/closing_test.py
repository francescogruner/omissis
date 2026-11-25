# -*- coding: utf-8 -*-
"""Con la copia di prova accesa (vedi ci_tests.sh), sui processi veri: il motore e poi il proxy vengono sospesi (vivi, ma
non rispondono piu') e si guarda che il pannello se ne accorga e li rimetta in piedi; poi il pannello viene chiuso di
colpo, come in un guasto, e si guarda che il motore e il proxy si chiudano da soli invece di restare accesi a tenere le
porte. Vale per Mac e Linux; va lanciata per ultima, perche' dopo la copia di prova non c'e' piu'. Dura circa tre minuti.

   Uso: python3 packaging/mac/closing_test.py      (legge OMISSIS_PORT e OMISSIS_DATA, come le altre prove)
"""
import json
import os
import socket
import sys
import time
from pathlib import Path

import psutil

BASE = int(os.environ.get("OMISSIS_PORT") or 8765)   # il motore; il pannello e' sulla porta dopo
outcomes = []


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(f"{'OK    ' if ok else 'ERRORE'} {name}{'   ' + str(note) if note else ''}", flush=True)


def answers(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def listeners(port):
    """I processi di questo utente che ascoltano sulla porta."""
    found = []
    for p in psutil.process_iter(["pid"]):
        try:
            if any(c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port for c in p.net_connections(kind="tcp")):
                found.append(p)
        except psutil.Error:
            continue
    return found


def recovers(name, port, other, seconds=160):
    """Sospende chi ascolta sulla porta: entro il tempo dato ci deve essere un processo nuovo, e sull'altra porta quello di prima."""
    before, beside = listeners(port), {p.pid for p in listeners(other)}
    for p in before:
        p.suspend()
    begun, fresh = time.time(), []
    while time.time() - begun < seconds and not fresh:
        time.sleep(1)
        fresh = [p for p in listeners(port) if p.pid not in {x.pid for x in before}]
    took = time.time() - begun
    for p in before:   # se nessuno l'avesse chiuso, non resti li' sospeso
        try:
            p.kill()
        except psutil.Error:
            pass
    time.sleep(3)
    mark(f"{name} vivo ma sospeso: il pannello lo chiude e ne avvia uno nuovo, l'altro processo resta quello di prima",
         bool(before) and bool(fresh) and answers(port) and {p.pid for p in listeners(other)} == beside,
         f"dopo {took:.0f} s · prima {[p.pid for p in before]} · ora {[p.pid for p in fresh]}")


def main():
    try:
        proxy = int(json.loads((Path(os.environ["OMISSIS_DATA"]) / "settings.json").read_text(encoding="utf-8")).get("port") or 8080)
    except (OSError, ValueError, KeyError):
        proxy = 8080
    print(f"porte: motore {BASE}, pannello {BASE + 1}, proxy {proxy}")
    mark("prima: motore, pannello e proxy rispondono", answers(BASE) and answers(BASE + 1) and answers(proxy),
         (answers(BASE), answers(BASE + 1), answers(proxy)))
    panel = listeners(BASE + 1)
    others = {p.pid for p in listeners(BASE) + listeners(proxy)}
    mark("il pannello e' un processo a parte da motore e proxy", len(panel) == 1 and panel[0].pid not in others and len(others) >= 2,
         ([p.pid for p in panel], sorted(others)))
    recovers("motore", BASE, proxy)
    recovers("proxy", proxy, BASE)
    for p in panel:
        try:
            p.kill()   # di colpo: nessuna occasione di fermare gli altri due
        except psutil.Error:
            pass
    waited = 0.0
    while waited < 20 and (answers(BASE) or answers(proxy)):
        time.sleep(0.5)
        waited += 0.5
    mark("pannello chiuso di colpo: motore e proxy si chiudono da soli", not answers(BASE) and not answers(proxy),
         f"dopo {waited:.1f} s · motore risponde {answers(BASE)} · proxy risponde {answers(proxy)}")
    print(f"\n{'TUTTO OK' if all(outcomes) else 'ERRORI'}: {sum(outcomes)}/{len(outcomes)}")
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
