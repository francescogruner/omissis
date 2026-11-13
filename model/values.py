# -*- coding: utf-8 -*-
"""Valori inventati per i dati di addestramento di msp-pii.

Indipendente dal benchmark: non importa nulla dal benchmark, ha elenchi e
formati propri. Ogni classe espone metodi senza argomenti; ETI dice quale etichetta ha il
valore restituito (assente = testo non sensibile).
"""
import importlib
import string
import unicodedata

from faker.providers.address.it_IT import Provider as _A
from faker.providers.person.it_IT import Provider as _P

NOMI_M, NOMI_F, COGNOMI, COMUNI, PROV = _P.first_names_male, _P.first_names_female, _P.last_names, _A.cities, _A.states_abbr
STRANIERI_N, STRANIERI_C = [], []
for _loc in ("en_US", "de_DE", "es_ES", "fr_FR", "ro_RO", "tr_TR", "pt_BR"):
    _m = importlib.import_module(f"faker.providers.person.{_loc}").Provider
    STRANIERI_N += list(_m.first_names)[:250]
    STRANIERI_C += list(_m.last_names)[:250]
STRANIERI_N += ("Mohamed Ahmed Fatima Youssef Aisha Omar Karim Amina Hassan Wei Chen Jing Xin Priya Raj Arjun Ion Andrei "
                "Mihai Olga Oksana Dmytro Ardit Erion Blerina Mamadou Ibrahima Fatou Abdou Kwame Nadia Samir Dragan "
                "Jelena Svetlana Nguyen Thi Sandeep Gurpreet Rashid Khadija Bogdan Florin Valbona Besnik").split() * 4
STRANIERI_C += ["El Amrani", "Benali", "Hossain", "Rahman", "Singh", "Kaur", "Chen", "Wang", "Zhang", "Hu", "Popescu",
                "Ionescu", "Hoxha", "Shehu", "Krasniqi", "Diop", "Ndiaye", "Traoré", "Kovač", "Petrović", "Shevchenko",
                "Kovalenko", "Khan", "Perera", "Fernando", "Okafor", "Mensah", "Nguyen", "Ben Salah", "Çelik",
                "Gashi", "Dervishi", "Ursu", "Munteanu", "Bah", "Sow", "Islam", "Begum", "Liu", "Zhou"] * 4
PROVIDER = ("gmail.com libero.it hotmail.it outlook.com yahoo.it alice.it tiscali.it virgilio.it icloud.com live.it "
            "outlook.it hotmail.com fastwebnet.it tim.it email.it proton.me").split()
PEC = "pec.it legalmail.it arubapec.it postecert.it pec.libero.it cert.legalmail.it pecimprese.it".split()
ODONIMI = ("Via Viale Piazza Corso Vicolo Largo Strada Via Via Via Piazzale Lungomare Contrada Località Frazione "
           "Salita Vico Borgo Via Viale").split()
INTITOLAZIONI = ("Roma Garibaldi Mazzini Cavour Dante Alighieri Verdi XX Settembre IV Novembre Marconi Matteotti "
                 "della Repubblica dei Mille Kennedy Gramsci Manzoni Leopardi Carducci San Francesco Santa Maria "
                 "delle Rose dei Tigli del Lavoro dell'Industria dell'Artigianato Europa Trento Trieste Brennero "
                 "Nazionale Provinciale Aldo Moro Giovanni XXIII Papa Luciani dei Caduti della Stazione del Mercato "
                 "Vittorio Veneto Piave Isonzo Monte Grappa Solferino Volta Galilei Fermi Pascoli Foscolo "
                 "Ugo Bassi Cesare Battisti Fratelli Bandiera Don Minzoni San Marco Sant'Antonio al Ponte").split(" ")
RADICI = ("Tecno Edil Agri Idro Termo Auto Info Medi Euro Ital Nord Alpi Dolomiti Adige Brenta Garda Lario Tirreno "
          "Adria Etna Sarda Meccanica Elettro Logi Trans Farma Bio Eco Green Sol Net Data Soft Sistemi Costruzioni "
          "Impianti Serramenti Trasporti Carni Vini Mobili Marmi Plast Metal Legno Carta Tessile Moda Ottica Dental "
          "Immobiliare Assicura Finanza Consult Service Global Prime Nova Alfa Beta Delta Omega Sigma Vega Orion "
          "Stella Aurora Fenice Aquila Leone Torre Ponte Porto Valle Monte Lago").split()
CODE = ("tech service group system solution project lab works point line plus italia impianti engineering consulting "
        "logistica trade food energy design studio media digital cloud sicurezza ambiente forniture").split()
FORME = ["S.r.l.", "SRL", "Srl", "S.p.A.", "SpA", "SPA", "s.n.c.", "snc", "S.a.s.", "sas", "S.r.l.s.", "Soc. Coop.",
         "S.c.a.r.l.", "& C. S.a.s.", "& Figli S.r.l.", "srl", "s.r.l.", "S.R.L.", "Società Cooperativa", "ONLUS"]
PAROLE_PW = ("Estate Inverno Primavera Autunno Milano Roma Napoli Torino Juventus Inter Milan Napoli Ferrari Ducati "
             "Vespa Pizza Sole Mare Luna Stella Amore Fragola Limone Gatto Cane Drago Tigre Leone Benvenuto Cambiami "
             "Password Ufficio Azienda Welcome Admin Backup Server Qwerty Lavoro Segreto Dolomiti Trento Verona "
             "Bologna Firenze Palermo Samsung Lenovo Casa Montagna").split()
MESI = "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre".split()
CIFRE = "zero uno due tre quattro cinque sei sette otto nove".split()
# Enti pubblici: restano in chiaro (si riconoscono dal nome comune: Comune, Tribunale, Agenzia...).
ENTI = ["INPS", "INAIL", "Agenzia delle Entrate", "Camera di Commercio", "Garante Privacy", "ASL", "Comune", "Regione",
        "Tribunale", "Guardia di Finanza", "SIAE", "ACI", "PRA", "Agenzia delle Dogane", "Motorizzazione Civile", "Prefettura",
        "Questura", "Corte d'Appello", "Giudice di Pace", "Organismo di Mediazione", "Ordine degli Avvocati", "Cassa Edile",
        "Fondo Est", "Banca d'Italia", "CONSOB", "IVASS", "ANAC", "Consip", "MEPA", "Procura della Repubblica", "ATS",
        "Ufficio del Registro", "Ministero dell'Interno", "MEF", "Polizia Postale", "Carabinieri", "Vigili del Fuoco", "ACN",
        "CSIRT Italia", "AgID", "Ordine dei Commercialisti", "Ispettorato del Lavoro", "Agenzia delle Entrate-Riscossione",
        "Catasto", "Conservatoria", "Registro Imprese", "INPS Gestione Separata", "Cassa Forense", "Anagrafe", "SUAP", "ARPA"]
ENTI_LUOGO = ["Comune di", "Tribunale di", "ASL di", "Questura di", "Prefettura di", "Camera di Commercio di", "Procura di",
              "Università di", "Provincia di", "INPS di", "Ospedale di", "Agenzia delle Entrate di", "Giudice di Pace di"]
# Marchi commerciali: il modello li tratta come qualsiasi organizzazione (ORG); a lasciarli in
# chiaro pensa l'elenco dei nomi noti (known.py), che e' deterministico e si puo' estendere.
MARCHI = ["Microsoft", "Google", "Fortinet", "Cisco", "Aruba", "TIM", "Vodafone", "Fastweb", "Poste Italiane", "Zucchetti",
          "TeamSystem", "Sophos", "Veeam", "HP", "Dell", "Lenovo", "Apple", "Amazon", "PayPal", "Enel", "A2A", "Hera",
          "Trenitalia", "Booking", "Fineco", "Intesa Sanpaolo", "UniCredit", "BPER", "Banco BPM", "Credem", "ING", "Generali",
          "Allianz", "UnipolSai", "AXA", "Zurich", "Reale Mutua", "Nexi", "Satispay", "DHL", "BRT", "GLS", "SDA", "UPS",
          "Ryanair", "ITA Airways", "Italo", "Telepass", "Iliad", "WindTre", "Sky", "Netflix", "Register.it", "OVH",
          "TeamViewer", "AnyDesk", "ESET", "Kaspersky", "Ubiquiti", "Synology", "QNAP", "Canon", "Epson", "Brother", "Ricoh",
          "Kyocera", "Samsung", "Xiaomi", "Wolters Kluwer", "Buffetti", "Namirial", "InfoCert", "Esprinet", "Ingram Micro",
          "Computer Gross", "TD Synnex", "Mediaworld", "Unieuro", "Leroy Merlin", "Esselunga", "Coop", "Eni", "Edison",
          "Sorgenia", "Mediolanum", "Banca Sella", "Crédit Agricole", "Monte dei Paschi", "Cattolica", "Vittoria Assicurazioni",
          "FedEx", "TNT", "Bartolini", "Adobe", "Oracle", "SAP", "IBM", "Intel", "AMD", "Nvidia", "Logitech", "Acer", "Asus",
          "Huawei", "Zyxel", "Netgear", "TP-Link", "D-Link", "Watchguard", "SonicWall", "Palo Alto Networks", "Check Point",
          "CrowdStrike", "Trend Micro", "Bitdefender", "Acronis", "Datto", "Kaseya", "ConnectWise", "Cloudflare", "Dropbox",
          "Zoom", "Slack", "Atlassian", "Salesforce", "Meta", "LinkedIn", "OpenAI", "Anthropic", "Wind", "Tiscali", "Eolo",
          "Sielte", "Lepida", "Infocamere", "Sogei", "Engineering", "Reply", "Accenture", "Deloitte", "KPMG", "Randstad", "Adecco"]
PRODOTTI = ["Outlook", "Teams", "OneDrive", "SharePoint", "Excel", "Windows 11", "Office 365", "Microsoft 365",
            "FortiClient", "FortiGate 60F", "Veeam Backup", "NinjaOne", "Acronis", "SentinelOne", "Bitdefender",
            "HP EliteBook 840 G9", "Lenovo ThinkPad T14", "Dell Latitude 5540", "Synology DS920+", "QNAP TS-453",
            "Zucchetti Infinity", "TeamSystem Alyante", "Mago4", "Danea Easyfatt", "AutoCAD", "Adobe Acrobat",
            "Chrome", "Edge", "Zimbra", "3CX", "Yealink T46", "UniFi", "pfSense", "Sophos XGS", "Exchange Online",
            "Active Directory", "Entra ID", "Intune", "VPN", "RDP", "gestionale", "CRM", "stampante Ricoh MP C3004"]
PRODOTTI += ["Zabbix", "Nagios", "Grafana", "Wazuh", "VMware", "vCenter", "Hyper-V", "Citrix", "Nextcloud", "Plesk", "cPanel",
             "WordPress", "Thunderbird", "Firefox", "WhatsApp", "Telegram", "Google Drive", "Gmail", "Google Workspace",
             "PowerShell", "Linux", "Debian", "macOS", "iOS", "Android", "MikroTik", "Mexal", "Passepartout", "Arca Evolution",
             "Business Central", "Dynamics 365", "Power BI", "Power Automate", "Copilot", "Defender", "Purview", "Autopilot",
             "HaloPSA", "Halo", "Ninja", "NinjaRMM", "Splashtop", "RustDesk", "KeePass", "Bitwarden", "LastPass", "1Password",
             "Word", "PowerPoint", "Access", "Visio", "Project", "Planner", "Forms", "Lists", "Viva", "Skype", "Webex", "Meet",
             "Fatture in Cloud", "Aruba PEC", "SPID", "PagoPA", "Fisconline", "Entratel", "Desktop Telematico", "Dike", "ArubaSign",
             "GoSign", "Hypervisor", "Kubernetes", "Docker", "Git", "GitHub", "GitLab", "Jira", "Confluence", "Trello", "Notion",
             "ChatGPT", "Claude", "Gemini", "Photoshop", "Illustrator", "InDesign", "SolidWorks", "Revit", "Archicad", "SketchUp",
             "Veeam Agent", "Hornetsecurity", "Libraesva", "Proofpoint", "Mimecast", "Duo", "Authenticator", "Okta", "OpenVPN",
             "WireGuard", "Tailscale", "Unifi Controller", "Omada", "Meraki", "Windows 10", "Windows", "Office", "Exchange",
             "Wi-Fi", "Bluetooth", "Ethernet", "NVMe", "Thunderbolt", "DisplayPort", "HDMI", "toner", "plotter", "centralino",
             "gestionale paghe", "portale clienti", "firma digitale", "fatturazione elettronica", "cassetto fiscale"]
