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
| pynput | 1.8.2 | LGPL-3.0 |
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

`pystray` e `pynput` sono LGPL-3.0. Usarle come dipendenze installate a parte non impone nulla al
nostro codice. Se un giorno si distribuisce un installer che le contiene, chi lo riceve deve poterle
sostituire con una versione modificata: con Python basta lasciarle come moduli separati e riportare
qui la loro licenza. Nessun componente di questo progetto è AGPL: per i PDF si usa `pypdf`.
