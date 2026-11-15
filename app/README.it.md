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
| App desktop | avviare Claude, ChatGPT, Kimi e Copilot per Windows con la protezione dentro la finestra (sperimentale) |
| Liste | termini da mascherare sempre / da non mascherare mai |
| Archivio | corrispondenza segnaposto ↔ valore reale (resta su questo PC) |
| Impostazioni | modello, porta, file, finestra di prova, certificato |

`start.py` è la variante da terminale, senza pagina: mostra una riga per richiesta.

## Il pannello

La pagina sta nella cartella `panel`: `index.html` (lo scheletro), `style.css`, `app.js` e le
frasi in `locales\<codice>.json`. Nessuna libreria e nessun file caricato da fuori; la pagina vieta
a se stessa qualunque codice che non venga dai suoi file (intestazione Content-Security-Policy).

Le sezioni, senza doppioni:

| Sezione | Cosa c'è | Per chi |
|---|---|---|
| Inizio | stato, avvio e arresto, numeri di oggi; in modalità avanzata lo stato dei quattro collegamenti e i grafici | tutti |
| Testo | una casella sola: incollando, un testo normale viene mascherato e una risposta con i segnaposto ripristinata; il risultato va da solo negli appunti e si corregge sul posto | tutti |
| Documenti | file trascinati (in automatico: ripristina quelli con i segnaposto, anonimizza gli altri, e scarica il risultato) e cartelle intere, scelte con la finestra di Windows | tutti |
| Guida | come si usa, in quattro passi | tutti |
| Impostazioni | Generali: lingua, tema, modalità, scorciatoie da tastiera, aggiornamenti. Riconoscimento (avanzata): modello, difese, liste «sempre» e «mai» | tutti |
| Collegamenti | Browser (estensione), App desktop, Terminale (gateway), Proxy (porta, certificato, finestra di prova) | tecnico |
| Servizi AI | Regole (cosa fare per ogni servizio) e Rilevati su questo PC (l'inventario degli strumenti AI, tenuto nel tempo) | tecnico |
| Attività | il registro delle richieste | tecnico |
| Archivio | la corrispondenza tra segnaposto e valori: ricerca, eliminazioni mirate, pulizia | tecnico |

**Configurazione guidata.** La prima volta che si apre il pannello compare una finestra di pochi passi,
ognuno saltabile: una prova con dati inventati (che non entra nei conteggi), dove si usa l'AI (browser, app
installate, terminale), il collegamento dell'estensione del browser, e due righe su che cosa sapere. Chiusa o
saltata, non torna più (`onboarded` nelle impostazioni); si rivede dalla Guida. Non compare sui PC con
impostazioni imposte da chi li amministra. L'estensione, appena installata, apre a sua volta una pagina che
dice che cosa manca (il collegamento al programma) e lo fa fare con un clic: il pannello aperto da lì
(`#/connect`) consegna da solo il codice di collegamento a quel browser.

**Contatti.** In fondo al menu e nella Guida c'è il collegamento per scrivere a chi fa Omissis. È un
collegamento e basta: si apre solo se lo si preme, e il programma non manda nulla.

**Lingue.** Italiano e inglese. Ogni frase che l'utente vede (pagina, menu dell'icona, notifiche,
messaggi d'errore) sta in `panel\locales\it.json` e `en.json`, con le stesse chiavi; il codice
contiene solo le chiavi. «Automatica» segue la lingua di Windows (inglese se non è tra quelle
presenti). Per aggiungere una lingua: copiare `it.json` con il codice della lingua (`de.json`),
tradurre i valori e cambiare `_language`: compare da sola nelle Impostazioni. `check_languages.py`
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

- **Testo selezionato, sul posto** (con il programma aperto): si seleziona un testo in qualsiasi
  programma e si preme `Ctrl+Alt+S`. Omissis lo copia, lo maschera e lo incolla al posto
  dell'originale; una notifica dice quanti dati ha sostituito. Se non trova nulla di sensibile, o
  se la protezione non risponde, il testo resta com'era.
- **Appunti**: `Ctrl+Alt+M` sostituisce il testo copiato con la versione mascherata, pronta da
  incollare; `Ctrl+Alt+R` rimette i valori veri in una risposta copiata. Le stesse due azioni sono
  nel menu dell'icona vicino all'orologio.
- **Testo**: nella sezione Testo si incolla ciò che si vuole dare all'AI: viene mascherato e
  copiato da solo; a risposta ricevuta la si incolla lì per riavere i valori veri.
- **Documenti**: nella sezione Documenti si trascinano i file (Word, Excel, PowerPoint, testo, PDF
  con testo) oppure si sceglie una cartella intera con «Sfoglia». Per Cowork e simili: si
  anonimizza la cartella (`Pratica` → `Pratica.anon`), si fa lavorare l'AI sulla copia, poi si
  ripristina (`Pratica.anon` → `Pratica.restored`). «Apri la cartella» mostra il risultato in
  Esplora file. Da terminale: `documents.py anonimizza <percorso>`.

**Correggere il risultato.** Nessun riconoscimento è perfetto, quindi nella sezione Testo il
risultato si sistema senza ricominciare:

- un segnaposto di troppo: lo si preme e si sceglie «Lascia in chiaro» (solo per questo testo)
  oppure «Non mascherare mai» (finisce nell'elenco `never.txt`, e vale anche per ciò che trovano
  le regole: per esempio l'indirizzo email generico dell'azienda);
- un dato sfuggito: lo si seleziona nel risultato (o lo si scrive), si sceglie che cos'è e si preme
  «Maschera anche questo»; con «sempre» finisce nell'elenco `always.txt`.

A ogni correzione il testo viene rifatto e ricopiato. Le correzioni «per questo testo» si vedono
sotto il risultato e si tolgono con un clic. Un testo oltre 200.000 caratteri viene rifiutato con
un messaggio, mai tagliato in silenzio: per quelli si usa un file in Documenti.

**Scorciatoie.** Le tre combinazioni si cambiano (la lettera da premere con `Ctrl+Alt`) o si
spengono in Impostazioni → Generali; nel file delle impostazioni (`shortcuts`) si può scrivere
qualunque combinazione, anche con `shift` o un tasto funzione. Sono registrate con la funzione di
Windows per le scorciatoie globali: Windows consegna al programma **solo quelle combinazioni**,
gli altri tasti premuti non li vede (prima si usava una libreria che ascoltava tutta la tastiera:
è stata tolta). Se all'avvio una combinazione è già di un altro programma (succede spesso: la
sovrapposizione delle schede NVIDIA, per esempio, usa `Ctrl+Alt+M` e `Ctrl+Alt+R`), Omissis ne
registra una libera con una lettera vicina, la salva e lo dice con una notifica; guida e pagine
mostrano sempre le combinazioni in uso davvero. Se invece si sceglie a mano una lettera occupata,
il pannello lo segnala e se ne sceglie un'altra. Cose da sapere:

