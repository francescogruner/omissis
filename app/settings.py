# -*- coding: utf-8 -*-
"""Impostazioni condivise tra pannello e proxy: data\\settings.json."""
import json
import re
import urllib.parse

import catalog
import managed
import paths

FILE = paths.DATA / "settings.json"
DEFAULTS = {
    "model": "omissis-small",  # omissis-small (di serie: piu' leggero e veloce) oppure omissis-base (un po' piu' preciso, piu' memoria)
    "device": "auto",            # auto | cpu | cuda
    "port": 8080,
    "restore": True,          # False: le risposte restano con i segnaposto (per vedere cosa riceve il servizio)
    "attachments": True,            # anonimizza i file allegati ai messaggi (Word, Excel, PowerPoint, testo, PDF, immagini con testo)
    "block_files": False,        # True: blocca il caricamento di file, che il proxy non sa mascherare
    "policies": {},             # id del servizio -> proteggi | registra | blocca | ignora (assente = predefinita)
    "box": True,             # sostituisce i dati gia' nella casella di scrittura, prima dell'invio (la difesa piu' stabile)
    "updates": "automatic",   # automatici (scarica e installa) | avvisa (controlla soltanto) | mai
    "language": "auto",            # auto (quella di Windows) oppure il codice di una lingua presente in panel\\lingue
    "theme": "auto",              # auto (come il sistema) | chiaro | scuro
    "view": "simple",         # semplice (stato, testo, documenti, guida) | avanzata (tutto, per il tecnico)
    # scorciatoie da tastiera, valide in ogni programma; "" = spenta. sostituisci: maschera sul posto il testo selezionato
    "shortcuts": {"replace": "ctrl+alt+s", "mask": "ctrl+alt+m", "restore": "ctrl+alt+r"},
    "scan": "weekly",    # analisi degli strumenti AI sul PC: settimanale | giornaliera | mai (resta quella a mano)
    "vault_days": 0,        # 0 = l'archivio tiene tutto; N = toglie da solo le voci non usate da N giorni
    "categories": [],             # categorie in piu' da sostituire (DATA, PROFESSIONE, SALUTE...): di serie restano in chiaro
    "mcp_folders": [],            # cartelle in piu' che il server MCP puo' usare, oltre a Documenti, Desktop e Download
    "gateway_upstreams": {},      # chi ha gia' un proprio gateway: nome usato nell'indirizzo (anthropic, openai...) -> dove inoltrare
    # gruppi di dati che NON vengono sostituiti (vedi GROUPS). Di serie restano in chiaro solo i nomi di aziende e
    # organizzazioni (non sono dati personali); gli altri gruppi sono accesi, e spegnerne uno riduce la protezione
    "groups_off": ["organizations"],
    # un profilo imposto (da chi amministra il PC, o dalla console): fissa insieme gruppi e categorie in piu' (vedi PROFILES).
    # Chi usa il PC non lo sceglie da qui: per lui un profilo e' solo un modo rapido di accendere e spegnere le singole voci
    "profile": "",
    # True: la protezione non si ferma dal pannello ne' dall'icona, e il programma non si chiude dall'icona. Nel pannello non
    # c'e': la impone chi amministra il PC, oppure la console. Non ferma chi chiude il programma da Gestione attivita'
    "always_on": False,
    # console centrale (facoltativa, per le organizzazioni): dove mandare il riepilogo di questo PC. Vuoto = non parte nulla
    "console_url": "",            # indirizzo https della console
    "console_key": "",            # chiave di collegamento data dalla console: dice a quale organizzazione appartiene il PC
    "console_names": True,        # False: il riepilogo non porta il nome del computer ne' quello dell'utente
    "console_pin": "",            # impronta SHA-256 del certificato della console, per quelle in rete locale che se lo fanno da se'
    "console_rules": False,       # True: questo PC applica le regole che la console gli manda (solo quelle di CONSOLE_RULES)
    "onboarded": False,           # la configurazione guidata del primo avvio e' gia' stata vista (o saltata)
    # server di inferenza in rete (facoltativo, vedi remote.py). Un PC o presta il suo modello o lo chiede a un altro
    "engine_url": "",             # indirizzo https del server: il modello lo ha lui, questo PC gli chiede il riconoscimento
    "engine_key": "",             # la chiave che il server da' ai PC dell'organizzazione
    "engine_pin": "",             # impronta SHA-256 del certificato del server: il PC parla solo con quello
    "serve": False,               # True: questo PC presta il suo modello agli altri PC della rete
    "serve_port": 8770,           # la porta su cui lo fa
}
# impostazioni che l'amministratore impone voce per voce: il resto della tabella resta dell'utente
MERGED = {"policies"}
# Che cosa una console puo' imporre a un PC che ha scelto di accettarne le regole. Restano fuori, apposta, gli indirizzi a
# cui il PC manda qualcosa (console, server di inferenza, gateway), le cartelle che apre, il nome nel riepilogo e questa
# stessa scelta: chi entra in una console non deve poter dirottare i dati dei PC.
CONSOLE_RULES = {"policies", "block_files", "attachments", "box", "updates", "scan", "groups_off", "always_on", "profile"}
CONSOLE_FILE = paths.DATA / "console_rules.json"
_cache = {"mtime": None, "managed": None, "console": None, "data": None}


