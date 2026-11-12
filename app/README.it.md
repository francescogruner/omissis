# Omissis: programma di gestione, estensione del browser e proxy (prototipo)

Sta tra le app di chat e Internet, su questo PC. Sostituisce i dati sensibili del messaggio con
segnaposto (`[PERSONA_1]`, `[EMAIL_3]`…) prima che partano e li rimette al loro posto nella risposta:
chi scrive vede il testo vero, il servizio vede solo segnaposto. In più tiene il conto dei servizi
AI contattati e fa l'inventario degli strumenti AI presenti sul PC (Shadow AI).

## Avvio

```
cd app
.venv\Scripts\python.exe panel.py
```

Si apre il pannello nel browser (http://127.0.0.1:8766) e compare un'icona vicino all'orologio:
da lì si avvia e si ferma la protezione, si mascherano e ripristinano gli appunti e si esce dal
programma.

Il pannello ha due modalità. Quella **semplice**, con cui si apre, mostra solo ciò che serve a chi
usa il programma: Inizio, Testo, Documenti, Guida. Quella **avanzata** (in basso a sinistra)
aggiunge le sezioni per chi lo gestisce. Tutte le sezioni:

| Sezione | A cosa serve |
|---|---|
| Panoramica | stato, messaggi protetti, tipi di dato sostituiti, avvisi |
| Attività | una riga per richiesta (solo conteggi e nomi dei campi, mai i testi) |
| Servizi AI | per ogni servizio: proteggi, lascia passare e registra, blocca, ignora |
| Shadow AI | strumenti AI sul PC (programmi, estensioni, modelli locali) e servizi contattati |
| Testo | mascherare un testo prima di darlo all'AI e ripristinare la risposta |
| Documenti | anonimizzare e ripristinare file e cartelle intere |
| Guida | come si usa, in quattro passi |
| Browser | installare e collegare l'estensione per Chrome ed Edge |
| Terminale | collegare Claude Code, Codex e gli altri strumenti da terminale (gateway) |
| App desktop | avviare Claude e ChatGPT per Windows con la protezione dentro la finestra (sperimentale) |
| Liste | termini da mascherare sempre / da non mascherare mai |
| Archivio | corrispondenza segnaposto ↔ valore reale (resta su questo PC) |
| Impostazioni | modello, porta, file, finestra di prova, certificato |

`start.py` è la variante da terminale, senza pagina: mostra una riga per richiesta.

## Il pannello

La pagina sta nella cartella `pannello`: `index.html` (lo scheletro), `style.css`, `app.js` e le
frasi in `locales\<codice>.json`. Nessuna libreria e nessun file caricato da fuori; la pagina vieta
a se stessa qualunque codice che non venga dai suoi file (intestazione Content-Security-Policy).

Le sezioni, senza doppioni:

| Sezione | Cosa c'è | Per chi |
|---|---|---|
| Inizio | stato, avvio e arresto, numeri di oggi; in modalità avanzata lo stato dei quattro collegamenti e i grafici | tutti |
| Testo | una casella sola: incollando, un testo normale viene mascherato e una risposta con i segnaposto ripristinata; il risultato va da solo negli appunti | tutti |
| Documenti | file trascinati (in automatico: ripristina quelli con i segnaposto, anonimizza gli altri, e scarica il risultato) e cartelle intere | tutti |
| Guida | come si usa, in quattro passi | tutti |
| Impostazioni | Generali: lingua, tema, modalità, aggiornamenti. Riconoscimento (avanzata): modello, difese, liste «sempre» e «mai» | tutti |
| Collegamenti | Browser (estensione), App desktop, Terminale (gateway), Proxy (porta, certificato, finestra di prova) | tecnico |
| Servizi AI | Regole (cosa fare per ogni servizio) e Rilevati su questo PC (gli strumenti AI trovati) | tecnico |
| Attività, Archivio | il registro delle richieste e la corrispondenza tra segnaposto e valori | tecnico |

**Lingue.** Italiano e inglese. Ogni frase che l'utente vede (pagina, menu dell'icona, notifiche,
messaggi d'errore) sta in `panel\locales\it.json` e `en.json`, con le stesse chiavi; il codice
contiene solo le chiavi. «Automatica» segue la lingua di Windows (inglese se non è tra quelle
presenti). Per aggiungere una lingua: copiare `it.json` con il codice della lingua (`de.json`),
tradurre i valori e cambiare `_lingua`: compare da sola nelle Impostazioni. `check_languages.py`
dice cosa manca, cosa avanza e dove le parole tra graffe non coincidono. Gli eventi vengono scritti
nel registro in italiano: la pagina traduce quelli noti.

L'**estensione del browser** ha le sue frasi in `extension\_locales\<lingua>\messages.json`, nel
formato che chiedono i browser e gli store (nome e descrizione compresi), e segue la lingua del
browser, non quella scelta nel programma: finestrella, pagina di blocco, avvisi nelle pagine,
testo dell'icona. Nelle app desktop gli stessi avvisi li porta il connettore, nella lingua del
programma. Lo stesso `check_languages.py` controlla anche questi file. `e2e_extension.py
--lang=en` avvia il browser di prova in inglese.

Browser provati con `e2e_extension.py --browser=<percorso dell'eseguibile>` (profilo vuoto e a
parte, servizio finto): **Edge 157 e Brave 157, 26 controlli su 26**, oltre al Chromium di prova.
**Chrome** di marca non accetta più estensioni dalla riga di comando: lì va caricata a mano da
`chrome://extensions`, e la prova automatica non si può fare; il motore è lo stesso del Chromium di
prova. Nessun browser è stato ancora provato con un account vero. Firefox non è coperto.

**Accessibilità.** Struttura con punti di riferimento (menu, contenuto), collegamento «vai al
contenuto», un solo titolo per pagina, linguette usabili con le frecce, ogni pulsante e ogni campo
con un nome, avvisi annunciati agli schermi parlanti, contrasto adeguato in chiaro e in scuro,
nessuna animazione per chi le ha disattivate, uso completo dalla tastiera. Lo controlla
`e2e_panel.py`; non è stato provato con uno schermo parlante vero.

## Allegati

Il file che l'utente allega a un messaggio (scelto dal pulsante, trascinato o incollato) viene fermato **prima che
la pagina lo riceva**, mandato al programma sul PC e sostituito con la copia anonimizzata: la pagina, e quindi il
servizio, vede solo quella. Come per la casella di scrittura, non dipende da come il sito carica poi il file.

| Cosa si allega | Cosa arriva al servizio |
|---|---|
| Word, Excel, PowerPoint | lo stesso formato, con i dati sostituiti (`nome.anon.docx`) |
| testo, CSV, JSON e simili | lo stesso formato, con i dati sostituiti |
| PDF | un file di testo con il contenuto anonimizzato (`nome.anon.txt`) |
| immagine con del testo (scansione, schermata) | un file di testo con ciò che è stato letto, anonimizzato: la lettura può contenere errori |
| immagine o PDF senza testo leggibile | il file così com'è: non c'è testo da sostituire (un volto resta un volto) |
| altri formati, o file oltre 20 MB (8 MB nelle app desktop) | secondo «Blocca il caricamento di file»: non allegato, oppure allegato com'è con una riga in Attività |

Se la protezione non risponde il file non viene allegato. Nel registro finiscono il tipo di file e i conteggi, mai il
nome. La lettura di Word, PDF e immagini la fa il programma di gestione: il motore, che non ne ha le librerie, gliela
chiede sullo stesso PC. L'impostazione è «Anonimizza gli allegati» (Impostazioni → Riconoscimento), accesa.

Provato con il servizio finto nell'estensione (scelta, trascinamento, incolla; testo e Word) e nell'app di prova
(trascinamento). **Non ancora provato sui siti e sulle app veri**: lì può darsi che un sito legga il file per una
strada diversa dalle tre coperte, e va visto servizio per servizio. I file che l'AI restituisce si riportano ai valori
veri dalla sezione Documenti.

## Catalogo e radar

I servizi di intelligenza artificiale stanno su due livelli.

- **Catalogo** (`catalog.py`, una settantina di servizi): quelli che il programma conosce uno per uno. Alcuni li sa
  leggere e quindi proteggere; per tutti si sceglie tra proteggere, registrare, bloccare, ignorare. L'estensione
  chiede l'accesso ai loro siti.
- **Radar**: servizi che il programma non sa leggere e che servono solo a rilevare, registrare e bloccare.
  `radar.json` accanto al codice è il radar di base, con i più noti. Un elenco esteso si aggiunge mettendo un
  secondo `radar.json`, nello stesso formato, nella cartella dei dati: non fa parte del programma pubblico.
  `check_radar.py [file] --network` ne controlla forma, doppioni, domini troppo generici e, chiedendo al DNS,
  che ogni dominio esista.

L'estensione **non chiede l'accesso** ai siti del radar: quelli che si sceglie di bloccare li ferma con una regola
del browser (la richiesta non parte; compare l'errore del browser, non la pagina di avviso). Chi passa dal proxy
viene fermato allo stesso modo. Regola per chi compila l'elenco: solo domini dedicati a un servizio AI, mai quello
di una piattaforma generale (bloccare `google.com` per fermare un suo servizio fermerebbe tutto il resto).

## Uso manuale, dentro qualsiasi app

Funziona con ogni app e ogni abbonamento, perché non legge il traffico di nessuno. Richiede solo
la protezione attiva.

- **Testo**: nella sezione Testo si incolla ciò che si vuole dare all'AI, si copia la versione
  mascherata, e a risposta ricevuta la si incolla lì per riavere i valori veri.
- **Appunti** (con il programma aperto): `Ctrl+Alt+M` sostituisce il testo copiato con la versione
  mascherata, pronta da incollare; `Ctrl+Alt+R` rimette i valori veri in una risposta copiata.
- **Documenti**: nella sezione Documenti si trascinano i file (Word, Excel, PowerPoint, testo, PDF
  con testo) oppure si indica una cartella intera. Per Cowork e simili: si anonimizza la cartella
  (`Pratica` → `Pratica.anon`), si fa lavorare l'AI sulla copia, poi si ripristina
  (`Pratica.anon` → `Pratica.ripristinato`). Da terminale: `documents.py anonimizza <percorso>`.

Nei file Office la formattazione resta e vengono trattati anche intestazioni, piè di pagina, note,
commenti, testo eliminato con le revisioni; autore, azienda e autori di revisioni e commenti vengono
tolti (e non tornano con il ripristino). PDF scansionati e immagini vengono letti con il
riconoscimento dei caratteri di Windows (`ocr.py`: gira in locale, serve l'italiano tra le
lingue di Windows); il testo letto può contenere errori (una I scambiata per 1) e va riletto.
Limiti: le immagini inserite dentro i documenti non sono coperte (nelle cartelle i file non coperti
vengono saltati, non copiati); da PDF e immagini esce un file di testo; nei
fogli Excel ogni cella è valutata da sola, senza l'intestazione della colonna, quindi il modello
può sbagliare di più; i nomi dei file e dei fogli restano come sono.

## Estensione del browser (Chrome ed Edge)

È la strada automatica per chi usa i servizi dal sito, con il proprio abbonamento: niente proxy,
niente certificato. L'estensione lavora dentro la pagina, prima che il messaggio venga cifrato:
manda il testo al programma su questo PC (solo `127.0.0.1`), fa partire la versione con i
segnaposto e riscrive la risposta mentre arriva. Chi scrive vede sempre i valori veri.

Installazione di prova: `chrome://extensions` → Modalità sviluppatore → Carica estensione non
pacchettizzata → cartella `estensione`. Poi nel pannello, aperto in quel browser, sezione Browser →
Collega questo browser. Finché non è collegata, o se la protezione è ferma, sui servizi protetti i
messaggi **non partono** (compare un avviso rosso nella pagina); dalla finestrella dell'icona si
può sospendere la protezione in quel browser.

Le difese sono due, in fila. La prima è sulla **casella di scrittura**: all'Invio (o al clic sul
pulsante di invio) i dati vengono sostituiti già nella casella, prima che il sito legga il testo.
Non dipende dal formato delle richieste, che i siti cambiano senza preavviso, ed è quindi quella che
regge meglio agli aggiornamenti dei servizi (si spegne da Impostazioni). La seconda legge le
richieste della pagina e sostituisce ciò che la prima non ha visto (cronologia, testo modificato,
strumenti che non passano dalla casella). Con la prima attiva, nella conversazione salvata dal
servizio restano i segnaposto: i valori veri si vedono solo dove c'è Omissis.

## Cosa può rompersi con gli aggiornamenti dei servizi

| Pezzo | Cosa lo rompe | Quanto spesso |
|---|---|---|
| Testo, Documenti, scorciatoie sugli appunti | nulla che dipenda dai fornitori | mai |
| Gateway per il terminale | un cambio delle API ufficiali (pubbliche, con versioni) | di rado |
| Casella di scrittura (estensione e app desktop) | un cambio della casella o del pulsante di invio | ogni tanto |
| Lettura delle richieste (estensione, proxy) | un cambio del formato interno dei siti | spesso |
| Avvio protetto delle app desktop | che il produttore tolga la porta di collegamento | imprevedibile |

Quando la lettura delle richieste non riconosce più un formato il messaggio passa senza
sostituzioni e resta solo una riga nel registro («nessun campo di testo riconosciuto»): per questo
la casella di scrittura va lasciata accesa. Le prove automatiche vanno rilanciate a ogni
aggiornamento importante dei servizi.

Cosa fa, servizio per servizio, lo decide la sezione Servizi AI (le stesse scelte del proxy):

- **proteggi**: sostituisce i dati nelle richieste e li rimette nelle risposte;
- **registra**: segna solo la visita (Shadow AI), senza proxy;
- **blocca**: al posto del sito compare una pagina di blocco; il sito non viene nemmeno contattato.

Come è fatta: `page.js` (dentro la pagina: intercetta `fetch` e `XMLHttpRequest`), `content.js`
(accanto alla pagina: tramite, avvisi, valori veri nel testo), `background.js` (parla con il programma,
applica i blocchi), `bridge.py` (nel motore: riusa gli adattatori di `restore.py`, gli stessi
del proxy). `build_extension.py` riscrive `manifest.json` dal catalogo: va rilanciato quando
cambia `catalog.py`.

Limiti dell'estensione:

- **mai provata con gli account veri**: i siti di Claude, ChatGPT e Mistral mostrano al browser
  automatico di prova una pagina di verifica, quindi lì non si è visto nulla; la prima prova vera è
  quella nel proprio browser, con dati inventati;
- i valori rimessi nella risposta sono visibili agli script del sito (vale per qualunque strumento
  che ripristina dentro la pagina, proxy compreso): chi non lo vuole spegne «Ripristina i valori
  nelle risposte» e ripristina con `Ctrl+Alt+R` dopo aver copiato;
- le risposte che arrivano via `XMLHttpRequest` (Gemini) o WebSocket (Copilot) non vengono
  riscritte in rete: i valori veri compaiono nel testo della pagina, ma il tasto «copia» del sito
  copia i segnaposto. I messaggi **inviati** via WebSocket non sono coperti: il registro lo segnala;
- le richieste fatte da un processo secondario della pagina (web worker) non sono intercettate;
- i file allegati vengono anonimizzati al momento della scelta (vedi «Allegati»); ciò che non si riesce ad anonimizzare
  si può bloccare;
- solo Chrome ed Edge; Firefox non è stato fatto;
- il collegamento con il programma passa da `127.0.0.1` con un codice: per la versione definitiva
  va sostituito con la messaggistica nativa del browser, e l'installazione va fatta dai criteri
  aziendali (estensione forzata, che l'utente non può togliere).

## Strumenti da terminale: il gateway

Per Claude Code, Codex, opencode, aider e ogni programma a cui si può dire dove sta il servizio.
`gateway.py` parte insieme alla protezione su `http://127.0.0.1:8767`: lo strumento parla con lui
invece che con il servizio vero, lui sostituisce i dati, inoltra in HTTPS e rimette i valori veri
nella risposta. Niente certificato e niente proxy:

```
$env:ANTHROPIC_BASE_URL="http://127.0.0.1:8767/anthropic"; claude
$env:OPENAI_BASE_URL="http://127.0.0.1:8767/openai/v1"
```

Gli altri indirizzi (DeepSeek, Mistral, Groq, OpenRouter, Ollama, LM Studio…) sono nella sezione
Terminale del pannello. Le credenziali passano così come sono e non vengono scritte.

Questi strumenti rimandano a ogni richiesta tutta la conversazione, comprese le azioni già fatte e
i loro risultati; per questo gli adattatori sono diversi da quelli delle chat (`agents.py`):

- nella richiesta si mascherano il testo, i risultati degli strumenti (file letti, uscita dei
  comandi) e gli argomenti delle azioni già fatte;
- nella risposta si ripristinano il testo e gli argomenti delle nuove azioni, altrimenti lo
  strumento scriverebbe file o eseguirebbe comandi con dentro i segnaposto;
- i ragionamenti firmati non si toccano, né all'andata né al ritorno;
- nel contesto tecnico che lo strumento aggiunge da sé (istruzioni di sistema, promemoria) si
  sostituiscono solo i dati personali, non nomi di strumenti, identificativi e percorsi.

Verificato: `e2e_gateway.py` (19 controlli contro un servizio finto) e **due prove dal vivo con
Claude Code** e accesso in abbonamento, con dati inventati. Nella prima un messaggio semplice: 0
valori in chiaro verso il servizio, risposta tornata con i valori veri. Nella seconda un'azione:
Claude Code ha scritto un file, sul disco ci sono i valori veri e il servizio ha visto solo
segnaposto anche nella richiesta successiva, dove l'azione fatta torna nella cronologia. Non ancora
provato con una sessione di lavoro lunga (molti comandi e file): lì il rischio non è la fuga di dati
ma un contesto molto mascherato, che può confondere il modello. I nomi degli strumenti dichiarati
nella richiesta non vengono mai sostituiti. Il formato OpenAI è provato solo con il servizio finto; Codex con accesso
ChatGPT (non con chiave) parla con un indirizzo diverso e non è coperto.

## App desktop: Claude e ChatGPT per Windows (sperimentale)

Le due app installate su questo PC sono, sotto, un browser Chromium con dentro il sito del servizio
(Claude: Electron 45; ChatGPT/Codex di OpenAI: un Chromium 157 proprio). Avviate con la porta di
debug, `connector.py` ci si collega e porta dentro la finestra **lo stesso codice dell'estensione**:
il testo viene sostituito prima di essere cifrato, quindi niente certificato, niente proxy, e non
conta se l'app controlla i certificati. Chi usa l'app tiene il proprio abbonamento e tutte le
funzioni dell'app.

Dal pannello: sezione App desktop → Avvia protetta (la protezione deve essere attiva e l'app
**chiusa del tutto**, anche dall'icona vicino all'orologio). Da terminale:
`.venv\Scripts\python.exe connector.py --avvia claude` (oppure `chatgpt`).

Le barriere sono due. Quella **dentro la pagina** sostituisce i dati e riscrive le risposte mentre
arrivano. Quella **a livello di rete** ferma ogni invio verso un servizio protetto prima che parta e
lo ricontrolla: serve perché una finestra appena aperta può mandare richieste prima che il codice al
suo interno sia attivo (provato: senza la seconda barriera quei messaggi uscivano in chiaro; con la
seconda, 60 finestre su 60 partono mascherate). Per quelle richieste la risposta resta con i
segnaposto finché la pagina non è pronta.

Da sapere:

- **l'app di ChatGPT non manda i messaggi come richieste della finestra**: la finestra li consegna
  al processo principale dell'app per un canale interno, che da fuori non si può sorvegliare (per
  questo le prime prove dal vivo sono fallite: il codice era dentro la finestra ma non vedeva passare
  nulla). Lì lavora la **barriera sulla casella di scrittura**: all'Invio, o al clic sul pulsante di
  invio, il testo viene sostituito nella casella prima che l'app lo legga; i valori veri tornano poi
  nel testo a schermo, anche quando l'app scrive un segnaposto spezzato in più pezzi.
  **Verificato dal vivo sull'app di ChatGPT** con dati inventati: avviso «3 dati sostituiti», e
  ChatGPT ha risposto citando i segnaposto, quindi ha ricevuto solo quelli. Limiti di questa strada:
  nell'app (cronologia, titolo della conversazione, altri dispositivi) restano i segnaposto, e i
  valori veri si vedono solo sul PC con Omissis; il tasto «copia» dell'app copia i segnaposto (si
  ripristinano con `Ctrl+Alt+R`); dettatura e modifica di vecchi messaggi non sono coperti. Gli allegati seguono la
  stessa strada dell'estensione, provata sull'app di prova e non ancora su quella vera.
  Lo stato nel pannello ha tre livelli: non protetta, collegata ma non verificata, verificata dopo
  il primo messaggio passato dalla protezione. Su Claude Desktop non è mai stato provato. Sull'app
  di prova: `e2e_connector.py`, 29 controlli;