- una scorciatoia registrata vince sul programma in primo piano: se `Ctrl+Alt+S` serve già in un
  programma che usate, cambiate lettera;
- sulle tastiere dove `AltGr` più una lettera scrive un carattere (`AltGr` equivale a `Ctrl+Alt`),
  evitate quella lettera;
- la sostituzione sul posto preme `Ctrl+C` e `Ctrl+V` per conto dell'utente: per questo **non
  lavora nelle finestre del terminale**, dove `Ctrl+C` interrompe il programma in corso (lì si
  copia e si usa `Ctrl+Alt+M`). Nel terminale dentro un editor non può accorgersene: selezionare
  sempre prima il testo;
- negli appunti, dopo, resta il testo mascherato; il testo originale passa dagli appunti per un
  istante, e chi tiene la cronologia degli appunti di Windows lo ritrova lì;
- non lavora nelle finestre aperte come amministratore, se Omissis non lo è.

Nei file Office la formattazione resta e vengono trattati anche intestazioni, piè di pagina, note,
commenti, testo eliminato con le revisioni; autore, azienda e autori di revisioni e commenti vengono
tolti (e non tornano con il ripristino). PDF scansionati e immagini vengono letti con il
riconoscimento dei caratteri di Windows (`ocr.py`: gira in locale, serve l'italiano tra le
lingue di Windows); il testo letto può contenere errori (una I scambiata per 1) e va riletto.
Limiti: le immagini inserite dentro i documenti non sono coperte (nelle cartelle i file non coperti
vengono saltati, non copiati); da PDF e immagini esce un file di testo; nei
fogli Excel ogni cella è valutata da sola, senza l'intestazione della colonna, quindi il modello
può sbagliare di più; i nomi dei file e dei fogli restano come sono.

## Cosa sostituire: i gruppi che si possono spegnere

Di serie viene sostituito tutto ciò che il modello considera un identificativo, e per quasi tutti è
la scelta giusta: non c'è nessun profilo da scegliere. Chi però fa lavorare l'AI proprio su certi
dati può spegnerne il gruppo in Impostazioni → Riconoscimento → Cosa sostituire:

| Gruppo | Che cosa contiene | Si può spegnere |
|---|---|---|
| Persone, contatti e documenti d'identità | nomi, e-mail, telefoni, indirizzi, CAP, città, data di nascita, codice fiscale, documenti | no |
| Password, chiavi e altri segreti | password, token, chiavi, stringhe di connessione | no |
| Conti e pagamenti | IBAN, carte, partita IVA | sì |
| Aziende e organizzazioni | nomi di aziende, studi, clienti; caselle generiche (info@, amministrazione@…) | sì |
| Dati informatici | indirizzi IP e MAC, nomi di PC e server, domini, indirizzi web, account, identificativi cloud e di dispositivo | sì |
| Pratiche, utenze e veicoli | polizze, protocolli, matricole, dati catastali, codici di fornitura, targhe, telai | sì |

Esempi: un tecnico che chiede all'AI di ragionare su una rete spegne i dati informatici e tiene
tutto il resto; uno studio che vuole leggere i numeri di pratica nelle risposte spegne l'ultimo
gruppo. Spegnere **riduce la protezione**: quei dati partono in chiaro da ogni strada (browser, app,
terminale, documenti, MCP). Per questo il pannello chiede conferma e la pagina iniziale lo ricorda
ogni volta, con il collegamento per cambiare idea. Ciò che si è scelto a mano resta sostituito
comunque: i termini della lista «sostituisci sempre» e le correzioni fatte nella sezione Testo
vincono sui gruppi spenti. L'impostazione è `groups_off` in `settings.json`; l'effetto è immediato.

**Le caselle di posta.** Un indirizzo con il nome di una persona (`mario.rossi@…`) è sempre
sostituito. Una casella generica di un'organizzazione (`info@`, `amministrazione@`,
`ufficio.acquisti@`…) è un dato dell'azienda e segue il suo gruppo: sostituita finché «Aziende e
organizzazioni» è acceso, perché il dominio dice chi è l'azienda; in chiaro quando lo si spegne.
Fa eccezione la casella generica presso un servizio di posta per privati (`info@gmail.com`): lì
dietro c'è quasi sempre una persona o una ditta individuale, quindi resta protetta. Il criterio è
il nome prima della chiocciola: un elenco di parole d'ufficio in italiano e in inglese, in
`settings.py`.

## Categorie in più

Dalla versione 2 il modello riconosce, oltre agli identificativi diretti (nomi, contatti, codici,
dati informatici), altre 13 categorie in due gruppi:

- **dati particolari**, quelli che il GDPR tratta come più delicati: salute, religione, opinioni
  politiche e sindacali, orientamento sessuale, origine e nazionalità;
- **dettagli che aiutano a riconoscere una persona**: date, orari, età, genere, titoli,
  professione, titolo di studio, luoghi (paese, regione, provincia).

Di serie **restano in chiaro**: spesso sono proprio il contenuto su cui l'AI deve lavorare («il
paziente ha il diabete», «la riunione è il 3 marzo»), e una volta tolto chi è la persona non sono
più riferibili a nessuno. Chi ha bisogno della protezione più stretta le accende, un gruppo per
volta, in Impostazioni → Riconoscimento → Categorie in più; l'effetto è immediato e vale per tutti
i collegamenti. Tecnicamente: le categorie spente sono elencate in `omissis.json` accanto ai pesi
del modello, quelle accese stanno nell'impostazione `categories`, e la probabilità che il modello
assegna a una categoria spenta viene contata come «non sensibile», così spegnerle non cambia le
decisioni sulle altre. Con un modello della versione 1 la scheda non compare.

## Archivio

`data\vault.sqlite` tiene la corrispondenza tra ogni valore e il suo segnaposto, cifrata con la
protezione dei dati di Windows legata all'utente. La sezione Archivio serve a tenerlo in ordine:

- **cercare** un segnaposto o un valore vero: la ricerca guarda i valori anche quando restano
  nascosti (si vede `G•••••••••••`), così si controlla se un nome è in archivio senza mostrarli tutti;
- filtrare per tipo, ordinare per data di creazione o di **ultimo uso** (aggiornato ogni volta che
  il valore ricompare in un testo o viene ripristinato);
- **eliminare** le voci scelte, oppure tutte quelle non usate da 30, 90, 180 o 365 giorni (anche
  di un solo tipo): prima dice quante sono e chiede conferma;
- **pulizia automatica**: ogni giorno toglie da sola le voci non usate da più del tempo scelto
  (spenta finché non la si accende);
- svuotare tutto.

Ciò che si elimina non si può più ripristinare nei testi e nei documenti vecchi. **Un numero non
viene mai riusato**, nemmeno dopo aver svuotato l'archivio: `[PERSONA_7]`, una volta eliminato,
non indicherà mai un'altra persona, quindi un documento vecchio non può essere «ripristinato» con
il valore sbagliato.

## Inventario degli strumenti AI (Shadow AI)

