# Mettere in servizio la console centrale di Omissis

Per chi installa la console su un server proprio. Alla fine c'è una pagina dove compaiono i PC dei clienti, che
parte da sola con il server e ha una copia di sicurezza ogni notte.

La console è gratuita fino a 5 PC di un solo cliente; oltre serve una licenza (vedi «La licenza», più sotto). È
software proprietario, distribuito compilato: le condizioni d'uso sono in `LICENZA.it.md`.

English: `GUIDE.md`.

## Due modi di metterla in rete

| | In rete locale (di serie) | Raggiungibile da Internet |
|---|---|---|
| Per chi | Console e PC nella stessa rete, o collegati da una VPN | Un MSP che segue da un posto solo clienti in sedi diverse |
| Indirizzo | `https://192.168.1.10:8800`, o il nome del server | `https://console.tuodominio.it` |
| Certificato | La console se lo fa da sé al primo avvio | Uno vero, chiesto e rinnovato da Caddy |
| Che cosa serve | Niente: né nome pubblico, né porte 80 e 443, né altri programmi | Un nome che punta al server, porte 80 e 443 aperte (o un tunnel), Caddy |
| Come i PC la riconoscono | Dall'**impronta** del certificato, data insieme alla chiave | Come un browser riconosce un sito |

In tutti e due i casi il collegamento è cifrato: i PC accettano **solo** `https://`, perché il riepilogo porta la
chiave di collegamento del cliente.

Serve un server sempre acceso: Windows Server 2019 o successivo (o Windows 10/11). La console è
leggera: 1 processore e 1 GB di memoria bastano per centinaia di PC.

## In rete locale, su Windows

1. **Scompatta** il pacchetto `omissis-console-<versione>.zip` in una cartella qualsiasi del server.
2. **Installa**, da PowerShell aperto come amministratore, nella cartella scompattata:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\Install-Console.ps1
   ```

   Lo script:
   - copia il programma in `C:\OmissisConsole` e chiude la cartella agli utenti normali del server;
   - registra due attività pianificate con l'account a bassi privilegi LOCAL SERVICE: la console (parte con il
     server, viene riavviata se si ferma) e la copia notturna dell'archivio;
   - apre la porta 8800 nel firewall di Windows, solo per le reti di dominio e private, mai per quelle pubbliche
     (se Windows considera «pubblica» la rete del server, lo script lo scrive alla voce `warning`: finché il
     profilo della rete non diventa «privato», dagli altri PC la console non si raggiunge);
   - avvia la console, che al primo avvio si crea il certificato, e alla fine scrive l'indirizzo e l'**impronta**.

   Il programma è compilato e completo (`app\omissis-console.exe`): non c'è nient'altro da installare. Con `-Root D:\Altro` cambia
   cartella, con `-Port` la porta, con `-PruneDays 400` la copia notturna toglie anche i conteggi più vecchi di
   400 giorni.
3. **Crea il tuo accesso**: sul server stesso apri `https://127.0.0.1:8800/` in un browser. Il browser avvisa che
   non conosce il certificato: è atteso, perché nessuna autorità lo ha firmato; si prosegue («Avanzate», poi
   «Procedi»). La pagina, vedendo che non esiste ancora nessun accesso, ti chiede nome e password (almeno 12
   caratteri) ed entri. **Funziona solo dal computer della console**: dalla rete nessuno può crearselo prima di te.
   Subito dopo la pagina mostra i «Primi passi»: creare un cliente, dare il file ai PC, aspettare il primo riepilogo.

   Chi preferisce il terminale, o lavora senza schermo (in una finestra da amministratore):

   ```powershell
   C:\OmissisConsole\app\omissis-console.exe --data C:\OmissisConsole\data --add-user tuonome --role msp
   ```

4. **Da allora si entra da qualunque PC della rete**: `https://<nome o indirizzo del server>:8800/`, con lo stesso
   avviso sul certificato la prima volta. Chi vuole essere sicuro di parlare con il server giusto confronta
   l'impronta SHA-256 che il browser mostra nei dettagli del certificato con quella scritta dallo script.

L'impronta si rilegge quando serve con `omissis-console.exe --data C:\OmissisConsole\data --show-pin`, e la pagina la
mostra nella scheda dei clienti. Il certificato resta lo stesso per dieci anni: non va rinnovato. **Non
cancellare la cartella `data\tls`**: un certificato nuovo avrebbe un'impronta nuova, e tutti i PC andrebbero
ricollegati.

## Raggiungibile da Internet

Per questa via la console parla in chiaro solo con il server stesso, e davanti ci va un servizio che fa HTTPS
con un certificato vero.