PRODOTTI += ["FortiGate FGT60F", "FortiGate 100F", "Synology DS923+", "QNAP TS-464", "Exchange Online", "HP LaserJet Pro M404dn",
             "Cisco SG350-28", "UniFi U6-LR", "Yealink T46U", "ThinkPad L14 Gen 4", "OptiPlex 7010", "MacBook Air M2", "iPhone 15",
             "Galaxy A54", "Surface Pro 9", "Kyocera TASKalfa 2554ci", "APC Smart-UPS 1500", "Zyxel GS1900-24",
             "Windows Server 2022", "SQL Server 2019", "Ubuntu 22.04 LTS", "PAN-OS", "ESXi 8.0", "Proxmox VE 8", "polizza Casa Sicura",
             "conto Business Plus", "tariffa Flex 50", "piano Premium", "abbonamento Annuale", "domain controller", "file server"]
SIGLE = ("VPN PC NAS ERP CRM PDF DDT IVA CED RDP DNS DHCP AD GPO MFA OTP PEC SPID CIE POS UPS SSD RAM HDD USB LAN WAN SIM PIN "
         "PUK URL IT HR CEO CFO RSPP DPO GDPR ISO UE EU DSU ISEE INPS INAIL CCNL TFR CU RCA CID PNR SLA KPI FAQ API SQL IIS SMTP "
         "IMAP FTP SSH SSL TLS BIOS UEFI LDAP SSO EDR XDR SOC NOC RMM PSA OK KO NB RE FW R I TS AR DOC XLS IMG RIF ODA RDA DURC "
         "SDI CIG CUP ISA TARI IMU L.C.S. N.B. P.S. C.A. S.V. c.a. p.c. n.d. ASAP FYI TBD WIP EOL RMA SKU QTY "
         "GDO DMS WSUS NPS SCCM MDM MAM VDI VM VLAN VoIP PBX SIP DID ISP ADSL FTTH FTTC LTE APN NAT DMZ ACL QoS SNMP NTP RADIUS "
         "SAML OIDC OAuth DKIM SPF DMARC MX CNAME TTL SSID WPA KVM PDU RAID LUN SAN iSCSI NFS SMB CIFS OST PST CSV XML JSON HTML "
         "CSS PHP SDK IDE CLI GUI UAC UPN SID OU DC RODC FSMO DFS GPT MBR TPM OEM CSP NCE E3 E5 P1 P2 MSP MSSP SIEM SOAR IDS IPS "
         "WAF DLP IAM PAM CASB ZTNA SASE BCP DRP RTO RPO MTTR SLA OLA ITIL COBIT NIST CIS PCI HIPAA SOX DPIA RPCT RLS RSU CIGS "
         "NASpI ANF F24 730 CUD LUL DM10 UNIEMENS UNILAV SCIA CILA DIA APE VIA AUA DVR HACCP POS PSC PIMUS CE UNI EN DIN IP65 "
         "AC DC kW kWh kVA Hz GB MB TB Mbps Gbps MHz dB DPI RGB CMYK A3 A4 B2B B2C PMI SRL SPA SNC SAS ETS APS ASD ODV RUNTS "
         "TODO FIX BUG ERR WARN INFO DEBUG NULL N/A N.D. TBC ETA EOD COB OOO PTO Q1 Q2 Q3 Q4 H1 H2 YTD MTD ROI EBITDA CAPEX OPEX").split()
TITOLI = ["richiesta", "urgente", "sollecito", "oggetto", "allegato", "preventivo", "fattura", "ordine", "conferma", "intervento",
          "assistenza", "risolto", "chiuso", "in attesa", "attenzione", "importante", "nota bene", "dimissione", "cedolino paga",
          "verbale", "contratto", "comunicazione", "avviso", "promemoria", "riepilogo", "report mensile", "lettera di dimissione",
          "bolletta energia elettrica", "scheda intervento", "rapporto di intervento", "problema", "descrizione", "soluzione",
          "note", "risposta", "inoltro", "aggiornamento", "scadenza", "pagamento", "consegna", "reso", "reclamo", "disdetta",
          "offerta", "proposta", "convocazione", "informativa privacy", "condizioni generali", "manuale utente", "istruzioni",
          "benvenuto", "ufficio principale", "sede centrale", "magazzino", "amministrazione", "direzione", "reception",
          "sala riunioni", "cardiologia", "pronto soccorso", "radiologia", "ortopedia", "ufficio tecnico", "ufficio acquisti",
          "risorse umane", "contabilità", "metalmeccanici", "commercio", "terziario", "mediazione forense", "arrivi", "partenze",
          "creazione utente", "nuova richiesta", "richiesta di supporto", "notifica", "refresh", "share", "program", "manager",
          "service", "assist", "informatica", "tecnico", "laboratorio", "produzione", "logistica", "qualità", "marketing",
          "studio", "ufficio", "segreteria", "portineria", "lei", "voi", "conosco", "pagano", "principale", "controller"]
COMANDI = ["New-Object System.Management.Automation.PSCredential($user, $pass)", "$cred = Get-Credential",
           "Invoke-Command -ComputerName $server -Credential $cred -ScriptBlock { Get-Service }",
           "robocopy D:\\Dati E:\\Backup /MIR /R:2 /W:5 /LOG:C:\\Temp\\robocopy.log", "Get-Service -Name Spooler | Restart-Service",
           "sudo systemctl restart nginx", "docker compose up -d", "image: postgres:16", "image: redis:7-alpine", "ipconfig /all",
           "sfc /scannow", "gpupdate /force", "chkdsk C: /f", "TTY=pts/0 ; PWD=/root ; USER=root ; COMMAND=/usr/bin/apt update",
           "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "user agent python-requests/2.31", "curl/8.4.0",
           "C:\\Windows\\System32\\drivers\\etc\\hosts", "/var/log/auth.log", "/etc/nginx/nginx.conf",
           "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run", "Device Role: WINDOWS_WORKSTATION", "Device Role: WINDOWS_SERVER",
           "Location: Ufficio principale", "Policy: Windows Workstation", "Organization Policy: Default", "NT AUTHORITY\\SYSTEM",
           "USER=root", "login as: root", "user: admin", "utente Administrator", "ping 8.8.8.8", "nslookup google.com 1.1.1.1",
           "127.0.0.1 localhost", "netmask 255.255.255.0", "https://portal.azure.com", "https://login.microsoftonline.com",
           "https://admin.microsoft.com", "https://support.microsoft.com/it-it", "SHA256", "apt-get update && apt-get upgrade -y",
           "SELECT * FROM clienti WHERE attivo = 1", "git pull origin main", "pip install -r requirements.txt",
           "services:\n  db:\n    image: mariadb:11", "edit \"VPN-SEDE\"", "set vdom root", "interface GigabitEthernet0/1",
           "switchport mode trunk", "fattura_novembre.pdf", "busta_paga_ottobre.pdf", "clienti_2026.xlsx", "preventivo_rev2.docx",
           "backup_2025-10-31.zip", "IMG_20251014_0931.jpg", "scansione0001.pdf", "listino prezzi.xlsx", "registry.hub.docker.com/library/nginx:1.25",
           "Get-ADUser -Filter * -Properties LastLogonDate", "net use Z: /delete", "wmic bios get serialnumber", "systeminfo",
           "tracert 1.1.1.1", "Test-NetConnection -Port 443", "attachments.zip", "export.csv", "report_finale_v3.pdf"]
DIAGNOSI = ["diabete mellito di tipo 2", "ipertensione arteriosa", "lombosciatalgia", "frattura del radio distale",
            "sindrome ansioso-depressiva", "asma bronchiale", "ernia discale L5-S1", "fibrillazione atriale",
            "celiachia", "ipotiroidismo", "emicrania cronica", "BPCO", "gastrite erosiva", "distorsione del ginocchio"]
FARMACI = ["metformina 500 mg", "ramipril 5 mg", "ibuprofene 600 mg", "sertralina 50 mg", "levotiroxina 75 mcg",
           "pantoprazolo 20 mg", "bisoprololo 2,5 mg", "amoxicillina 1 g", "paracetamolo 1000 mg", "atorvastatina 20 mg"]
REPARTI = "AMM COMM HR IT PROD MAG ACQ DIR TEC LAB REC UFF VEND LOG".split()
_DISP = dict(zip(string.digits + string.ascii_uppercase,
                 [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12,
                  14, 16, 10, 22, 25, 24, 23]))
B64 = string.ascii_letters + string.digits
ALNUM_M = string.ascii_uppercase + string.digits


def pulisci(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if c.isascii() and c.isalpha())


def _v(ch):
    return int(ch) if ch.isdigit() else ord(ch) - 65


def _ctrl(s):
    return chr(65 + sum(_DISP[c] if i % 2 == 0 else _v(c) for i, c in enumerate(s)) % 26)


def _tre(s, nome=False):
    s = pulisci(s).upper()
    cons, voc = [c for c in s if c not in "AEIOU"], [c for c in s if c in "AEIOU"]
    if nome and len(cons) >= 4:
        cons = [cons[0], cons[2], cons[3]]
    return ("".join(cons + voc) + "XXX")[:3]


def luhn(base):
    s = 0
    for i, ch in enumerate(reversed(base)):
        d = int(ch) * (2 if i % 2 == 0 else 1)
        s += d - 9 if d > 9 else d
    return base + str((10 - s % 10) % 10)


def cifre(r, n):
    return "".join(r.choice(string.digits) for _ in range(n))


def caso(r, n, alfabeto=ALNUM_M):
    return "".join(r.choice(alfabeto) for _ in range(n))


def piva(r):
    b = cifre(r, 10)
    s = sum(int(c) if i % 2 == 0 else (2 * int(c) - 9 if int(c) > 4 else 2 * int(c)) for i, c in enumerate(b))
    return b + str((10 - s % 10) % 10)


def iban(r):
    abi, cab, conto = "0" + cifre(r, 4), cifre(r, 5), ("0000" + cifre(r, 8)) if r.random() < .7 else caso(r, 12)
    bban = _ctrl(abi + cab + conto) + abi + cab + conto
    num = "".join(str(int(c, 36)) for c in bban + "IT00")
    return f"IT{98 - int(num) % 97:02}{bban}"


def data(r, a0=2019, a1=2026, nascita=False):
    g, m, a = r.randint(1, 28), r.randint(1, 12), r.randint(a0, a1)
    f = r.random()
    if f < .45:
        return f"{g:02}/{m:02}/{a}"
    if f < .58:
        return f"{g} {MESI[m - 1]} {a}"
    if f < .68:
        return f"{g:02}.{m:02}.{a}"
    if f < .78:
        return f"{g:02}-{m:02}-{a}"
    if f < .86:
        return f"{a}-{m:02}-{g:02}"
    if f < .93:
        return f"{g}/{m}/{a}"
    return f"{g:02}/{m:02}/{a % 100:02}"