`scan.py` fotografa il PC: programmi e app installati, estensioni del browser e dell'editor di
codice, comandi da terminale, modelli in locale, programmi AI aperti, servizi AI contattati di
recente. `inventory.py` salva ogni fotografia in `data\inventory.sqlite` e la confronta con la
precedente. In Servizi AI → Rilevati si vede:

- quando è stata fatta l'ultima analisi e quando sarà la prossima: si ripete da sola **ogni
  settimana** (oppure ogni giorno, oppure mai); «Analizza ora» ne fa una subito;
- le **novità**: cosa è comparso e cosa non c'è più. Se un'analisi automatica trova strumenti
  nuovi compare una notifica di Windows;
- l'inventario: per ogni voce da quando c'è, l'ultima volta che è stata vista, la scelta fatta
  nelle Regole per il servizio a cui appartiene, se un'estensione legge tutti i siti;
- un **giudizio** per ogni voce (da valutare, approvato, da rimuovere) e una nota: restano anche
  quando la voce sparisce;
- l'esportazione in CSV (si apre con Excel) e «Dimentica ciò che non c'è più».

La prima analisi fa da punto di partenza: non segnala nulla come nuovo. Ciò che va e viene da solo
(un programma aperto o chiuso, un sito contattato) viene annotato quando compare, ma non quando
sparisce. Nel file ci sono nomi di programmi ed estensioni, versioni e date: nessun contenuto e
nessuna cronologia di navigazione. Tutto resta sul PC: non esiste (ancora) una raccolta centrale
per chi gestisce molti PC, e l'esportazione serve anche a quello.

## Estensione del browser (Chrome ed Edge)

È la strada automatica per chi usa i servizi dal sito, con il proprio abbonamento: niente proxy,
niente certificato. L'estensione lavora dentro la pagina, prima che il messaggio venga cifrato:
manda il testo al programma su questo PC (solo `127.0.0.1`), fa partire la versione con i
segnaposto e riscrive la risposta mentre arriva. Chi scrive vede sempre i valori veri.

Installazione di prova: `chrome://extensions` → Modalità sviluppatore → Carica estensione non
pacchettizzata → cartella `extension`. Poi nel pannello, aperto in quel browser, sezione Browser →
Collega questo browser. Finché non è collegata, o se la protezione è ferma, sui servizi protetti i
messaggi **non partono** (compare un avviso rosso nella pagina); dalla finestrella dell'icona si
può sospendere la protezione in quel browser, tranne che sui servizi la cui regola è imposta da chi
amministra il PC (vedi «Nelle organizzazioni»): lì la sospensione non vale, e la finestrella lo dice.

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
del proxy). `build_extension.py` riscrive `manifest.json` dal catalogo e `build.json` con l'impronta
dei file: va rilanciato quando cambia `catalog.py` e ogni volta che si tocca un file dell'estensione
(`build_extension.py --check` dice se è stato dimenticato).

**Quando il programma si aggiorna.** Un'estensione caricata da una cartella resta, nel browser, quella
letta al momento del caricamento: se il programma si aggiorna e nella cartella i file cambiano,
continuerebbe a girare il codice di prima. Per questo l'estensione rilegge `build.json` dal disco (al
massimo ogni minuto) e, se l'impronta non è più la sua, si ricarica da sola; lo stesso fa la
finestrella dell'icona quando il servizio in background non la capisce. Dopo una ricarica le pagine
già aperte chiedono di essere ricaricate, e fino ad allora i messaggi non partono. Installata da uno
store, i file cambiano solo insieme all'estensione e non succede nulla.

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
  sostituiscono solo i dati personali, non nomi di strumenti, identificativi e percorsi. Fanno parte
  del contesto tecnico anche i messaggi con ruolo `system` messi a metà conversazione (Claude Code ne
  manda uno da 12.000 caratteri con l'ambiente e l'elenco degli strumenti), e lì non si toccano le
  parole del mestiere (`agents.KNOWN`: Claude, Anthropic, GitHub, Tool…), che il rilevatore prendeva
  per persone e aziende. Misurato il 14/11/2026 su una richiesta vera di Claude Code 2.1.325: su
  23.700 caratteri di contesto le sostituzioni scendono da circa 75 a 5 (il nome utente dentro un
  percorso, l'indirizzo email dell'account e tre falsi positivi), e i dati del messaggio restano
  tutti sostituiti. Nel testo scritto dall'utente l'elenco non vale: un signor Claude resta una persona;
- una richiesta compressa (`Content-Encoding`: gzip, deflate; zstd e brotli se i moduli ci sono)
  viene aperta prima di essere controllata e inoltrata non compressa. Se non si riesce ad aprirla
  **non parte** (415): letta così com'è sarebbe sembrata «senza testo» e sarebbe uscita in chiaro.

Su questo PC Codex da terminale e OpenCode usano l'accesso con l'account ChatGPT: parlano con
`chatgpt.com/backend-api/codex` e non con `api.openai.com`, quindi **non passano dal gateway e non
sono coperti**. Codex 0.164 ha un'impostazione per cambiare indirizzo (`openai_base_url`) e comprime
le richieste con zstd: la strada c'è, ma va provata dal vivo con l'account prima di dichiararla.

Verificato: `e2e_gateway.py` (33 controlli contro un servizio finto) e **due prove dal vivo con
Claude Code** e accesso in abbonamento, con dati inventati. Nella prima un messaggio semplice: 0
valori in chiaro verso il servizio, risposta tornata con i valori veri. Nella seconda un'azione:
Claude Code ha scritto un file, sul disco ci sono i valori veri e il servizio ha visto solo
segnaposto anche nella richiesta successiva, dove l'azione fatta torna nella cronologia. Non ancora
provato con una sessione di lavoro lunga (molti comandi e file): lì il rischio non è la fuga di dati
ma un contesto molto mascherato, che può confondere il modello. I nomi degli strumenti dichiarati
nella richiesta non vengono mai sostituiti. Il formato OpenAI è provato solo con il servizio finto.

**Codex con l'accesso di ChatGPT (abbonamento).** Chi usa Codex con l'abbonamento non ha una
chiave: Codex manda il proprio accesso a un indirizzo di ChatGPT diverso da quello delle chiavi. Il
gateway lo riconosce da sé (dall'intestazione dell'account, o dal gettone stesso) e inoltra lì,
con lo stesso formato; le regole applicate sono quelle del servizio ChatGPT. Per farlo passare dal
gateway si aggiunge un fornitore alla configurazione di Codex (`config.toml` nella cartella
`.codex`), le righe esatte sono nella sezione Terminale del pannello:

```
model_provider = "omissis"            # in cima al file, prima di ogni sezione

[model_providers.omissis]             # in fondo al file
name = "Omissis"
base_url = "http://127.0.0.1:8767/openai/v1"
wire_api = "responses"
requires_openai_auth = true
```