- finché l'app è aperta così, qualunque programma di questo PC può comandarla dalla porta;
- nel codice di Claude Desktop la porta di debug è in un elenco di opzioni a cui l'app reagisce
  (risulta che spenga il collegamento locale e il gestore delle password): l'app potrebbe anche
  limitarsi o rifiutarsi, e il produttore può togliere questa possibilità quando vuole. Non è una
  strada ufficiale: quelle ufficiali restano l'estensione per il web e la modalità "gateway";
- il connettore deve attivare una funzione di debug (`Runtime.enable`) di cui un sito può
  accorgersi: una verifica anti-automazione dentro l'app potrebbe rifiutarla;
- se il programma si stacca, nell'app i messaggi verso i servizi protetti restano bloccati finché
  non la si riavvia normalmente (non esce nulla in chiaro);
- stessi limiti dell'estensione per WebSocket, file e processi secondari della pagina.

Cosa si è visto leggendo le app (sola lettura): Claude Desktop **non blocca i certificati** su una
chiave fissa, ha un elenco di 33 chiavi che rifiuta: il certificato creato dal nostro proxy non può
essere in quell'elenco, quindi anche la strada proxy + certificato (sezione più sotto) è plausibile,
ma resta da provare. Nell'app di OpenAI non ci sono tracce di controlli nel codice leggibile; quelli
eventuali starebbero nella parte compilata.

