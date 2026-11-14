# -*- coding: utf-8 -*-
"""How much does a model mask things that are public knowledge?   python public_probe.py <model folder> [--show]

Sentences about public facts: institutions, well-known companies and products, famous people, places, laws,
history. Nothing in them is personal data that needs protecting, so every masked span is over-masking: the AI
service would receive "[PERSONA_1] painted the Mona Lisa" and could no longer use what it knows.
The sentences are written for this test and are not in the training data.
"""
import collections
import sys

from inference import Detector

PUBLIC = {
    "institutions": [
        "L'Agenzia delle Entrate ha pubblicato la circolare sul nuovo regime forfettario.",
        "Il Garante per la protezione dei dati personali ha sanzionato la società per violazione del GDPR.",
        "La Corte di Cassazione ha confermato la sentenza della Corte d'Appello di Milano.",
        "L'INPS eroga l'assegno unico tramite il portale istituzionale.",
        "Il Parlamento europeo ha approvato il regolamento sull'intelligenza artificiale.",
        "La Banca d'Italia e la Banca centrale europea hanno lasciato i tassi invariati.",
        "Il Comune di Bologna ha aperto il bando per i contributi alle imprese.",
        "The European Commission opened an investigation under the Digital Markets Act.",
        "Il Ministero della Salute raccomanda la vaccinazione antinfluenzale.",
        "L'Università di Padova è una delle più antiche d'Europa.",
    ],
    "companies and products": [
        "Microsoft ha rilasciato un aggiornamento di Windows 11 e di Office 365.",
        "Ferrari e Lamborghini hanno presentato i nuovi modelli al Salone di Ginevra.",
        "Poste Italiane e Intesa Sanpaolo offrono il servizio tramite SPID.",
        "Ho installato Fortinet FortiGate e uno switch Cisco Catalyst nel rack.",
        "Amazon Web Services e Google Cloud hanno regioni in Italia.",
        "Il backup è su Veeam, la posta su Exchange Online, l'antivirus è Bitdefender.",
        "Stellantis produce la Fiat Panda nello stabilimento di Pomigliano.",
        "Apple presented the new iPhone and Samsung answered with the Galaxy.",
        "La fattura elettronica passa dal Sistema di Interscambio e si può gestire con Zucchetti o TeamSystem.",
        "Netflix, Spotify e YouTube sono i servizi più usati.",
    ],
    "famous people": [
        "Leonardo da Vinci dipinse la Gioconda, oggi esposta al Louvre.",
        "Dante Alighieri scrisse la Divina Commedia in esilio.",
        "Il presidente della Repubblica Sergio Mattarella ha firmato il decreto.",
        "Giuseppe Verdi nacque a Busseto nel 1813.",
        "Albert Einstein published the theory of general relativity in 1915.",
        "Papa Francesco ha celebrato la messa in piazza San Pietro.",
        "Il teorema di Pitagora si studia alle scuole medie.",
        "Alessandro Manzoni è l'autore dei Promessi Sposi.",
        "Secondo Bill Gates il software cambierà la sanità.",
        "La legge Fornero prende il nome dalla ministra Elsa Fornero.",
    ],
    "places and geography": [
        "Roma è la capitale d'Italia e Milano il centro finanziario.",
        "Il Colosseo si trova a Roma, la Torre pendente a Pisa.",
        "Il fiume Po attraversa la Pianura Padana fino al mare Adriatico.",
        "La Sicilia e la Sardegna sono le due isole maggiori.",
        "Il traforo del Monte Bianco collega l'Italia alla Francia.",
        "Paris is the capital of France and Berlin the capital of Germany.",
        "L'aeroporto di Fiumicino è il principale scalo italiano.",
        "Venezia, Firenze e Napoli sono tra le città più visitate.",
    ],
    "laws, dates and history": [
        "Il Regolamento (UE) 2016/679 è applicabile dal 25 maggio 2018.",
        "La Costituzione italiana è entrata in vigore il 1º gennaio 1948.",
        "L'articolo 2043 del codice civile riguarda il risarcimento per fatto illecito.",
        "La seconda guerra mondiale finì nel 1945.",
        "Il decreto legislativo 81/2008 riguarda la sicurezza sul lavoro.",
        "La direttiva NIS2 doveva essere recepita entro il 17 ottobre 2024.",
        "Il 2 giugno si celebra la Festa della Repubblica.",
        "La scadenza per il modello 730 è il 30 settembre.",
    ],
    "technical, no personal data": [
        "Per riavviare il servizio usare systemctl restart nginx e controllare la porta 443.",
        "L'indirizzo 127.0.0.1 è il localhost, 8.8.8.8 è il DNS pubblico di Google.",
        "Scarica l'aggiornamento da https://www.microsoft.com/it-it/software-download.",
        "Il protocollo HTTPS usa TLS 1.3; la versione 1.0 è deprecata.",
        "Aprire il Pannello di controllo e scegliere Programmi e funzionalità.",
        "Il dominio example.com è riservato alla documentazione.",
    ],
}