Vengono sostituiti i messaggi, le modifiche ai file già fatte, i comandi già eseguiti e i loro
risultati, il riassunto del ragionamento; il ragionamento cifrato viaggia identico. Le richieste
compresse (Codex le manda in zstd) vengono aperte e controllate; un collegamento WebSocket, che
non si saprebbe leggere, viene rifiutato e lo strumento ripiega sulle richieste normali.
**Provato solo con un servizio finto**: dal vivo con Codex non ancora, e la configurazione di
Codex è condivisa con l'app di ChatGPT, quindi va cambiata quando l'app non sta lavorando.

**Chi ha già un proprio gateway** (aziendale, LiteLLM, OpenRouter…) lo tiene: nella sezione
Terminale si scrive il suo indirizzo al posto dell'API di Anthropic o di OpenAI, e Omissis gli sta
davanti: sostituisce i dati e inoltra lì invece che al servizio vero (per gli altri nomi:
`gateway_upstreams` in `settings.json`). Le credenziali passano così come sono, quindi vanno a
quell'indirizzo: è una scelta di chi lo scrive. Fa eccezione l'accesso in abbonamento di Codex, che
va sempre e solo a ChatGPT. Provato solo con un servizio finto.

## Server MCP: i documenti, dentro le app (sperimentale)

MCP è il modo ufficiale con cui Claude Desktop, Claude Code, Codex, ChatGPT (modalità sviluppatore),
Cursor, Windsurf, Antigravity e VS Code ricevono strumenti in più. `mcp_server.py` è uno di questi
strumenti: l'app si continua a usare come sempre, **con il proprio abbonamento**, senza chiavi, senza
porte di collegamento e senza riavvii speciali. È la strada che funziona anche dove il connettore non
arriva (gli editor) o viene rifiutato.

Che cosa cambia: quando si chiede all'assistente di lavorare su un documento indicandone il percorso,
l'assistente lo fa leggere a Omissis. Il file viene aperto sul PC, i dati sostituiti, e
all'assistente arriva solo il testo con i segnaposto. Gli strumenti sono cinque:

| Strumento | Che cosa fa | Che cosa torna all'assistente |
|---|---|---|
| `read_anonymized` | legge un documento (Word, Excel, PowerPoint, PDF anche scansionato, immagini con testo, file di testo) | il testo con i segnaposto, a pezzi se è lungo |
| `anonymize_copy` | scrive accanto all'originale una copia anonimizzata, nello stesso formato, di un file o di una cartella intera | dove sta la copia, e i conteggi |
| `restore_text` | rimette i valori veri in un testo scritto dall'assistente (una mail, una risposta) e lo lascia negli appunti, oppure in un file nuovo | solo quanti segnaposto ha ripristinato |
| `restore_copy` | scrive una copia con i valori veri di un file o di una cartella con i segnaposto | solo dove sta la copia |
| `omissis_status` | dice se Omissis è acceso e quali cartelle può usare | lo stato |

Tre garanzie tenute dal codice e provate: **nessuno strumento restituisce un valore vero** (il
ripristino scrive sul PC e risponde solo «fatto»); il server legge e scrive **solo nelle cartelle
permesse** (Documenti, Desktop e Download, più quelle aggiunte nel pannello; mai la cartella dei dati
di Omissis); **con Omissis spento non esce nulla**, errore e non testo in chiaro.

**Come si collega.** Pannello → Collegamenti → MCP: per Claude Desktop c'è un pulsante che aggiunge
Omissis alla sua configurazione senza toccare il resto (prima ne tiene una copia; poi Claude Desktop
va chiuso del tutto e riaperto); per le altre app ci sono i testi pronti da copiare. Da riga di
comando: `python mcp_server.py --config` li stampa, `--install claude-desktop` e `--uninstall
claude-desktop` fanno ciò che fa il pulsante.

**Che cosa NON fa**, ed è il limite di questa strada per chiunque la usi:

- non vede ciò che si scrive nella chat né i file allegati a mano: quelli partono così come sono, a
  meno che l'app sia protetta anche dal connettore o dall'estensione. Il server MCP protegge i
  documenti, non la conversazione;
- funziona se l'assistente sceglie di usarlo. Le istruzioni che il server gli consegna glielo
  chiedono, e nella prova dal vivo l'ha fatto da solo; ma un assistente che ha anche strumenti propri
  per leggere i file può aprire l'originale. Per sicurezza: chiedere «usa Omissis», oppure fargli
  lavorare una copia anonimizzata;
- in un foglio Excel letto con `read_anonymized` anche i numeri passano dal riconoscimento (un
  telefono scritto come numero viene sostituito); nella copia fatta con `anonymize_copy` restano i
  limiti dei documenti descritti più sopra (numeri nelle celle numeriche, nomi dei fogli).

Verificato: `e2e_mcp.py` (27 controlli: il protocollo, i cinque strumenti su tutti i formati, i
limiti delle cartelle, il motore spento, la registrazione in Claude Desktop su un file di prova) e
**una prova dal vivo con Claude Code** (14/11/2026, accesso in abbonamento, un verbale Word
inventato): l'assistente ha usato da solo `read_anonymized`, ha visto solo segnaposto, ha scritto la
risposta e l'ha fatta ripristinare negli appunti senza vedere i nomi. **Non ancora provato** dentro
Claude Desktop, ChatGPT, Cursor e le altre app: la registrazione in Claude Desktop è provata solo su
un file di prova.

## App desktop: Claude, ChatGPT, Kimi e Copilot per Windows (sperimentale)

Queste app sono, sotto, un browser Chromium con dentro il sito del servizio (Claude e Kimi: Electron;
ChatGPT/Codex di OpenAI: un Chromium 157 proprio; Microsoft Copilot: un Edge vero e proprio). Avviate
con la porta di debug, `connector.py` ci si collega e porta dentro la finestra **lo stesso codice
dell'estensione**: il testo viene sostituito prima di essere cifrato, quindi niente certificato,
niente proxy, e non conta se l'app controlla i certificati. Chi usa l'app tiene il proprio
abbonamento e tutte le funzioni dell'app.

Dal pannello: sezione App desktop → Avvia protetta (la protezione deve essere attiva). Da terminale:
`.venv\Scripts\python.exe connector.py --start claude` (oppure `chatgpt`, `kimi`, `copilot`).

| App | Come parte protetta | Verificata dal vivo |
|---|---|---|
| ChatGPT / Codex | stessa app, riavviata con la porta | sì, un messaggio con dati inventati (12/11/2026) |
| Claude | stessa app, riavviata con la porta | no |
| Kimi | **non si può**: avviata con la porta di collegamento si chiude da sola in un secondo (codice 1), anche con la porta 0 | provato il 14/11/2026 sulla 3.2.24; il pannello lo dice e non offre il pulsante |
| Microsoft Copilot | con un **profilo separato**, tenuto in `data\app_profiles\copilot` | solo l'aggancio: 5 finestre seguite, nessun errore, nessun messaggio inviato (14/11/2026) |
| Microsoft 365 Copilot, Copilot dentro Teams e Outlook | non coperte: sono WebView2, e il servizio non ha un formato che il programma sa leggere | — |
| Visual Studio (GitHub Copilot) | non coperta: è un programma nativo, le richieste partono da un suo processo e non da una finestra web. Il servizio si può solo registrare o bloccare | — |
| Editor derivati da VS Code (Antigravity, Cursor, Windsurf) | non coperti dal connettore: la chat parla con il servizio da un processo dell'editor, e la casella è un editor di codice che non si riscrive come una casella web | non installati sul PC di prova |
| Perplexity | da provare: non era installata sul PC di prova | — |