FANTASIA = ("Arcadia Zenit Orizzonte Mosaico Girasole Quadrifoglio Armonia Atlante Bussola Cometa Corallo Cristallo Diamante "
            "Eclisse Elica Faro Galassia Giada Icaro Iride Kairos Labirinto Lanterna Meridiana Minerva Mirto Nautilus Nettuno "
            "Oasi Olimpo Origami Pegaso Perla Prisma Quadrante Rondine Rubino Saturno Scintilla Sestante Sirio Sorgente Spiga "
            "Tandem Timone Trifoglio Ulisse Vela Venere Vertice Vortice Zaffiro Zefiro Abaco Agorà Alveare Aquilone Archimede "
            "Argo Astra Atena Aurea Azimut Boreale Calypso Cedro Centauro Cigno Clessidra Colibrì Dedalo Delfino Domus Ducale "
            "Eden Egeo Elios Ermes Esperia Estro Etrusca Falco Fucina Gemma Ginepro Giotto Glicine Grifone Ilios Intreccio Itaca "
            "Kronos Levante Libeccio Lince Logos Lumen Maestrale Magnolia Melograno Mercurio Metis Mistral Nexus Novecento Olmo "
            "Orsa Ponente Primula Quercia Rinascita Salice Scirocco Sfera Sinergia Solaris Tiglio Traguardo Tramontana Tulipano "
            "Vettore Vulcano Zagara Antares Altair Andromeda Cassiopea Polaris Rigel Sigma Kappa Lambda Gamma Epsilon Tau").split()
_EN1 = ("Blue Smart Next Net Green Pro Easy Fast Top Open Sky Star Sun Red Gold Prime Core Meta Tech Data Info Logic Micro "
        "Macro Multi Omni Uni Euro Inter Trans Digi Web Soft Nord Sud All Best Big City Clear Deep Fine First Free Fresh "
        "Hyper Just Key Lead Main Max Mega New One Over Pure Quick Real Safe Sharp Total True Ultra Wide Work").split()
_EN2 = ("Line Point Way Sky Soft Tech Net Lab Hub Box Wave Link Flow Mind Side Works Service Group System Team Vision Trade "
        "Print Food Car Home Med Farm Energy Power Light Steel Wood Glass Pack Mec Bit Byte Code Desk Field Gate Grid Land "
        "Mark Path Port Rise Shift Space Step Stone Track View Ware Zone").split()
_CONS = "b c d f g l m n p r s t v z br cr dr fr gr pr tr st sp sc pl cl fl ch k".split()
_VOC = "a e i o u a e i o ia eo".split()
_SUFF = ("tek mec sys lab nova tec data net plast fer gest log med car pack service group lux mar tex chem farm bit soft "
         "matic tronic ware line point works project system impianti edil therm gas oil trans food wine auto motor").split()


def _una_parola(r, cognome):
    """Ragione sociale di una sola parola: cognome, nome evocativo, marchio inventato, composto inglese, sigla."""
    f = r.random()
    if f < .20:
        n = cognome
    elif f < .34:
        n = r.choice(FANTASIA)
    elif f < .58:
        n = "".join(r.choice(_CONS) + r.choice(_VOC) for _ in range(r.choice([2, 2, 3, 3, 4])))
        n = (n + (r.choice(_SUFF) if r.random() < .45 else r.choice(["", "", "n", "r", "s", "l", "x", "t", "k"]))).capitalize()
    elif f < .76:
        a, b = r.choice(_EN1), r.choice(_EN2)
        n = a + r.choice([b, b, b.lower(), b.lower(), " " + b, "-" + b])
    elif f < .88:
        n = "".join(r.choice(string.ascii_uppercase) for _ in range(r.randint(2, 5)))
        g = r.random()
        if g < .15:
            n = ".".join(n) + "."
        elif g < .30:
            n = r.choice("2345") + n[:2]
        elif g < .40:
            n = n[:1] + "&" + n[1:2]
    elif f < .95:
        n = r.choice(RADICI) + r.choice(RADICI).lower()
    else:
        n = (cognome[:r.randint(2, 4)] + r.choice(COGNOMI)[:r.randint(2, 4)].lower() + r.choice(["", "", "x", "s", "tec", "edil"])).capitalize()
    g = r.random()
    return n.upper() if g < .14 else (n.lower() if g < .19 else n)


class Azienda:
    ETI = dict(nome="ORG", breve="ORG", NOME="ORG", min="ORG", x="ORG", piva="PIVA", piva_it="PIVA", dom="DOMINIO",
               email="EMAIL", pec="EMAIL", iban="IBAN", tel="TELEFONO", via="INDIRIZZO", cap="CAP", citta="CITTA",
               cf="PIVA", cod="ID_PRATICA")

    def __init__(s, r):
        s.r = r
        f = r.random()
        cg = r.choice(COGNOMI)
        if f < .30:
            s._b = r.choice(RADICI) + r.choice(["", "", " ", "-"]) + r.choice(CODE).capitalize()
        elif f < .45:
            s._b = r.choice(RADICI) + r.choice(RADICI).lower()
        elif f < .60:
            s._b = r.choice(["Studio Legale", "Studio Associato", "Studio Commercialisti", "Studio Tecnico",
                             "Studio Dentistico", "Studio Notarile", "Studio"]) + " " + cg + \
                   (" e " + r.choice(COGNOMI) if r.random() < .4 else "")
        elif f < .75:
            s._b = r.choice(["Farmacia", "Officina", "Hotel", "Ristorante", "Agenzia Immobiliare", "Autofficina",
                             "Panificio", "Carrozzeria", "Ottica", "Ferramenta", "Azienda Agricola", "Cantina",
                             "Poliambulatorio", "Fondazione", "Cooperativa", "Autotrasporti", "Impresa Edile"]) + " " + \
                   r.choice([cg, cg, r.choice(RADICI), "San " + r.choice(NOMI_M), r.choice(COMUNI)])
        elif f < .90:
            s._b = cg + r.choice([" ", " & ", " e "]) + r.choice([r.choice(COGNOMI), "Figli", "C.", r.choice(CODE).capitalize()])
        else:
            s._b = "".join(r.choice(string.ascii_uppercase) for _ in range(r.randint(2, 4))) + " " + r.choice(CODE).capitalize()
        if r.random() < .45:   # nome di una sola parola, come la maggior parte dei clienti nei ticket
            s._b = _una_parola(r, cg)
        s._forma = r.choice(FORME) if not s._b.startswith(("Studio", "Fondazione")) or r.random() < .2 else ""
        base = pulisci(s._b.replace("Studio ", "").split(" e ")[0]).lower()[:r.randint(6, 16)] or "azienda"
        s._dom = base + r.choice([".it", ".it", ".it", ".com", ".eu", ".net", "srl.it", "-group.it", ".tn.it", "spa.com"])
        s.sigla = (pulisci(s._b).upper() + "XX")[:r.randint(2, 4)]
        s._citta, s._via, s._cap = r.choice(COMUNI), indirizzo(r), cifre(r, 5)

    def nome(s): return (s._b + " " + s._forma).strip()
    def breve(s): return s._b
    def NOME(s): return s.nome().upper()
    def min(s): return s._b.lower()
    def x(s): return s.r.choice([s.nome, s.nome, s.breve, s.breve, s.NOME, s.min])()
    def piva(s): return piva(s.r)
    def piva_it(s): return "IT" + piva(s.r)
    def cf(s): return piva(s.r)
    def dom(s): return s._dom
    def email(s): return s.r.choice(["info", "amministrazione", "segreteria", "ufficio", "commerciale", "acquisti",
                                    "hr", "contabilita", "assistenza", "direzione"]) + "@" + s._dom
    def pec(s): return s._dom.split(".")[0] + "@" + s.r.choice(PEC)
    def iban(s): return _fmt_iban(s.r, iban(s.r))
    def tel(s): return fisso(s.r)
    def via(s): return s._via
    def cap(s): return s._cap
    def citta(s): return s._citta
    def prov(s): return s.r.choice(PROV)
    def cod(s): return s.r.choice(["CL", "C", "CLI-", "K", ""]) + cifre(s.r, s.r.randint(4, 7))


def indirizzo(r):
    civ = str(r.randint(1, 240)) + r.choice(["", "", "", "", "/A", "/B", " bis", "/c", " int. 4", "A"])
    return f"{r.choice(ODONIMI)} {r.choice(INTITOLAZIONI + list(COGNOMI[:300]))}{r.choice([' ', ', ', ' n. ', ' '])}{civ}"


def fisso(r):
    p, n = r.choice(["02", "06", "011", "081", "051", "055", "0461", "045", "049", "010", "091", "0471", "030", "035",
                     "0464", "0422", "071", "080", "070", "0432"]), cifre(r, r.randint(6, 8))
    return r.choice([f"{p} {n}", f"{p}/{n}", f"{p}{n}", f"+39 {p} {n}", f"{p}-{n}", f"{p}.{n}", f"(+39) {p} {n[:3]} {n[3:]}"])


def cellulare(r):
    p, n = r.choice(["320", "328", "329", "333", "335", "338", "339", "340", "342", "345", "346", "347", "348", "349",
                     "351", "366", "368", "370", "380", "388", "389", "391", "392", "393"]), cifre(r, 7)
    return r.choice([f"{p} {n}", f"{p}{n}", f"+39 {p} {n}", f"+39{p}{n}", f"{p} {n[:3]} {n[3:]}", f"{p}-{n}",
                     f"{p}/{n}", f"{p}.{n[:2]}.{n[2:4]}.{n[4:]}", f"0039 {p} {n}", f"+39 {p} {n[:3]} {n[3:]}",
                     f"{p} {n[:2]} {n[2:4]} {n[4:]}", f"({p}) {n}"])


def _fmt_iban(r, i):
    f = r.random()
    if f < .45:
        return i
    if f < .80:
        return " ".join(i[k:k + 4] for k in range(0, 27, 4))
    if f < .88:
        return i.lower()
    if f < .94:
        return f"{i[:4]} {i[4]} {i[5:10]} {i[10:15]} {i[15:]}"
    return "-".join(i[k:k + 4] for k in range(0, 27, 4))


FAMOSI_OMONIMI = ["Giuseppe Verdi", "Vasco Rossi", "Valentino Rossi", "Mario Draghi", "Giuseppe Conte", "Matteo Renzi", "Matteo Salvini",
                  "Enrico Letta", "Paolo Maldini", "Roberto Baggio", "Francesco Totti", "Laura Pausini", "Lucio Dalla", "Renzo Piano",
                  "Carlo Rubbia", "Elsa Fornero", "Giovanni Falcone", "Aldo Moro", "Romano Prodi", "Enzo Ferrari", "Giorgio Armani",
                  "Primo Levi", "Umberto Eco", "Italo Calvino", "Sergio Mattarella", "Antonio Tajani", "Marco Polo", "Andrea Bocelli"]


