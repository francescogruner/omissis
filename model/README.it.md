# Il modello

Riconosce i dati personali e riservati in testi italiani e li restituisce come intervalli con
un'etichetta. Sono tre strati, applicati insieme da `inference.py`:

1. **il modello** (`models\omissis-base` o `omissis-small`; `omissis-light` è `omissis-small` compresso, solo in
   formato ONNX, ed è quello che il programma usa di serie): classificatore di parole su mmBERT,
   41 etichette (`taxonomy.py`). Ventotto sono identificativi (nomi, recapiti, codici, credenziali,
   nomi di macchine) e vengono sempre restituite. Le altre tredici sono dettagli che identificano
   solo insieme ad altro o categorie particolari (date, orari, età, genere, titoli, professione,
   istruzione, origine, luoghi, salute, religione, politica, orientamento): il modello le riconosce,
   ma di serie non le restituisce, perché toglierle cambia il senso del testo. L'elenco di quelle
   spente è in `omissis.json` (`off`); `Detector(..., off=[])` le accende tutte;
2. **le regole** (`rules.py`): espressioni con controllo delle cifre per ciò che ha una forma certa
   (codice fiscale, partita IVA, IBAN, carte, indirizzi IP, chiavi);
3. **gli elenchi**: `known.py` (nomi noti da lasciare in chiaro: produttori, prodotti),
   `lists\never.txt` e `lists\always.txt` (personalizzabili dal pannello).

```python
from inference import Detector
det = Detector("models/omissis-small")
for start, end, label in det.analyze("Scrivi a Giulia Ferraresi, giulia.ferraresi@example.com"):
    print(start, end, label)
```

Le **soglie di decisione** stanno in `omissis.json` dentro la cartella dei pesi: una parola resta
"non sensibile" solo se il modello ne è sicuro almeno a quel livello (`threshold`). Alzarla maschera di
più, abbassarla di meno. Alcune etichette hanno una soglia propria (`thresholds`): più alta dove sbagliare
costa di più (il nome di un cliente), più bassa dove il modello vede l'etichetta troppo facilmente
(un dominio in mezzo a un testo inglese). `calibrate.py` scrive le stesse soglie anche dentro i pesi,
così chi usa il modello senza questo codice ottiene lo stesso comportamento.

## Due motori, stessi risultati

- **PyTorch** (`requirements.txt`): quello dell'addestramento; usa la scheda grafica se c'è.
- **ONNX** (`requirements-light.txt`): solo processore, ma senza PyTorch. Serve il file `model.onnx`
  nella cartella dei pesi; si scarica insieme al modello, oppure si crea con
  `python export_onnx.py models\omissis-small`.

Senza PyTorch installato si usa ONNX da solo; con la variabile `OMISSIS_ENGINE=onnx` lo si sceglie
comunque. `python compare_engines.py models\omissis-small` confronta i due motori sugli stessi
testi: sui 405 testi di controllo trovano esattamente gli stessi dati. Sul processore, per un testo di
media lunghezza: circa 36 ms con PyTorch e 26 ms con ONNX per il modello piccolo, 79 e 61 ms per
quello grande (misura del 14 novembre 2026, dopo aver tolto dal file ONNX i passaggi inutili: vedi
`slim` in `export_onnx.py`). La versione con i pesi a 8 bit è stata scartata: cambiava l'esito su
una parte delle parole (dallo 0,3 allo 0,7%) e il risultato dipendeva dal processore.

I nomi nel codice sono in inglese. Fanno eccezione `values.py` e `fragments.py`, che sono il
vocabolario italiano dei testi sintetici: lì i nomi dei metodi sono i segnaposto delle frasi modello
(`{p.citta}`, `{a.piva}`) e restano com'erano, come le chiavi dei dati di addestramento (`testo`,
`spans`, `forma`).

## Misure su benchmark pubblici

