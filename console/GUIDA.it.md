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

## Gestire i PC dalla console

Quattro cose in più, tutte nella pagina, per chi segue molti PC. Le vede e le usa solo chi ha il ruolo che gestisce la
console; il cliente con accesso in sola lettura vede i suoi avvisi e nient'altro.

### Regole per i PC di un cliente

Scegli un cliente in alto: compare la scheda «Regole per i PC di questo cliente». Lì si fissano le regole per servizio
(proteggi, registra, blocca, ignora), il caricamento di file, gli allegati, la sostituzione nella casella di scrittura,
gli aggiornamenti, l'analisi degli strumenti AI, e si possono vietare la protezione ridotta e lo spegnimento della
protezione. «Salva e manda ai PC»: ogni PC le riceve in risposta al suo prossimo riepilogo, quindi entro un'ora, e
subito con «Invia ora» dal suo pannello. Con «Tutti i clienti» la scheda non c'è: le regole sono di un cliente.

**Un PC che deve fare diversamente dagli altri.** Nella tabella dei PC ogni riga ha il pulsante «Regole»: apre le
regole di quel solo PC, che partono da quelle del suo cliente. Ogni voce può restare «Come il cliente», avere un valore
suo, che vince su quello del cliente, oppure essere «Libera su questo PC»: il PC è esentato da quella regola del
cliente, e lì torna a decidere chi lo usa. Serve, per esempio, al PC del tecnico che deve poter fermare la protezione,
o a chi lavora proprio con un servizio che agli altri è bloccato. La riga del PC porta il segno «regole proprie»;
«Torna alle regole del cliente» le toglie. Ogni cambio finisce nel registro di conformità, con il nome del PC.

**«Spegnere la protezione: Vietato».** Sul PC il pulsante «Ferma» del pannello resta fermo, dall'icona vicino
all'orologio non si ferma la protezione e non si chiude il programma, e se la protezione è ferma il programma la
riaccende da solo. Non è una serratura: Omissis gira con l'utente che lo usa, e chi lo chiude da Gestione attività, o
lo disinstalla, ci riesce. In quel caso la console lo dice, con l'avviso «Protezione spenta» o «Non si fa sentire».

Tre cose da sapere:

- **Il PC deve aver scelto di accettarle.** Di serie un PC ignora le regole della console. Si accende dal pannello
  (Impostazioni → Console centrale → «Accetta le regole da questa console») oppure, per tutti i PC insieme, mettendo
  `"console_rules": true` nel file che dai a `Set-OmissisPolicy.ps1`. La scheda dice quanti PC le accettano e quanti le
  hanno già applicate.
- **La console non può spostare i dati.** L'elenco di ciò che si può imporre è chiuso, e sta sia nella console sia nel
  programma: restano fuori l'indirizzo della console e del server di inferenza, i gateway, le cartelle, il nome del
  computer e dell'utente nel riepilogo. Chi entrasse nella console senza diritto potrebbe allentare le regole dei PC che
  le accettano, non farsi mandare i loro dati.
- **L'amministratore del PC vince.** Una regola scritta nel registro di Windows del PC (`Set-OmissisPolicy.ps1`) vale
  più di quella della console. Per vietare del tutto le regole della console su un PC: `"console_rules": false` imposto.

### Avvisi

La scheda «Avvisi» elenca ciò che chiede attenzione: un PC che ha spento la protezione, uno che non si fa sentire da tre
giorni, uno strumento AI comparso su un PC che prima non l'aveva. I primi due si chiudono da soli quando il PC torna a
posto; ogni avviso si può chiudere con «Visto».

Con «Dove mandarli» gli avvisi nuovi partono anche fuori dalla pagina, entro un minuto e in un solo messaggio:

- a un **indirizzo web** (webhook): il messaggio è nel campo `text`, la forma che accettano Slack, Mattermost e i
  connettori di Teams; l'indirizzo deve iniziare con `https://`;
- per **posta**, con un server SMTP (STARTTLS o SSL). La password resta tra i dati della console, in chiaro perché
  serve per inviare: è un motivo in più per tenere chiusa la cartella dei dati. Conviene una casella dedicata.

Nel messaggio ci sono il cliente, il nome del computer e che cosa è successo: mai il nome dell'utente, mai conteggi o
testi. «Manda un avviso di prova» dice subito se la destinazione risponde. Se un invio fallisce la pagina lo scrive e
la console riprova da sola.

### Registro di conformità

In fondo alla pagina: chi è entrato (o ha provato), chi ha creato o tolto accessi e clienti, chi ha cambiato le regole
dei PC (con quelle di prima e quelle nuove), le licenze caricate, le destinazioni degli avvisi, ogni esportazione. Per
ogni riga: quando, chi, da quale indirizzo. Si scarica in CSV, anche per un solo cliente.

Le righe non si modificano e non si cancellano dalla console, e ognuna porta un'impronta che dipende da quella prima:
se qualcuno ritocca o toglie una riga nell'archivio, la pagina (e `console --data <dati> --verify-audit`) dice da quale
riga la catena non torna. **Il limite**: chi ha accesso al server e riscrive tutto il registro da capo non viene
scoperto da qui. Per questo la pagina mostra l'impronta dell'ultima riga, e ogni CSV la riporta: annotata ogni tanto
fuori dal server (in un ticket, in una mail), è la prova che il registro di quel giorno era quello.

Il registro non viene mai ripulito da solo, nemmeno da `--prune`. Quello delle versioni precedenti (`audit.jsonl`)
viene portato dentro al primo avvio e il file rinominato `audit-importato.jsonl`.

### Accessi, e ingresso con l'account Microsoft

Nella scheda «Accessi» si creano e si tolgono gli accessi alla console, senza passare dal terminale.