class Persona:
    ETI = dict(nc="PERSONA", cn="PERSONA", CN="PERSONA", NC="PERSONA", n="PERSONA", c="PERSONA", C="PERSONA",
               N="PERSONA", nc_min="PERSONA", iniz="PERSONA", x="PERSONA", n_c="PERSONA", c_n="PERSONA", cC="PERSONA",
               cvn="PERSONA",
               email="EMAIL", pec="EMAIL", email_dett="EMAIL", lav="EMAIL", tel="TELEFONO", fisso="TELEFONO",
               tel_parole="TELEFONO", cf="CF", cf_min="CF", cf_sp="CF", cf_err="CF", dn="DATA_NASCITA",
               citta="CITTA", luogo_n="CITTA", via="INDIRIZZO", cap="CAP", iban="IBAN", carta="CARTA", cvv="CARTA_SEC",
               scad="CARTA_SEC", targa="TARGA", vin="ID_VEICOLO", ci="DOC_ID", passap="DOC_ID", patente="DOC_ID",
               ts="DOC_ID", user="ACCOUNT", upn="ACCOUNT", handle="ACCOUNT", matr="ID_PRATICA",
               eta="ETA", sig="TITOLO", tit="TITOLO", sesso="GENERE")

    def __init__(s, r, az=None):
        s.r, s.az = r, az
        s.f = r.random() < .45
        if r.random() < .15:
            s.nome, s.cogn = r.choice(STRANIERI_N), r.choice(STRANIERI_C)
        else:
            s.nome = r.choice(NOMI_F if s.f else NOMI_M)
            if r.random() < .10:
                s.nome += " " + r.choice(NOMI_F if s.f else NOMI_M)
            s.cogn = r.choice(COGNOMI)
            f = r.random()
            if f < .07:
                s.cogn = r.choice(["De ", "Di ", "Lo ", "D'", "Dal ", "Della ", "La ", "Del "]) + s.cogn
            elif f < .12:
                s.cogn += r.choice([" ", " ", "-"]) + r.choice(COGNOMI)
        if r.random() < .012:   # un omonimo di una persona famosa resta una persona da proteggere
            s.nome, _, s.cogn = r.choice([x for x in FAMOSI_OMONIMI]).partition(" ")
        s._n, s._c = pulisci(s.nome).lower(), pulisci(s.cogn).lower()
        s._g, s._m, s._a = r.randint(1, 28), r.randint(1, 12), r.randint(1940, 2015)
        s._citta, s._via, s._cap, s._ln = r.choice(COMUNI), indirizzo(r), cifre(r, 5), r.choice(COMUNI)
        s._prov = r.choice(PROVIDER)
        s._user = r.choice([f"{s._n[0]}.{s._c}", f"{s._n[0]}{s._c}", f"{s._n}.{s._c}", f"{s._c}{s._n[0]}", f"{s._c}.{s._n}",
                            f"{s._n}{s._c[0]}", f"{s._c}", f"{s._n}.{s._c}{r.randint(1, 99)}", f"{s._n[:3]}{s._c[:3]}",
                            f"{s._n}_{s._c}"])
        b = _tre(s.cogn) + _tre(s.nome, True) + f"{s._a % 100:02}" + "ABCDEHLMPRST"[s._m - 1] + \
            f"{s._g + (40 if s.f else 0):02}" + r.choice("ABCDEFGHILM") + cifre(r, 3)
        s._cf = b + _ctrl(b)

    def nc(s): return f"{s.nome} {s.cogn}"
    def cn(s): return f"{s.cogn} {s.nome}"
    def CN(s): return s.cn().upper()
    def NC(s): return s.nc().upper()
    def n(s): return s.nome
    def N(s): return s.nome.upper()
    def c(s): return s.cogn
    def C(s): return s.cogn.upper()
    def cC(s): return f"{s.cogn.upper()} {s.nome}"
    def cvn(s): return f"{s.cogn}, {s.nome}"
    def nc_min(s): return s.nc().lower()
    def iniz(s): return s.r.choice([f"{s.nome[0]}. {s.cogn}", f"{s.cogn} {s.nome[0]}.", f"{s.nome[0]}.{s.cogn}"])
    def n_c(s): return s.r.choice(["_", "-", ".", ""]).join([s.nome.replace(" ", ""), s.cogn.replace(" ", "")])
    def c_n(s): return s.r.choice(["_", "-", "."]).join([s.cogn.replace(" ", ""), s.nome.replace(" ", "")]).upper() \
        if s.r.random() < .4 else s.r.choice(["_", "-"]).join([s._c, s._n])
    def x(s): return s.r.choice([s.nc] * 6 + [s.cn] * 3 + [s.CN, s.CN, s.NC, s.NC, s.nc_min, s.cC, s.iniz, s.cvn])()
    def email(s): return f"{s.r.choice([s._user, s._user, s._n + '.' + s._c, s._n + s._c + cifre(s.r, 2), s._c + str(s._a)])}@{s._prov}"
    def lav(s): return f"{s._user}@{s.az._dom if s.az else s._prov}"
    def pec(s): return f"{s._n}.{s._c}@{s.r.choice(PEC)}"
    def email_dett(s): return f"{s._n} punto {s._c} chiocciola {s._prov.split('.')[0]} punto {s._prov.split('.')[-1]}"
    def tel(s): return cellulare(s.r)
    def fisso(s): return fisso(s.r)
    def tel_parole(s): return " ".join(CIFRE[int(d)] for d in "3" + cifre(s.r, 9))
    def cf(s): return s._cf
    def cf_min(s): return s._cf.lower()
    def cf_sp(s): return f"{s._cf[:3]} {s._cf[3:6]} {s._cf[6:11]} {s._cf[11:]}"
    def cf_err(s): return s._cf[:15] + s.r.choice([c for c in string.ascii_uppercase if c != s._cf[15]])
    def dn(s):
        f = s.r.random()
        return (f"{s._g:02}/{s._m:02}/{s._a}" if f < .5 else f"{s._g} {MESI[s._m - 1]} {s._a}" if f < .7 else
                f"{s._g:02}.{s._m:02}.{s._a}" if f < .8 else f"{s._g:02}-{s._m:02}-{s._a}" if f < .9 else
                f"{s._g}/{s._m}/{s._a % 100:02}")
    def eta(s): return str(2026 - s._a)
    def citta(s): return s._citta
    def CITTA(s): return s._citta.upper()
    def luogo_n(s): return s._ln
    def via(s): return s._via
    def cap(s): return s._cap
    def prov(s): return s.r.choice(PROV)
    def iban(s): return _fmt_iban(s.r, iban(s.r))
    def carta(s):
        pref = s.r.choice(["4", "4", "51", "52", "53", "54", "55"])
        n = luhn(pref + cifre(s.r, 15 - len(pref)))
        return s.r.choice([n, " ".join(n[i:i + 4] for i in range(0, 16, 4)), "-".join(n[i:i + 4] for i in range(0, 16, 4))])
    def cvv(s): return cifre(s.r, 3)
    def scad(s): return f"{s.r.randint(1, 12):02}/{s.r.randint(26, 31)}"
    def targa(s):
        l, t = caso(s.r, 4, "ABCDEFGHJKLMNPRSTVWXYZ"), cifre(s.r, 3)
        return s.r.choice([f"{l[:2]}{t}{l[2:]}", f"{l[:2]}{t}{l[2:]}", f"{l[:2]} {t} {l[2:]}", f"{l[:2]}-{t}-{l[2:]}",
                           f"{l[:2]}{t}{cifre(s.r, 2)}", (l[:2] + t + l[2:]).lower()])
    def vin(s): return s.r.choice(["ZFA", "ZAR", "WVW", "VF1", "WBA", "ZLA", "JTD", "W0L"]) + caso(s.r, 14, "ABCDEFGHJKLMNPRSTUVWXYZ0123456789")
    def ci(s): return s.r.choice([f"C{caso(s.r, 1, 'ABCDEF')}{cifre(s.r, 5)}{caso(s.r, 2, string.ascii_uppercase)}",
                                 f"A{caso(s.r, 1, 'RSTUVXY')} {cifre(s.r, 7)}", f"A{caso(s.r, 1, 'RSTUVXY')}{cifre(s.r, 7)}"])
    def passap(s): return s.r.choice(["YA", "YB", "AA", "YC"]) + cifre(s.r, 7)
    def patente(s): return s.r.choice([f"{s.r.choice(PROV)}{cifre(s.r, 7)}{caso(s.r, 1, string.ascii_uppercase)}",
                                      f"U1{caso(s.r, 1, string.ascii_uppercase)}{cifre(s.r, 6)}{caso(s.r, 1, string.ascii_uppercase)}"])
    def ts(s): return "8038000" + cifre(s.r, 13)
    def user(s): return s._user
    def upn(s): return f"{s._user}@{(s.az._dom.split('.')[0] if s.az else 'azienda')}.{s.r.choice(['local', 'lan', 'intra', 'onmicrosoft.com', 'loc'])}"
    def handle(s): return "@" + s.r.choice([s._user, s._n + s._c + cifre(s.r, 2), s._n + "_" + s._c, s._c + "." + s._n])
    def matr(s): return s.r.choice(["", "M", "MAT-", "00"]) + cifre(s.r, s.r.randint(4, 6))
    def sig(s): return "Sig.ra" if s.f else "Sig."
    def tit(s): return s.r.choice(TITOLI_F if s.f else TITOLI_M)
    def sesso(s): return s.r.choice(["femmina", "F", "donna", "femminile", "Femmina"] if s.f else ["maschio", "M", "uomo", "maschile", "Maschio"])
    def oa(s): return "a" if s.f else "o"