`python benchmark.py models\omissis-base` scarica (una volta sola, solo i file dei dati) due
benchmark pubblici e misura il modello: [PIIMB](https://huggingface.co/datasets/piimb/pii-masking-benchmark),
circa 150.000 frasi in sei gruppi tra cui testi legali veri di EUR-Lex e una parte in italiano, e
[CV-PII-Bench](https://huggingface.co/datasets/abamerdeen/cv-pii-bench), 200 curriculum inventati.
Le misure sono quelle di PIIMB: a livello di carattere e senza guardare l'etichetta (quanti
caratteri di dati personali risultano coperti, quanti caratteri coperti lo erano davvero).
`--mode model` misura la sola rete, come fa PIIMB con gli altri modelli; senza, misura ciò che fa
Omissis (soglia, regole, nomi noti). `--by-label all` mostra la copertura per ogni etichetta del
benchmark: serve a distinguere ciò che il modello sbaglia da ciò che per scelta non maschera
(date generiche, età, genere, titoli, professioni). Le frasi di questi benchmark non sono mai
state usate per addestrare o mettere a punto i modelli; delle stesse raccolte sono state usate le
parti di addestramento, che sono altri testi (vedi sotto).

Il 13 novembre 2026, con i soli pesi: `omissis-base` F2 medio 0,911, `omissis-small` 0,912; il migliore
degli altri 36 modelli in elenco 0,836. `python leaderboard.py` rifà il confronto.

`python benchmark.py <nome di un modello su Hugging Face> --mode other` misura con lo stesso codice un altro
classificatore (solo i pesi in formato safetensors, nessun codice del modello viene eseguito): è così che sono
fatte le tabelle di [docs/BENCHMARKS.md](../docs/BENCHMARKS.md).

## Rifare l'addestramento

I dati sono di due tipi. Tutto è sintetico, tranne due raccolte di sentenze che contengono nomi veri,
già pubblici negli atti:

- **i nostri**: documenti italiani sintetici, generati. `values.py` contiene i generatori dei valori
  (persone, aziende, codici con cifre di controllo valide), `fragments.py` i modelli di frase per
  ambito (legale, fiscale, sanitario, HR, banca, assistenza informatica, cose pubbliche che non vanno
  mascherate…), `generate_data.py` li compone in documenti;
- **nove raccolte pubbliche**, solo le parti di addestramento (`external_data.py` le scarica e le
  converte alle nostre etichette):

  | Raccolta | Licenza | Cosa porta |
  |---|---|---|
  | ai4privacy/pii-masking-openpii-1m | CC BY 4.0 | 23 lingue |
  | nvidia/Nemotron-PII | CC BY 4.0 | documenti in inglese, 55 tipi di dato |
  | gretelai/gretel-pii-masking-en-v1 | Apache 2.0 | documenti di settore in inglese |
  | piimb/privy | MIT | JSON, SQL, tracciati di protocollo |
  | dglover1/mapa-eur-lex | CC BY 4.0 | sentenze EUR-Lex in 21 lingue, annotate a mano |
  | gretelai/synthetic_pii_finance_multilingual | Apache 2.0 | documenti finanziari interi in 7 lingue |
  | Wismut/nym-pii-multilingual-data | MIT | 23 lingue, etichette esatte per costruzione |
  | Text Anonymization Benchmark | MIT | sentenze della Corte europea dei diritti dell'uomo, annotate a mano |
  | urchade/synthetic-pii-ner-mistral-v1 | Apache 2.0 | testi brevi in 5 lingue, anche sanitari |

```
python generate_data.py 200000 2000          # data\train.jsonl e data\dev.jsonl (i nostri)
python external_data.py download             # circa 1,5 GB in data\external\raw
python external_data.py convert
python build_train.py --first-pass <modello di un primo giro> --teacher <modello addestrato solo sui nostri>
python train.py <cartella di mmBERT> models\mio-modello --epochs 1 --tokens 8000 --ema 0.999 --llrd 0.95 --mask 0.08
python calibrate.py models\mio-modello --threshold 0.93 --label ORG=0.98 DOMINIO=0.4
python export_onnx.py models\mio-modello
```

Le raccolte non annotano le stesse cose: una etichetta le professioni ma non i titoli, un'altra il
contrario, e nessuna i nomi delle macchine. Dire alla rete che un titolo non etichettato è "niente"
le insegnerebbe a non vedere i titoli. Per questo ogni testo porta il nome della sua raccolta e
`train.py` non penalizza un'etichetta che quella raccolta non poteva dare (`build_train.py` spiega le
regole, raccolta per raccolta). Le più importanti:

- i nostri documenti sono generati, quindi sappiamo tutto ciò che contengono: valgono per tutte le
  etichette e sono ciò che impedisce a un'etichetta nuova di "rubare" i nomi delle aziende;
- il nome di un'azienda è la cosa più difficile: nelle raccolte pubbliche quasi nessuna è etichettata.
  Lì un nome proprio in mezzo a una frase resta neutro; contano come "non è un'azienda" solo titoli,
  nomi di campo e parole a inizio riga;
- una raccolta etichettata da un modello linguistico (i documenti finanziari) viene creduta solo dove
  anche un modello nostro vede qualcosa.

Il modello piccolo si ottiene da quello grande (`train.py ... --teacher models\mio-modello --temp 2
--alpha 0.5`). Serve una scheda grafica: su una RTX 4080 SUPER il modello grande richiede circa un'ora
e mezza. Un solo lavoro per volta sulla scheda.

`public_probe.py` misura quanto viene mascherato in frasi che contengono solo cose pubbliche
(istituzioni, personaggi famosi, leggi, città citate in generale); `leaderboard.py` mette i risultati
salvati da `benchmark.py --save` accanto a quelli degli altri modelli misurati da PIIMB.