## Prova sul web con il proxy (non cambia nulla nel sistema)

Con la protezione attiva, da Impostazioni → Finestra di prova sul web (oppure
`.venv\Scripts\python.exe browser_window.py https://claude.ai`). Si apre una finestra di Chrome
separata, con un profilo suo: bisogna rifare l'accesso al servizio. Solo quella finestra passa
dal proxy. **Usare dati inventati** finché il servizio non risulta verificato.

## Prova con le app desktop (richiede il certificato)

Le app accettano il proxy solo se Windows si fida del suo certificato: si installa da
Impostazioni → Certificato (vale per il solo utente corrente, Windows chiede conferma) e da lì si
rimuove a prova finita. Poi si chiude l'app e la si riavvia facendola passare dal proxy:

```
& "C:\Program Files\WindowsApps\Claude_5.1231.2.0_x64__pzs8sxrjxfjjc\app\Claude.exe" --proxy-server=http://127.0.0.1:8080
```

(il percorso cambia a ogni aggiornamento dell'app). Finché il certificato è installato, chi
possiede la chiave privata in `data\ca` può leggere il traffico HTTPS di questo utente: la cartella
non va copiata né condivisa.

## Quanto è verificato

| Servizio | Stato |
|---|---|
| Claude, ChatGPT, API Anthropic, API OpenAI | formato noto, provato con un servizio finto; **non ancora con gli account veri** |
| API compatibili con OpenAI (DeepSeek, Mistral, Groq, OpenRouter…) | stesso formato dell'API OpenAI |
| Gemini | **sperimentale**: formato scritto a memoria, provato solo su un'imitazione |
| Copilot, Perplexity, Kimi, Grok, Le Chat e gli altri "generici" | riconoscimento dei campi dal nome: **da verificare uno per uno** |
| Tutti gli altri del catalogo | il proxy non li legge: si possono solo registrare o bloccare |
| Gateway per gli strumenti da terminale | servizio finto (`e2e_gateway.py`, 19 controlli) e **Claude Code dal vivo** con un messaggio di dati inventati |
| Connettore per le app desktop | app di prova (`e2e_connector.py`, 29 controlli) e **app vera di ChatGPT**: un messaggio di dati inventati è arrivato al servizio con i soli segnaposto (barriera sulla casella di scrittura) |
| Estensione del browser | stessi formati, provati in un browser vero contro il servizio finto (`e2e_extension.py`, 25 controlli); pagine vere solo aperte, senza accedere |

Per questo, all'inizio, sono impostati su "proteggi" solo i primi quattro: gli altri si attivano
da Servizi AI dopo averli provati con dati inventati.

## Cosa guardare durante una prova

Nella sezione Attività (o in `data\activity.jsonl`):

- `mascherata` = tutto regolare;
- `nessun campo di testo riconosciuto` = il servizio usa un formato che il proxy non conosce:
  la richiesta è partita **non mascherata**. La riga riporta la struttura (senza valori), che
  serve per adattarlo;
- `VALORI_IN_CHIARO` = un dato già mascherato compare in chiaro in un'altra richiesta;
- `file NON mascherato` = è stato caricato un file.

## Limiti noti

- Gli allegati vengono anonimizzati solo dove lavora l'estensione o il connettore delle app (vedi «Allegati»); chi passa
  dal solo proxy o dal gateway carica i file così come sono, e lì si possono soltanto bloccare.
- I messaggi su WebSocket (Copilot) sono gestiti ma mai provati.
- Shadow AI in rete: su questo PC la memoria DNS di Windows è vuota, quindi si vedono solo il
  traffico che passa dal proxy e i programmi AI con connessioni aperte. Lo storico completo della
  rete richiede il proxy per tutti, oppure i registri DNS del firewall.
- Cattura del traffico per processo (senza avviare le app con `--proxy-server`): non ancora fatta,
  richiede i diritti di amministratore.
- L'archivio è cifrato con la protezione dei dati di Windows (DPAPI), legata all'utente: copiato su
  un altro PC o letto da un altro utente non si apre. Un programma che gira con lo stesso utente,
  però, può chiedere a Windows di decifrarlo: protegge dal furto del file, non da un programma
  malevolo già in esecuzione nel proprio profilo. Se il profilo di Windows va perso, l'archivio non
  è recuperabile.
- Se il programma viene chiuso di forza, motore e proxy possono restare accesi: alla ripartenza
  la porta risulta occupata e vanno chiusi a mano.

## Copia installata, modello e aggiornamenti

Chi installa Omissis con l'installer (`Omissis-<versione>-setup.exe`) non ha bisogno di Python: il
pacchetto porta con sé l'interprete e le librerie, si installa per il solo utente senza diritti di
amministratore e mette il programma in `%LOCALAPPDATA%\Programs\Omissis`. Tutto ciò che è
dell'utente (archivio dei valori, impostazioni, registro, liste personali, certificato del proxy,
modello) sta invece in `%LOCALAPPDATA%\Omissis`: un aggiornamento riscrive la cartella del
programma e non tocca i dati. La disinstallazione chiede se eliminare anche i dati (e in quel caso
toglie il certificato del proxy da Windows); altrimenti restano dove sono.
Una copia lanciata dai sorgenti continua a tenere i dati in `dati`, accanto al codice.

