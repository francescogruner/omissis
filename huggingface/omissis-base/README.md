---
license: apache-2.0
language:
- it
- en
- de
- fr
- es
- nl
- multilingual
base_model: jhu-clsp/mmBERT-base
pipeline_tag: token-classification
library_name: transformers
datasets:
- ai4privacy/pii-masking-openpii-1m
- nvidia/Nemotron-PII
- gretelai/gretel-pii-masking-en-v1
- gretelai/synthetic_pii_finance_multilingual
- piimb/privy
- dglover1/mapa-eur-lex
- Wismut/nym-pii-multilingual-data
- mattmdjaga/text-anonymization-benchmark-train
- urchade/synthetic-pii-ner-mistral-v1
tags:
- pii
- privacy
- anonymization
- pseudonymization
- gdpr
- italian
- multilingual
- token-classification
---

# omissis-base

**English** · [Italiano](#italiano)

Detects personal and confidential data in text, so it can be replaced with placeholders before the
text is sent to an AI service. Built first for Italian and for the texts of IT support (host names,
accounts, secrets, customer names), and trained on 23 languages. It is the model behind
[Omissis](https://github.com/francescogruner/omissis), which also contains the desktop program, the
browser extension and the code to redo the training.

- **Base:** [mmBERT-base](https://huggingface.co/jhu-clsp/mmBERT-base) (307.8 M parameters), trained by us starting from the language model
- **Lighter version:** [omissis-small](https://huggingface.co/francescogruner/omissis-small) (140.9 M)
- **Licence:** Apache 2.0

## Labels

41 labels, BIO format. The label names are Italian because they are also what the AI service sees
in a placeholder (`[PERSONA_1]`, `[IBAN_2]`).

**28 identifiers**, always meant to be masked:

| Area | Labels |
|---|---|
| People and contacts | `PERSONA` (person) `EMAIL` `TELEFONO` (phone) `INDIRIZZO` (street address) `CAP` (postcode) `CITTA` (city) `DATA_NASCITA` (date of birth) |
| Identifiers | `CF` (tax code, social security number) `PIVA` (VAT number) `DOC_ID` (identity document) `TARGA` (licence plate) `ID_VEICOLO` (vehicle identification number) `ID_PRATICA` (case, policy, customer or record number) `CATASTO` (land-registry data) `ID_UTENZA` (utility account) |
| Payments | `IBAN` (also other bank account numbers) `CARTA` (card number) `CARTA_SEC` (card security code) |
| Organisations | `ORG` (a company, firm or private customer; public bodies and well-known vendors are left alone) |
| IT | `IP` `MAC` `HOSTNAME` `DOMINIO` (domain) `URL` `ACCOUNT` `SEGRETO` (password, key, token) `ID_CLOUD` (cloud identifier) `ID_DISPOSITIVO` (serial number) |

**13 more**, details that identify only together with something else, and special categories of
data. The model recognises them; the Omissis program leaves them in clear unless asked, because
removing them changes the meaning of a text:

`DATA` (date) `ORA` (time) `ETA` (age) `GENERE` (gender) `TITOLO` (title: Mr, Dr) `PROFESSIONE`
(occupation) `ISTRUZIONE` (education) `ORIGINE` (nationality, ethnicity, language) `LUOGO` (country,
region, coordinates) `SALUTE` (health) `RELIGIONE` (religion) `POLITICA` (political views)
`ORIENTAMENTO` (sexual orientation)

## Usage

With the model alone:

```python
from transformers import pipeline
ner = pipeline("token-classification", model="francescogruner/omissis-base", aggregation_strategy="simple")
ner("Scrivi a Giulia Ferraresi, giulia.ferraresi@example.com, per il ticket del PC-AMM-07.")
```

The model is **cautious by construction**: the decision thresholds are inside the weights, so the
most likely class is already the cautious answer (a word stays "not sensitive" only if the model is
at least 93% sure; 98% for company names, where a miss costs more; 40% for domain names, which the
model otherwise sees too easily in English prose). Used this way it returns all 41 labels: drop the
13 above if you only want identifiers.

`inference.py` in the repository adds to the model:

- the choice of which of the 13 extra labels to return (none by default) and of the thresholds
  (file `omissis.json`);
- **rules** with checksum validation for tax code, VAT number, IBAN, cards, IP addresses;
- **lists**: well-known names to leave in clear (vendors and products) and terms chosen by the user.

## Training data

About 1.05 million texts from ten sources. Everything is synthetic except two collections of court
decisions, which contain real names that are already public in the decisions themselves.

- **200,000 synthetic documents in Italian**, produced by a generator written for this project
  (`generate_data.py`): legal, tax, insurance, healthcare, human resources, banking, IT support and
  security, plus sentences about public things that must not be masked. Values such as tax codes and
  IBANs carry valid check digits.
- **The training splits of nine public datasets** (their test splits were never used):

| Dataset | Licence | What it brings |
|---|---|---|
| [ai4privacy/pii-masking-openpii-1m](https://huggingface.co/datasets/ai4privacy/pii-masking-openpii-1m) | CC BY 4.0 | 23 languages |
| [nvidia/Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII) | CC BY 4.0 | English documents, 55 kinds of data |
| [gretelai/gretel-pii-masking-en-v1](https://huggingface.co/datasets/gretelai/gretel-pii-masking-en-v1) | Apache 2.0 | English domain documents |
| [gretelai/synthetic_pii_finance_multilingual](https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual) | Apache 2.0 | full financial documents in 7 languages |
| [piimb/privy](https://huggingface.co/datasets/piimb/privy) | MIT | JSON, SQL, protocol traces |
| [dglover1/mapa-eur-lex](https://huggingface.co/datasets/dglover1/mapa-eur-lex) | CC BY 4.0 | EUR-Lex court documents in 21 languages, annotated by hand |
| [Wismut/nym-pii-multilingual-data](https://huggingface.co/datasets/Wismut/nym-pii-multilingual-data) | MIT | 23 languages, labels exact by construction |
| [Text Anonymization Benchmark](https://huggingface.co/datasets/mattmdjaga/text-anonymization-benchmark-train) | MIT | European Court of Human Rights cases, annotated by hand |
| [urchade/synthetic-pii-ner-mistral-v1](https://huggingface.co/datasets/urchade/synthetic-pii-ner-mistral-v1) | Apache 2.0 | short texts in 5 languages, also medical |

The sources do not annotate the same things: one labels occupations but not titles, another the
opposite, and none of the public ones labels host names. So every text carries the name of its
source, and the training does not penalise a label that the source could not have given. The rules,
source by source, are in `build_train.py`.

Recipe: one epoch over about 1.05 million texts, batches of 8,000 tokens, learning rate 5e-5 with layer-wise decay 0.95, weight moving average 0.999, 8% of input words masked.

## Measurements

All measured on 13 November 2026, on the published weights.

### Public benchmark

[PIIMB](https://huggingface.co/datasets/piimb/pii-masking-benchmark): about 150,000 sentences in six
tasks, scored at character level without looking at the label (F2, which weighs a missed character
more than a masked one). Weights alone, all labels, as PIIMB measures every model:

| | Average F2 | ai4privacy-en | ai4privacy-multi | nemotron-pii | gretel | privy | mapa-eur-lex |
|---|---|---|---|---|---|---|---|
| **omissis-base** | **0.911** | 0.988 | 0.992 | 0.970 | 0.974 | 0.940 | 0.600 |
| best other model of the 36 listed | 0.836 | 0.975 | 0.970 | 0.907 | 0.973 | 0.818 | 0.373 |

How to read it:

- all six tasks come from datasets whose **training** splits are among our training data. The test
  sentences were never used, and the training texts that also occur in the benchmark were removed;
  still, a model trained on the same families of data has an advantage over one that was not, and
  several models in the list were not;
- the best other model in a single task scores more than ours in three of them (nemotron-pii 0.972,
  gretel 0.983, privy 0.987): ours is first on average, not everywhere;
- legal text (mapa-eur-lex) is where every model does worst, ours included.

The same benchmark, as the Omissis program works (thresholds, rules, lists):

| | ai4privacy-en | ai4privacy-multi | gretel | nemotron-pii | privy |
|---|---|---|---|---|---|
| Precision with the 28 identifiers only (the default) | 96.6% | 97.4% | 93.8% | 95.4% | 89.8% |

With all 41 labels on: average F2 0.909, recall 93.7%, precision 82.6%.

### Next to other models

Five other models, measured by us with the same code as ours (`benchmark.py --mode other`: the weights alone,
most likely class). For each of them the PIIMB average obtained this way matches the published one.

| Model | Parameters | PIIMB average | PIIMB, Italian sentences | Real IT-support texts, known values protected |
|---|---|---|---|---|
| **omissis-base** | 308 M | **0.911** | **0.925** | **95.1%** (98.8% as the program works) |
| **omissis-small** | 141 M | **0.912** | **0.927** | **94.6%** (98.8% as the program works) |
| OpenMed/privacy-filter-multilingual-v2 | 1,400 M | 0.840 | 0.879 | 81.5% |
| openai/privacy-filter | 1,400 M | 0.664 | 0.811 | 79.0% |
| bardsai/eu-pii-anonimization-multilang | 278 M | 0.686 | 0.705 | 88.3% |
| tabularisai/eu-pii-safeguard | 559 M | 0.634 | 0.687 | 40.5% |
| iiiorg/piiranha-v1-detect-personal-information | 278 M | 0.518 | 0.687 | 32.3% |

Not first everywhere: on the 40 CVs of CV-PII-Bench the bardsai model scores 0.837, ours 0.75 and 0.71 with
every label on (0.840 as the program ships, with the 28 identifiers only). The full comparison, with what it
does and does not show, is in
[docs/BENCHMARKS.md](https://github.com/francescogruner/omissis/blob/main/docs/BENCHMARKS.md).

### Real texts

On a **private** set of 2,000 real IT-support texts, not publishable, with the thresholds of the
model, rules and lists active, the 28 identifiers only:

| Measure | This model | Previous version |
|---|---|---|
| Known sensitive values that end up masked | 98.8% | 98.4% |
| Masked text over the total | 17.0% | 17.2% |
| Company names in free text that end up masked | 94% | 89% |

How to read them:

- the "known values" are those that can be derived from the data attached to each text (requester,
  company, contacts): the measure says how many of **those** are covered, not how many of all the
  sensitive data in the text;
- the thresholds were chosen on a second set of 2,000 texts, kept apart; this set was used to
  compare training rounds and to confirm the thresholds, so it is not untouched;
- **precision** on real text is not measured yet: that needs a hand-labelled set, which is being
  prepared. The share of masked text gives the order of magnitude of how much the model intervenes.

### Public things

In 78 sentences that contain only public knowledge (institutions, famous people, laws, cities named
in general, well-known products) the model masks 2.9% of the text; the previous version masked
11.6%. In 24 control sentences with private data it masks all 24 values. `public_probe.py`.

## Without PyTorch

The folder also contains `model.onnx` (1.2 GB): the same model in ONNX format, to run it on CPU with
`onnxruntime` alone. On 405 check texts it gives exactly the same results as the PyTorch version.
On CPU, for a text of average length: about 79 ms with PyTorch, 61 ms with ONNX.

## Limits

- Strongest in Italian and on IT-support text; measured in other languages only through the public
  benchmark above.
- Legal text: about a third of the personal data in court documents is missed.
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

Riconosce dati personali e riservati in un testo, per sostituirli con segnaposto prima di mandarlo a
un servizio di intelligenza artificiale. Nasce per l'italiano e per i testi dell'assistenza
informatica (nomi di macchine, utenze, credenziali, nomi dei clienti), ed è addestrato su 23 lingue.
È il modello di [Omissis](https://github.com/francescogruner/omissis), che contiene anche il
programma, l'estensione del browser e il codice per rifare l'addestramento.

- **Base:** [mmBERT-base](https://huggingface.co/jhu-clsp/mmBERT-base) (307,8 M di parametri), addestrato da noi a partire dal modello linguistico
- **Versione più leggera:** [omissis-small](https://huggingface.co/francescogruner/omissis-small) (140,9 M)
- **Licenza:** Apache 2.0

## Etichette

41 etichette, in formato BIO.

**28 identificativi**, da mascherare sempre:

| Ambito | Etichette |
|---|---|
| Persone e contatti | `PERSONA` `EMAIL` `TELEFONO` `INDIRIZZO` `CAP` `CITTA` `DATA_NASCITA` |
| Identificativi | `CF` `PIVA` `DOC_ID` `TARGA` `ID_VEICOLO` `ID_PRATICA` `CATASTO` `ID_UTENZA` |
| Pagamenti | `IBAN` `CARTA` `CARTA_SEC` |
| Organizzazioni | `ORG` (azienda, studio o cliente privato; enti pubblici e fornitori noti restano in chiaro) |
| Informatica | `IP` `MAC` `HOSTNAME` `DOMINIO` `URL` `ACCOUNT` `SEGRETO` `ID_CLOUD` `ID_DISPOSITIVO` |

**Altre 13**, dettagli che identificano solo insieme ad altro e categorie particolari di dati. Il
modello le riconosce; il programma Omissis le lascia in chiaro finché non glielo si chiede, perché
toglierle cambia il senso di un testo:

`DATA` `ORA` `ETA` `GENERE` `TITOLO` `PROFESSIONE` `ISTRUZIONE` `ORIGINE` `LUOGO` `SALUTE`
`RELIGIONE` `POLITICA` `ORIENTAMENTO`

## Uso

Con il solo modello: vedi l'esempio in inglese qui sopra.

Il modello è **prudente per costruzione**: le soglie di decisione sono dentro i pesi, quindi la classe
più probabile è già la risposta prudente (una parola resta "non sensibile" solo se il modello ne è
sicuro almeno al 93%; al 98% per i nomi di azienda, dove sbagliare costa di più; al 40% per i domini,
che altrimenti vede troppo facilmente nei testi in inglese). Usato così restituisce tutte le 41
etichette: basta scartare le 13 qui sopra se servono solo gli identificativi.

`inference.py` del repository aggiunge al modello:

- la scelta di quali delle 13 etichette in più restituire (nessuna, di serie) e delle soglie (file
  `omissis.json`);
- le **regole** con controllo delle cifre per codice fiscale, partita IVA, IBAN, carte, indirizzi IP;
- gli **elenchi**: nomi noti da lasciare in chiaro (produttori e prodotti) e termini scelti dall'utente.

## Dati di addestramento

Circa 1,05 milioni di testi da dieci fonti. Tutto è sintetico, tranne due raccolte di sentenze che
contengono nomi veri, già pubblici nelle sentenze stesse.

- **200.000 documenti sintetici in italiano**, prodotti da un generatore scritto per questo progetto
  (`generate_data.py`): ambito legale, fiscale, assicurativo, sanitario, risorse umane, bancario,
  assistenza informatica e sicurezza, più frasi su cose pubbliche che non vanno mascherate. Valori
  come codici fiscali e IBAN hanno cifre di controllo valide.
- **Le parti di addestramento di nove raccolte pubbliche** (quelle di prova non sono mai state usate):
  l'elenco, con le licenze, è nella tabella in inglese qui sopra.

Le fonti non annotano le stesse cose: una etichetta le professioni ma non i titoli, un'altra il
contrario, e nessuna di quelle pubbliche i nomi delle macchine. Per questo ogni testo porta il nome
della sua fonte, e l'addestramento non penalizza un'etichetta che quella fonte non poteva dare. Le
regole, fonte per fonte, sono in `build_train.py`.

Ricetta: un'epoca su circa 1,05 milioni di testi, lotti da 8.000 token, tasso di apprendimento 5e-5 con decadimento per strato 0,95, media mobile dei pesi 0,999, 8% delle parole in ingresso mascherate.

## Misure

Tutte fatte il 13 novembre 2026, sui pesi pubblicati.

### Benchmark pubblico

[PIIMB](https://huggingface.co/datasets/piimb/pii-masking-benchmark): circa 150.000 frasi in sei
gruppi, valutate a livello di carattere senza guardare l'etichetta (F2, che pesa un carattere
sfuggito più di uno mascherato a torto). Solo i pesi, tutte le etichette, come PIIMB misura ogni
modello:

| | F2 medio | ai4privacy-en | ai4privacy-multi | nemotron-pii | gretel | privy | mapa-eur-lex |
|---|---|---|---|---|---|---|---|
| **omissis-base** | **0,911** | 0,988 | 0,992 | 0,970 | 0,974 | 0,940 | 0,600 |
| il migliore degli altri 36 modelli in elenco | 0,836 | 0,975 | 0,970 | 0,907 | 0,973 | 0,818 | 0,373 |

Come leggerlo:

- tutti e sei i gruppi vengono da raccolte le cui parti di **addestramento** sono tra i nostri dati.
  Le frasi di prova non sono mai state usate, e i testi di addestramento presenti anche nel benchmark
  sono stati tolti; resta che un modello addestrato sulle stesse famiglie di dati è avvantaggiato
  rispetto a uno che non lo è, e diversi modelli in elenco non lo sono;
- in tre gruppi il migliore degli altri modelli fa più del nostro (nemotron-pii 0,972, gretel 0,983,
  privy 0,987): il nostro è primo in media, non dappertutto;
- i testi legali (mapa-eur-lex) sono quelli in cui tutti i modelli vanno peggio, il nostro compreso.

Lo stesso benchmark, come lavora il programma Omissis (soglie, regole, elenchi):

| | ai4privacy-en | ai4privacy-multi | gretel | nemotron-pii | privy |
|---|---|---|---|---|---|
| Precisione con i soli 28 identificativi (di serie) | 96,6% | 97,4% | 93,8% | 95,4% | 89,8% |

Con tutte le 41 etichette accese: F2 medio 0,909, copertura 93,7%, precisione 82,6%.

### Accanto agli altri modelli

Cinque altri modelli, misurati da noi con lo stesso codice dei nostri (`benchmark.py --mode other`: solo i
pesi, la classe più probabile). Per ognuno la media su PIIMB ottenuta così coincide con quella pubblicata.

| Modello | Parametri | PIIMB, media | PIIMB, frasi in italiano | Testi reali di assistenza, valori noti protetti |
|---|---|---|---|---|
| **omissis-base** | 308 M | **0,911** | **0,925** | **95,1%** (98,8% come lavora il programma) |
| **omissis-small** | 141 M | **0,912** | **0,927** | **94,6%** (98,8% come lavora il programma) |
| OpenMed/privacy-filter-multilingual-v2 | 1.400 M | 0,840 | 0,879 | 81,5% |
| openai/privacy-filter | 1.400 M | 0,664 | 0,811 | 79,0% |
| bardsai/eu-pii-anonimization-multilang | 278 M | 0,686 | 0,705 | 88,3% |
| tabularisai/eu-pii-safeguard | 559 M | 0,634 | 0,687 | 40,5% |
| iiiorg/piiranha-v1-detect-personal-information | 278 M | 0,518 | 0,687 | 32,3% |

Non primi dappertutto: sui 40 curriculum di CV-PII-Bench il modello di bardsai fa 0,837, i nostri 0,75 e 0,71
con tutte le etichette accese (0,840 con le impostazioni di serie del programma, solo i 28 identificativi). Il
confronto completo, con ciò che mostra e ciò che non mostra, è in
[docs/BENCHMARKS.md](https://github.com/francescogruner/omissis/blob/main/docs/BENCHMARKS.md).

### Testi reali

Su un insieme **privato** di 2.000 testi reali di assistenza informatica, non pubblicabile, con le
soglie del modello, regole ed elenchi attivi, solo i 28 identificativi:

| Misura | Questo modello | Versione precedente |
|---|---|---|
| Valori sensibili noti che risultano mascherati | 98,8% | 98,4% |
| Testo mascherato sul totale | 17,0% | 17,2% |
| Nomi di azienda in testo libero mascherati | 94% | 89% |

Come leggerle:

- i "valori noti" sono quelli ricavabili dai dati che accompagnano ogni testo (richiedente, azienda,
  contatti): la misura dice quanti di **quelli** vengono coperti, non quanti di tutti i dati sensibili
  presenti;
- le soglie sono state scelte su un secondo insieme di 2.000 testi, tenuto a parte; questo insieme è
  servito a confrontare i giri di addestramento e a confermare le soglie, quindi non è intatto;
- la **precisione** sui testi reali non è ancora misurata: serve un insieme etichettato a mano, che è
  in preparazione. La quota di testo mascherato dà l'ordine di grandezza di quanto il modello
  interviene.

### Cose pubbliche

In 78 frasi che contengono solo cose pubbliche (istituzioni, personaggi famosi, leggi, città citate
in generale, prodotti noti) il modello maschera il 2,9% del testo; la versione precedente
l'11,6%. In 24 frasi di controllo con dati privati maschera tutti e 24 i valori. `public_probe.py`.

## Senza PyTorch

Nella cartella c'è anche `model.onnx` (1,2 GB): lo stesso modello in formato ONNX, per farlo
girare sul processore con il solo `onnxruntime`. Su 405 testi di controllo dà esattamente gli stessi
risultati della versione PyTorch. Sul processore, per un testo di media lunghezza: circa 79 ms
con PyTorch, 61 ms con ONNX.

## Limiti

- Dà il meglio in italiano e sui testi di assistenza informatica; nelle altre lingue è misurato solo
  con il benchmark pubblico qui sopra.
- Testi legali: circa un terzo dei dati personali nelle sentenze sfugge.
- Una data senza contesto può essere etichettata come data di nascita.
- I nomi di azienda composti da parole comuni sono il caso più difficile.
- È un filtro, non una garanzia: per i termini che il modello non può conoscere va usato un elenco.
