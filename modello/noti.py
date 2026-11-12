# -*- coding: utf-8 -*-
"""Nomi noti da lasciare in chiaro: produttori, prodotti e servizi di uso comune.

Il modello tratta ogni nome di organizzazione allo stesso modo (ORG). Decidere che "Microsoft"
non va mascherato e "Rossi Impianti" si' non e' un compito da modello: e' un elenco, certo e
modificabile. Questo e' l'elenco predefinito; chi installa puo' aggiungere voci proprie con
i file liste/mai.txt (da non mascherare) e liste/sempre.txt (da mascherare sempre).
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
"""
NOTI = {x.strip() for x in _TESTO.replace("\n", " ").split(";") if x.strip()}
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
