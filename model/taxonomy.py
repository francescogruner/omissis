# -*- coding: utf-8 -*-
"""Tassonomia di Omissis (v0): unica fonte per etichette, strati e azione predefinita.

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
  - DATA_NASCITA si maschera sempre; le altre date sono DATA, che di serie resta in chiaro.
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
TAXONOMY = [
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
    # --- dalla versione 2: quasi-identificatori e categorie particolari (art. 9 GDPR). Il modello le riconosce tutte;
    #     nel programma sono spente finche' non si sceglie la protezione rigorosa, perche' toglierle cambia il senso del testo.
    ("DATA",           "date e date con ora, diverse dalla nascita",             ("modello",),                        "profilo",  0),
    ("ORA",            "orari",                                                  ("modello",),                        "profilo",  0),
    ("ETA",            "eta' di una persona (il numero)",                        ("modello",),                        "profilo",  0),
    ("GENERE",         "sesso o genere",                                         ("modello",),                        "profilo",  0),
    ("TITOLO",         "titoli e appellativi: Dott., Avv., Sig.ra",              ("modello",),                        "profilo",  0),
    ("PROFESSIONE",    "mestiere, mansione, condizione lavorativa",              ("modello",),                        "profilo",  0),
    ("ISTRUZIONE",     "titolo di studio",                                       ("modello",),                        "profilo",  0),
    ("ORIGINE",        "nazionalita', etnia, lingua madre",                      ("modello",),                        "profilo",  0),
    ("LUOGO",          "paese, regione, provincia, coordinate (non la citta')",  ("modello",),                        "profilo",  0),
    ("SALUTE",         "diagnosi, farmaci, gruppo sanguigno, invalidita'",       ("modello",),                        "profilo",  0),
    ("RELIGIONE",      "fede o convinzione religiosa",                           ("modello",),                        "profilo",  0),
    ("POLITICA",       "opinioni politiche, appartenenza a partiti e sindacati", ("modello",),                        "profilo",  0),
    ("ORIENTAMENTO",   "orientamento sessuale",                                  ("modello",),                        "profilo",  0),
    ("IMPORTO",        "somme di denaro",                                        (),                                  "lascia",   2),
]

LABELS = [t[0] for t in TAXONOMY if t[4] == 0]          # quelle che il modello riconosce
OFF = [t[0] for t in TAXONOMY if t[4] == 0 and t[3] == "profilo"]   # riconosciute ma non sostituite, salvo richiesta
CLASSES = ["O"] + [f"{p}-{e}" for e in LABELS for p in ("B", "I")]
CLASS_ID = {c: i for i, c in enumerate(CLASSES)}

if __name__ == "__main__":
    print(f"{len(LABELS)} etichette nel modello ({len(OFF)} spente di serie), {len(CLASSES)} classi BIO")
    for e, d, s, a, f in TAXONOMY:
        print(f"{e:17} fase {f}  {a:9} {'+'.join(s) or '-':22} {d}")
