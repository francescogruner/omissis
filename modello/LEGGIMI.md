# Il modello

Riconosce i dati personali e riservati in testi italiani e li restituisce come intervalli con
un'etichetta. Sono tre strati, applicati insieme da `inferenza.py`:

1. **il modello** (`modelli\omissis-base` o `omissis-small`): classificatore di parole su mmBERT,
   28 etichette (`tassonomia.py`);
2. **le regole** (`regole.py`): espressioni con controllo delle cifre per ciò che ha una forma certa
   (codice fiscale, partita IVA, IBAN, carte, indirizzi IP, chiavi);
3. **gli elenchi**: `noti.py` (nomi noti da lasciare in chiaro: produttori, prodotti),
   `liste\mai.txt` e `liste\sempre.txt` (personalizzabili dal pannello).

```python
from inferenza import Rilevatore
ril = Rilevatore("modelli/omissis-small")
for inizio, fine, etichetta in ril.analizza("Scrivi a Giulia Ferraresi, giulia.ferraresi@example.com"):
    print(inizio, fine, etichetta)
```

La **soglia di decisione** sta in `msp_pii.json` dentro la cartella dei pesi (0,85): una parola resta
"non sensibile" solo se il modello ne è sicuro almeno a quel livello. Alzarla maschera di più,
abbassarla di meno.

## Due motori, stessi risultati

- **PyTorch** (`requirements.txt`): quello dell'addestramento; usa la scheda grafica se c'è.
- **ONNX** (`requirements-leggero.txt`): solo processore, ma senza PyTorch. Serve il file `model.onnx`
  nella cartella dei pesi; si scarica insieme al modello, oppure si crea con
  `python esporta_onnx.py modelli\omissis-small`.

Senza PyTorch installato si usa ONNX da solo; con la variabile `OMISSIS_MOTORE=onnx` lo si sceglie
comunque. `python confronta_motori.py modelli\omissis-small` confronta i due motori sugli stessi
testi: sui 405 testi di controllo trovano gli stessi 3.942 dati. Sul processore, per un testo di
media lunghezza: circa 37 ms con PyTorch e 52 ms con ONNX per il modello piccolo, 91 e 118 ms per
quello grande. La versione con i pesi a 8 bit è stata scartata: cambiava l'esito sull'1% delle parole.

## Rifare l'addestramento

I dati sono sintetici e si rigenerano: nessun dato personale reale.

```
python genera_dati.py 180000 2000          # dati\train.jsonl e dati\dev.jsonl
python addestra.py <cartella di mmBERT> modelli\mio-modello --ema --llrd --maschera --smooth
```

`valori.py` contiene i generatori dei valori (persone, aziende, codici con cifre di controllo
valide), `frammenti.py` i modelli di frase per ambito (legale, fiscale, sanitario, HR, banca,
assistenza informatica…), `genera_dati.py` li compone in documenti.

Serve una scheda grafica: su una RTX 4080 SUPER il modello base richiede circa un'ora.
