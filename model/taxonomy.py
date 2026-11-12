# -*- coding: utf-8 -*-
"""Tassonomia di msp-pii (v0): unica fonte per etichette, strati e azione predefinita.

Per ogni etichetta:
  strati   chi la rileva: "modello" (rete neurale), "regole" (regex + checksum),
           "dizionario" (elenchi sincronizzati dal PSA: clienti, utenti, dispositivi)
  azione   "maschera"  = sostituita sempre con un segnaposto reversibile
           "profilo"   = mascherata solo nei profili che lo chiedono (sanitario, legale, HR)
           "lascia"    = non mascherata: serve all'AI per rispondere bene
  fase     0 = nel primo addestramento; 2 = definita ma non ancora addestrata

Regole di confine (valgono per dati di addestramento e benchmark):
  - ORG e' il nome di un'azienda, studio o cliente privato. Enti pubblici e fornitori noti
    (INPS, Agenzia delle Entrate, Microsoft, Fortinet) NON si mascherano.
  - CITTA si maschera quando e' residenza, sede, luogo di nascita o parte di un indirizzo;
    non dentro il nome di un ente ("Tribunale di Milano").
  - DATA_NASCITA si maschera; le altre date no.
  - ID_PRATICA e' un numero che porta a una persona: polizza, sinistro, matricola, cartella
    clinica, protocollo, RG, prenotazione, PNR, ordine, codice cliente. Numeri di fattura,
    tracking e ticket no.
  - ACCOUNT e' cio' che identifica un'utenza: nome utente, UPN, DOMINIO\\utente, account di
    servizio, SID, DN LDAP, handle social.
  - SEGRETO e' tutto cio' che da' accesso: password, token, chiavi, PSK, stringhe di
    connessione, webhook con token, codici di recupero, hash di password.
  - HOSTNAME e' il nome di una macchina (PC, server, FQDN interno); DOMINIO e' un dominio
    DNS, tenant o NetBIOS.
"""

#  etichetta            descrizione                                             strati                               azione      fase
TASSONOMIA = [
    ("PERSONA",        "nome e cognome, anche solo cognome, iniziali puntate",   ("modello", "dizionario"),           "maschera", 0),
    ("EMAIL",          "indirizzo email o PEC, anche dettato",                   ("regole", "modello"),               "maschera", 0),
    ("TELEFONO",       "fisso, cellulare, interno, anche a parole",              ("modello", "regole"),               "maschera", 0),
    ("INDIRIZZO",      "via e numero civico",                                    ("modello",),                        "maschera", 0),
    ("CAP",            "codice di avviamento postale",                           ("modello",),                        "maschera", 0),
    ("CITTA",          "comune di residenza, sede o nascita",                    ("modello",),                        "maschera", 0),
    ("DATA_NASCITA",   "data di nascita",                                        ("modello",),                        "maschera", 0),
    ("CF",             "codice fiscale, anche con errori di battitura",          ("regole", "modello"),               "maschera", 0),
    ("PIVA",           "partita IVA",                                            ("regole", "modello"),               "maschera", 0),
    ("IBAN",           "IBAN, anche spezzato o con spazi",                       ("regole", "modello"),               "maschera", 0),
    ("CARTA",          "numero di carta di pagamento",                           ("regole", "modello"),               "maschera", 0),
    ("CARTA_SEC",      "CVV e scadenza della carta",                             ("modello",),                        "maschera", 0),
    ("DOC_ID",         "carta d'identita', passaporto, patente, tessera sanitaria", ("modello",),                     "maschera", 0),
    ("TARGA",          "targa di veicolo",                                       ("modello", "regole"),               "maschera", 0),
    ("ID_VEICOLO",     "numero di telaio (VIN)",                                 ("modello",),                        "maschera", 0),
    ("ORG",            "azienda, studio o cliente privato",                      ("dizionario", "modello"),           "maschera", 0),
    ("ID_PRATICA",     "polizza, sinistro, matricola, cartella, protocollo, PNR", ("modello",),                       "maschera", 0),
    ("CATASTO",        "foglio, particella, subalterno",                         ("modello",),                        "maschera", 0),
    ("ID_UTENZA",      "POD, PDR, codice fornitura, matricola contatore",        ("modello", "regole"),               "maschera", 0),
    ("IP",             "indirizzo IPv4 o IPv6",                                  ("regole", "modello"),               "maschera", 0),
    ("MAC",            "indirizzo MAC",                                          ("regole", "modello"),               "maschera", 0),
    ("HOSTNAME",       "nome di PC, server, FQDN interno",                       ("modello", "dizionario"),           "maschera", 0),
    ("DOMINIO",        "dominio DNS, tenant, NetBIOS",                           ("modello", "dizionario"),           "maschera", 0),
    ("URL",            "indirizzo web o di servizio",                            ("regole", "modello"),               "maschera", 0),
    ("ACCOUNT",        "nome utente, UPN, account di servizio, SID, DN",         ("modello", "dizionario"),           "maschera", 0),
    ("SEGRETO",        "password, token, chiavi, stringhe di connessione",       ("regole", "modello"),               "maschera", 0),
    ("ID_CLOUD",       "tenant ID, subscription ID, account cloud",              ("modello", "regole"),               "maschera", 0),
    ("ID_DISPOSITIVO", "seriale, IMEI, ICCID, service tag, ID di controllo remoto", ("modello", "dizionario"),        "maschera", 0),
    ("SALUTE",         "diagnosi, farmaci, esenzioni, codici ICD",               ("modello",),                        "profilo",  2),
    ("DATO_PARTICOLARE", "sindacato, religione, orientamento, condanne (art. 9 e 10 GDPR)", ("modello",),            "profilo",  2),
    ("DATA",           "date diverse dalla nascita",                             (),                                  "lascia",   2),
    ("IMPORTO",        "somme di denaro",                                        (),                                  "lascia",   2),
]

ETICHETTE = [t[0] for t in TASSONOMIA if t[4] == 0]          # quelle del modello v0
CLASSI = ["O"] + [f"{p}-{e}" for e in ETICHETTE for p in ("B", "I")]
ID_CLASSE = {c: i for i, c in enumerate(CLASSI)}

if __name__ == "__main__":
    print(f"{len(ETICHETTE)} etichette nel modello v0, {len(CLASSI)} classi BIO")
    for e, d, s, a, f in TASSONOMIA:
        print(f"{e:17} fase {f}  {a:9} {'+'.join(s) or '-':22} {d}")
