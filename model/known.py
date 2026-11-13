# -*- coding: utf-8 -*-
"""Nomi noti da lasciare in chiaro: produttori, prodotti e servizi di uso comune.

Il modello tratta ogni nome di organizzazione allo stesso modo (ORG). Decidere che "Microsoft"
non va mascherato e "Rossi Impianti" si' non e' un compito da modello: e' un elenco, certo e
modificabile. Questo e' l'elenco predefinito; chi installa puo' aggiungere voci proprie con
i file lists/never.txt (da non mascherare) e lists/always.txt (da mascherare sempre).
"""
import re
from pathlib import Path

_TESTO = """
microsoft; google; apple; amazon; aws; azure; meta; facebook; instagram; linkedin; youtube; twitter; tiktok; whatsapp; telegram;
openai; anthropic; chatgpt; claude; gemini; copilot; mistral; perplexity;
office; office 365; microsoft 365; m365; o365; outlook; teams; onedrive; sharepoint; excel; word; powerpoint; visio;
planner; exchange; exchange online; entra; entra id; azure ad; active directory; intune; defender; purview; autopilot; power bi;
power automate; dynamics; dynamics 365; business central; windows; windows 10; windows 11; windows server; sql server; hyper-v;
powershell; edge; skype; bing; xbox; surface; github; gitlab; bitbucket; visual studio; vs code;
gmail; google workspace; google drive; chrome; android; google meet; google maps; pixel;
icloud; iphone; ipad; macbook; imac; macos; ios; safari; airpods;
linux; ubuntu; debian; centos; red hat; redhat; rhel; suse; fedora; proxmox; vmware; vsphere; vcenter; esxi; citrix; nutanix;
docker; kubernetes; ansible; terraform; jenkins; jira; confluence; atlassian; trello; notion; slack; zoom; webex; discord;
dropbox; wetransfer; nextcloud; owncloud; wordpress; joomla; plesk; cpanel; cloudflare; godaddy; ovh; hetzner; aruba;
register.it; serverplan; siteground; keliweb; netsons; seeweb;
fortinet; fortigate; forticlient; fortianalyzer; fortimanager; cisco; meraki; sophos; watchguard; sonicwall; palo alto;
palo alto networks; check point; checkpoint; zyxel; netgear; tp-link; d-link; ubiquiti; unifi; mikrotik; aruba networks; hpe;
juniper; huawei; draytek; pfsense; opnsense; openvpn; wireguard; tailscale; zerotier;
veeam; acronis; datto; kaseya; connectwise; ninjaone; ninja; ninjarmm; halopsa; halo; atera; n-able; solarwinds; zabbix; nagios;
grafana; prtg; wazuh; splunk; teamviewer; anydesk; splashtop; rustdesk; supremo; iperius;
crowdstrike; sentinelone; bitdefender; kaspersky; eset; trend micro; mcafee; norton; avast; avg; malwarebytes; webroot; cynet;
hornetsecurity; libraesva; proofpoint; mimecast; barracuda; okta; authenticator; keepass; bitwarden; lastpass; 1password;
hp; hewlett packard; dell; lenovo; acer; asus; msi; toshiba; fujitsu; samsung; lg; sony; philips; benq; xiaomi; oppo; motorola;
nokia; intel; amd; nvidia; qualcomm; kingston; crucial; sandisk; western digital; wd; seagate; synology; qnap; apc; eaton; riello;
logitech; jabra; plantronics; yealink; snom; grandstream; 3cx; wildix; voispeed; avaya; alcatel;
canon; epson; brother; ricoh; kyocera; lexmark; xerox; konica minolta; olivetti; sharp; zebra; dymo; oki;
adobe; acrobat; photoshop; illustrator; indesign; autocad; autodesk; revit; solidworks; archicad; sketchup; oracle; sap; ibm;
salesforce; hubspot; odoo; zoho; mailchimp; brevo; sendgrid; twilio; stripe; shopify; woocommerce; prestashop; magento;
zucchetti; teamsystem; wolters kluwer; buffetti; namirial; infocert; aruba pec; legalmail; passepartout; mexal; danea;
easyfatt; fatture in cloud; mago4; arca evolution; alyante; profis; ipsoa; dike; arubasign;
gosign; spid; cie; pagopa; fisconline; entratel; desktop telematico; sdi; pec;
tim; telecom; telecom italia; vodafone; fastweb; windtre; wind tre; iliad; tiscali; eolo; linkem; sky; open fiber; openfiber;
poste; poste italiane; postepay; dhl; ups; fedex; tnt; brt; bartolini; gls; sda; nexive;
intesa; intesa sanpaolo; unicredit; bper; banco bpm; credem; ing; fineco; mediolanum; mps; monte dei paschi; bnl; credit agricole;
crédit agricole; banca sella; widiba; n26; revolut; paypal; nexi; satispay; sumup; visa; mastercard; american express; amex;
generali; allianz; unipolsai; unipol; axa; zurich; reale mutua; cattolica; vittoria assicurazioni; groupama; helvetia;
enel; eni; a2a; hera; iren; acea; edison; sorgenia; plenitude; snam; terna; italgas;
trenitalia; italo; ryanair; easyjet; ita airways; alitalia; booking; airbnb; expedia; telepass; autostrade;
netflix; spotify; dazn; prime video; disney; rai; mediaset;
esprinet; ingram micro; computer gross; td synnex; mediaworld; unieuro; euronics; trony; leroy merlin; ikea; esselunga; conad;
lidl; eurospin; decathlon; zalando; ebay; subito; aliexpress; temu;
accenture; deloitte; kpmg; pwc; ey; randstad; adecco; manpower; gi group;
inps; inail; agenzia delle entrate; camera di commercio; garante privacy; asl; ats; siae; aci; pra; consob; ivass; anac; consip;
mepa; agid; acn; mef; istat; inl; guardia di finanza; carabinieri; polizia; polizia postale; vigili del fuoco; banca d'italia;
unione europea; commissione europea; gdpr; nis2; iso;
elitebook; probook; zbook; elitedesk; prodesk; pavilion; proliant; laserjet; officejet; deskjet; thinkpad; thinkcentre; thinkstation;
ideapad; latitude; optiplex; vostro; precision; poweredge; inspiron; galaxy; taskalfa; ecosys; workforce; smart-ups; diskstation;
catalyst; firepower; xgs; fortiswitch; fortiap; aironet; nas; ups; firewall; switch; access point; notebook; pc; stampante; monitor;
stellantis; volkswagen; audi; bmw; mercedes-benz; porsche; toyota; tesla; volvo; honda; nissan; hyundai; kia; skoda; dacia; opel; jeep;
suzuki; mazda; yamaha; kawasaki; iveco; lamborghini; maserati; alfa romeo; fiat; lancia;
nutella; mulino bianco; san pellegrino; coca-cola; pepsi; nestlé; nestle; danone; unilever; mcdonald's; burger king; starbucks; kfc;
gucci; dolce & gabbana; bulgari; luxottica; ray-ban; h&m; nike; adidas; puma; lacoste; louis vuitton; chanel; rolex; swatch;
coop; carrefour; auchan; despar; penny market; ovs; upim; rinascente;
corriere della sera; la repubblica; la stampa; il sole 24 ore; gazzetta dello sport; ansa; bbc; cnn; reuters; new york times;
juventus; atalanta; fiorentina; real madrid; bayern monaco; manchester united; paris saint-germain; serie a; champions league;
uefa; fifa; coni; figc; nba; formula 1; motogp; nasa; esa; onu; nato; oms; unesco; unicef; fmi; bce; ocse; croce rossa; caritas; wwf;
greenpeace; amazon web services; google cloud; microsoft azure; oracle cloud; alibaba; tencent; uber; deliveroo; glovo; just eat;
tripadvisor; trivago; skyscanner; flixbus; blablacar; wikipedia; wikimedia; mozilla; firefox; duckduckgo; reddit; pinterest; snapchat;
twitch; signal; apache; nginx; mysql; postgresql; mongodb; redis; python; javascript; node.js; php;
fincantieri; saipem; tenaris; prysmian; mediobanca; ferrovie dello stato; trenord; atac; anas; autostrade per l'italia; lufthansa;
air france; british airways; emirates; costa crociere; hilton; marriott;
parlamento europeo; consiglio europeo; corte di giustizia; corte di cassazione; corte costituzionale; consiglio di stato; corte dei conti;
senato; camera dei deputati; governo; ministero della salute; ministero dell'interno; ministero dell'economia; protezione civile;
"""
NOTI = {x.strip() for x in _TESTO.replace("\n", " ").split(";") if x.strip()}
# Indirizzi tecnici che non dicono nulla di nessuno: l'indirizzo della macchina stessa, i DNS pubblici, le maschere di rete,
# i siti di produttori, enti e documentazione. Un indirizzo privato (192.168..., il sito di un cliente) non e' tra questi.
IP_PUBBLICI = {"127.0.0.1", "::1", "0.0.0.0", "8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9", "149.112.112.112", "208.67.222.222",
               "208.67.220.220", "255.255.255.255", "255.255.255.0", "255.255.0.0", "255.0.0.0", "255.255.255.128", "255.255.255.192",
               "255.255.255.224", "255.255.255.240", "255.255.255.248", "255.255.255.252", "255.255.254.0", "255.255.252.0", "255.255.248.0"}