class IT:
    ETI = dict(host="HOSTNAME", srv="HOSTNAME", fqdn="HOSTNAME", host_min="HOSTNAME", dom_loc="DOMINIO",
               tenant="DOMINIO", netbios="DOMINIO", pub="DOMINIO", url="URL", url_int="URL", share="URL",
               ip="IP", ipp="IP", cidr="IP", ip6="IP", mac="MAC", guid="ID_CLOUD", aws="ID_CLOUD", pw="SEGRETO",
               token="SEGRETO", jwt="SEGRETO", psk="SEGRETO", otp="SEGRETO", recovery="SEGRETO", bitlocker="SEGRETO",
               lic="SEGRETO", hash="SEGRETO", pem="SEGRETO", connstr="SEGRETO", webhook="SEGRETO", snmp="SEGRETO",
               pin="SEGRETO", svc="ACCOUNT", adm="ACCOUNT", ad="ACCOUNT", sid="ACCOUNT", dn="ACCOUNT",
               serial="ID_DISPOSITIVO", tag="ID_DISPOSITIVO", imei="ID_DISPOSITIVO", iccid="ID_DISPOSITIVO",
               anydesk="ID_DISPOSITIVO", tv="ID_DISPOSITIVO", nodo="ID_DISPOSITIVO")

    def __init__(s, r, az, p):
        s.r, s.az, s.p = r, az, p
        s._base = az._dom.split(".")[0].replace("-", "")[:12]
        s._loc = s._base + r.choice([".local", ".lan", ".intra", ".loc", ".internal", ".local", ".corp"])
        s._nb = s._base.upper()[:r.randint(4, 10)]
        s._rete = r.choice([f"192.168.{r.randint(0, 254)}", f"10.{r.randint(0, 254)}.{r.randint(0, 254)}",
                            f"172.{r.randint(16, 31)}.{r.randint(0, 254)}", "192.168.1", "192.168.0", "10.0.0"])

    def host(s):
        r, c, n, g = s.r, pulisci(s.p.cogn).upper(), pulisci(s.p.nome).upper(), s.az.sigla
        return r.choice([f"PC-{c}", f"NB-{n[0]}{c}-{r.randint(1, 9):02}", "DESKTOP-" + caso(r, 7), "LAPTOP-" + caso(r, 8),
                         f"{g}-PC-{r.randint(1, 250):03}", f"WKS{r.randint(1, 999):03}", f"NB{r.randint(1, 9999):04}",
                         f"{n.lower()[0]}{c.lower()}-mbp", f"PC{r.randint(1, 99):02}-{r.choice(REPARTI)}",
                         f"{g}NB{r.randint(1, 99):02}", f"pc-{c.lower()}", f"{g}-{r.choice(REPARTI)}-{r.randint(1, 30):02}",
                         f"PC{r.randint(100, 999)}", f"{g}{r.choice(['WS', 'LT', 'DT', 'NB', 'PC'])}{cifre(r, 3)}",
                         f"NOTEBOOK-{c}", f"{c}-PC", f"MacBook-di-{n.capitalize()}", f"{n[:1]}{c[:6]}-NB", "WIN-" + caso(r, 11),
                         f"{r.choice(REPARTI)}{r.randint(1, 40):02}", f"PC_{n}_{c[0]}", f"postazione{r.randint(1, 30)}"])

    def srv(s):
        r, g = s.r, s.az.sigla
        ruolo = r.choice(["DC", "FILE", "SQL", "APP", "TS", "RDS", "PRINT", "MAIL", "WEB", "BKP", "ERP", "DB", "FS", "VEEAM",
                          "GEST", "HV", "ESX", "NAS", "FW", "SW", "AP", "PBX", "NVR", "PROXY", "WSUS"])
        return r.choice([f"SRV-{ruolo}{r.randint(1, 4):02}", f"SRV{ruolo}{r.randint(1, 9)}", f"{g}-{ruolo}-{r.randint(1, 3):02}",
                         f"VM-{ruolo}-{r.choice(['PROD', 'TEST', 'DEV'])}", f"{ruolo}{r.randint(1, 9):02}", f"srv-{ruolo.lower()}-{r.randint(1, 9):02}",
                         f"{g}SRV{r.randint(1, 20):02}", f"{ruolo}-{pulisci(s.az._citta).upper()[:3] or 'MI'}-{r.randint(1, 9):02}",
                         f"{g}{ruolo}{r.randint(1, 9)}", f"{ruolo.lower()}{r.randint(1, 9)}.{s._loc}", f"SERVER{r.randint(1, 9)}",
                         f"{g}-{ruolo}"])

    def fqdn(s): return f"{s.r.choice([s.host, s.srv])().split('.')[0].lower()}.{s._loc}"
    def host_min(s): return s.host().lower()
    def dom_loc(s): return s._loc
    def tenant(s): return s._base + ".onmicrosoft.com"
    def netbios(s): return s._nb
    def pub(s): return s.r.choice(["", "", "mail.", "vpn.", "portal.", "remote.", "webmail.", "owa.", "cloud.", "ftp.", "gest."]) + s.az._dom
    def url(s):
        r = s.r
        return r.choice([f"https://{s.pub()}", f"https://{s.pub()}/{r.choice(['login', 'owa', 'portal', 'admin', 'webmail', 'app/index.php', 'remote/login'])}",
                         f"https://{s._base}.sharepoint.com/sites/{r.choice(['Amministrazione', 'Commerciale', 'HR', 'Direzione', 'Progetti'])}/Documenti%20condivisi",
                         f"https://{s._base}-my.sharepoint.com/personal/{s.p._user.replace('.', '_')}_{s.az._dom.replace('.', '_')}",
                         f"http://{s.pub()}:{r.choice([8080, 8443, 5000, 9090])}/", f"https://www.{s.az._dom}/area-riservata?id={cifre(r, 6)}",
                         f"www.{s.az._dom}", f"https://{s._base}.{r.choice(['zendesk.com', 'atlassian.net', 'freshdesk.com', 'my.salesforce.com'])}/tickets/{cifre(r, 5)}"])
    def url_int(s): return s.r.choice([f"https://{s.ipp()}:{s.r.choice([443, 8443, 4444, 5001, 10443])}", f"http://{s.ipp()}/admin",
                                       f"http://{s.fqdn()}:{s.r.choice([8080, 9392, 3000])}/", f"https://{s.fqdn()}/"])
    def share(s): return f"\\\\{s.srv().split('.')[0]}\\{s.r.choice(['Dati', 'Comune', 'Amministrazione', 'Scansioni', 'Backup$', 'Utenti', 'Commesse', 'Public'])}" + \
        (f"\\{s.r.choice(['Contabilita', 'Clienti', 'HR', '2025', 'Offerte'])}" if s.r.random() < .5 else "")
    def ipp(s): return f"{s._rete}.{s.r.randint(1, 254)}"
    def ip(s): return f"{s.r.choice([2, 5, 31, 37, 46, 62, 79, 80, 82, 85, 87, 93, 95, 109, 151, 176, 185, 188, 193, 212, 213, 217])}.{s.r.randint(0, 255)}.{s.r.randint(0, 255)}.{s.r.randint(1, 254)}"
    def cidr(s): return f"{s._rete}.0/{s.r.choice([24, 24, 24, 23, 25, 16, 22])}"
    def ip6(s): return s.r.choice(["fe80::", "2001:db8:", "2a01:4f8:", "fd00:"]) + ":".join(caso(s.r, s.r.randint(1, 4), "0123456789abcdef") for _ in range(s.r.randint(2, 4)))
    def mac(s):
        b = [caso(s.r, 2, "0123456789ABCDEF") for _ in range(6)]
        return s.r.choice([":".join(b), "-".join(b), ":".join(b).lower(), "-".join(b).lower(),
                           ".".join("".join(b)[i:i + 4] for i in (0, 4, 8)).lower(), "".join(b)])
    def guid(s): return "-".join(caso(s.r, n, "0123456789abcdef") for n in (8, 4, 4, 4, 12))
    def aws(s): return cifre(s.r, 12)
    def pw(s):
        r, w = s.r, s.r.choice(PAROLE_PW)
        sim = r.choice("!!!.?#@$*-_+&%")
        return r.choice([f"{w}{r.randint(2018, 2026)}{sim}", f"{w}{sim}{cifre(r, r.randint(2, 4))}", caso(r, r.randint(10, 18), B64 + "!@#$%&*?-_+"),
                         f"{w}-{r.choice(PAROLE_PW)}-{cifre(r, 2)}", f"{pulisci(s.p.cogn).capitalize()}{cifre(r, 3)}{sim}",
                         f"{w.lower()}{cifre(r, r.randint(1, 4))}", f"{w}{cifre(r, 2)}", caso(r, r.randint(8, 12), B64),
                         f"{w[0]}{w[1:].replace('a', '@').replace('o', '0').replace('e', '3')}{sim}{cifre(r, 2)}",
                         f"{s.az.sigla.capitalize()}{sim}{r.randint(2020, 2026)}", f"{w}{r.choice(PAROLE_PW)}{cifre(r, 2)}{sim}",
                         f"{sim}{w}{cifre(r, 3)}", f"{w.upper()}{cifre(r, 4)}", caso(r, 20, B64 + "!@#$%^&*()-_=+[]{}")])
    def pin(s): return cifre(s.r, s.r.choice([4, 4, 5, 6, 8]))
    def token(s):
        r = s.r
        return r.choice(["ghp_" + caso(r, 36, B64), "github_pat_" + caso(r, 22, B64) + "_" + caso(r, 59, B64), "AKIA" + caso(r, 16),
                         caso(r, 40, B64 + "+/"), "sk-" + caso(r, 48, B64), "sk-proj-" + caso(r, 64, B64 + "-_"),
                         f"xoxb-{cifre(r, 12)}-{cifre(r, 13)}-{caso(r, 24, B64)}", "SG." + caso(r, 22, B64) + "." + caso(r, 43, B64 + "-_"),
                         caso(r, 32, "0123456789abcdef"), caso(r, 40, "0123456789abcdef"), caso(r, 64, "0123456789abcdef"),
                         caso(r, 3, B64) + "8Q~" + caso(r, 34, B64 + "._-~"), "glpat-" + caso(r, 20, B64 + "-_"),
                         "AIza" + caso(r, 35, B64 + "-_"), "pk_live_" + caso(r, 24, B64), "rk_live_" + caso(r, 24, B64),
                         "Bearer " + caso(r, 44, B64 + "-_"), caso(r, 32, B64), "dop_v1_" + caso(r, 64, "0123456789abcdef"),
                         "npm_" + caso(r, 36, B64), "hf_" + caso(r, 34, B64)])
    def jwt(s): return "eyJ" + caso(s.r, 33, B64) + ".eyJ" + caso(s.r, s.r.randint(40, 120), B64) + "." + caso(s.r, 43, B64 + "-_")
    def psk(s): return s.r.choice([s.pw(), caso(s.r, s.r.randint(12, 24), B64), f"{s.az.sigla}wifi{cifre(s.r, 4)}", f"{s.r.choice(PAROLE_PW)}{s.r.choice(PAROLE_PW)}{cifre(s.r, 2)}"])
    def otp(s): return s.r.choice([cifre(s.r, 6), f"{cifre(s.r, 3)} {cifre(s.r, 3)}", cifre(s.r, 8)])
    def recovery(s): return "-".join(caso(s.r, 4) for _ in range(s.r.choice([3, 4, 4])))
    def bitlocker(s): return "-".join(cifre(s.r, 6) for _ in range(8))
    def lic(s): return "-".join(caso(s.r, 5) for _ in range(5))
    def hash(s): return s.r.choice([caso(s.r, 32, "0123456789abcdef"), "aad3b435b51404eeaad3b435b51404ee:" + caso(s.r, 32, "0123456789abcdef"),
                                    "$2b$12$" + caso(s.r, 53, B64 + "./"), "$6$" + caso(s.r, 8, B64) + "$" + caso(s.r, 86, B64 + "./"),
                                    caso(s.r, 64, "0123456789abcdef")])
    def pem(s):
        t = s.r.choice(["RSA PRIVATE KEY", "PRIVATE KEY", "OPENSSH PRIVATE KEY", "EC PRIVATE KEY"])
        return f"-----BEGIN {t}-----\n" + "\n".join(caso(s.r, 64, B64 + "+/") for _ in range(s.r.randint(2, 5))) + f"\n{caso(s.r, 30, B64)}==\n-----END {t}-----"
    def connstr(s):
        r, db, u = s.r, s.r.choice(["gestionale", "erp", "crm", "produzione", "contab", "app", "magazzino"]), s.r.choice(["sa", "admin", "dbuser", s.svc(), "app_user", "postgres", "root"])
        h = r.choice([s.srv().split(".")[0], s.ipp(), s.fqdn()])
        return r.choice([f"Server={h};Database={db};User Id={u};Password={s.pw()};", f"postgresql://{u}:{s.pw()}@{h}:5432/{db}",
                         f"mongodb+srv://{u}:{s.pw()}@cluster0.{caso(r, 5, string.ascii_lowercase)}.mongodb.net/{db}",
                         f"mysql://{u}:{s.pw()}@{h}:3306/{db}", f"Data Source={h},1433;Initial Catalog={db};User ID={u};Password={s.pw()};Encrypt=True",
                         f"redis://:{s.pw()}@{h}:6379/0", f"jdbc:sqlserver://{h}:1433;databaseName={db};user={u};password={s.pw()}",
                         f"DefaultEndpointsProtocol=https;AccountName={s._base};AccountKey={caso(r, 86, B64 + '+/')}==;EndpointSuffix=core.windows.net",
                         f"amqp://{u}:{s.pw()}@{h}:5672/", f"ftp://{u}:{s.pw()}@{s.pub()}"])
    def webhook(s):
        r = s.r
        return r.choice([f"https://hooks.slack.com/services/T{caso(r, 10)}/B{caso(r, 10)}/{caso(r, 24, B64)}",
                         f"https://{s._base}.webhook.office.com/webhookb2/{s.guid()}@{s.guid()}/IncomingWebhook/{caso(r, 32, '0123456789abcdef')}/{s.guid()}",
                         f"https://discord.com/api/webhooks/{cifre(r, 18)}/{caso(r, 68, B64 + '-_')}",
                         f"https://api.telegram.org/bot{cifre(r, 10)}:{caso(r, 35, B64 + '-_')}/sendMessage",
                         f"https://{s.pub()}/api/hook?token={caso(r, 32, B64)}"])
    def snmp(s): return s.r.choice([f"{s.az.sigla.lower()}_ro", f"snmp{s.az.sigla}{cifre(s.r, 3)}", caso(s.r, 10, B64), f"{s._base}RW!"])
    def svc(s): return s.r.choice(["svc_", "svc-", "srv_", "sa_", "svc.", "service_"]) + s.r.choice(["backup", "sql", "veeam", "scan", "ldap", "ninja", "sync", "erp", "stampa", "sharepoint", "monitor", "task"])
    def adm(s): return s.r.choice([f"adm.{s.p._c}", f"adm-{s.p._user}", f"admin.{s.p._c}", f"{s.p._user}_adm", f"{s.az.sigla.lower()}admin", f"admin{s.az.sigla.lower()}", f"a-{s.p._user}", f"da_{s.p._c}"])
    def ad(s): return f"{s._nb}\\{s.r.choice([s.p._user, s.p._user, s.adm(), s.svc()])}"
    def sid(s): return f"S-1-5-21-{cifre(s.r, 10)}-{cifre(s.r, 10)}-{cifre(s.r, 9)}-{s.r.randint(1000, 9999)}"
    def dn(s): return f"CN={s.p.nc()},OU={s.r.choice(['Utenti', 'Users', 'Amministrazione', 'Staff', 'Sede'])},DC={s._loc.split('.')[0]},DC={s._loc.split('.')[1]}"
    def serial(s): return s.r.choice(["5CD" + caso(s.r, 7), "5CG" + caso(s.r, 7), "PF" + caso(s.r, 6), "PC" + caso(s.r, 6), "CND" + caso(s.r, 7),
                                      "MXL" + caso(s.r, 7), caso(s.r, 10), "S" + caso(s.r, 11), "FGT60F" + caso(s.r, 10), "C02" + caso(s.r, 9),
                                      "R9" + caso(s.r, 6), caso(s.r, 12), "VNB" + caso(s.r, 7), caso(s.r, 15), caso(s.r, 17), caso(s.r, 18),
                                      caso(s.r, 20), caso(s.r, 22), "CN0" + caso(s.r, 17), cifre(s.r, 14) + caso(s.r, 4), caso(s.r, 24),
                                      caso(s.r, 16).lower(), "S" + cifre(s.r, 17)])
    def tag(s): return caso(s.r, 7)
    def imei(s): return luhn(s.r.choice(["35", "86", "01", "49"]) + cifre(s.r, 12))
    def iccid(s): return "8939" + cifre(s.r, s.r.choice([15, 16]))
    def anydesk(s): return s.r.choice([f"{cifre(s.r, 3)} {cifre(s.r, 3)} {cifre(s.r, 3)}", cifre(s.r, 9), f"1 {cifre(s.r, 3)} {cifre(s.r, 3)} {cifre(s.r, 3)}"])
    def tv(s): return s.r.choice([f"{cifre(s.r, 1)} {cifre(s.r, 3)} {cifre(s.r, 3)} {cifre(s.r, 3)}", f"{cifre(s.r, 3)} {cifre(s.r, 3)} {cifre(s.r, 3)}", cifre(s.r, 10)])
    def nodo(s): return s.r.choice(["", "NODE-", "dev_"]) + cifre(s.r, s.r.randint(4, 6))
    def ssid(s): return s.r.choice([f"{s.az.sigla}-WiFi", f"{s._base}_guest", "Ospiti", f"{s.az.sigla}_UFFICI", "FRITZ!Box 7590", "Vodafone-" + caso(s.r, 8)])
    def porta(s): return str(s.r.choice([22, 80, 443, 3389, 8443, 1433, 445, 25, 587, 993, 5060, 1194, 51820]))


