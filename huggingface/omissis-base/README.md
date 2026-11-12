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

Riconosce dati personali e riservati in testi italiani, per sostituirli con segnaposto prima di
mandare un testo a un servizio di intelligenza artificiale. È il modello di
[Omissis](https://github.com/francescogruner/omissis), che contiene anche il programma, l'estensione
del browser e il codice per rifare l'addestramento.

*Italian-first PII detector (token classification, 28 labels) built to pseudonymise prompts before
they reach an AI service. Model card in Italian; code and tooling at the link above.*

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

Con il solo modello:

```python
from transformers import pipeline
ner = pipeline("token-classification", model="francescogruner/omissis-base", aggregation_strategy="simple")
ner("Scrivi a Giulia Ferraresi, giulia.ferraresi@example.com, per il ticket del PC-AMM-07.")
```

Il risultato migliore si ha con `inferenza.py` del repository, che aggiunge al modello:

- una **soglia di decisione** (0,85, nel file `msp_pii.json`): una parola resta "non sensibile" solo se
  il modello ne è sicuro almeno a quel livello. È la manopola tra protezione e testo mascherato;
- le **regole** con controllo delle cifre per codice fiscale, partita IVA, IBAN, carte, indirizzi IP;
- gli **elenchi**: nomi noti da lasciare in chiaro (produttori e prodotti) e termini scelti dall'utente.

## Dati di addestramento

180.000 documenti **sintetici** in italiano, prodotti da un generatore scritto per questo progetto
(`genera_dati.py`): ambito legale, fiscale, assicurativo, sanitario, risorse umane, bancario,
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

## Citazione

```
Francesco Gruner, Omissis: pseudonimizzazione locale dei dati personali per l'uso degli assistenti AI, 2026.
https://github.com/francescogruner/omissis
```
