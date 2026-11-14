# Distribuire Omissis su più PC

Per chi gestisce i computer di un'azienda o di più clienti (un MSP): quattro script PowerShell per installare
Omissis in silenzio, già configurato, bloccarne le impostazioni, controllarne lo stato e toglierlo. Funzionano
con qualsiasi strumento che sappia lanciare uno script: un RMM, Intune, uno script di accesso.

| File | A cosa serve |
|---|---|
| `Install-Omissis.ps1` | Installa in silenzio, applica le scelte del cliente, porta il modello, avvia la protezione |
| `Set-OmissisPolicy.ps1` | Blocca le impostazioni scelte per tutti gli utenti del PC. È l'unico che va lanciato **come amministratore** |
| `Get-OmissisStatus.ps1` | Dice in una riga come sta Omissis su quel PC; con `-MinVersion` fa da regola di rilevamento |
| `Uninstall-Omissis.ps1` | Toglie il programma; con `-RemoveData` anche i dati |
| `settings.example.json` | Modello delle scelte del cliente (l'utente le può cambiare) |
| `policy.example.json` | Modello delle impostazioni bloccate (l'utente non le può cambiare) |

## La regola che conta: si lancia come utente

Omissis si installa **per il singolo utente**, senza diritti di amministratore, e i suoi dati (l'archivio dei
valori sostituiti, cifrato e legato a quell'utente) stanno nel suo profilo. Gli script vanno quindi eseguiti
**con l'utente che usa il PC**, non come SYSTEM e non come amministratore: lanciati come SYSTEM
installerebbero il programma nel profilo sbagliato. Su un PC usato da più persone si lancia una volta per
ciascuna. L'unica eccezione è `Set-OmissisPolicy.ps1`, che scrive in una zona del registro riservata agli
amministratori: quello va lanciato come amministratore o come SYSTEM, una volta per PC.

## Che cosa serve

1. **L'installer** `Omissis-<versione>-setup.exe` e la sua **impronta SHA-256**. L'impronta sta in
   `update.json`, pubblicato firmato accanto all'installer: lo script rifiuta un file con un'impronta diversa.
2. Facoltativo, ma consigliato: **una cartella con il modello**, così ogni PC non scarica 537 MB per conto suo.
   Dentro ci va una sottocartella con il nome del modello (`omissis-small`) e i cinque file che il programma
   scaricherebbe (`config.json`, `tokenizer.json`, `tokenizer_config.json`, `omissis.json`, `model.onnx`).
   Ogni file viene accettato solo se dimensione e impronta sono quelle dell'elenco che viaggia con il
   programma; se uno non torna, la copia viene scartata e il programma scarica il modello da sé.
3. Facoltativo: **le scelte del cliente**, un file come `settings.example.json`.

```powershell
powershell -ExecutionPolicy Bypass -File Install-Omissis.ps1 `
  -Installer "\\server\software\Omissis-0.1.0-setup.exe" -Sha256 "<impronta>" `
  -Settings "\\server\software\cliente.json" -ModelSource "\\server\software\modelli"
```

`-Installer` accetta anche un indirizzo `https://`. Con `-NoAutostart` Omissis non parte insieme a Windows,
con `-NoStart` non viene avviato alla fine. Lo script scrive una riga in JSON con l'esito ed esce con
`0` (fatto), `2` (installer non ottenuto o impronta sbagliata), `3` (installazione fallita), `4`
(installato, ma la protezione non è partita entro tre minuti: di solito sta ancora scaricando il modello).

## Le scelte del cliente

Solo le chiavi scritte nel file vengono imposte; ogni altra impostazione resta come l'ha l'utente. Le più utili:

| Chiave | Valori | Che cosa decide |
|---|---|---|
| `model` | `omissis-small` (di serie), `omissis-base` | Il modello. Su PC da ufficio il piccolo; il grande vuole 16 GB |
| `updates` | `automatic`, `notify`, `never` | `never` se le versioni le distribuisci tu, con questo stesso script |
| `policies` | per servizio: `protect`, `record`, `block`, `ignore` | Per esempio `"deepseek": "block"`. I nomi dei servizi sono quelli della sezione Servizi AI del pannello |
| `groups_off` | `payments`, `organizations`, `it`, `records` | Gruppi di dati da **non** sostituire. Di serie nessuno: spegnerne uno riduce la protezione |
| `view` | `simple`, `advanced` | Che cosa vede l'utente quando apre il pannello |
| `language` | `it`, `en`, `auto` | La lingua del pannello |

L'utente può cambiare queste impostazioni dal pannello: rilanciare lo script le rimette. Per impedirglielo
ci sono le impostazioni bloccate, qui sotto.

## Bloccare le impostazioni

`Set-OmissisPolicy.ps1` scrive le impostazioni di un file JSON nella chiave di registro
`HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Omissis`, che un utente normale non può modificare. Omissis la legge:
ciò che trova lì vince sulle scelte dell'utente, e nel pannello quei comandi compaiono fermi, con la scritta
«decisa da chi amministra questo PC». Non c'è nessuna password: comanda chi ha i diritti di amministratore sul PC.

```powershell
powershell -ExecutionPolicy Bypass -File Set-OmissisPolicy.ps1 -Settings "\\server\software\cliente-blocco.json"
```

- Va lanciato **come amministratore o come SYSTEM** (è il modo in cui RMM e Intune lanciano gli script di serie).
- I nomi sono gli stessi delle scelte del cliente (`policy.example.json` è un modello). `policies` blocca solo i
  servizi scritti: gli altri restano all'utente. Ogni altra impostazione è bloccata per intero.
- La chiave rispecchia il file: un'impostazione tolta dal file torna libera. Con `-Remove` torna tutto libero, e
  ogni utente ritrova le scelte che aveva prima.
- Esce con `0` (fatto), `3` (file mancante o non valido), `5` (non ha i diritti per scrivere).
- Chi preferisce i criteri di gruppo o Intune può scrivere gli stessi valori da lì: testo (`REG_SZ`) per le
  scelte, numero (`REG_DWORD`, 0 o 1) per quelle sì/no, e JSON dentro un testo per elenchi e tabelle.

**Che cosa non è.** Omissis è installato nel profilo dell'utente, che quindi può modificarne i file: il blocco
ferma i cambi fatti dal pannello e dal file delle impostazioni, non chi manomette il programma. Chi deve
impedire anche questo usa gli strumenti di Windows (AppLocker, controllo delle applicazioni).

## La console centrale

Di serie Omissis non manda nulla a nessuno. Un'organizzazione che vuole vedere tutti i suoi PC in un posto solo
può collegarli a una console centrale: bastano due impostazioni, `console_url` (un indirizzo `https://`) e
`console_key` (la chiave di collegamento del cliente, che dà la console), messe nel file delle impostazioni
bloccate o in quello delle scelte del cliente.

Da quel momento ogni PC manda alla console, una volta all'ora, un riepilogo fatto di conteggi: versione e stato
del programma, quante richieste avevano dati da sostituire, quanti valori per tipo di dato, verso quali servizi,
quante richieste sono state fermate, e i nomi e le versioni degli strumenti AI trovati sul PC. **Mai i testi, mai
i valori sostituiti.** Chi usa il PC lo vede: nel pannello, in Impostazioni, c'è scritto a chi è collegato e il
pulsante «Vedi che cosa parte» mostra il riepilogo esatto.

- Il riepilogo porta il nome del computer e dell'utente, perché chi gestisce i PC deve sapere quale va
  controllato. Con `"console_names": false` non li porta. **Attenzione**: conteggi per singola persona possono
  essere un controllo a distanza dei lavoratori; prima di attivarli si sente chi si occupa di privacy e, dove
  serve, si informano i dipendenti.
- Il protocollo è aperto (`app/central.py`): una richiesta `POST` a `<console_url>/api/v1/report` con la chiave
  nell'intestazione `Authorization`. La console in sé non fa parte di questo repository.
- Un rinvio verso un altro indirizzo non viene seguito, e un indirizzo non `https` viene rifiutato.

## Con un RMM (NinjaOne e simili)

- Caricare i tre script e, se lo strumento lo permette, l'installer; altrimenti metterlo su una condivisione
  o a un indirizzo `https://`.
- Creare un'automazione che lancia `Install-Omissis.ps1` con i parametri del cliente, **eseguita come utente
  connesso** (in NinjaOne: «Esegui come: utente attualmente connesso»).
- Per il controllo periodico: `Get-OmissisStatus.ps1` senza parametri, sempre come utente. Esce con `0` se la
  protezione è accesa, `1` se Omissis è installato ma spento, `2` se non è installato; la riga in JSON si può
  salvare in un campo personalizzato.

## Con Intune

- Impacchettare installer e script in un'app Win32 (`.intunewin`).
- **Comando di installazione**: `powershell -ExecutionPolicy Bypass -File Install-Omissis.ps1 -Installer
  Omissis-0.1.0-setup.exe -Sha256 <impronta> -Settings cliente.json`
- **Comando di disinstallazione**: `powershell -ExecutionPolicy Bypass -File Uninstall-Omissis.ps1`
- **Comportamento di installazione**: Utente (non Sistema).
- **Regola di rilevamento**: script personalizzato, `Get-OmissisStatus.ps1 -MinVersion 0.1.0` (esce con `0`
  e scrive una riga solo se quella versione, o una successiva, è installata).
- Il modello conviene lasciarlo scaricare al programma, oppure metterlo su una condivisione raggiungibile dai
  PC: dentro il pacchetto peserebbe troppo.

## Che cosa dice lo stato

```json
{"installed":true,"version":"0.1.0","computer":"PC-07","user":"m.rossi","protectionOn":true,"panelUp":true,
 "startsWithWindows":true,"model":"omissis-small","modelPresent":true,"updates":"notify","groupsOff":[],
 "days":7,"requestsWithReplacements":41,"valuesReplaced":187,"stopped":2}
```

Gli ultimi tre numeri vengono dal registro di Omissis degli ultimi `-Days` giorni: quante richieste avevano
dati da sostituire, quanti valori sono stati sostituiti, quante richieste sono state fermate. Sono conteggi:
il registro non contiene mai i testi. Su un PC con impostazioni bloccate la riga porta anche `locked` (quali) e
`console` (se il PC è collegato a una console).

## L'estensione del browser

Gli script installano il programma, non l'estensione. Due cose restano da fare:

- **Installarla.** Finché non è pubblicata sugli store dei browser si carica a mano dalla cartella indicata nel
  pannello. Quando sarà pubblicata si potrà imporre con il criterio `ExtensionInstallForcelist` di Chrome e di
  Edge (un criterio di macchina: qui servono i diritti di amministratore).
- **Collegarla.** Ogni utente apre una volta il pannello, sezione Browser, e preme «Collega»: il codice di
  collegamento è diverso su ogni PC e non esce da lì. Un collegamento automatico non c'è ancora.

## Aggiornare e togliere

- **Aggiornare**: di serie Omissis si aggiorna da solo con aggiornamenti firmati. Con `updates: never` si
  rilancia `Install-Omissis.ps1` con l'installer nuovo: i dati dell'utente restano.
- **Togliere**: `Uninstall-Omissis.ps1`. Senza `-RemoveData` i dati restano, e una nuova installazione li
  ritrova. Con `-RemoveData` vengono eliminati: **senza l'archivio i segnaposto delle vecchie conversazioni
  non si possono più riportare ai valori veri**.

## Che cosa è provato

Il 14 novembre 2026, su un solo PC con Windows 11 e Windows PowerShell 5.1: installer con impronta sbagliata
rifiutato senza installare nulla; installazione in silenzio in 21 secondi con le scelte del cliente applicate,
il modello copiato da una cartella e la protezione accesa; un testo inventato mascherato dalla copia
installata; stato letto a programma acceso; disinstallazione con i dati senza lasciare programma, dati, voce
di avvio o collegamento nel menu Start.

Sempre il 14 novembre 2026: `Set-OmissisPolicy.ps1` provato su una chiave di prova dell'utente (scrive, il
programma rilegge i valori nella forma giusta, un file ridotto libera le impostazioni tolte, `-Remove` toglie
tutto) e, senza diritti di amministratore, sulla chiave vera, dove si rifiuta senza scrivere nulla. Blocco e
invio del riepilogo sono coperti dalle prove automatiche del programma (`app/e2e_central.py`).

**Non ancora provato**: `Set-OmissisPolicy.ps1` lanciato davvero come amministratore su un PC con Omissis
installato, e la riga `locked` di `Get-OmissisStatus.ps1`; il lancio da un RMM o da Intune veri, un PC con più utenti, un PC con restrizioni
sull'esecuzione dei programmi (AppLocker e simili) o con un antivirus diverso da quello di Windows, i
conteggi dell'attività su un registro con dati veri.