class Varie:
    ETI = dict(marchio="ORG", polizza="ID_PRATICA", sinistro="ID_PRATICA", cartella="ID_PRATICA", prot="ID_PRATICA", rg="ID_PRATICA",
               pren="ID_PRATICA", pnr="ID_PRATICA", ordine="ID_PRATICA", cli="ID_PRATICA", mutuo="ID_PRATICA",
               nre="ID_PRATICA", pratica="ID_PRATICA", inps="ID_PRATICA", catasto="CATASTO", pod="ID_UTENZA",
               pdr="ID_UTENZA", forn="ID_UTENZA", contatore="ID_UTENZA",
               data="DATA", ora="ORA", diag="SALUTE", farmaco="SALUTE")

    def __init__(s, r): s.r = r
    def data(s): return data(s.r)
    def ora(s): return f"{s.r.randint(7, 20):02}{s.r.choice([':', '.', ':'])}{s.r.choice(['00', '15', '30', '45', cifre(s.r, 1) + '5'])}"
    def imp(s): return s.r.choice([f"{s.r.randint(20, 9999)},{cifre(s.r, 2)} €", f"€ {s.r.randint(1, 250)}.{cifre(s.r, 3)},00", f"{s.r.randint(50, 5000)} euro", f"Euro {s.r.randint(1, 90)}.{cifre(s.r, 3)}"])
    def anno(s): return str(s.r.randint(2018, 2026))
    def ticket(s): return s.r.choice(["#", "n. ", "TK-", "INC", "#00", "", "SV", "SV ", "SR-", "RITM", "REQ", "CHG", "RFC ", "RFC-", "DDT n. ",
                                      "DDT ", "ODA ", "PRJ-", "CS", "WO-", "rif. ", "numero ", "ticket ", "ID ", "riga ", "pos. "]) + cifre(s.r, s.r.randint(2, 8))
    def legge(s):
        r = s.r
        return r.choice([f"art. {r.randint(1, 2969)} c.{r.choice('pc')}.", f"L. {r.randint(1, 999)}/{r.randint(1942, 2025)}",
                         f"D.Lgs. {r.randint(1, 400)}/{r.choice(['2003', '2008', '2001', '2016', '2018', '2023', '08', '01', '03'])}",
                         "L. 104/92", f"art. {r.randint(1, 99)} L. 300/1970", "Regolamento UE 2016/679", "Regulation (EU) 2016/679",
                         "D.Lgs. 196/2003", "D.Lgs. 81/08", f"DPR {r.randint(1, 999)}/{r.randint(1970, 2020)}", f"art. {r.randint(1, 120)} del GDPR",
                         "ISO " + r.choice(["9001", "27001", "14001", "45001", "22301", "9001:2015", "27017", "20000-1"]), "ISO/IEC 27001:2022",
                         "UNI EN ISO 9001:2015", f"direttiva {r.randint(2000, 2024)}/{r.randint(1, 999)}/UE", f"codice tributo {r.randint(1001, 9999)}",
                         f"comma {r.randint(1, 12)}", f"CVE-{r.randint(2015, 2026)}-{r.randint(1000, 49999)}", f"MITRE ATT&CK T{r.randint(1001, 1600)}.{r.randint(1, 9):03}",
                         f"CVSS {r.randint(1, 10)}.{r.randint(0, 9)}", f"{r.randint(2010, 2022)}-{r.randint(2023, 2026)}", "direttiva NIS2",
                         f"codice di uscita {r.randint(1, 255)}", f"livello {r.choice('ABCD')}{r.randint(1, 3)} CCNL {r.choice(['Metalmeccanici', 'Commercio', 'Terziario', 'Studi professionali'])}",
                         f"interno {r.randint(1, 30)}", f"piano {r.randint(1, 9)}", f"scala {r.choice('ABC')}", f"parcella n. {r.randint(1, 300)}/{r.randint(2020, 2026)}"])
    def sigla(s): return s.r.choice(SIGLE)
    def titolo(s):
        w = s.r.choice(TITOLI)
        return s.r.choice([w.upper(), w.upper(), w.capitalize(), w.title(), w])
    def cmd(s): return s.r.choice(COMANDI)
    def sep(s): return s.r.choice(["-", "-", "-", "_", "_", "=", "*", "#", "~", "·", "- ", "* "]) * s.r.randint(4, 72)
    def invisibile(s): return "".join(s.r.choice(["͏  ", "͏  ", "‌ ", " ", "​", "͏", " "]) for _ in range(s.r.randint(4, 60)))
    def simbolo(s): return s.r.choice(["#", "*", "_", "-", "@", "👍", "👍🏻", "✅", "🤖", ">", ">>", "|", "•", "→", "...", "!!!", "???", "(", ")", "/", "=", "+"])
    def fatt(s): return s.r.choice([f"{s.r.randint(1, 4000)}/{s.anno()}", f"FT{cifre(s.r, 5)}", f"{s.r.randint(1, 900)}/PA", f"FPR {s.r.randint(1, 900)}/{s.r.randint(22, 26)}"])
    def ver(s): return s.r.choice([f"{s.r.randint(1, 24)}.{s.r.randint(0, 12)}.{s.r.randint(0, 40)}", f"v{s.r.randint(1, 9)}.{s.r.randint(0, 9)}", f"{s.r.choice(['22H2', '23H2', '24H2'])}", f"10.0.{s.r.choice([19045, 22631, 26100])}.{cifre(s.r, 4)}", f"{s.r.randint(7, 8)}.{s.r.randint(0, 4)}.{s.r.randint(0, 17)}"])
    def kb(s): return "KB50" + cifre(s.r, 5)
    def evt(s): return str(s.r.choice([4624, 4625, 4740, 7031, 1001, 41, 6008, 10016, 4776]))
    def err(s): return s.r.choice(["0x8007" + caso(s.r, 4, "0123456789ABCDEF"), "0xC000" + caso(s.r, 4, "0123456789ABCDEF"), f"errore {s.r.randint(400, 599)}", "AADSTS" + cifre(s.r, 5), "0x80004005"])
    def prod(s): return s.r.choice(PRODOTTI)
    def ente(s): return s.r.choice(ENTI) if s.r.random() < .7 else s.r.choice(ENTI_LUOGO) + " " + s.r.choice(COMUNI)
    def marchio(s): return s.r.choice(MARCHI)
    def qta(s): return str(s.r.randint(1, 60))
    def perc(s): return f"{s.r.randint(1, 99)}%"
    def diag(s): return s.r.choice(DIAGNOSI)
    def farmaco(s): return s.r.choice(FARMACI)
    def polizza(s): return s.r.choice([f"POL-{s.anno()}-{cifre(s.r, 6)}", cifre(s.r, s.r.randint(8, 10)), f"{caso(s.r, 2, string.ascii_uppercase)}{cifre(s.r, 8)}", f"{cifre(s.r, 3)}/{cifre(s.r, 7)}", f"RCA{cifre(s.r, 9)}", f"{cifre(s.r, 4)}.{cifre(s.r, 6)}.{cifre(s.r, 2)}"])
    def sinistro(s): return s.r.choice([f"SIN/{s.anno()}/{cifre(s.r, 6)}", f"{s.anno()}-{cifre(s.r, 7)}", f"S{cifre(s.r, 9)}", f"{cifre(s.r, 2)}/{s.anno()}/{cifre(s.r, 5)}", f"SX{cifre(s.r, 8)}"])
    def cartella(s): return s.r.choice([f"CC-{s.anno()}-{cifre(s.r, 6)}", f"{s.anno()}/{cifre(s.r, 6)}", cifre(s.r, 8), f"CCE{cifre(s.r, 7)}"])
    def prot(s): return s.r.choice([f"{cifre(s.r, 5)}/{s.anno()}", f"{s.anno()}/{cifre(s.r, 6)}", f"PG/{s.anno()}/{cifre(s.r, 6)}", f"{cifre(s.r, 7)}", f"U.{cifre(s.r, 7)}.{s.data()[:5].replace('/', '-')}-{s.anno()}"])
    def rg(s): return f"{s.r.randint(1, 9999)}/{s.anno()}"
    def pren(s): return s.r.choice([cifre(s.r, 10), "BK" + cifre(s.r, 8), caso(s.r, 8), f"{cifre(s.r, 4)}.{cifre(s.r, 3)}.{cifre(s.r, 3)}", "HTL-" + cifre(s.r, 7)])
    def pnr(s): return caso(s.r, 6)
    def ordine(s): return s.r.choice(["#" + cifre(s.r, 9), "ORD-" + cifre(s.r, 7), f"{cifre(s.r, 3)}-{cifre(s.r, 7)}-{cifre(s.r, 7)}", "IT" + cifre(s.r, 10), f"{s.anno()}{cifre(s.r, 6)}"])
    def cli(s): return s.r.choice(["CL", "C", "K", "CLI", ""]) + cifre(s.r, s.r.randint(5, 9))
    def mutuo(s): return s.r.choice([cifre(s.r, 10), f"MU/{cifre(s.r, 8)}", f"{cifre(s.r, 4)}/{cifre(s.r, 8)}"])
    def nre(s): return cifre(s.r, 4) + "A" + cifre(s.r, 10)
    def pratica(s): return s.r.choice([f"PR-{s.anno()}-{cifre(s.r, 5)}", f"{cifre(s.r, 6)}/{s.anno()}", f"P{cifre(s.r, 8)}", f"{caso(s.r, 3, string.ascii_uppercase)}/{cifre(s.r, 6)}"])
    def inps(s): return s.r.choice([cifre(s.r, 10), f"{cifre(s.r, 8)}/{cifre(s.r, 2)}"])
    def catasto(s):
        f, p, sb = s.r.randint(1, 180), s.r.randint(1, 2400), s.r.randint(1, 40)
        return s.r.choice([f"foglio {f}, particella {p}, sub. {sb}", f"Fg. {f} Part. {p} Sub. {sb}", f"foglio {f} mappale {p} subalterno {sb}",
                           f"fg {f} p.lla {p} sub {sb}", f"Foglio {f}, Particella {p}", f"foglio {f}, mappale {p}, sub {sb}",
                           f"F. {f} - P. {p} - S. {sb}", f"foglio n. {f}, particella n. {p}, subalterno n. {sb}", f"fg. {f} mapp. {p}/{sb}",
                           f"sez. {s.r.choice('ABCU')} foglio {f} particella {p} sub {sb}", f"FOGLIO {f} PARTICELLA {p} SUB {sb}"])
    def pod(s): return f"IT{cifre(s.r, 3)}E{cifre(s.r, 8)}"
    def pdr(s): return cifre(s.r, 14)
    def forn(s): return s.r.choice([cifre(s.r, 9), cifre(s.r, 12), f"{cifre(s.r, 3)} {cifre(s.r, 3)} {cifre(s.r, 3)}"])
    def contatore(s): return s.r.choice([cifre(s.r, 8), caso(s.r, 2, string.ascii_uppercase) + cifre(s.r, 9), f"{cifre(s.r, 2)}E{cifre(s.r, 9)}"])