**Il modello** non sta nell'installer. Al primo avvio il programma scarica i pesi dalla pagina
pubblica del modello (537 MB o 1,2 GB, secondo la scelta nelle Impostazioni) e mostra l'avanzamento
nella Panoramica; se la rete cade riprende da dove era arrivato. Ogni file viene accettato solo se
dimensione e impronta SHA-256 sono quelle scritte in `weights.json`, che viaggia con il programma:
un file diverso da quello con cui la versione è stata provata viene scartato. Dopo, il programma
lavora senza rete.

**Gli aggiornamenti** (sezione Impostazioni): una volta al giorno il programma legge dalla pagina
pubblica delle versioni un foglio, `update.json`, con il numero dell'ultima versione, il nome
dell'installer e la sua impronta. È una semplice lettura: non parte nessun dato, nessun
identificativo del PC. Il foglio vale solo se è **firmato** (Ed25519) con la chiave dell'autore, la
cui metà pubblica è scritta in `updates.py`: chi manomettesse la pagina delle versioni o la
rete non potrebbe far installare un programma suo. L'installer scaricato viene confrontato con
l'impronta del foglio firmato, e ricontrollato un attimo prima di lanciarlo; una versione più
vecchia di quella installata non viene mai accettata. Tre scelte: scarica e installa da solo (al
successivo avvio del programma, oppure subito con «Installa ora»: il programma si chiude e si
riapre in pochi secondi), avvisa soltanto, non controllare. La copia lanciata dai sorgenti avvisa
soltanto. Una copia arrivata dal Microsoft Store non controlla nulla: la aggiorna lo Store.