1. Installa con `.\Install-Console.ps1 -BehindProxy` (ascolta solo su `127.0.0.1:8800`, nessuna porta aperta nel
   firewall) e crea il tuo accesso **dal terminale**, con il comando qui sopra: attraverso il servizio messo davanti
   la pagina non lo lascia creare, perché da lì non distingue te da chiunque arrivi da Internet.
2. Metti davanti [Caddy](https://caddyserver.com/download), un solo file: in `C:\Caddy` insieme a
   `Caddyfile.example` rinominato in `Caddyfile`, con il tuo nome al posto di `console.example.it`. Poi, come
   amministratore:

   ```powershell
   sc.exe create caddy start= auto binPath= "C:\Caddy\caddy.exe run --config C:\Caddy\Caddyfile"
   sc.exe start caddy
   ```

   Caddy chiede il certificato e lo rinnova da solo. Chi non vuole aprire porte può usare un tunnel (Cloudflare
   Tunnel o simili) che inoltra il nome a `http://127.0.0.1:8800`.
3. Apri `https://console.tuodominio.it/`: nessun avviso, e ai PC non serve l'impronta.

## Collegare il primo cliente

1. Nella console, **Nuovo cliente**: scrivi il nome. Compaiono l'indirizzo, la **chiave di collegamento** (una
   volta sola: la console ne conserva soltanto l'impronta) e, in rete locale, l'impronta del certificato.
2. Premi **«Scarica il file per i PC»**: è `omissis-console.json`, con quelle tre cose già scritte. Se vuoi
   bloccare anche altre scelte, aggiungile lì (i nomi sono in `policy.example.json` del kit di distribuzione):

   ```json
   {
    "console_url": "https://192.168.1.10:8800",
    "console_key": "omk_...",
    "console_pin": "3f9a...",
    "updates": "never",
    "policies": { "deepseek": "block" }
   }
   ```

3. Dal tuo RMM, su ogni PC del cliente:
   - `Set-OmissisPolicy.ps1 -Settings omissis-console.json` eseguito **come SYSTEM**: blocca le impostazioni e
     collega il PC;
   - `Install-Omissis.ps1 ...` eseguito **come utente connesso**: installa il programma.
4. Entro un'ora (o subito, dal pannello del PC: Impostazioni, Console centrale, «Invia ora») il PC compare.

Per provare con un PC solo, senza RMM: nel pannello di quel PC, Impostazioni, Console centrale (in modalità
avanzata), si scrivono a mano indirizzo, chiave e impronta.

Se il cliente vuole vedere i suoi numeri, creagli un accesso in sola lettura:
`console --data ... --add-user nome --role customer --tenant "Nome del cliente"`.

**Prima di collegare un cliente** senti chi si occupa di privacy da lui: con i nomi dei computer e degli utenti
la console mostra quanto ogni persona usa i servizi AI, e può essere un controllo a distanza dei lavoratori.
Con `"console_names": false` nel file arrivano solo i totali.

## La licenza

Senza licenza la console funziona, e segue fino a **5 PC di un cliente solo**. Per seguirne di più serve un file di
licenza: dice a chi è intestata, quanti PC e quanti clienti copre e fino a quando. È firmato: cambiando un numero
smette di valere.

- **Chiederla**: nella scheda «Licenza» premi «Richiedi una licenza», scrivi a chi va intestata e quanti PC e
  clienti deve coprire, e scarica il file `richiesta-licenza-omissis.json`. Mandalo a chi ti ha fornito la
  console. Dalla pagina non parte nulla: il file lo mandi tu.
- Il file porta l'**identificativo dell'installazione** (`OMC-XXXX-XXXX-XXXX-XXXX`, si legge nella stessa scheda e
  con `--licence-info`): la licenza che ricevi vale solo su questa installazione.
- **Caricarla**: dalla pagina, scheda «Licenza» → «Carica un file di licenza»; oppure dal terminale con
  `--licence <file>`. Vale subito, senza riavviare.
- **Se il server cambia** (computer nuovo, sistema reinstallato) l'identificativo cambia e la licenza smette di
  valere: la pagina lo dice, e ne va chiesta una nuova con l'identificativo nuovo. I dati non si perdono.
- **Vedere quanto è usata**: nella stessa scheda, o con `--licence-info`.
- **PC oltre il numero coperto**: la console tiene i primi arrivati e non accoglie i riepiloghi degli altri; la
  pagina lo scrive in cima. Nulla viene cancellato: con una licenza più ampia riprendono da dove erano.
- **Scadenza**: da trenta giorni prima la pagina lo ricorda. Dopo la scadenza la licenza vale ancora per 14
  giorni; poi la console torna a 5 PC e un cliente, finché non se ne carica una nuova.

## Tutti i giorni

| Che cosa | Come |
|---|---|
| Vedere clienti e accessi | `console --data <dati> --list` |
| Cambiare una password | `console --data <dati> --set-password nome` (chiude le sessioni aperte di quell'accesso) |
| Togliere un accesso | `console --data <dati> --remove-user nome` |
| Rileggere l'impronta del certificato | `console --data <dati> --show-pin` |
| Installare una licenza, vedere quanto è usata | `console --data <dati> --licence <file>`, `console --data <dati> --licence-info` |
| Chi è entrato e che cosa ha cambiato | `<dati>\audit.jsonl`: ingressi riusciti e falliti, clienti creati, chiavi cambiate, PC tolti, licenze caricate |
| Fare una copia adesso | `console --data <dati> --backup <cartella>` (funziona anche a console accesa) |
| Togliere i dati vecchi | `console --data <dati> --prune 400` |

Qui `console` sta per `C:\OmissisConsole\app\omissis-console.exe` e `<dati>` per `C:\OmissisConsole\data`. In uno script la password si
può dare con `--password-file <file>` invece di scriverla.

## Copie di sicurezza e ripristino

Ogni notte alle 02:30 una copia coerente dell'archivio finisce in `C:\OmissisConsole\backup`; restano le ultime 14. **Portale anche fuori dal server**, con lo strumento
di backup che usi già: sono file normali. In rete locale salva anche la cartella `data\tls`, una volta: contiene
il certificato, e con lui l'impronta che i PC conoscono.

La licenza sta nella cartella dei dati (`licence.json`): conserva anche il file che hai ricevuto.

Per ripristinare: ferma la console (l'attività pianificata «Omissis Console»), copia il file scelto sopra `console.sqlite` nella cartella dei dati, togli gli
eventuali `console.sqlite-wal` e `console.sqlite-shm`, riavvia.

## Aggiornare e togliere

- **Aggiornare**: scompatta il pacchetto nuovo e rilancia `Install-Console.ps1` con le stesse opzioni.
  Sostituisce il programma; dati, accessi, certificato e copie restano.
- **Togliere**: `Install-Console.ps1 -Remove`. Toglie le attività, la regola del firewall e il programma; `data`
  e `backup` restano dove sono, e si cancellano a mano quando non servono più.

## Se qualcosa non va

| Che cosa vedi | Che cosa guardare |
|---|---|
| La pagina non si apre da un altro PC | Il server risponde a `ping`? La rete del server è «privata» o «di dominio» per Windows (su una rete «pubblica» la porta resta chiusa)? Dal server, `https://127.0.0.1:8800/` si apre? |
| Nel pannello del PC: «Il certificato della console non è quello atteso» | L'impronta nel PC non è quella della console (`--show-pin`), oppure manca: in rete locale serve sempre |
| Nel pannello del PC: «Chiave non accettata» | Chiave sbagliata, o ne è stata creata una nuova |
| Nel pannello del PC: «Console non raggiungibile» | Indirizzo o porta sbagliati, firewall, server spento |
| «Troppi tentativi» all'ingresso | Dopo cinque password sbagliate ci si ferma per un quarto d'ora |
| Tutti i PC di un cliente spariscono | È stata creata una chiave nuova: quella vecchia non vale più, i PC vanno ricollegati |

## Che cosa è stato provato

Il 15 novembre 2026: le chiamate della console (39 controlli); l'HTTPS integrato con il
programma vero di Omissis (impronta giusta: il riepilogo arriva; sbagliata o assente: non parte nulla); la pagina
in HTTPS con il file da scaricare; il pacchetto scompattato, con il programma **compilato**, installato in una
cartella di prova **senza** registrare attività (`-NoTasks`), acceso, collegato, messo sotto licenza, salvato,
aggiornato e tolto (22 controlli); il primo accesso creato dalla pagina, solo dal computer della console; la licenza: soglia gratuita, file firmato, file toccato rifiutato, licenza di
un'altra installazione rifiutata, scadenza.

Sempre il 15 novembre 2026, `Install-Console.ps1` lanciato come amministratore su un Windows 11 in italiano: la
console parte con l'account di servizio, la cartella è chiusa agli utenti normali, la regola del firewall c'è
(reti di dominio e private), la console risponde in HTTPS sull'indirizzo di rete del PC con l'impronta scritta
dallo script, e in chiaro non risponde. La prima prova si era fermata perché lo script chiamava l'account con il
nome inglese, che su un Windows in un'altra lingua non esiste: ora lo ricava dal suo identificativo.

Quella prova è stata fatta con il pacchetto di prima, che portava con sé Python: con il programma compilato
l'installazione da amministratore va rifatta.

**Non ancora provato**: il riavvio del server e la copia notturna fatta dall'attività pianificata; un PC che si
collega da un'altra macchina della rete; un aggiornamento sopra un'installazione in funzione; Caddy e il
certificato vero.