Per far entrare le persone con l'account Microsoft dell'organizzazione (Entra ID) al posto di nome e password:

1. nel centro di amministrazione di Entra, **Registrazioni app → Nuova registrazione**, account «solo di questa
   organizzazione», piattaforma **Web**, con l'indirizzo di reindirizzamento che la console mostra in «Accesso con
   Microsoft» (è l'indirizzo della console seguito da `/auth/microsoft/callback`);
2. in **Certificati e segreti** crea un segreto client;
3. nella console, «Accesso con Microsoft»: incolla ID della directory, ID dell'applicazione e segreto, e attivalo;
4. aggiungi un accesso «Con account Microsoft» per ogni persona, con il suo indirizzo. **Entra solo chi è in
   quell'elenco**: avere un account nell'organizzazione non basta.

Al primo ingresso l'accesso viene legato all'account preciso: un altro account che un giorno prendesse lo stesso
indirizzo non entra. Tieni sempre almeno un accesso con password, per quando Microsoft non è raggiungibile. Il segreto
dell'applicazione scade: alla scadenza se ne crea uno nuovo e lo si incolla di nuovo. Serve un indirizzo `https://`
che Microsoft accetti: con la console in rete locale e il certificato fatto da sé il browser mostrerà il suo avviso.

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
| Togliere un accesso | `console --data <dati> --remove-user nome` (o dalla scheda «Accessi») |
| Creare un accesso che entra con l'account Microsoft | `console --data <dati> --add-user nome@azienda.it --microsoft` |
| Rileggere l'impronta del certificato | `console --data <dati> --show-pin` |
| Installare una licenza, vedere quanto è usata | `console --data <dati> --licence <file>`, `console --data <dati> --licence-info` |
| Chi è entrato e che cosa ha cambiato | Scheda «Registro di conformità» della pagina, con il CSV da scaricare |
| Controllare che il registro non sia stato ritoccato | `console --data <dati> --verify-audit` |
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
| Password dimenticata | Vedi qui sotto, «Password dimenticata» |
| Tutti i PC di un cliente spariscono | È stata creata una chiave nuova: quella vecchia non vale più, i PC vanno ricollegati |

### Password dimenticata

La console non manda password per posta e non le conserva in una forma che si possa rileggere: una password persa
non si recupera, **se ne mette una nuova**. Lo fa chi ha i diritti di amministratore sul computer della console, che
è la stessa persona che potrebbe comunque reinstallarla.

1. Sul computer della console apri PowerShell **come amministratore**.
2. Se non ricordi nemmeno il nome dell'accesso: `C:\OmissisConsole\app\omissis-console.exe --data C:\OmissisConsole\data --list`
3. Metti la password nuova (almeno 12 caratteri; viene chiesta due volte e non si vede mentre la scrivi):
   `C:\OmissisConsole\app\omissis-console.exe --data C:\OmissisConsole\data --set-password nome`

Non serve fermare la console. Le sessioni aperte di quell'accesso si chiudono, e nel registro di conformità resta
scritto che la password è stata cambiata dal terminale. Vale anche dopo «Troppi tentativi»: si aspetta il quarto
d'ora, oppure si riavvia la console.

Se nessuno riesce più a entrare (l'unico accesso entrava con l'account Microsoft e Microsoft non è raggiungibile, o
l'accesso è stato tolto per errore), dallo stesso terminale se ne crea uno nuovo:
`... --add-user nuovo.nome --role msp`. I dati, i clienti e la licenza non vengono toccati.

Chi ha un accesso da cliente, in sola lettura, chiede la password nuova a chi gestisce la console.

## Che cosa è stato provato

Il 15 e 16 novembre 2026: le chiamate della console (101 controlli, comprese le regole per singolo PC); l'HTTPS integrato con il
programma vero di Omissis (impronta giusta: il riepilogo arriva; sbagliata o assente: non parte nulla); la pagina
in HTTPS con il file da scaricare; il pacchetto scompattato, con il programma **compilato**, installato in una
cartella di prova **senza** registrare attività (`-NoTasks`), acceso, collegato, messo sotto licenza, salvato,
aggiornato e tolto (21 controlli); il primo accesso creato dalla pagina, solo dal computer della console; la licenza: soglia gratuita, file firmato, file toccato rifiutato, licenza di
un'altra installazione rifiutata, scadenza.

Sempre il 15 novembre 2026, `Install-Console.ps1` lanciato come amministratore su un Windows 11 in italiano: la
console parte con l'account di servizio, la cartella è chiusa agli utenti normali, la regola del firewall c'è
(reti di dominio e private), la console risponde in HTTPS sull'indirizzo di rete del PC con l'impronta scritta
dallo script, e in chiaro non risponde. La prima prova si era fermata perché lo script chiamava l'account con il
nome inglese, che su un Windows in un'altra lingua non esiste: ora lo ricava dal suo identificativo.

Quella prova è stata fatta con il pacchetto di prima, che portava con sé Python: con il programma compilato
l'installazione da amministratore va rifatta.

Le parti di «Gestire i PC dalla console» sono provate in automatico, sullo stesso computer: le regole arrivano al
programma vero, che le applica solo se ha scelto di accettarle; gli avvisi arrivano a un indirizzo web e a un server di
posta finti; il registro scopre una riga cambiata o tolta. **L'ingresso con l'account Microsoft è provato solo contro un
servizio di accesso finto**: con un'organizzazione vera su Entra ID non è ancora stato provato, e nemmeno gli avvisi
verso Teams, Slack o un server di posta veri.

**Non ancora provato**: il riavvio del server e la copia notturna fatta dall'attività pianificata; un PC che si
collega da un'altra macchina della rete; un aggiornamento sopra un'installazione in funzione; Caddy e il
certificato vero.