# --- versione 2: quasi-identificatori e categorie particolari. Valori inventati, scelti a caso: non descrivono nessuno.
TITOLI_M = ["Dott.", "Dott.", "Dr.", "Avv.", "Ing.", "Arch.", "Geom.", "Rag.", "Prof.", "Sig.", "Sig.", "Signor", "On.", "Cav.", "Notaio", "P.I.", "dott.", "avv.", "ing."]
TITOLI_F = ["Dott.ssa", "Dott.ssa", "Dr.ssa", "Avv.", "Ing.", "Arch.", "Prof.ssa", "Sig.ra", "Sig.ra", "Signora", "Sig.na", "On.", "Notaio", "dott.ssa", "avv."]
PROFESSIONI = ("impiegato impiegata operaio operaia insegnante infermiere infermiera medico avvocato commercialista geometra architetto "
               "ingegnere idraulico elettricista muratore cuoco cameriera commessa autista magazziniere programmatore sistemista "
               "farmacista veterinario dentista notaio giornalista fotografo parrucchiera estetista falegname meccanico carrozziere "
               "agricoltore panettiere macellaio barista bidello segretaria ragioniere contabile fisioterapista psicologa "
               "biologo chimico ricercatrice bibliotecaria postino vigile carabiniere pompiere camionista tassista pilota "
               "hostess portiere badante colf baby-sitter traduttrice interprete grafico designer sviluppatore analista "
               "consulente dirigente imprenditore artigiano commerciante rappresentante saldatore tornitore fresatore gruista").split()
PROFESSIONI += ["tecnico informatico", "responsabile amministrativo", "agente di commercio", "consulente del lavoro", "addetta alle vendite",
                "medico di base", "direttore tecnico", "IT manager", "libero professionista", "responsabile del personale",
                "addetto alla logistica", "operatore socio-sanitario", "assistente sociale", "guardia giurata", "docente di ruolo",
                "responsabile di produzione", "capo cantiere", "addetta alla contabilità", "tecnico di laboratorio", "amministratore di condominio",
                "project manager", "software engineer", "account manager", "responsabile acquisti", "educatrice professionale",
                "operaio specializzato", "impiegata amministrativa", "autista di autobus", "collaboratore scolastico", "medico chirurgo",
                "giudice", "magistrato", "cancelliere", "avvocato generale", "presidente di sezione", "giudice relatore", "procuratore",
                "pubblico ministero", "ufficiale giudiziario", "funzionario", "dirigente scolastico", "sindaco", "assessore",
                "segretario comunale", "professore ordinario", "ricercatore", "primario", "direttore sanitario", "revisore dei conti",
                "curatore fallimentare", "perito", "consulente tecnico d'ufficio", "mediatore", "ispettore del lavoro"]
STATI_LAVORO = ["disoccupato", "disoccupata", "pensionato", "pensionata", "in cassa integrazione", "assunto a tempo indeterminato",
                "assunta a tempo determinato", "lavoratore autonomo", "studente", "studentessa", "casalinga", "part-time", "tirocinante",
                "in cerca di prima occupazione", "apprendista", "stagionale", "in mobilità", "full time"]
STUDI = ["laurea magistrale in Economia", "laurea triennale in Informatica", "laurea in Giurisprudenza", "laurea in Medicina e Chirurgia",
         "diploma di ragioneria", "diploma di liceo scientifico", "diploma di liceo classico", "licenza media", "licenza elementare",
         "dottorato di ricerca in Chimica", "master in Diritto tributario", "diploma di perito industriale", "qualifica professionale",
         "diploma di geometra", "laurea in Ingegneria gestionale", "diploma magistrale", "laurea in Scienze infermieristiche",
         "diploma ITIS", "laurea in Lettere", "diploma alberghiero", "master di secondo livello", "specializzazione in Cardiologia",
         "terza media", "diploma di maturità", "laurea in Psicologia", "abilitazione forense"]
NAZIONALITA = ("italiana italiano rumena rumeno albanese marocchina marocchino cinese ucraina ucraino tedesca tedesco francese spagnola "
               "polacca polacco moldava indiana indiano filippina senegalese egiziano pakistano brasiliana peruviana nigeriano tunisina "
               "bengalese svizzera austriaco croata serbo greca turco russa americano inglese argentina colombiana").split()
ORIGINI = ["di origine rom", "di etnia curda", "di origine magrebina", "afrodiscendente", "di origine sinti", "madrelingua araba",
           "di madrelingua tedesca", "di lingua slovena", "madrelingua ucraina", "di origine albanese", "di etnia tamil", "di origine cinese",
           "parla solo rumeno", "madrelingua spagnolo", "di origine eritrea"]
RELIGIONI = ["cattolico", "cattolica", "musulmano", "musulmana", "ebreo", "ebrea", "evangelico", "ortodossa", "buddista", "induista",
             "testimone di Geova", "valdese", "ateo", "agnostica", "sikh", "di religione islamica", "di fede ebraica", "cattolico praticante",
             "di religione ortodossa", "protestante", "di fede buddista", "di confessione valdese", "mormone", "avventista"]
POLITICHE = ["iscritto al Partito Democratico", "tesserata di Fratelli d'Italia", "simpatizzante della Lega", "militante del Movimento 5 Stelle",
             "elettore di Forza Italia", "iscritto alla CGIL", "delegata CISL", "rappresentante sindacale UIL", "di idee progressiste",
             "di orientamento conservatore", "attivista di Sinistra Italiana", "iscritto a un sindacato di base", "candidato in una lista civica",
             "iscritta alla FIOM", "vicino ai Verdi", "consigliere comunale di Azione", "tesserato di Italia Viva", "RSU della USB",
             "di simpatie anarchiche", "iscritto ai Radicali"]
ORIENTAMENTI = ["omosessuale", "eterosessuale", "bisessuale", "gay", "lesbica", "asessuale", "pansessuale"]
SALUTE = ["gruppo sanguigno A positivo", "gruppo sanguigno 0 Rh negativo", "gruppo B+", "gruppo AB negativo", "0+", "A-",
          "invalidità civile al 75%", "invalidità al 46%", "allergia alla penicillina", "portatore di pacemaker", "celiachia",
          "in gravidanza alla ventesima settimana", "intolleranza al lattosio", "disturbo d'ansia generalizzato", "sieropositivo",
          "dializzato", "ipovedente", "portatrice di protesi d'anca", "in trattamento chemioterapico", "asma bronchiale",
          "depressione maggiore", "epilessia", "disabilità ai sensi della legge 104"]
REGIONI = ("Lombardia Piemonte Veneto Liguria Toscana Lazio Campania Puglia Sicilia Sardegna Calabria Umbria Marche Abruzzo Molise "
           "Basilicata Friuli-Venezia Giulia Trentino-Alto Adige Emilia-Romagna Valle d'Aosta").split()
REGIONI = [x for x in REGIONI if x not in ("Giulia", "Adige", "d'Aosta")] + ["Friuli-Venezia Giulia", "Trentino-Alto Adige", "Valle d'Aosta"]
PAESI = ("Italia Francia Germania Spagna Svizzera Austria Romania Albania Marocco Cina Ucraina Polonia Regno Unito Stati Uniti Brasile "
         "India Egitto Tunisia Grecia Belgio Olanda Portogallo Croazia Slovenia Argentina Senegal Nigeria Pakistan Filippine").split()
PAESI = [x for x in PAESI if x not in ("Regno", "Unito", "Stati", "Uniti")] + ["Regno Unito", "Stati Uniti", "San Marino"]


class Profilo:
    """Ciò che descrive una persona senza nominarla: mestiere, studi, origine, convinzioni, salute, orientamento, luoghi."""
    ETI = dict(prof="PROFESSIONE", stato="PROFESSIONE", ruolo="PROFESSIONE", studio="ISTRUZIONE", naz="ORIGINE", origine="ORIGINE",
               religione="RELIGIONE", politica="POLITICA", orient="ORIENTAMENTO", salute="SALUTE", regione="LUOGO", paese="LUOGO",
               provincia="LUOGO", genere="GENERE", eta="ETA")

    def __init__(s, r): s.r = r
    def prof(s): return s.r.choice(PROFESSIONI)
    def stato(s): return s.r.choice(STATI_LAVORO)
    def ruolo(s): return s.r.choice(RUOLI_MESTIERE)
    def ufficio(s): return s.r.choice(RUOLI_UFFICIO)     # un reparto, non un mestiere: resta senza etichetta
    def studio(s): return s.r.choice(STUDI)
    def naz(s): return s.r.choice(NAZIONALITA)
    def origine(s): return s.r.choice(ORIGINI)
    def religione(s): return s.r.choice(RELIGIONI)
    def politica(s): return s.r.choice(POLITICHE)
    def orient(s): return s.r.choice(ORIENTAMENTI)
    def salute(s): return s.r.choice(SALUTE)
    def regione(s): return s.r.choice(REGIONI)
    def paese(s): return s.r.choice(PAESI)
    def provincia(s): return "provincia di " + s.r.choice(COMUNI)
    def genere(s): return s.r.choice(["maschio", "femmina", "M", "F", "uomo", "donna", "maschile", "femminile", "non binario", "Maschio", "Femmina"])
    def eta(s): return str(s.r.randint(18, 92))


