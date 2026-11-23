# -*- coding: utf-8 -*-
"""La segnalazione di un problema: che cosa non ha funzionato, con quale programma e con quale versione.

Le app e i siti protetti cambiano da soli (un aggiornamento dell'app, un formato nuovo): quando un messaggio non viene
letto il pannello lo dice e offre «Segnala il problema». Questo modulo prepara il testo; il pannello lo mostra per
intero; parte solo se chi usa il computer lo invia (su GitHub, oppure copiato dove vuole). Omissis da solo non manda
nulla a nessuno.

Dentro ci sono solo versioni, nomi dei programmi, conteggi e la FORMA delle richieste non lette (nomi dei campi, tipi,
lunghezze): sono le righe del registro, che i testi non li contiene mai. I nomi dei campi che non sembrano nomi di
campo (spazi, chiocciole, troppo lunghi) vengono comunque tolti.
"""
import json
import platform
import re
import time
from pathlib import Path

import activity
import catalog
import i18n
import paths
import settings
import updates
from version import VERSION

ISSUES = "https://github.com/francescogruner/omissis/issues/new"
DAYS = 30
RX_FIELD = re.compile(r"[\w./:+-]{1,48}")
FIELDS = ("service", "via", "client", "event", "method", "kind", "path", "error")


def system():
    """«Windows 11 10.0.26300 AMD64», «macOS 26.1 arm64», «Ubuntu 24.04 (Linux 6.8) x86_64»."""
    name, machine = platform.system(), platform.machine()
    try:
        if name == "Darwin":
            return f"macOS {platform.mac_ver()[0]} {machine}"
        if name == "Linux":
            about = platform.freedesktop_os_release()
            return f"{about.get('NAME', 'Linux')} {about.get('VERSION_ID', '')} (Linux {platform.release().split('-')[0]}) {machine}".replace("  ", " ")
    except Exception:   # noqa: BLE001  (un sistema che non lo dice: resta il nome generico)
        pass
    return f"{name} {platform.release()} {platform.version()} {machine}".strip()


def problem(entry):
    """La riga del registro racconta qualcosa che non ha funzionato?"""
    event = str(entry.get("event") or "")
    return any(k in event for k in ("no_text_field", "not_read", "not_prepared", "blocked_engine", "blocked_model"))


def strong(entry):
    """Cio' che va detto subito a chi usa il computer: «blocked» (un messaggio fermato perche' non si riesce a leggerlo),
    «page» (il codice della casella non e' entrato nella pagina). Il resto si vede nel pannello, senza disturbare."""
    event = str(entry.get("event") or "")
    if event.startswith("blocked") and "not_read" in event:
        return "blocked"
    return "page" if "page_not_prepared" in event else None


def safe(node):
    """La forma di una richiesta, com'e' nel registro, senza i nomi di campo che potrebbero non essere nomi di campo."""
    if isinstance(node, dict):
        return {(k if RX_FIELD.fullmatch(str(k)) else "(…)"): safe(v) for k, v in node.items()}
    if isinstance(node, list):
        return [safe(v) for v in node]
    return node if isinstance(node, (int, float, bool)) or node is None else str(node)[:60]


def _lines(start=0):
    """Le righe del registro da un certo punto del file in poi: (righe, dove si e' arrivati)."""
    f = paths.DATA / "activity.jsonl"
    if not f.exists():
        return [], 0
    with f.open("rb") as x:
        x.seek(start)
        raw = x.read()
    cut = raw.rfind(b"\n") + 1   # una riga scritta a meta' si legge al prossimo giro
    out = []
    for line in raw[:cut].decode("utf-8", "replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out, start + cut


def problems(days=DAYS, limit=12):
    """Le richieste non lette degli ultimi giorni, una per tipo, con quante volte e quando l'ultima. Le piu' recenti prima."""
    f = paths.DATA / "activity.jsonl"
    size = f.stat().st_size if f.exists() else 0
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - days * 86400))
    groups = {}
    for e in _lines(max(0, size - 6_000_000))[0]:
        if not problem(e) or str(e.get("stamp", "")) < since:
            continue
        form = safe(e.get("structure")) if e.get("structure") is not None else None
        key = json.dumps([[e.get(k) for k in FIELDS], form], ensure_ascii=False, sort_keys=True)
        g = groups.setdefault(key, {**{k: e.get(k) for k in FIELDS if e.get(k)}, "structure": form, "n": 0, "last": ""})
        g["n"] += 1
        g["last"] = max(g["last"], str(e.get("stamp", "")))
    return sorted(groups.values(), key=lambda g: g["last"], reverse=True)[:limit]