Se un'app rifiuta la porta quando la si riavvia (lo fa Kimi), il connettore se ne accorge in pochi
secondi, non aspetta i 40 del tempo massimo e dice che l'app ora è chiusa e va riaperta normalmente.
Per le app di cui lo si sa già (`"refuses": True` in `connector.APP`) non la chiude nemmeno.

**App già aperta.** Un'app aperta dal menu Start non ha la porta, e avviarla di nuovo porterebbe solo
in primo piano la finestra che c'è già, senza protezione. Il pannello se ne accorge (legge l'elenco
dei processi: per Claude distingue l'app dal Claude da terminale, che ha lo stesso nome) e al posto di
«Avvia protetta» mostra **«Chiudi e riapri protetta»**: chiede conferma, chiede alle finestre dell'app
di chiudersi, aspetta 8 secondi, ferma ciò che resta acceso vicino all'orologio e la riavvia con la
porta. Le conversazioni restano; ciò che non era stato inviato si perde. Senza quella conferma il
connettore non chiude nulla (`connector.AlreadyOpen`). In Inizio la casella «App desktop» diventa
gialla finché c'è un'app aperta senza protezione.

**Riaggancio.** Se Omissis si chiude o si aggiorna mentre un'app protetta è aperta, al riavvio la
ritrova dalla porta e si ricollega da solo (controllo ogni 10 secondi, solo a protezione attiva).
Dopo «Stacca», invece, l'app resta staccata finché non la si riavvia da qui.

**Profilo separato (Copilot).** Dalla versione 136 Chromium ignora la porta di debug sul profilo
predefinito (provato: con il profilo normale Copilot parte e la porta resta chiusa). Per questo la
Copilot protetta gira con un profilo suo: la prima volta va rifatto l'accesso, e la finestra normale
di Copilot — quella del menu Start o del tasto Copilot — **non è protetta**. Chiusa la finestra,
Copilot resta acceso in sottofondo senza porta: prima di ogni avvio il connettore ferma le copie
rimaste sul suo profilo, altrimenti la finestra nuova la aprirebbero loro, senza protezione.

**La politica del servizio conta.** Il connettore maschera solo verso i servizi impostati su
«Proteggi». Copilot parte su «Registra» (formato riconosciuto dal nome dei campi, da verificare):
finché resta così l'app si collega ma i messaggi non vengono toccati, e il pannello lo scrive sotto
il nome dell'app.

Le barriere sono due. Quella **dentro la pagina** sostituisce i dati e riscrive le risposte mentre
arrivano. Quella **a livello di rete** ferma ogni invio verso un servizio protetto prima che parta e
lo ricontrolla: serve perché una finestra appena aperta può mandare richieste prima che il codice al
suo interno sia attivo (provato: senza la seconda barriera quei messaggi uscivano in chiaro). Per
quelle richieste la risposta resta con i segnaposto finché la pagina non è pronta.

La barriera di rete è accesa **due volte**: su ogni finestra, e sul browser intero. La seconda è
arrivata dopo una prova fallita (14 novembre 2026). Una finestra che l'app crea già con il suo
indirizzo comincia a caricarsi subito, e la notizia che esiste arriva al connettore qualche
millisecondo dopo: con la barriera accesa solo finestra per finestra, una pagina veloce in quel tempo
aveva già mandato il suo primo messaggio (da 1 a 5 finestre su 20, a seconda dei tempi della
macchina; il giorno prima, sulla stessa macchina, zero). Accesa sul browser intero, la barriera
trattiene anche il caricamento della pagina finché il connettore non risponde, e a quel punto
l'aggancio è completo: 160 finestre su 160 partono mascherate. Se il browser di un'app non lo
permette il connettore lo annota (`notices`) e resta la barriera finestra per finestra, con quel
limite. Sull'app vera questa parte non è ancora stata provata.

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
  di prova: `e2e_connector.py`, 37 controlli;
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

## Nelle organizzazioni: impostazioni bloccate e console centrale

Due cose pensate per chi gestisce molti PC. Chi usa Omissis per conto proprio non le incontra mai.

**Impostazioni bloccate.** Chi amministra il PC può fissare alcune scelte scrivendole nella chiave di registro
`HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Omissis`, che un utente normale non può modificare (`managed.py`; lo
script `deploy\Set-OmissisPolicy.ps1` lo fa da un file JSON). Ogni valore ha il nome di un'impostazione, gli
stessi di `settings.json`. Ciò che sta lì vince sulle scelte dell'utente: nel pannello quei comandi restano
visibili ma fermi, e il programma rifiuta di cambiarli. `policies` blocca solo i servizi scritti; ogni altra
impostazione è bloccata per intero. Nel file dell'utente restano le sue scelte: tolto il blocco, tornano.
Sui servizi scritti in `policies` nemmeno l'estensione del browser si lascia sospendere. Resta fuori chi
toglie o spegne l'estensione dal browser: quello si impedisce solo con i criteri del browser.
Non c'è una password di amministratore: comanda chi ha i diritti di amministratore su quel PC. E non è una
difesa da chi manomette il programma, che è installato nel profilo dell'utente.

**Server di inferenza in rete.** Di serie ogni PC carica il suo modello. Dove non tutti lo reggono (poca
memoria, PC vecchi, terminali) un PC con Omissis può **prestare il suo modello** agli altri: Impostazioni →
Riconoscimento → «Server di inferenza in rete» (`remote.py`). Il PC che presta apre una seconda porta (8770) in
HTTPS, con un certificato che si fa da sé e una chiave; la pagina dà la **configurazione** da incollare negli
altri PC (`engine_url`, `engine_key`, `engine_pin`), che così partono senza caricare né scaricare il modello.

- In rete viaggia, cifrato, il testo da controllare, e tornano **solo le posizioni** dei dati trovati dal
  modello. Regole, elenchi personali, segnaposto e archivio con i valori veri restano sul PC che ha chiesto.
- Il server non scrive i testi e non li mette nel registro: tiene, finché è acceso, il conto di quali PC hanno
  chiesto e quanti testi.