def _own():
    """Le scelte dell'utente, cosi' come sono nel file."""
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _typed(source, allowed=None):
    """I valori arrivati da fuori (registro di Windows, console), tenuti solo se hanno il tipo dell'impostazione."""
    raw = {}
    for k, v in source.items():
        if k not in DEFAULTS or (allowed is not None and k not in allowed):
            continue
        kind = type(DEFAULTS[k])
        if kind is bool:
            v = v not in (False, 0, "false", "0", "")
        elif kind is int and not isinstance(v, int):
            continue
        elif kind is str:
            v = str(v)
        elif kind in (dict, list) and not isinstance(v, kind):
            continue   # un valore scritto male non impone nulla
        raw[k] = v
    if not raw:
        return {}
    clean = _clean({**DEFAULTS, **raw})
    return {k: clean[k] for k in raw}


def _admin():
    """Le impostazioni imposte da chi amministra il PC (managed.py), ripulite come quelle dell'utente."""
    return _typed(managed.read())


def console_file():
    """Cio' che la console ha mandato l'ultima volta (lo scrive central.py): {"url", "version", "rules", "received"}."""
    try:
        data = json.loads(CONSOLE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("rules"), dict) else {}
    except (OSError, ValueError):
        return {}


def from_console(admin=None):
    """Le regole della console in vigore su questo PC. Valgono solo se il PC ha scelto di accettarle (console_rules), e'
    collegato a una console, e le regole vengono proprio da quella: cambiando console quelle vecchie non restano."""
    admin = _admin() if admin is None else admin
    own = {**DEFAULTS, **_own(), **{k: v for k, v in admin.items() if k not in MERGED}}
    received = console_file()
    if own.get("console_rules") is not True or not (own.get("console_url") and own.get("console_key")) or received.get("url") != own["console_url"]:
        return {}
    return _typed(received["rules"], CONSOLE_RULES)


def imposed():
    """Tutto cio' che l'utente non puo' cambiare: le impostazioni dell'amministratore del PC e, sotto, le regole della
    console. Dove dicono cose diverse vince l'amministratore del PC."""
    admin = _admin()
    console = from_console(admin)
    out = {**console, **admin}
    if console.get("policies") and admin.get("policies"):
        out["policies"] = {**console["policies"], **admin["policies"]}
    # un profilo imposto fissa gruppi e categorie: chi usa il PC non li cambia. Se chi vince (l'amministratore del PC) ha
    # scritto lui gruppi o categorie voce per voce, valgono quelli
    chosen = PROFILES.get(out.get("profile") or "")
    if chosen is None:
        out.pop("profile", None)
    else:
        for key, value in chosen.items():
            if key not in admin:
                out[key] = list(value)
    return out