# The same idea with people, places and phrasings that appear nowhere in the training templates: it tells whether
# the model learned "public context" or only memorised a list of names.
UNSEEN = {
    "famous people, unseen": [
        "Margherita Hack ha dedicato la vita alla divulgazione dell'astrofisica.",
        "Le inchieste di Oriana Fallaci sono ancora oggetto di studio nelle scuole di giornalismo.",
        "Durante il settennato di Carlo Azeglio Ciampi l'Italia entrò nell'euro.",
        "Sofia Goggia ha conquistato la coppa di discesa per la quarta volta.",
        "L'ultimo film di Paolo Sorrentino è candidato all'Oscar.",
        "In questo saggio Noam Chomsky critica il ruolo dei media.",
        "Margaret Thatcher governò il Regno Unito per undici anni.",
        "Serena Williams ha vinto ventitré tornei del Grande Slam.",
        "Chi ha scritto L'amica geniale? Elena Ferrante, uno pseudonimo.",
        "Il cancelliere Olaf Scholz ha incontrato la premier danese a Copenaghen.",
        "What did Franklin Roosevelt promise with the New Deal?",
        "Le poesie di Eugenio Montale furono premiate con il Nobel nel 1975.",
    ],
    "places, unseen": [
        "Matera è stata capitale europea della cultura.",
        "Da Bergamo a Lecce ci vogliono dieci ore di treno.",
        "Oslo e Helsinki sono tra le capitali più care del mondo.",
        "Il clima di Trento è più rigido di quello di Salerno.",
        "Kyoto ospitò la conferenza sul clima del 1997.",
        "In Umbria si produce un ottimo olio; il capoluogo è Perugia.",
        "Which is bigger, Lisbon or Porto?",
        "Il Brennero collega il Tirolo all'Alto Adige.",
    ],
    "companies, unseen": [
        "Il titolo di Leonardo è salito dopo la commessa per gli elicotteri.",
        "Esselunga ha aperto un nuovo punto vendita; Conad risponde con gli sconti.",
        "Airbus e Boeing si dividono il mercato degli aerei di linea.",
        "Siemens e Schneider Electric producono quadri di automazione.",
        "La nuova collezione di Moncler sfila a Milano.",
        "Qual è la differenza tra Revolut e una banca tradizionale?",
    ],
}
# The opposite check: personal data in ordinary private contexts. Here every name must be masked, including the
# namesakes of famous people and names next to a public word. Each entry: (sentence, values that must be masked).
PRIVATE = [
    ("Buongiorno, sono Mario Draghi dell'ufficio acquisti, mi può richiamare al 347 5551234?", ["Mario Draghi", "347 5551234"]),
    ("Il cliente Giuseppe Verdi (cod. fiscale VRDGPP80A01H501U) non riesce ad accedere alla posta.", ["Giuseppe Verdi", "VRDGPP80A01H501U"]),
    ("Nuova utenza per Laura Pausini, reparto contabilità: email laura.pausini@nevatek.example.", ["Laura Pausini", "laura.pausini@nevatek.example"]),
    ("Ticket aperto da Paolo Maldini della Nevatek S.r.l.: il PC-AMM-07 non si accende.", ["Paolo Maldini", "Nevatek S.r.l.", "PC-AMM-07"]),
    ("La signora Elsa Fornero, residente a Torino in via Roma 12, chiede il rimborso.", ["Elsa Fornero", "via Roma 12"]),
    ("Contratto tra Rossi Impianti S.r.l. e il sig. Ermete Valcanover, nato a Milano il 3 marzo 1980.", ["Rossi Impianti S.r.l.", "Ermete Valcanover", "3 marzo 1980"]),
    ("Inoltro la richiesta di Giulia Ferraresi: password provvisoria Estate2024!, da cambiare al primo accesso.", ["Giulia Ferraresi", "Estate2024!"]),
    ("Il server SRV-DC01 (192.168.10.5) della Ferrari Costruzioni Srl di Modena è irraggiungibile.", ["SRV-DC01", "192.168.10.5", "Ferrari Costruzioni Srl"]),
    ("Chiamare il dott. Albert Rossi allo 0461 123456 per la pratica n. POL-2024-004512.", ["Albert Rossi", "0461 123456", "POL-2024-004512"]),
    ("Bonifico a favore di Enzo Ferrari, IBAN IT60X0542811101000000123456.", ["Enzo Ferrari", "IT60X0542811101000000123456"]),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    detector = Detector(sys.argv[1], never=[], always=[])
    show = "--show" in sys.argv
    total_chars = total_masked = 0
    by_label = collections.Counter()
    print(f"{sys.argv[1]}: what gets masked in sentences that contain only public knowledge\n")
    groups = dict(PUBLIC)
    if "--unseen" in sys.argv:
        groups.update(UNSEEN)
    for group, sentences in groups.items():
        found = detector.many(sentences, complete=True)
        chars = sum(len(s) for s in sentences)
        masked = sum(e - s for spans in found for s, e, _ in spans)
        touched = sum(bool(spans) for spans in found)
        total_chars, total_masked = total_chars + chars, total_masked + masked
        by_label.update(label for spans in found for _, _, label in spans)
        print(f"  {group:30} {touched:2} of {len(sentences):2} sentences touched, {masked / chars:5.1%} of the text masked")
        if show:
            for sentence, spans in zip(sentences, found):
                for s, e, label in spans:
                    print(f"      {label:12} {sentence[s:e]}")
    print(f"\n  overall: {total_masked / total_chars:.1%} of the text masked · by label: {dict(by_label.most_common())}")
    if "--unseen" in sys.argv:   # and what must be masked: private sentences, namesakes of famous people included
        found = detector.many([s for s, _ in PRIVATE], complete=True)
        missed, total = [], 0
        for (sentence, values), spans in zip(PRIVATE, found):
            covered = bytearray(len(sentence))
            for s, e, _ in spans:
                covered[s:e] = b"\x01" * (e - s)
            for value in values:
                total += 1
                at = sentence.index(value)
                if not all(covered[i] for i in range(at, at + len(value)) if sentence[i].isalnum()):
                    missed.append(value)
        print(f"\n  private sentences: {total - len(missed)} of {total} values masked" + (f" · MISSED: {missed}" if missed else ""))


if __name__ == "__main__":
    main()
