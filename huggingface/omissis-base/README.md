---
license: apache-2.0
language:
- it
base_model: jhu-clsp/mmBERT-base
pipeline_tag: token-classification
library_name: transformers
tags:
- pii
- privacy
- anonymization
- pseudonymization
- gdpr
- italian
- token-classification
---

# omissis-base

**English** · [Italiano](#italiano)

Detects personal and confidential data in Italian text, so it can be replaced with placeholders
before the text is sent to an AI service. It is the model behind
[Omissis](https://github.com/francescogruner/omissis), which also contains the desktop program, the
browser extension and the code to redo the training.

- **Base:** [mmBERT-base](https://huggingface.co/jhu-clsp/mmBERT-base) (307.8 M parameters), trained by us starting from the language model
- **Lighter version:** [omissis-small](https://huggingface.co/francescogruner/omissis-small) (140.9 M)
- **Licence:** Apache 2.0

## Labels

28 labels, BIO format. The label names are Italian because they are also what the AI service sees
in a placeholder (`[PERSONA_1]`, `[IBAN_2]`).

| Area | Labels |
|---|---|
| People and contacts | `PERSONA` (person) `EMAIL` `TELEFONO` (phone) `INDIRIZZO` (street address) `CAP` (postcode) `CITTA` (city) `DATA_NASCITA` (date of birth) |
| Identifiers | `CF` (tax code) `PIVA` (VAT number) `DOC_ID` (identity document) `TARGA` (licence plate) `ID_VEICOLO` (vehicle identification number) `ID_PRATICA` (case or ticket number) `CATASTO` (land-registry data) `ID_UTENZA` (utility account) |
| Payments | `IBAN` `CARTA` (card number) `CARTA_SEC` (card security code) |
| Organisations | `ORG` |
| IT | `IP` `MAC` `HOSTNAME` `DOMINIO` (domain) `URL` `ACCOUNT` `SEGRETO` (password, key, token) `ID_CLOUD` (cloud identifier) `ID_DISPOSITIVO` (serial number) |

## Usage

With the model alone:

```python
from transformers import pipeline
ner = pipeline("token-classification", model="francescogruner/omissis-base", aggregation_strategy="simple")
ner("Scrivi a Giulia Ferraresi, giulia.ferraresi@example.com, per il ticket del PC-AMM-07.")
```

The best result comes from `inference.py` in the repository, which adds to the model:

- a **decision threshold** (0.85, in the file `omissis.json`): a word stays "not sensitive" only if
  the model is at least that sure. It is the knob between protection and amount of masked text;
- **rules** with checksum validation for tax code, VAT number, IBAN, cards, IP addresses;
- **lists**: well-known names to leave in clear (vendors and products) and terms chosen by the user.

## Training data

180,000 **synthetic** documents in Italian, produced by a generator written for this project
(`generate_data.py`): legal, tax, insurance, healthcare, human resources, banking, IT support and
security. Values such as tax codes and IBANs carry valid check digits.
**No real personal data was used for training.**

Recipe: one epoch, batch 32, learning rate 5e-5 with layer-wise decay 0.95, weight moving average
0.999, 8% of input words masked, label smoothing 0.05.

## Measurements

On a **private** set of 2,000 real IT-support texts, never used to tune the model and not
publishable, with threshold 0.85, rules and lists active:

| Measure | Value |
|---|---|
| Known sensitive values that end up masked | 98.4% |
| Masked text over the total | 17.2% |
| Company names in free text that end up masked | 89% |
| Time for a short text on CPU | about 63 ms |

How to read them:

- the "known values" are those that can be derived from the data attached to each text (requester,
  company, contacts): the measure says how many of **those** are covered, not how many of all the
  sensitive data in the text;
- **precision** on real text is not measured: that needs a hand-labelled set. The 17.2% of masked
  text gives the order of magnitude of how much the model intervenes;
- on synthetic held-out data the model scores above 99%, but those texts come from the same
  generator as the training set: it is not an independent measure and should not be quoted as one.

## Without PyTorch

The folder also contains `model.onnx` (1.2 GB): the same model in ONNX format, to run it on CPU with
`onnxruntime` alone. On the check texts it gives the same results as the PyTorch version.

## Limits

- Built for Italian; in other languages it recognises formats (email, IBAN, IP addresses) but has
  not been measured.
- A date without context may be labelled as a date of birth.
- Company names made of common words are the hardest case.
- It is a filter, not a guarantee: for terms the model cannot know, use a list.

## Citation

```
Francesco Gruner, Omissis: local pseudonymisation of personal data for the use of AI assistants, 2026.
https://github.com/francescogruner/omissis
```

---

# Italiano

Riconosce dati personali e riservati in testi italiani, per sostituirli con segnaposto prima di
mandare un testo a un servizio di intelligenza artificiale. È il modello di
[Omissis](https://github.com/francescogruner/omissis), che contiene anche il programma, l'estensione
del browser e il codice per rifare l'addestramento.

- **Base:** [mmBERT-base](https://huggingface.co/jhu-clsp/mmBERT-base) (307,8 M di parametri), addestrato da noi a partire dal modello linguistico
- **Versione più leggera:** [omissis-small](https://huggingface.co/francescogruner/omissis-small) (140,9 M)
- **Licenza:** Apache 2.0

## Etichette

28 etichette, in formato BIO:

| Ambito | Etichette |
|---|---|
| Persone e contatti | `PERSONA` `EMAIL` `TELEFONO` `INDIRIZZO` `CAP` `CITTA` `DATA_NASCITA` |
| Identificativi | `CF` `PIVA` `DOC_ID` `TARGA` `ID_VEICOLO` `ID_PRATICA` `CATASTO` `ID_UTENZA` |
| Pagamenti | `IBAN` `CARTA` `CARTA_SEC` |
| Organizzazioni | `ORG` |
| Informatica | `IP` `MAC` `HOSTNAME` `DOMINIO` `URL` `ACCOUNT` `SEGRETO` `ID_CLOUD` `ID_DISPOSITIVO` |

## Uso

Con il solo modello: vedi l'esempio in inglese qui sopra. Il risultato migliore si ha con
`inference.py` del repository, che aggiunge al modello:

- una **soglia di decisione** (0,85, nel file `omissis.json`): una parola resta "non sensibile" solo se
  il modello ne è sicuro almeno a quel livello. È la manopola tra protezione e testo mascherato;
- le **regole** con controllo delle cifre per codice fiscale, partita IVA, IBAN, carte, indirizzi IP;
- gli **elenchi**: nomi noti da lasciare in chiaro (produttori e prodotti) e termini scelti dall'utente.

## Dati di addestramento

180.000 documenti **sintetici** in italiano, prodotti da un generatore scritto per questo progetto
(`generate_data.py`): ambito legale, fiscale, assicurativo, sanitario, risorse umane, bancario,
assistenza informatica e sicurezza. Valori come codici fiscali e IBAN hanno cifre di controllo valide.
**Nessun dato personale reale è stato usato per l'addestramento.**

Ricetta: un'epoca, lotto 32, tasso di apprendimento 5e-5 con decadimento per strato 0,95, media mobile
dei pesi 0,999, 8% delle parole in ingresso mascherate, label smoothing 0,05.

## Misure

Su un insieme **privato** di 2.000 testi reali di assistenza informatica, mai usato per mettere a
punto il modello e non pubblicabile, con soglia 0,85, regole ed elenchi attivi:

| Misura | Valore |
|---|---|
| Valori sensibili noti che risultano mascherati | 98,4 % |
| Testo mascherato sul totale | 17,2 % |
| Nomi di azienda in testo libero mascherati | 89 % |
| Tempo per testo breve su processore | circa 63 ms |

Come leggerle:

- i "valori noti" sono quelli ricavabili dai dati che accompagnano ogni testo (richiedente, azienda,
  contatti): la misura dice quanti di **quelli** vengono coperti, non quanti di tutti i dati sensibili
  presenti;
- la **precisione** sui testi reali non è misurata: serve un insieme etichettato a mano. Il 17,2% di
  testo mascherato dà l'ordine di grandezza di quanto il modello interviene;
- sui dati sintetici di controllo il modello supera il 99%, ma quei testi vengono dallo stesso
  generatore dell'addestramento: non è una misura indipendente e non va citata come tale.

## Senza PyTorch

Nella cartella c'è anche `model.onnx` (1,2 GB): lo stesso modello in formato ONNX, per farlo girare sul
processore con il solo `onnxruntime`. Sui testi di controllo dà gli stessi risultati della versione PyTorch.

## Limiti

- Pensato per l'italiano; su altre lingue riconosce i formati (email, IBAN, indirizzi IP) ma non è
  stato misurato.
- Una data senza contesto può essere etichettata come data di nascita.
- I nomi di azienda composti da parole comuni sono il caso più difficile.
- È un filtro, non una garanzia: per i termini che il modello non può conoscere va usato un elenco.