def locked(cfg_imposed=None):
    """Che cosa l'utente non puo' cambiare: le impostazioni imposte per intero e, per le regole, i singoli servizi."""
    data = imposed() if cfg_imposed is None else cfg_imposed
    admin = _admin()
    console = from_console(admin)   # da dove viene il vincolo, per dirlo nel pannello: qui solo cio' che la console impone davvero
    by_console = sorted(k for k in console if k not in MERGED and k not in admin) + \
        sorted(f"policies.{s}" for s in (console.get("policies") or {}) if s not in (admin.get("policies") or {}))
    return {"keys": sorted(k for k in data if k not in MERGED), "policies": sorted(data.get("policies") or {}), "console": by_console}


def first_run(test=False):
    """Va proposta la configurazione guidata? Solo a chi apre il programma per la prima volta e lo configura da se':
    su un PC con impostazioni imposte ha gia' deciso chi lo amministra, e nelle prove automatiche coprirebbe la pagina."""
    return not test and not read()["onboarded"] and not any(locked().values())


def read():
    try:
        m = FILE.stat().st_mtime
    except OSError:
        m = None
    try:
        c = CONSOLE_FILE.stat().st_mtime
    except OSError:
        c = None
    source = managed.read()
    if _cache["data"] is None or _cache["mtime"] != m or _cache["managed"] is not source or _cache["console"] != c:
        data, fixed = {**DEFAULTS, **_own()}, imposed()
        for k, v in fixed.items():
            data[k] = {**(data[k] if isinstance(data[k], dict) else {}), **v} if k in MERGED else v
        _cache.update(mtime=m, managed=source, console=c, data=data)
    return _cache["data"]


# I gruppi di dati che si possono spegnere (Impostazioni > Riconoscimento > Cosa sostituire). Serve a chi lavora proprio su
# quei dati: un tecnico che fa ragionare l'AI su una rete, uno studio che vuole leggere i numeri di pratica nelle risposte.
GROUPS = {"payments": ["IBAN", "CARTA", "CARTA_SEC", "PIVA"],
          "organizations": ["ORG"],
          "it": ["IP", "MAC", "HOSTNAME", "DOMINIO", "URL", "ACCOUNT", "ID_CLOUD", "ID_DISPOSITIVO"],
          "records": ["ID_PRATICA", "CATASTO", "ID_UTENZA", "TARGA", "ID_VEICOLO"]}
# Questo gruppo di serie e' spento: i nomi di aziende e organizzazioni non sono dati personali. Chi vuole tenerli riservati
# lo accende. Tenerlo spento non e' «protezione ridotta».
OPTIONAL = ("organizations",)
# Le categorie in piu' che il modello conosce e di serie lascia in chiaro, nei due gruppi con cui si accendono
SPECIAL = ["SALUTE", "RELIGIONE", "POLITICA", "ORIENTAMENTO", "ORIGINE"]
DETAILS = ["DATA", "ORA", "ETA", "GENERE", "TITOLO", "PROFESSIONE", "ISTRUZIONE", "LUOGO"]
# I profili: combinazioni pronte di gruppi e categorie, dalla meno alla piu' stretta. Nessuno spegne un gruppo acceso di
# serie: un profilo non riduce mai la protezione.
PROFILES = {"standard": {"groups_off": ["organizations"], "categories": []},        # persone, identificativi, pagamenti, informatica
            "confidential": {"groups_off": [], "categories": []},                  # anche aziende e organizzazioni
            "special": {"groups_off": [], "categories": sorted(SPECIAL)},          # anche i dati particolari del GDPR
            "maximum": {"groups_off": [], "categories": sorted(SPECIAL + DETAILS)}}   # tutto cio' che il modello riconosce
# Questi non si spengono: sono il motivo per cui il programma esiste.
ALWAYS_ON = {"people": ["PERSONA", "EMAIL", "TELEFONO", "INDIRIZZO", "CAP", "CITTA", "DATA_NASCITA", "CF", "DOC_ID"], "secrets": ["SEGRETO"]}


