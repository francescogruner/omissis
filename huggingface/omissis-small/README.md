---
license: apache-2.0
language:
- it
base_model: jhu-clsp/mmBERT-small
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

# omissis-small

La versione leggera di [omissis-base](https://huggingface.co/francescogruner/omissis-base): stesse 28
etichette e stessi dati di addestramento, metà delle dimensioni e circa metà del tempo. È quella
consigliata sui computer senza scheda grafica. Fa parte di
[Omissis](https://github.com/francescogruner/omissis).

*Lightweight Italian-first PII detector (token classification, 28 labels). Model card in Italian.*

- **Base:** [mmBERT-small](https://huggingface.co/jhu-clsp/mmBERT-small) (140,9 M di parametri), addestrato da noi a partire dal modello linguistico
- **Licenza:** Apache 2.0

## Uso

```python
from transformers import pipeline
ner = pipeline("token-classification", model="francescogruner/omissis-small", aggregation_strategy="simple")
ner("Scrivi a Giulia Ferraresi, giulia.ferraresi@example.com, per il ticket del PC-AMM-07.")
```

Etichette, soglia di decisione, regole ed elenchi sono descritti nella scheda di
[omissis-base](https://huggingface.co/francescogruner/omissis-base).

## Addestramento

Stessi 180.000 documenti sintetici del modello base (nessun dato personale reale). Un'epoca, lotto 32,
tasso di apprendimento 8e-5 con decadimento per strato 0,95, media mobile dei pesi 0,999, 8% delle
parole in ingresso mascherate, label smoothing 0,05, con distillazione dal modello base
(temperatura 2, peso 0,5).

## Misure

Sullo stesso insieme privato di 2.000 testi reali di assistenza informatica usato per il modello base,
con soglia 0,85, regole ed elenchi attivi:

| Misura | omissis-small | omissis-base |
|---|---|---|
| Valori sensibili noti che risultano mascherati | 98,0 % | 98,4 % |
| Testo mascherato sul totale | 17,6 % | 17,2 % |
| Nomi di azienda in testo libero mascherati | 80 % | 89 % |
| Tempo per testo breve su processore | circa 34 ms | circa 63 ms |

Valgono le stesse avvertenze della scheda del modello base: la precisione sui testi reali non è
misurata, e i "valori noti" non sono tutti i dati sensibili presenti nel testo.

## Senza PyTorch

Nella cartella c'è anche `model.onnx` (563 MB): lo stesso modello in formato ONNX, per farlo girare sul
processore con il solo `onnxruntime`. Sui testi di controllo dà gli stessi risultati della versione PyTorch.

## Limiti

Gli stessi del modello base; in più riconosce peggio i nomi di azienda scritti in testo libero.