- Il PC parla solo con il server che presenta il certificato atteso (l'impronta) e il server risponde solo a
  chi ha la chiave; chi prova chiavi a caso viene lasciato fuori per un minuto.
- Le categorie in più accese su un PC valgono per le richieste di quel PC, non per il server né per gli altri.
- **Se il server non risponde, sul PC non viene mascherato nulla e quindi non parte nulla**: la pagina iniziale
  lo dice. Non c'è ripiego sul modello locale, che su quel PC può non esserci: un portatile fuori dall'ufficio
  resta fermo finché non torna in rete o non torna al suo modello.
- Chi amministra i PC può imporre le tre impostazioni con `Set-OmissisPolicy.ps1`, come le altre.
- Sul PC che presta, la prima volta Windows chiede se consentire l'accesso alla rete: senza quel consenso (o una
  regola del firewall per la porta 8770) gli altri PC non lo raggiungono.

Non provato: due PC veri in rete (qui server e PC erano due copie sullo stesso computer, attraverso
`127.0.0.1`), il firewall di Windows, più PC insieme.

**Console centrale.** Di serie Omissis non manda nulla a nessuno. Se nelle impostazioni ci sono `console_url`
(un indirizzo `https://`) e `console_key` (la chiave di collegamento), il programma manda a quell'indirizzo,
una volta all'ora, un riepilogo (`central.py`):

- versione, canale e stato del programma, modello in uso, gruppi di dati spenti, impostazioni bloccate;
- per ciascuno degli ultimi 35 giorni: quante richieste avevano dati da sostituire, quanti valori per tipo di
  dato, verso quali servizi, quante richieste sono state fermate;
- nomi e versioni degli strumenti AI trovati dall'inventario;
- il nome del computer e dell'utente, a meno che `console_names` sia spento, e un identificativo a caso
  dell'installazione.

Mai i testi, mai i valori sostituiti, mai l'archivio: il riepilogo viene dal registro delle attività, che
contiene già solo conteggi. Nel registro entra anche l'uso manuale (la sezione Testo, gli appunti e le
scorciatoie, i documenti anonimizzati dal pannello), sotto la voce «Uso manuale»: un testo corretto a mano più
volte conta una volta sola, un documento una volta. In Impostazioni > Console centrale (vista avanzata, o sempre se il PC è collegato)
si vede a chi è collegato il PC, quando è partito l'ultimo riepilogo, e «Vedi che cosa parte» lo mostra per
intero. La chiave di collegamento viaggia solo verso l'indirizzo scelto: un rinvio altrove non viene seguito, e
un indirizzo non `https` fuori da questo PC viene rifiutato. Di serie il certificato della console deve essere
valido come per un browser. Per una console in rete locale, che si fa il certificato da sé, c'è `console_pin`:
l'impronta SHA-256 di quel certificato. Con l'impronta il programma si collega, senza passare da un proxy, solo
al server che presenta proprio quel certificato, e lo controlla appena finita la stretta di mano, prima che parta
la richiesta con la chiave. La console che riceve i riepiloghi è un prodotto a
parte e non sta in questo repository; il protocollo è una `POST` a `<console_url>/api/v1/report`.

**Regole dalla console.** La console risponde a ogni riepilogo con le regole che vorrebbe imporre ai PC di
quell'organizzazione. Di serie il PC **le ignora e non le conserva**. Le applica solo se si accende `console_rules`
(Impostazioni > Console centrale > «Accetta le regole da questa console», oppure imposto da chi amministra il PC):
da quel momento valgono come le impostazioni bloccate, il pannello dice quante sono e quando sono arrivate, e
nell'elenco dei vincoli risulta che vengono dalla console (`settings.from_console`). Tre limiti, scritti nel codice:

- la console può imporre **solo** le regole per servizio (`policies`), `block_files`, `attachments`, `box`,
  `updates`, `scan` e `groups_off` (`settings.CONSOLE_RULES`). Non può toccare gli indirizzi a cui il PC manda
  qualcosa (console, server di inferenza, gateway), le cartelle, il nome nel riepilogo, né questa stessa scelta:
  chi entrasse in una console senza diritto potrebbe allentare le regole, non farsi mandare i dati;
- dove console e amministratore del PC dicono cose diverse **vince l'amministratore del PC** (il registro di
  Windows), che può anche vietare le regole della console imponendo `console_rules` spento;
- le regole valgono solo finché il PC è collegato alla console che le ha mandate: scollegato, o collegato a
  un'altra, non restano in vigore.

Il riepilogo successivo dice alla console se il PC accetta le regole e quale versione ha applicato. Provato con
la console vera sullo stesso computer (`e2e_central.py` e le prove della console); non ancora tra due macchine.

Conteggi per singola persona possono essere un controllo a distanza dei lavoratori: un'organizzazione che
collega i PC con i nomi deve prima sentire chi si occupa di privacy e, dove serve, informare i dipendenti.

## Quanto è verificato

| Servizio | Stato |
|---|---|
| Claude, ChatGPT, API Anthropic, API OpenAI | formato noto, provato con un servizio finto; **non ancora con gli account veri** |
| API compatibili con OpenAI (DeepSeek, Mistral, Groq, OpenRouter…) | stesso formato dell'API OpenAI |
| Gemini | **sperimentale**: formato scritto a memoria, provato solo su un'imitazione |
| Copilot, Perplexity, Kimi, Grok, Le Chat e gli altri "generici" | riconoscimento dei campi dal nome: **da verificare uno per uno** |
| Tutti gli altri del catalogo | il proxy non li legge: si possono solo registrare o bloccare |
| Gateway per gli strumenti da terminale | servizio finto (`e2e_gateway.py`, 33 controlli; Codex in abbonamento e gateway proprio solo qui) e **Claude Code dal vivo** con un messaggio di dati inventati (rifatto il 14/11/2026 dopo la rinomina del codice) |
| Server MCP (documenti dentro le app) | `e2e_mcp.py` (27 controlli) e **Claude Code dal vivo** con un verbale inventato; non ancora dentro Claude Desktop e le altre app |
| Connettore per le app desktop | app di prova (`e2e_connector.py`, 37 controlli) e **app vera di ChatGPT**: un messaggio di dati inventati è arrivato al servizio con i soli segnaposto (barriera sulla casella di scrittura) |
| Estensione del browser | stessi formati, provati in un browser vero contro il servizio finto (`e2e_extension.py`, 39 controlli); pagine vere solo aperte, senza accedere |

Per questo, all'inizio, sono impostati su "proteggi" solo i primi quattro: gli altri si attivano
da Servizi AI dopo averli provati con dati inventati.

## Registro di compatibilità

I siti e le app cambiano senza avvisare: sapere che la protezione «funziona con ChatGPT» non basta,
serve sapere **con quale programma e quale versione** ha funzionato l'ultima volta. Il pannello lo
mostra in Collegamenti → Compatibilità, in due elenchi.

**Visto su questo PC.** Si compila da solo mentre si lavora. Ogni riga del registro delle attività
che dice qualcosa sulla protezione aggiorna una tabella (`compatibility`, in `data\contacts.sqlite`)
con: servizio, strada (estensione, app desktop, gateway, proxy), programma e versione, metodo
(casella di scrittura, rete, allegato, API) ed esito:

- `ok`: dei dati sono stati sostituiti prima dell'invio;
- `restoring`: dei valori sono stati rimessi nella risposta;
- `unread`: il servizio ha usato un formato che Omissis non ha riconosciuto.

Per ogni combinazione restano solo i conteggi e le date della prima e dell'ultima volta: **nessun
testo, nessun valore**. Il pannello riassume così: *funziona* se l'ultima cosa successa è una
sostituzione riuscita, *da ricontrollare* se dopo l'ultima riuscita un formato non è stato
riconosciuto (di solito vuol dire che il servizio o l'app si sono aggiornati) oppure se una
sostituzione non è mai riuscita. Il pulsante «Copia il riepilogo» mette l'elenco negli appunti,
per allegarlo a una segnalazione.

Da dove viene il nome del programma: l'estensione dichiara il browser e la sua versione
(`navigator.userAgentData`), il connettore legge la versione dell'app dalla sua porta di
collegamento, gateway e proxy la prendono dall'intestazione `User-Agent` della richiesta (per
esempio `claude-cli 2.1.0`). Tutto resta sul PC: la tabella non viene spedita da nessuna parte.

**Verificato dall'autore.** È il file `compatibility.json`, distribuito con il programma: le
combinazioni provate di persona, con la data e il livello della prova (`live` = servizio vero
con dati inventati, `fake_service` = prove automatiche contro il servizio simulato). Va
aggiornato a mano dopo ogni prova vera; una riga senza versione vuol dire che la versione non è
stata annotata.

Quando una riga passa a *da ricontrollare*: rilanciare le prove automatiche, guardare in Attività la
struttura della richiesta non riconosciuta e, finché non è sistemato, tenere accesa la casella di
scrittura (che non dipende dal formato interno del sito).

## Cosa guardare durante una prova

Nella sezione Attività (o in `data\activity.jsonl`):

- `masked` = tutto regolare;
- `no_text_field` = il servizio usa un formato che il proxy non conosce:
  la richiesta è partita **non mascherata**. La riga riporta la struttura (senza valori), che
  serve per adattarlo;
- `VALUES_IN_CLEAR` = un dato già mascherato compare in chiaro in un'altra richiesta;
- `file_not_masked` = è stato caricato un file.

## Requisiti

| | Minimo | Consigliato |
|---|---|---|
| Sistema | Windows 10 (versione 2004 o successiva) o Windows 11, a 64 bit su processore Intel o AMD | uguale |
| Processore | 4 core | 6 core o più, di generazione recente |
| Memoria | 8 GB, con il modello piccolo | 16 GB, necessari per il modello grande |
| Disco | 1 GB con il modello piccolo | 2 GB con il modello grande |
| Scheda video | non serve | non serve: la copia installata usa solo il processore |
| Rete | solo per scaricare il modello al primo avvio e per gli aggiornamenti | uguale |

Il programma tiene in memoria il modello finché la protezione è accesa: da 1,2 a 1,5 GB con
`omissis-small`, da 1,8 a 2,5 GB con `omissis-base`. La scheda video viene usata solo da chi lancia
il programma dai sorgenti con PyTorch (una NVIDIA con 2 GB liberi basta).

**Su un PC da ufficio conviene il modello piccolo.** La qualità misurata è quasi la stessa, la
velocità è doppia. Tempi del riconoscimento per lunghezza del testo, solo processore:

| Dove | Modello | 300 caratteri | 6.000 (due pagine) | 30.000 |
|---|---|---|---|---|
| PC veloce (i7-14700K, 20 core): misurato | small | 20 ms | 0,4 s | 2 s |
| | base | 39 ms | 0,9 s | 4 s |
| PC da ufficio a 4 core: **stima** | small | 0,12 s | 3 s | 15 s |
| | base | 0,22 s | 6 s | 29 s |
| PC di fascia bassa a 2 core: **stima** | small | 0,17 s | 5 s | 22 s |
| | base | 0,64 s | 16 s | 64 s |

Le due stime sono fatte il 14 novembre 2026 sullo stesso PC, lasciando al programma solo quattro o
due dei suoi core più lenti (`misure\pochi_core.py`): dicono l'ordine di grandezza, non sostituiscono
una misura su un portatile vero, che in più scalda e rallenta. In pratica: un messaggio normale passa
sempre in una frazione di secondo; a pesare sono i documenti lunghi, e lì su un PC modesto con il
modello grande si aspetta.

## Quanto pesa e quanto è veloce

Misurato il 14 novembre 2026 su un PC con Intel Core i7-14700K (20 core), 32 GB di memoria e una
RTX 4080 SUPER, con testi inventati in stile help desk (nomi, aziende, e-mail, telefoni, IBAN, nomi
di server, indirizzi IP). I tempi sono la mediana di una richiesta al motore, archivio compreso.

| Modello e motore | 300 caratteri | 6.000 (due pagine) | 30.000 | 120.000 | Memoria del motore |
|---|---|---|---|---|---|
| `omissis-base`, scheda video | 42 ms | 61 ms | 0,2 s | 1,1 s | 1,4 GB, più 1,7 GB sulla scheda |
| `omissis-small`, scheda video | 40 ms | 53 ms | 0,2 s | 0,9 s | 1,4 GB, più 0,9 GB sulla scheda |
| `omissis-base`, solo processore (copia installata) | 59 ms | 0,8 s | 3,7 s | 15 s | 1,8 GB, fino a 2,0 dopo testi lunghi |
| `omissis-small`, solo processore (copia installata) | 44 ms | 0,4 s | 1,7 s | 7 s | 1,2 GB, fino a 1,3 dopo testi lunghi |

- **A riposo** il programma non consuma processore (meno dello 0,5 % di un core) e, oltre al motore,
  occupa circa 120 MB (pannello e proxy). Il motore è pronto in circa 5 secondi dall'avvio.
- **Un messaggio normale** (qualche riga) costa da 40 a 70 ms: non si nota. Su un PC senza scheda
  video si nota invece un documento lungo: circa 8.000 caratteri al secondo con `omissis-base`,
  16.000 con `omissis-small`. Per chi lavora spesso su testi lunghi senza scheda video conviene il
  modello piccolo.
- **Gateway per gli strumenti da terminale**: a un messaggio corto aggiunge da 30 a 70 ms. La prima
  richiesta vera di Claude Code (101 KB, quasi tutta contesto) passa in 0,2 s con la scheda video,
  in 1,2 s (`small`) o 2,6 s (`base`) sul solo processore; i turni successivi in circa un decimo di
  secondo, perché il testo già visto non viene riesaminato.
- **Più richieste insieme** (8 per volta, messaggi da 300 caratteri): 56 al secondo con la scheda
  video, 25 (`base`) o 41 (`small`) sul solo processore, senza errori. Il motore esamina un testo
  per volta: sul solo processore un messaggio corto arrivato mentre gira un testo di 30.000
  caratteri aspetta che finisca (fino a 4 secondi con `omissis-base`).