# Le caselle generiche di un'azienda (info@, amministrazione@...) sono un dato dell'azienda, non di una persona: restano
# sempre in chiaro, con qualsiasi profilo. Le caselle con il nome di una persona sono sempre protette, come quelle generiche
# presso un servizio di posta per privati (qui sotto).
ROLE_WORDS = set(
    "info informazioni amministrazione admin segreteria ufficio uffici commerciale commerciali acquisti vendite sales contabilita "
    "fatturazione fatture billing ordini orders supporto support assistenza helpdesk service servizio servizi clienti customer help "
    "customercare care marketing hr personale risorse umane direzione noreply no reply donotreply postmaster webmaster office "
    "contact contatti contatto hello ciao privacy dpo legal legale pec logistica magazzino tecnico tecnica it sistemi ced press stampa "
    "jobs lavora con noi careers newsletter booking prenotazioni reception protocollo urp comunicazione qualita sicurezza abuse "
    "security mail posta general generale staff team".split())
# qui dietro a «info@» c'e' quasi sempre una persona o una ditta individuale: resta protetta
CONSUMER_DOMAINS = set(
    "gmail.com googlemail.com libero.it hotmail.it hotmail.com outlook.com outlook.it live.it live.com yahoo.it yahoo.com alice.it "
    "tiscali.it virgilio.it icloud.com me.com fastwebnet.it tim.it tin.it email.it proton.me protonmail.com msn.com inwind.it "
    "iol.it aruba.it pec.it legalmail.it arubapec.it postecert.it pec.libero.it".split())


def role_mailbox(address):
    """La casella generica di un'organizzazione: tutte le parole prima della chiocciola sono nomi di ufficio o di funzione
    (info, ufficio.acquisti, amministrazione2) e il dominio non e' quello di un servizio di posta per privati."""
    local, _, domain = str(address).strip().strip("<>.,;:").lower().partition("@")
    words = [w for w in re.split(r"[^a-z]+", local) if w]
    return bool(domain) and bool(words) and domain not in CONSUMER_DOMAINS and all(w in ROLE_WORDS for w in words)


def reduced(cfg=None):
    """I gruppi accesi di serie che qualcuno ha spento: e' questa la «protezione ridotta» che pannello e console segnalano."""
    return [g for g in ((cfg or read()).get("groups_off") or []) if g in GROUPS and g not in OPTIONAL]


def profile_of(cfg=None):
    """Il profilo a cui corrispondono le scelte in vigore, oppure «custom» se sono state fatte voce per voce."""
    cfg = cfg or read()
    now = (set(cfg.get("groups_off") or []), set(cfg.get("categories") or []))
    for name, p in PROFILES.items():
        if now == (set(p["groups_off"]), set(p["categories"])):
            return name
    return "custom"


def labels_off(cfg=None):
    """Le etichette che, per scelta di chi usa il PC, non vanno sostituite."""
    chosen = (cfg or read()).get("groups_off") or []
    return {label for g in chosen if g in GROUPS for label in GROUPS[g]}


def address_ok(text):
    """Un indirizzo a cui si puo' inoltrare: http o https, con il nome del computer."""
    try:
        u = urllib.parse.urlsplit(str(text).strip())
        return u.scheme in ("http", "https") and bool(u.hostname) and not u.query and not u.fragment
    except ValueError:
        return False


def write(data):
    """Salva le scelte dell'utente. Cio' che e' imposto dall'amministratore non entra nel file: se un giorno il vincolo
    viene tolto, torna la scelta che l'utente aveva. Restituisce le impostazioni in vigore."""
    FILE.parent.mkdir(parents=True, exist_ok=True)
    clean, fixed, before = _clean(data), imposed(), _clean({**DEFAULTS, **_own()})
    for k, v in fixed.items():
        if k in MERGED:   # le voci imposte restano, nel file, quelle che l'utente aveva scelto prima (se ne aveva)
            clean[k] = {**{n: x for n, x in clean[k].items() if n not in v}, **{n: x for n, x in before[k].items() if n in v}}
        else:
            clean[k] = before[k]
    FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    _cache["data"] = None
    return read()


