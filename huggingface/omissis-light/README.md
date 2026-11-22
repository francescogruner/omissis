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
base_model: francescogruner/omissis-small
base_model_relation: quantized
pipeline_tag: token-classification
library_name: onnx
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
- onnx
- quantized
- int8
- on-device
- mobile
---

# omissis-light

**English** · [Italiano](#italiano)

[omissis-small](https://huggingface.co/francescogruner/omissis-small) in **90 MB instead of 563**, for
phones and for computers where half a gigabyte of model is too much. It detects personal and
confidential data in text, so it can be replaced with placeholders before the text is sent to an AI
service. Same 41 labels, same built-in thresholds, almost the same results: on the public benchmark
it scores 0.910 where the full model scores 0.912 (see [Measurements](#measurements)).

- **Made from:** omissis-small (140.9 M parameters, based on [mmBERT-small](https://huggingface.co/jhu-clsp/mmBERT-small)), compressed without any retraining
- **Format:** ONNX only. It runs with `onnxruntime`, without PyTorch
- **Files:** `model.onnx` 90 MB and the tokenizer, 34 MB
- **Full-size versions:** [omissis-small](https://huggingface.co/francescogruner/omissis-small) (563 MB) and [omissis-base](https://huggingface.co/francescogruner/omissis-base) (1.2 GB)
- **Licence:** Apache 2.0

It belongs to [Omissis](https://github.com/francescogruner/omissis), which contains the desktop
program, the browser extension and the code that trained the full model.

## How it was made light

Nothing was trained again. The weights of omissis-small are stored, and partly computed, in a
smaller form:

- **The vocabulary table** is 70% of the full model: 256,000 rows of 384 numbers. The 64,000 tokens
  used most, which are 98.6% of the tokens met in the training texts, keep their own row, at 8 bits.
  The other 192,000 rows are rebuilt from 96 shared components. No token is dropped: a rare word is
  read a little less precisely, it does not become "unknown".
- **All the other weights** are stored at 8 bits instead of 32.
- **66 of the 90 weight matrices are computed with integers** (the attention projections and the
  first matrix of every feed-forward block). The other 24 are computed in floating point, because
  that is where integers cost accuracy.
- **The integer weights use 7 bits**, so the result is the same on every processor: on x86
  processors without VNNI, full 8-bit weights can overflow.

## Labels

The same 41 labels as omissis-small, in BIO format. The names are Italian because they are also what
the AI service sees in a placeholder (`[PERSONA_1]`, `[IBAN_2]`).

**28 identifiers**, always meant to be masked:

| Area | Labels |
|---|---|
| People and contacts | `PERSONA` (person) `EMAIL` `TELEFONO` (phone) `INDIRIZZO` (street address) `CAP` (postcode) `CITTA` (city) `DATA_NASCITA` (date of birth) |
| Identifiers | `CF` (tax code, social security number) `PIVA` (VAT number) `DOC_ID` (identity document) `TARGA` (licence plate) `ID_VEICOLO` (vehicle identification number) `ID_PRATICA` (case, policy, customer or record number) `CATASTO` (land-registry data) `ID_UTENZA` (utility account) |
| Payments | `IBAN` (also other bank account numbers) `CARTA` (card number) `CARTA_SEC` (card security code) |
| Organisations | `ORG` (a company, firm or private customer; public bodies and well-known vendors are left alone) |
| IT | `IP` `MAC` `HOSTNAME` `DOMINIO` (domain) `URL` `ACCOUNT` `SEGRETO` (password, key, token) `ID_CLOUD` (cloud identifier) `ID_DISPOSITIVO` (serial number) |

**13 more**, details that identify only together with something else, and special categories of
data:

`DATA` (date) `ORA` (time) `ETA` (age) `GENERE` (gender) `TITOLO` (title: Mr, Dr) `PROFESSIONE`
(occupation) `ISTRUZIONE` (education) `ORIGINE` (nationality, ethnicity, language) `LUOGO` (country,
region, coordinates) `SALUTE` (health) `RELIGIONE` (religion) `POLITICA` (political views)
`ORIENTAMENTO` (sexual orientation)

## Usage

```
pip install onnxruntime tokenizers huggingface_hub numpy
```

```python
import json

import numpy as np
import onnxruntime as ort
from huggingface_hub import snapshot_download
from tokenizers import Tokenizer

folder = snapshot_download("francescogruner/omissis-light")
labels = json.load(open(f"{folder}/config.json", encoding="utf-8"))["id2label"]
tokenizer = Tokenizer.from_file(f"{folder}/tokenizer.json")
session = ort.InferenceSession(f"{folder}/model.onnx", providers=["CPUExecutionProvider"])


def find(text):
    enc = tokenizer.encode(text)
    ids = np.array([enc.ids], dtype=np.int64)
    logits = session.run(None, {"input_ids": ids, "attention_mask": np.ones_like(ids)})[0][0]
    spans = []
    for (start, end), k in zip(enc.offsets, logits.argmax(-1)):
        label = labels[str(k)]
        if start == end or label == "O":
            continue
        if spans and spans[-1][2] == label[2:] and label[0] == "I":
            spans[-1][1] = end
        else:
            spans.append([start, end, label[2:]])
    return [(text[s:e].strip(), label) for s, e, label in spans]


print(find("Il server SRV-DC01 non risponde e l'utente m.bianchi non entra: chiamare Laura Conti al 347 5551234."))
# [('SRV-DC01', 'HOSTNAME'), ('m.bianchi', 'ACCOUNT'), ('Laura Conti', 'PERSONA'), ('347 5551234', 'TELEFONO')]
```

The model is **cautious by construction**: the decision thresholds are inside the weights, so the
most likely class is already the cautious answer (a word stays "not sensitive" only if the model is
at least 93% sure; 98% for company names, where a miss costs more; 40% for domain names). Used this
way it returns all 41 labels: drop the 13 above if you only want identifiers.

The example reads up to 512 tokens. For longer texts, and for everything the Omissis program adds to
the model, use `model/inference.py` from the repository: `Detector("<folder>")` works on this folder
with `onnxruntime` alone, splits long texts in overlapping windows and adds

- the choice of which of the 13 extra labels to return (none by default) and of the thresholds (file
  `omissis.json`);
- **rules** with checksum validation for tax code, VAT number, IBAN, cards, IP addresses;
- **lists**: well-known names to leave in clear (vendors and products) and terms chosen by the user.

## Measurements

All measured on 22 November 2026 on the published file, on a processor with ONNX Runtime, next to
omissis-small measured with the same code.

### Public benchmark

[PIIMB](https://huggingface.co/datasets/piimb/pii-masking-benchmark): about 150,000 sentences in six
tasks, scored at character level without looking at the label (F2, which weighs a missed character
more than a masked one). Weights alone, all labels, as PIIMB measures every model:

| | Average F2 | ai4privacy-en | ai4privacy-multi | nemotron-pii | gretel | privy | mapa-eur-lex |
|---|---|---|---|---|---|---|---|
| **omissis-light** (90 MB) | **0.910** | 0.988 | 0.989 | 0.970 | 0.976 | 0.941 | 0.599 |
| omissis-small (563 MB) | 0.912 | 0.988 | 0.991 | 0.970 | 0.976 | 0.941 | 0.605 |

On the Italian sentences of the benchmark: 0.925, the full model 0.927.

The six tasks come from datasets whose **training** splits are among the training data of
omissis-small: how to read these numbers, and the comparison with other models, are in the
[omissis-small card](https://huggingface.co/francescogruner/omissis-small#measurements).

The same benchmark as the Omissis program works (thresholds, rules, lists, the 28 identifiers only),
precision:

| | ai4privacy-en | ai4privacy-multi | gretel | nemotron-pii | privy |
|---|---|---|---|---|---|
| **omissis-light** | 96.4% | 96.4% | 94.3% | 95.6% | 90.1% |
| omissis-small | 96.6% | 97.3% | 94.5% | 96.0% | 90.2% |

### CVs

On the 40 CVs of CV-PII-Bench, as the program works: it covers 89.7% of the personal data, like the
full model, with a precision of 61.3% where the full model has 63.7%. It finds the same data and
masks a little more than needed.

### Real texts

On a **private** set of 2,000 real IT-support texts, not publishable, as the program works
(thresholds, rules, lists, the 28 identifiers only):

| Measure | omissis-light | omissis-small |
|---|---|---|
| Known sensitive values that end up masked | 98.8% | 98.8% |
| Masked text over the total | 17.1% | 17.2% |
| Company names in free text that end up masked | 90% | 93% |

What the "known values" are, and what this measure does not say, is explained in the
[omissis-small card](https://huggingface.co/francescogruner/omissis-small#real-texts).

### Size, speed, memory

On 11,741 development texts, same computer, processor only:

| | omissis-small | omissis-light |
|---|---|---|
| `model.onnx` | 563 MB | **90 MB** |
| Time for a text | 14.8 ms | **10.7 ms** |
| Memory of the whole process, at its peak | 1.55 GB | **1.05 GB** |

The process is Python with the tokenizer, and it passes the model up to 2,048 tokens at a time: one
message at a time takes much less. On an Android phone a build with full 8-bit integer weights, the
only difference from this file, loads in 0.7 seconds, takes about 350 MB of memory and reads a
message in 30 to 70 ms.

## Limits

- The limits of omissis-small all apply: strongest in Italian and on IT-support text, about a third
  of the personal data in court documents is missed, a date without context may be labelled as a date
  of birth, company names made of common words are the hardest case.
- It is a little less precise than the full model, as the tables show.
- A word on the edge of a decision can come out differently from the full model. An example: in
  `PC-AMM-07` the full model labels the whole host name, this one `-AMM-07`.
- For the same reason a few borderline words can change with the version of ONNX Runtime, with the
  processor family (x86 or ARM) and with the texts that are run together in a batch. For results that
  repeat exactly, run one window at a time.
- There are no PyTorch weights: to train further, start from omissis-small.
- It is a filter, not a guarantee: for terms the model cannot know, use a list.

## Citation

```
Francesco Gruner, Omissis: local pseudonymisation of personal data for the use of AI assistants, 2026.
https://github.com/francescogruner/omissis
```

---

# Italiano

[omissis-small](https://huggingface.co/francescogruner/omissis-small) in **90 MB invece di 563**,
per i telefoni e per i computer dove mezzo gigabyte di modello è troppo. Riconosce dati personali e
riservati in un testo, per sostituirli con segnaposto prima di mandarlo a un servizio di intelligenza
artificiale. Stesse 41 etichette, stesse soglie dentro i pesi, risultati quasi uguali: sul benchmark
pubblico fa 0,910 dove il modello intero fa 0,912 (vedi [Misure](#misure)).

- **Ricavato da:** omissis-small (140,9 M di parametri, base [mmBERT-small](https://huggingface.co/jhu-clsp/mmBERT-small)), compresso senza riaddestrarlo
- **Formato:** solo ONNX. Gira con `onnxruntime`, senza PyTorch
- **File:** `model.onnx` da 90 MB e il tokenizer, 34 MB
- **Versioni intere:** [omissis-small](https://huggingface.co/francescogruner/omissis-small) (563 MB) e [omissis-base](https://huggingface.co/francescogruner/omissis-base) (1,2 GB)
- **Licenza:** Apache 2.0

Fa parte di [Omissis](https://github.com/francescogruner/omissis), che contiene il programma,
l'estensione del browser e il codice che ha addestrato il modello intero.

## Come è stato alleggerito

Non è stato addestrato di nuovo. I pesi di omissis-small sono conservati, e in parte calcolati, in
una forma più piccola:

- **La tabella del vocabolario** è il 70% del modello intero: 256.000 righe da 384 numeri. I 64.000
  token più usati, che sono il 98,6% di quelli incontrati nei testi di addestramento, tengono la
  propria riga, a 8 bit. Le altre 192.000 righe si ricostruiscono da 96 componenti comuni. Nessun
  token viene tolto: una parola rara è letta con un po' meno precisione, non diventa «sconosciuta».
- **Tutti gli altri pesi** sono conservati a 8 bit invece di 32.
- **66 delle 90 matrici di pesi si calcolano con numeri interi** (le proiezioni dell'attenzione e la
  prima matrice di ogni blocco). Le altre 24 si calcolano in virgola mobile, perché è lì che gli
  interi costano precisione.
- **I pesi interi usano 7 bit**, così il risultato è lo stesso su ogni processore: sui processori
  x86 senza VNNI i pesi a 8 bit pieni possono andare fuori scala.

## Etichette

Le stesse 41 di omissis-small, in formato BIO.

**28 identificativi**, da mascherare sempre:

| Ambito | Etichette |
|---|---|
| Persone e contatti | `PERSONA` `EMAIL` `TELEFONO` `INDIRIZZO` `CAP` `CITTA` `DATA_NASCITA` |
| Identificativi | `CF` `PIVA` `DOC_ID` `TARGA` `ID_VEICOLO` `ID_PRATICA` `CATASTO` `ID_UTENZA` |
| Pagamenti | `IBAN` `CARTA` `CARTA_SEC` |
| Organizzazioni | `ORG` (azienda, studio o cliente privato; enti pubblici e fornitori noti restano in chiaro) |
| Informatica | `IP` `MAC` `HOSTNAME` `DOMINIO` `URL` `ACCOUNT` `SEGRETO` `ID_CLOUD` `ID_DISPOSITIVO` |

**Altre 13**, dettagli che identificano solo insieme ad altro e categorie particolari di dati:

`DATA` `ORA` `ETA` `GENERE` `TITOLO` `PROFESSIONE` `ISTRUZIONE` `ORIGINE` `LUOGO` `SALUTE`
`RELIGIONE` `POLITICA` `ORIENTAMENTO`

## Uso

L'esempio è nella parte in inglese qui sopra: bastano `onnxruntime`, `tokenizers`, `huggingface_hub`
e `numpy`.

Il modello è **prudente per costruzione**: le soglie di decisione sono dentro i pesi, quindi la classe
più probabile è già la risposta prudente (una parola resta «non sensibile» solo se il modello ne è
sicuro almeno al 93%; al 98% per i nomi di azienda, dove sbagliare costa di più; al 40% per i domini).
Usato così restituisce tutte le 41 etichette: basta scartare le 13 qui sopra se servono solo gli
identificativi.

L'esempio legge fino a 512 token. Per i testi più lunghi, e per tutto ciò che il programma Omissis
aggiunge al modello, c'è `model/inference.py` del repository: `Detector("<cartella>")` lavora su
questa cartella con il solo `onnxruntime`, divide i testi lunghi in finestre sovrapposte e aggiunge

- la scelta di quali delle 13 etichette in più restituire (nessuna, di serie) e delle soglie (file
  `omissis.json`);
- le **regole** con controllo delle cifre per codice fiscale, partita IVA, IBAN, carte, indirizzi IP;
- gli **elenchi**: nomi noti da lasciare in chiaro (produttori e prodotti) e termini scelti dall'utente.

## Misure

Tutte fatte il 22 novembre 2026 sul file pubblicato, sul processore con ONNX Runtime, accanto a
omissis-small misurato con lo stesso codice.

### Benchmark pubblico

[PIIMB](https://huggingface.co/datasets/piimb/pii-masking-benchmark): circa 150.000 frasi in sei
gruppi, valutate a livello di carattere senza guardare l'etichetta (F2, che pesa un carattere
sfuggito più di uno mascherato a torto). Solo i pesi, tutte le etichette, come PIIMB misura ogni
modello:

| | F2 medio | ai4privacy-en | ai4privacy-multi | nemotron-pii | gretel | privy | mapa-eur-lex |
|---|---|---|---|---|---|---|---|
| **omissis-light** (90 MB) | **0,910** | 0,988 | 0,989 | 0,970 | 0,976 | 0,941 | 0,599 |
| omissis-small (563 MB) | 0,912 | 0,988 | 0,991 | 0,970 | 0,976 | 0,941 | 0,605 |

Sulle frasi in italiano del benchmark: 0,925, il modello intero 0,927.

I sei gruppi vengono da raccolte le cui parti di **addestramento** sono tra i dati di omissis-small:
come leggere questi numeri, e il confronto con gli altri modelli, sono nella
[scheda di omissis-small](https://huggingface.co/francescogruner/omissis-small#misure).

Lo stesso benchmark come lavora il programma Omissis (soglie, regole, elenchi, solo i 28
identificativi), precisione:

| | ai4privacy-en | ai4privacy-multi | gretel | nemotron-pii | privy |
|---|---|---|---|---|---|
| **omissis-light** | 96,4% | 96,4% | 94,3% | 95,6% | 90,1% |
| omissis-small | 96,6% | 97,3% | 94,5% | 96,0% | 90,2% |

### Curriculum

Sui 40 curriculum di CV-PII-Bench, come lavora il programma: copre l'89,7% dei dati personali, come
il modello intero, con una precisione del 61,3% dove il modello intero ha il 63,7%. Trova gli stessi
dati e maschera un po' più del necessario.

### Testi reali

Su un insieme **privato** di 2.000 testi reali di assistenza informatica, non pubblicabile, come
lavora il programma (soglie, regole, elenchi, solo i 28 identificativi):

| Misura | omissis-light | omissis-small |
|---|---|---|
| Valori sensibili noti che risultano mascherati | 98,8% | 98,8% |
| Testo mascherato sul totale | 17,1% | 17,2% |
| Nomi di azienda in testo libero mascherati | 90% | 93% |

Che cosa sono i «valori noti», e che cosa questa misura non dice, è spiegato nella
[scheda di omissis-small](https://huggingface.co/francescogruner/omissis-small#testi-reali).

### Peso, tempo, memoria

Su 11.741 testi di sviluppo, stesso computer, solo processore:

| | omissis-small | omissis-light |
|---|---|---|
| `model.onnx` | 563 MB | **90 MB** |
| Tempo per un testo | 14,8 ms | **10,7 ms** |
| Memoria di tutto il processo, al massimo | 1,55 GB | **1,05 GB** |

Il processo è Python con il tokenizer, e passa al modello fino a 2.048 token per volta: un messaggio
alla volta ne chiede molta meno. Su un telefono Android una versione con i pesi interi a 8 bit pieni,
unica differenza da questo file, si carica in 0,7 secondi, occupa circa 350 MB di memoria e legge un
messaggio in 30-70 ms.

## Limiti

- Valgono tutti quelli di omissis-small: dà il meglio in italiano e sui testi di assistenza
  informatica, circa un terzo dei dati personali nelle sentenze sfugge, una data senza contesto può
  essere etichettata come data di nascita, i nomi di azienda composti da parole comuni sono il caso
  più difficile.
- È un po' meno preciso del modello intero, come mostrano le tabelle.
- Una parola al limite di una decisione può uscire diversa dal modello intero. Un esempio: in
  `PC-AMM-07` il modello intero etichetta tutto il nome della macchina, questo `-AMM-07`.
- Per lo stesso motivo qualche parola al limite può cambiare con la versione di ONNX Runtime, con la
  famiglia del processore (x86 o ARM) e con i testi elaborati insieme in un lotto. Per risultati che
  si ripetono identici, una finestra per volta.
- Non ci sono i pesi per PyTorch: per addestrarlo ancora si parte da omissis-small.
- È un filtro, non una garanzia: per i termini che il modello non può conoscere va usato un elenco.