RUOLI_MESTIERE = ["Responsabile amministrativo", "IT Manager", "Titolare", "Direttore tecnico", "Responsabile HR", "Sales Account", "Avvocato",
                  "Dottore commercialista", "Geometra", "Consulente", "Sistemista", "Responsabile di produzione", "CEO", "Office manager",
                  "Impiegata", "Tecnico", "Amministratore delegato", "Project manager", "Responsabile acquisti", "Contabile", "Ingegnere"]
RUOLI_UFFICIO = ["Ufficio acquisti", "Amministrazione", "Segreteria", "Helpdesk", "Ufficio tecnico", "Assistenza clienti", "Direzione"]


# --- cio' che e' di dominio pubblico: in un discorso generale (storia, notizie, geografia, richieste a un'AI) NON va
#     mascherato. Gli stessi nomi, dentro dati personali veri (un modulo, una firma), restano da mascherare: decide il contesto.
FAMOSI = [
    "Dante Alighieri", "Leonardo da Vinci", "Michelangelo Buonarroti", "Galileo Galilei", "Giuseppe Garibaldi", "Giuseppe Verdi",
    "Giacomo Puccini", "Alessandro Manzoni", "Giacomo Leopardi", "Francesco Petrarca", "Giovanni Boccaccio", "Niccolò Machiavelli",
    "Cristoforo Colombo", "Marco Polo", "Raffaello Sanzio", "Antonio Vivaldi", "Gioachino Rossini", "Guglielmo Marconi", "Enrico Fermi",
    "Alessandro Volta", "Maria Montessori", "Rita Levi-Montalcini", "Luigi Pirandello", "Italo Calvino", "Umberto Eco", "Primo Levi",
    "Federico Fellini", "Sophia Loren", "Luciano Pavarotti", "Andrea Bocelli", "Giorgio Armani", "Enzo Ferrari", "Gianni Agnelli",
    "Giuseppe Mazzini", "Aldo Moro", "Sandro Pertini", "Giorgio Napolitano", "Sergio Mattarella", "Giorgia Meloni", "Mario Draghi",
    "Giuseppe Conte", "Matteo Renzi", "Matteo Salvini", "Silvio Berlusconi", "Romano Prodi", "Enrico Letta", "Elly Schlein",
    "Antonio Tajani", "Roberto Baggio", "Francesco Totti", "Alessandro Del Piero", "Gianluigi Buffon", "Paolo Maldini", "Valentino Rossi",
    "Jannik Sinner", "Federica Pellegrini", "Marcell Jacobs", "Roberto Benigni", "Adriano Celentano", "Laura Pausini", "Eros Ramazzotti",
    "Vasco Rossi", "Lucio Dalla", "Fabrizio De André", "Ennio Morricone", "Renzo Piano", "Carlo Rubbia", "Samantha Cristoforetti",
    "Elsa Fornero", "Giovanni Falcone", "Paolo Borsellino", "Camillo Benso di Cavour", "Lorenzo de' Medici", "Giulio Cesare",
    "Marco Aurelio", "Albert Einstein", "Isaac Newton", "Charles Darwin", "Marie Curie", "Nikola Tesla", "Thomas Edison",
    "Stephen Hawking", "Alan Turing", "William Shakespeare", "Napoleone Bonaparte", "Abraham Lincoln", "George Washington",
    "Winston Churchill", "Nelson Mandela", "Mahatma Gandhi", "Martin Luther King", "John Kennedy", "Barack Obama", "Donald Trump",
    "Joe Biden", "Angela Merkel", "Emmanuel Macron", "Vladimir Putin", "Xi Jinping", "Ursula von der Leyen", "Christine Lagarde",
    "Bill Gates", "Steve Jobs", "Elon Musk", "Jeff Bezos", "Mark Zuckerberg", "Tim Cook", "Satya Nadella", "Sam Altman", "Sundar Pichai",
    "Warren Buffett", "Pablo Picasso", "Vincent van Gogh", "Wolfgang Amadeus Mozart", "Ludwig van Beethoven", "Johann Sebastian Bach",
    "Sigmund Freud", "Karl Marx", "Immanuel Kant", "Friedrich Nietzsche", "Lionel Messi", "Cristiano Ronaldo", "Diego Maradona",
    "Michael Jordan", "Roger Federer", "Rafael Nadal", "Novak Djokovic", "Usain Bolt", "Michael Schumacher", "Lewis Hamilton",
    "Ayrton Senna", "Muhammad Ali", "Michael Jackson", "Elvis Presley", "John Lennon", "Bob Dylan", "Taylor Swift",
    "Leonardo DiCaprio", "Meryl Streep", "Steven Spielberg", "Quentin Tarantino", "Walt Disney", "Charlie Chaplin", "Marilyn Monroe",
    "Ernest Hemingway", "George Orwell", "Franz Kafka", "Victor Hugo", "Greta Thunberg", "Malala Yousafzai", "Papa Francesco",
    "Giovanni Paolo II", "Madre Teresa", "Carlo Magno", "Giovanna d'Arco", "Adam Smith", "John Maynard Keynes", "Max Weber",
    "Tim Berners-Lee", "Linus Torvalds", "Ada Lovelace", "Guido van Rossum", "Jane Austen", "Agatha Christie", "Oscar Wilde",
]
FAMOSI_SOLI = ["Pitagora", "Archimede", "Platone", "Aristotele", "Socrate", "Caravaggio", "Dante", "Leonardo", "Michelangelo", "Galileo",
               "Garibaldi", "Mozart", "Beethoven", "Einstein", "Newton", "Darwin", "Shakespeare", "Napoleone", "Picasso", "Maradona",
               "Pelé", "Madonna", "Beyoncé", "Cleopatra", "Omero", "Virgilio", "Cicerone", "Euclide", "Keplero", "Copernico", "Fibonacci"]
CITTA_NOTE = ("Roma Milano Napoli Torino Palermo Genova Bologna Firenze Bari Catania Venezia Verona Trieste Padova Parma Pisa Siena Perugia "
              "Cagliari Parigi Londra Berlino Madrid Barcellona Tokyo Pechino Mosca Bruxelles Vienna Lisbona Atene Dublino Amsterdam Zurigo "
              "Ginevra Chicago Washington Sydney Dubai Paris London Rome Milan Berlin Monaco Lione Marsiglia Francoforte Stoccolma Praga "
              "Budapest Varsavia Istanbul Singapore Toronto Boston Seattle").split() + ["New York", "Los Angeles", "San Francisco", "Hong Kong"]
LUOGHI_NOTI = ["Colosseo", "Torre di Pisa", "Duomo di Milano", "Fontana di Trevi", "Ponte Vecchio", "Torre Eiffel", "Louvre", "Big Ben",
               "Statua della Libertà", "Cappella Sistina", "Galleria degli Uffizi", "Pantheon", "Teatro alla Scala", "Etna", "Vesuvio",
               "Monte Bianco", "Lago di Garda", "Lago di Como", "Po", "Tevere", "Arno", "Dolomiti", "Alpi", "Appennini", "Mar Mediterraneo",
               "Mar Adriatico", "Mar Tirreno", "Pianura Padana", "Costiera Amalfitana", "Cinque Terre", "Valle dei Templi", "Arena di Verona",
               "Piazza San Marco", "Piazza del Duomo", "Vaticano", "Reggia di Caserta", "Canal Grande", "Central Park", "Muraglia cinese"]
SQUADRE = ["Juventus", "Inter", "Milan", "Roma", "Napoli", "Lazio", "Atalanta", "Fiorentina", "Torino", "Bologna", "Real Madrid",
           "Barcellona", "Bayern Monaco", "Manchester United", "Liverpool", "Paris Saint-Germain", "Chelsea", "Arsenal", "Ferrari", "Ducati"]
MARCHE = ["Ferrari", "Lamborghini", "Maserati", "Fiat", "Alfa Romeo", "Barilla", "Ferrero", "Lavazza", "Armani", "Prada", "Gucci", "Versace",
          "Benetton", "Pirelli", "Piaggio", "Ducati", "Campari", "Peroni", "Mondadori", "Feltrinelli", "Volkswagen", "BMW", "Mercedes",
          "Toyota", "Tesla", "Ford", "Renault", "Nike", "Adidas", "Ikea", "Coca-Cola", "Nestlé", "Samsung", "Sony", "Stellantis", "Luxottica",
          "Eni", "Enel", "Leonardo", "Fincantieri", "Brembo", "Illy", "Mulino Bianco", "Nutella", "Vespa", "Olivetti", "Zara", "Rolex"]
IP_PUBBLICI = ["127.0.0.1", "8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9", "0.0.0.0", "255.255.255.0", "255.255.255.255", "::1",
               "208.67.222.222", "255.255.0.0"]
SITI_PUBBLICI = ["https://www.microsoft.com/it-it/software-download", "https://support.microsoft.com", "https://learn.microsoft.com/it-it/",
                 "https://www.google.com", "https://github.com", "https://it.wikipedia.org/wiki/Italia", "https://www.agenziaentrate.gov.it",
                 "https://www.inps.it", "https://www.garanteprivacy.it", "https://www.python.org/downloads/", "https://docs.fortinet.com",
                 "https://www.cisco.com", "https://support.apple.com/it-it", "https://www.mozilla.org", "https://eur-lex.europa.eu",
                 "www.google.it", "www.youtube.com", "https://stackoverflow.com/questions", "https://www.amazon.it", "https://www.poste.it"]
DOMINI_PUBBLICI = ["example.com", "example.org", "microsoft.com", "google.com", "github.com", "wikipedia.org", "apple.com", "amazon.it",
                   "gov.it", "europa.eu", "outlook.com", "gmail.com", "office.com", "windowsupdate.com", "localhost"]


class Pubblico:
    """Persone famose, citta' e indirizzi di dominio pubblico: nessuna etichetta. Le marche restano ORG come ogni azienda:
    che "Ferrari" si possa lasciare in chiaro lo decide l'elenco dei nomi noti (known.py), non il modello, altrimenti
    impara a ignorare anche il nome di un cliente scritto senza "S.r.l."."""
    ETI = dict(marca="ORG")

    def __init__(s, r): s.r = r
    def famoso(s): return s.r.choice(FAMOSI)
    def solo(s): return s.r.choice(FAMOSI_SOLI) if s.r.random() < .6 else s.r.choice(FAMOSI).split(" ")[-1]
    def citta(s): return s.r.choice(CITTA_NOTE)
    def luogo(s): return s.r.choice(LUOGHI_NOTI)
    def squadra(s): return s.r.choice(SQUADRE)
    def marca(s): return s.r.choice(MARCHE)
    def paese(s): return s.r.choice(PAESI)
    def ip(s): return s.r.choice(IP_PUBBLICI)
    def sito(s): return s.r.choice(SITI_PUBBLICI)
    def dominio(s): return s.r.choice(DOMINI_PUBBLICI)


def contesto(r):
    a, b = Azienda(r), Azienda(r)
    p = Persona(r, a)
    return dict(p=p, q=Persona(r, a if r.random() < .5 else b), r=Persona(r), a=a, b=b, t=IT(r, a, p), v=Varie(r), x=Profilo(r), g=Pubblico(r))