def _clean(data):
    clean = {k: data.get(k, v) for k, v in DEFAULTS.items()}
    clean["policies"] = {k: v for k, v in (clean["policies"] or {}).items()
                           if k in catalog.PER_ID and v in catalog.POLICIES}
    clean["onboarded"] = clean["onboarded"] is True
    clean["always_on"] = clean["always_on"] is True
    clean["profile"] = clean["profile"] if clean["profile"] in PROFILES else ""
    date = clean["shortcuts"] if isinstance(clean["shortcuts"], dict) else {}
    clean["shortcuts"] = {k: str(date.get(k, v)).strip().lower()[:40] for k, v in DEFAULTS["shortcuts"].items()}
    clean["categories"] = sorted({str(x) for x in clean["categories"] or [] if str(x).isupper() and len(str(x)) <= 24})
    own = clean["gateway_upstreams"] if isinstance(clean["gateway_upstreams"], dict) else {}
    clean["gateway_upstreams"] = {str(k): str(v).strip().rstrip("/") for k, v in own.items()
                                  if re.fullmatch(r"[a-z0-9-]{1,30}", str(k)) and str(k) != "codex" and address_ok(v)}
    clean["groups_off"] = sorted({str(g) for g in (clean["groups_off"] if isinstance(clean["groups_off"], list) else []) if str(g) in GROUPS})
    extra = clean["mcp_folders"] if isinstance(clean["mcp_folders"], list) else []
    clean["mcp_folders"] = list(dict.fromkeys(str(x).strip().strip('"') for x in extra if str(x).strip()))[:20]
    if clean["scan"] not in ("weekly", "daily", "never"):
        clean["scan"] = DEFAULTS["scan"]
    try:
        clean["vault_days"] = min(3650, max(0, int(clean["vault_days"] or 0)))
    except (TypeError, ValueError):
        clean["vault_days"] = 0
    address = str(clean["console_url"] or "").strip().rstrip("/")
    clean["console_url"] = address if console_address_ok(address) else ""
    clean["console_key"] = re.sub(r"[^A-Za-z0-9_.-]", "", str(clean["console_key"] or ""))[:200]
    clean["console_names"] = clean["console_names"] not in (False, 0, "false", "0")
    clean["console_rules"] = clean["console_rules"] is True
    pin = re.sub(r"(?i)^sha-?256[:=]|[\s:]", "", str(clean["console_pin"] or "")).lower()
    clean["console_pin"] = pin if re.fullmatch(r"[0-9a-f]{64}", pin) else ""
    address = str(clean["engine_url"] or "").strip().rstrip("/")
    clean["engine_url"] = address if console_address_ok(address) else ""   # stessa regola: in chiaro solo su questo PC
    clean["engine_key"] = re.sub(r"[^A-Za-z0-9_.-]", "", str(clean["engine_key"] or ""))[:200]
    pin = re.sub(r"(?i)^sha-?256[:=]|[\s:]", "", str(clean["engine_pin"] or "")).lower()
    clean["engine_pin"] = pin if re.fullmatch(r"[0-9a-f]{64}", pin) else ""
    try:
        port = int(clean["serve_port"])
    except (TypeError, ValueError):
        port = 0
    clean["serve_port"] = port if 1024 <= port <= 65535 else DEFAULTS["serve_port"]
    # un PC che chiede il riconoscimento a un altro non ha un modello da prestare
    clean["serve"] = clean["serve"] is True and not (clean["engine_url"] and clean["engine_key"])
    return clean


def console_address_ok(text):
    """La console si raggiunge solo in https: il riepilogo porta la chiave di collegamento. In chiaro solo su questo PC."""
    if not address_ok(text):
        return False
    u = urllib.parse.urlsplit(str(text).strip())
    return u.scheme == "https" or u.hostname in ("127.0.0.1", "localhost")


def policy(service, cfg=None):
    cfg = cfg or read()
    return cfg["policies"].get(service["id"]) or catalog.default_policy(service)


def guarded(cfg=None):
    return [s for s in catalog.SERVICES if s["adapter"] and policy(s, cfg) == "protect"]
