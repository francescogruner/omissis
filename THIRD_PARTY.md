# Componenti di terze parti

Omissis è distribuito con licenza Apache 2.0. Questo repository contiene solo codice nostro: le
librerie qui sotto vengono installate come dipendenze (`pip install`), non sono copiate nel
repository. Le licenze sono quelle dichiarate dai pacchetti alle versioni indicate; vanno ricontrollate
a ogni aggiornamento.

## Modello di base

| Componente | Licenza | Note |
|---|---|---|
| [mmBERT-base](https://huggingface.co/jhu-clsp/mmBERT-base), mmBERT-small | MIT | modello linguistico da cui parte l'addestramento |

## Programma (`app/requirements.txt`)

| Pacchetto | Versione provata | Licenza |
|---|---|---|
| mitmproxy | 12.3.1 | MIT |
| pystray | 0.19.5 | LGPL-3.0 |
| Pillow | 13.0.0 | MIT-CMU |
| lxml | 6.1.3 | BSD-3-Clause |
| pypdf | 7.0.1 | BSD-3-Clause |
| websocket-client | 1.9.2 | Apache-2.0 |
| winrt-runtime e winrt-Windows.* (PyWinRT) | 4.1.0 | MIT |

Solo per le prove automatiche (`app/requirements-test.txt`): playwright 1.65.1 (Apache-2.0),
python-docx 1.2.0 (MIT), openpyxl 3.1.5 (MIT), python-pptx 1.0.2 (MIT).

## Modello (`model/requirements.txt`)

| Pacchetto | Versione provata | Licenza |
|---|---|---|
| torch | 2.11.0 | BSD-3-Clause |
| transformers | 5.22.2 | Apache-2.0 |
| tokenizers | 0.23.3 | Apache-2.0 |
| safetensors | 0.8.0 | Apache-2.0 |
| huggingface-hub | 2.4.0 | Apache-2.0 |
| numpy | 2.4.6 | BSD-3-Clause e altre permissive |
| onnxruntime (installazione leggera) | 1.31.1 | MIT |

## Cosa contiene l'installer

L'installer per Windows porta con sé, oltre al codice di questo repository: l'interprete Python
ufficiale in versione «embeddable» (licenza PSF); le librerie elencate nel file `libraries.txt`
installato accanto al programma, ciascuna con la propria licenza nella sua cartella `*.dist-info`;
le librerie di esecuzione di Microsoft Visual C++ (`msvcp140*.dll`, `vcruntime140*.dll`), che
Microsoft consente di distribuire insieme ai programmi che le usano. L'installer è costruito con
Inno Setup (licenza propria, libera). I pesi del modello non sono nell'installer.

## Cosa cambia se si distribuisce un pacchetto già pronto

`pystray` è LGPL-3.0. Usarla come dipendenza installata a parte non impone nulla al
nostro codice. Se si distribuisce un installer che la contiene, chi lo riceve deve poterla
sostituire con una versione modificata: con Python basta lasciarla come modulo separato e riportare
qui la sua licenza. Nessun componente di questo progetto è AGPL: per i PDF si usa `pypdf`.

## Dati di addestramento dei modelli

I pesi di `omissis-base` e `omissis-small` (e quindi di `omissis-light`, che è `omissis-small` compresso) sono stati addestrati, oltre che sui documenti sintetici
prodotti da questo progetto, sulle parti di addestramento di queste raccolte pubbliche, convertite
alle etichette del progetto da `model/external_data.py` (che le scarica: non sono ridistribuite qui).
Le parti di prova non sono state usate.

| Raccolta | Autori | Licenza |
|---|---|---|
| [ai4privacy/pii-masking-openpii-1m](https://huggingface.co/datasets/ai4privacy/pii-masking-openpii-1m) | Ai4Privacy | CC BY 4.0 |
| [nvidia/Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII) | NVIDIA | CC BY 4.0 |
| [gretelai/gretel-pii-masking-en-v1](https://huggingface.co/datasets/gretelai/gretel-pii-masking-en-v1) | Gretel | Apache-2.0 |
| [gretelai/synthetic_pii_finance_multilingual](https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual) | Gretel | Apache-2.0 |
| [piimb/privy](https://huggingface.co/datasets/piimb/privy) (da beki/privy) | Benjamin Kilimnik | MIT |
| [dglover1/mapa-eur-lex](https://huggingface.co/datasets/dglover1/mapa-eur-lex) | progetto MAPA, su testi di EUR-Lex | CC BY 4.0 |
| [Wismut/nym-pii-multilingual-data](https://huggingface.co/datasets/Wismut/nym-pii-multilingual-data) | progetto nym | MIT |
| [Text Anonymization Benchmark](https://huggingface.co/datasets/mattmdjaga/text-anonymization-benchmark-train) | Pilán, Lison, Øvrelid, Papadopoulou, Sánchez, Batet (2022), su sentenze della Corte europea dei diritti dell'uomo | MIT |
| [urchade/synthetic-pii-ner-mistral-v1](https://huggingface.co/datasets/urchade/synthetic-pii-ner-mistral-v1) | Urchade Zaratiana | Apache-2.0 |

Il benchmark [PIIMB](https://huggingface.co/datasets/piimb/pii-masking-benchmark) (CC BY-NC 4.0) è
usato solo per misurare: `model/benchmark.py` lo scarica, non è ridistribuito e non è servito ad
addestrare.