def news(mark):
    """Che cosa e' successo di importante dall'ultima volta: [(tipo, servizio, programma)], e dove si e' arrivati nel file.
    `mark` e' il punto del file da cui leggere (None la prima volta: si parte da adesso, senza riparlare del passato)."""
    f = paths.DATA / "activity.jsonl"
    size = f.stat().st_size if f.exists() else 0
    if mark is None or size < mark:
        return [], size
    lines, end = _lines(mark)
    out = []
    for e in lines:
        kind = strong(e)
        if kind and (kind, e.get("service"), e.get("client")) not in [(a, b, c) for a, b, c in out]:
            out.append((kind, str(e.get("service") or ""), str(e.get("client") or "")))
    return out, end


def build(what="", phase="", model=""):
    """La segnalazione: {"title", "text", "issues", "problems"}. `what` e' il nome del programma da cui la si apre."""
    names = {s["id"]: s["name"] for s in catalog.SERVICES}
    name = lambda service: names.get(service, service or "?")   # noqa: E731
    groups, found = activity.compatibility(), problems()
    seen = sorted(activity.clients(), key=lambda c: c["last"], reverse=True)[:25]
    # di quale programma si parla: quello da ricontrollare (se la segnalazione parte dalla sua scheda, proprio lui)
    doubtful = sorted((g for g in groups if g["status"] == "to_recheck" and g["client"]), key=lambda g: g["last_unread"], reverse=True)
    subject = next((g["client"] for g in doubtful if what and g["client"].startswith(what)), "") or what \
        or (doubtful[0]["client"] if doubtful else "") or (found[0].get("client") if found else "") or "Omissis"
    model = Path(str(model or settings.read().get("model") or "")).name or "?"
    out = [i18n.t("report.text.omissis", version=VERSION, channel=updates.channel(), system=system(), language=i18n.active(), model=model,
                  phase=phase or "?"), ""]
    out.append(i18n.t("report.text.programs"))
    for g in groups:
        out.append(" | ".join([name(g["service"]), g["via"], g["client"] or "?", g["status"], "+".join(g["methods"]) or "-",
                               f"{g['ok']}/{g['restoring']}/{g['unread']}", g["last_ok"][:16] or "-", g["last_unread"][:16] or "-"]))
    if not groups:
        out.append(i18n.t("report.text.none"))
    out += ["", i18n.t("report.text.seen")]
    out += [" | ".join([name(c["service"]), c["via"], c["client"] or "?", c["last"][:16]]) for c in seen] or [i18n.t("report.text.none")]
    out += ["", i18n.t("report.text.problems", days=DAYS)]
    for g in found:
        head = " ".join(str(x) for x in (g["last"][:16], f"x{g['n']}", name(g.get("service")), g.get("via") or "proxy", f"«{g.get('client') or '?'}»",
                                         g.get("event"), g.get("method") or "", g.get("path") or "", g.get("kind") or "", g.get("error") or "") if x != "")
        out.append(head)
        if g["structure"] is not None:
            out.append("  " + json.dumps(g["structure"], ensure_ascii=False)[:900])
    if not found:
        out.append(i18n.t("report.text.none"))
    title = i18n.t("report.issue.title", what=subject) + f" · Omissis {VERSION} · {platform.system().replace('Darwin', 'macOS')}"
    return {"title": title[:140], "text": "\n".join(out), "issues": ISSUES, "problems": len(found), "to_recheck": len(doubtful)}