- **Il modello per il solo processore è stato snellito** (`export_onnx.py`, funzione `snellisci`):
  l'esportazione lasciava in ogni strato dei controlli sulla maschera di attenzione che prendevano
  più del 40 % del tempo. Tolti quelli, va circa il doppio più veloce e dà le stesse identiche
  uscite: nessun token cambia classe su 57.000 di controllo, e 405 testi su 405 restano identici
  al motore PyTorch. La variante con i pesi a 8 bit è stata provata e scartata: fino a 1,8 volte
  più veloce ancora, ma dallo 0,3 allo 0,7 % dei token cambia classe e il risultato dipende dal
  processore.
- **Archivio**: 5.700 voci occupano 3,2 MB e non rallentano nulla.
- **Tenuta sui testi lunghi**: nei testi di queste misure sono stati messi circa 30.000 dati
  inventati, in testi da 60 a 120.000 caratteri; nessuno è rimasto in chiaro, con nessuno dei due
  modelli e dei due motori. È un controllo che il programma non perda nulla quando un testo è lungo
  e viene esaminato a pezzi, non una misura della qualità del modello: i testi sono costruiti con
  poche frasi fisse. I numeri sulla qualità sono nella scheda del modello.

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
Una copia lanciata dai sorgenti continua a tenere i dati in `data`, accanto al codice.

**Il modello** non sta nell'installer. Al primo avvio il programma scarica i pesi dalla pagina
pubblica del modello (di serie `omissis-small`, 537 MB; chi sceglie `omissis-base` nelle
Impostazioni ne scarica 1,2 GB) e mostra l'avanzamento
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
aggiornamento dalla pagina vera delle versioni.
Senza firma del codice, Windows mostra l'avviso di SmartScreen al primo avvio dell'installer.

**La versione per il Microsoft Store.** È lo stesso programma in un pacchetto firmato dallo Store,
quindi senza avviso di SmartScreen. Dentro quel tipo di pacchetto Windows tiene separato ciò che il
programma scrive, e questo cambia quattro cose:

- i dati (archivio, impostazioni, modello) stanno nella cartella privata del pacchetto e vengono
  tolti con la disinstallazione;
- gli aggiornamenti li fa lo Store, e l'avvio insieme a Windows si spegne da Gestione attività;
- il **certificato del proxy non si può installare** per gli altri programmi: il proxy richiede la
  versione scaricata dal sito. Estensione, app desktop, terminale e MCP non ne hanno bisogno;
- il server MCP viene registrato con un nome fisso che Windows assegna al pacchetto
  (`omissis-python.exe -m mcp_server`); se Claude Desktop è installato fuori dallo Store le righe
  vanno incollate a mano, e la cartella dell'estensione da indicare al browser è una copia tenuta
  tra i Documenti.

Stato al 14 novembre 2026: la cartella del pacchetto e il suo manifesto esistono
(`costruisci_store.py`) e il programma, lanciato da lì con i comandi del manifesto, supera 9
controlli (`prova_store.py`). Lo strumento di Microsoft (`makeappx`) convalida il manifesto e chiude
il file `.msix` (82 MB) con l'identità assegnata dal Partner Center. Registrato su questo PC e
avviato dal menu Start supera altri 11 controlli (`prova_store_registrato.py`): la protezione si
accende con il motore del pacchetto, i dati finiscono nella cartella privata, il server MCP parte
dal nome fisso e parla con quel motore, l'avvio insieme a Windows risulta registrato; tolta la
registrazione non resta nulla. **Non ancora fatto**: l'invio, e la prova di una copia scaricata
davvero dallo Store. I passi sono in `pubblicazione\store\microsoft_it.md`.

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
`e2e_vault.py` (21 controlli) prova l'archivio cifrato, la ricerca, le eliminazioni e i numeri
mai riusati; `e2e_inventory.py` (14 controlli) l'inventario degli strumenti AI con analisi
inventate. Nessuno dei due ha bisogno di qualcosa acceso. Lo stesso vale per `e2e_central.py`
(40 controlli): le regole mandate dalla console (accettate solo per scelta, solo quelle ammesse, mai sopra
l'amministratore del PC), le impostazioni imposte dall'amministratore (da un file di prova e da una chiave di prova del
registro dell'utente, mai da quelle di sistema) e il riepilogo per la console centrale, mandato a un servizio
finto: che cosa contiene, chiave rifiutata, rinvio non seguito, console spenta, e una console con un certificato
fatto da sé, accettata solo con l'impronta giusta.
`e2e_remote.py` (15 controlli, serve la copia di prova accesa) prova il server di inferenza in rete: le fa prestare
il modello e lancia un secondo motore senza modello, con dati suoi, che glielo chiede in HTTPS. Controlla che dal PC
escano solo segnaposto, che regole, elenchi e archivio restino sul PC, che il server non scriva nulla, che chiave e
impronta sbagliate vengano rifiutate, che a server spento non parta nulla, e la scheda nella pagina nelle due lingue.
`e2e_desktop.py` (17 controlli, serve la protezione attiva) prova ciò che tocca il desktop:
scorciatoie registrate, cambiate e dichiarate occupate; il testo selezionato sostituito sul posto
in una finestrella che apre lui (i tasti partono solo se quella finestra è in primo piano,
altrimenti il controllo viene saltato e detto); la finestra di Windows per scegliere la cartella.
`e2e_panel.py` (66 controlli, serve la protezione attiva e una copia di prova: `OMISSIS_DATA`, e
`OMISSIS_LISTS` per provare anche gli elenchi, `OMISSIS_MANAGED_FILE` per le impostazioni imposte) apre ogni sezione del pannello in italiano e in
inglese: nessun errore, nessuna frase senza traduzione, nomi di pulsanti e campi, uso dalla
tastiera, il giro completo di un testo e di un documento con dati inventati, le correzioni a mano,
una cartella intera, ricerca ed eliminazione nell'archivio, l'inventario con analisi inventate e
poi quella vera del PC, le scorciatoie; e scatta le schermate che vanno nei documenti e nel sito. `check_languages.py` confronta i file delle lingue
tra loro e con il codice.
`e2e_install.py` (22 controlli, nulla acceso) prova lo scaricamento del modello e gli
aggiornamenti contro un servizio finto: ripresa, file manomessi, firma di un'altra chiave, foglio
ritoccato, versione più vecchia, installer sostituito sul disco.
`e2e_connector.py` prova il connettore per le app desktop sullo stesso browser di prova, avviato
con la porta di debug e senza estensione. `e2e_gateway.py` prova il gateway con un suo servizio
finto e ha bisogno solo del motore acceso. `e2e_mcp.py` (27 controlli) fa da app al server MCP:
lo lancia e gli parla come vuole il protocollo, su documenti inventati in una cartella provvisoria.

Per provare senza fermare il programma in uso: `set OMISSIS_PORT=8775` prima di avviare una
seconda copia (motore, pannello e gateway prendono le porte 8775, 8776 e 8777; la porta del proxy
si cambia nelle impostazioni di quella copia).