DOMINI_PUBBLICI = {x.strip() for x in """
example.com; example.org; example.net; localhost; microsoft.com; office.com; live.com; windows.com; windowsupdate.com; azure.com; msn.com;
google.com; google.it; youtube.com; gstatic.com; android.com; apple.com; icloud.com; amazon.com; amazon.it; aws.amazon.com; github.com;
gitlab.com; stackoverflow.com; wikipedia.org; wikimedia.org; mozilla.org; python.org; pypi.org; npmjs.com; docker.com; kubernetes.io;
ubuntu.com; debian.org; redhat.com; kernel.org; apache.org; nginx.org; cloudflare.com; fortinet.com; cisco.com; sophos.com; vmware.com;
veeam.com; adobe.com; oracle.com; ibm.com; dell.com; hp.com; lenovo.com; intel.com; nvidia.com; amd.com; mysql.com; postgresql.org;
linkedin.com; facebook.com; instagram.com; x.com; twitter.com; whatsapp.com; telegram.org; zoom.us; openai.com; anthropic.com; claude.ai;
europa.eu; gov.it; agenziaentrate.gov.it; inps.it; inail.it; garanteprivacy.it; poste.it; pagopa.gov.it; spid.gov.it; istat.it;
w3.org; ietf.org; iso.org; mitre.org; nist.gov; owasp.org
""".replace("\n", " ").split(";") if x.strip()}
_RX_HOST = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:www\.)?([a-z0-9.-]+\.[a-z]{2,}|localhost)(?::\d+)?(/[^?#\s]*)?$", re.I)


def tecnico_pubblico(valore, etichetta):
    """True se un indirizzo IP, un dominio o un indirizzo web e' di dominio pubblico (vedi sopra). Un indirizzo web con
    parametri (?...) non lo e' mai: li' possono stare codici e nomi."""
    v = valore.strip().strip(".,;:()[]<>\"'").lower()
    if etichetta == "IP":
        return v.split("/")[0] in IP_PUBBLICI
    if etichetta in ("URL", "DOMINIO", "HOSTNAME"):
        m = _RX_HOST.match(v)
        if not m:
            return False
        host = m.group(1)
        return any(host == d or host.endswith("." + d) for d in DOMINI_PUBBLICI)
    return False
_FORMA_G = re.compile(r"(?i)\b(s\.?r\.?l\.?s?|s\.?p\.?a|s\.?n\.?c|s\.?a\.?s|s\.?c\.?a\.?r\.?l|soc\.? ?coop\w*|onlus|studio|& ?c)\b")


def norma(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w&.'+-]+", " ", s.lower())).strip(" .-'")


def leggi_elenco(percorso):
    """Un termine per riga; righe vuote e righe che iniziano con # ignorate."""
    p = Path(percorso)
    if not p.exists():
        return []
    return [r.strip() for r in p.read_text(encoding="utf-8").splitlines() if r.strip() and not r.lstrip().startswith("#")]


_GENERICHE = set("pro business standard premium enterprise online cloud backup server desktop mobile italia support supporto "
                 "assistenza basic plus essentials professional home edition client agent app suite for per di".split())


def e_noto(valore, extra=frozenset()):
    """True se lo span e' un nome noto, anche seguito da un modello o da un'edizione
    ("HP EliteBook 840 G9", "Microsoft 365 Business"). Mai se contiene una forma giuridica."""
    v = norma(valore)
    if not v:
        return False
    if v in NOTI or v in extra:
        return True
    if _FORMA_G.search(v):
        return False
    parole, i, trovato = v.split(" "), 0, False
    if len(parole) > 6:
        return False
    while i < len(parole):
        for k in (3, 2, 1):
            frase = " ".join(parole[i:i + k])
            if i + k <= len(parole) and (frase in NOTI or frase in extra):
                i, trovato = i + k, True
                break
        else:
            if not (any(ch.isdigit() for ch in parole[i]) or parole[i] in _GENERICHE):
                return False
            i += 1
    return trovato