Provato davvero su questo PC: installazione in silenzio, scaricamento e verifica del modello da un
servizio locale, mascheratura con il motore del pacchetto, passaggio da 0.1.0 a 0.1.1 con
riapertura automatica e dati intatti, disinstallazione pulita. **Non ancora provato**: un PC appena
installato (senza altre librerie di sistema), lo scaricamento dalla pagina vera del modello, un
aggiornamento dalla pagina vera delle versioni, il pacchetto per il Microsoft Store (non esiste).
Senza firma del codice, Windows mostra l'avviso di SmartScreen al primo avvio dell'installer.

## Prove automatiche

Con `panel.py --test` (o `start.py --test`) e `mock_service.py` in esecuzione:
`e2e_proxy.py` (9 formati), `e2e_https.py` (intercettazione HTTPS reale senza account),
`e2e_policies.py pi.ai www.perplexity.ai` (blocco e registrazione), `e2e_documents.py`
(crea una cartella di esempio in `data\esempi`, la anonimizza, controlla e ripristina) e
`e2e_clipboard.py`.

Per l'estensione: `build_extension.py --test` (aggiunge il servizio finto ai siti su cui gira),
poi `e2e_extension.py` e alla fine `build_extension.py` per tornare alla versione normale.
Usa un browser di prova che sta in `.playwright` (740 MB, si può cancellare; si riscarica con
`set PLAYWRIGHT_BROWSERS_PATH=app\.playwright` e
`.venv\Scripts\python.exe -m playwright install chromium`). `e2e_sites.py` apre le pagine vere
dei servizi senza accedere e senza scrivere, per vedere se si caricano con l'estensione attiva.
`e2e_vault.py` prova l'archivio cifrato e non ha bisogno di nulla acceso.
`e2e_panel.py` (23 controlli, serve la protezione attiva) apre ogni sezione del pannello in
italiano e in inglese: nessun errore, nessuna frase senza traduzione, nomi di pulsanti e campi, uso
dalla tastiera, il giro completo di un testo e di un documento con dati inventati; e scatta le
schermate che vanno nei documenti e nel sito. `check_languages.py` confronta i file delle lingue
tra loro e con il codice.
`e2e_install.py` (22 controlli, nulla acceso) prova lo scaricamento del modello e gli
aggiornamenti contro un servizio finto: ripresa, file manomessi, firma di un'altra chiave, foglio
ritoccato, versione più vecchia, installer sostituito sul disco.
`e2e_connector.py` prova il connettore per le app desktop sullo stesso browser di prova, avviato
con la porta di debug e senza estensione. `e2e_gateway.py` prova il gateway con un suo servizio
finto e ha bisogno solo del motore acceso.

Per provare senza fermare il programma in uso: `set OMISSIS_PORT=8775` prima di avviare una
seconda copia (motore, pannello e gateway prendono le porte 8775, 8776 e 8777; la porta del proxy
si cambia nelle impostazioni di quella copia).
