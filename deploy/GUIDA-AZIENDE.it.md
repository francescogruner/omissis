# Omissis in azienda: guida pratica

Per chi deve mettere Omissis su più PC di un ufficio o dei propri clienti. Dice che cosa è gratuito e che cosa no,
quale schema scegliere, come distribuirlo e come accendere il server di inferenza. I dettagli di ogni script sono
in [`README.it.md`](README.it.md); quelli del programma in [`../app/README.it.md`](../app/README.it.md).

English: [`GUIDE-ORGANISATIONS.md`](GUIDE-ORGANISATIONS.md).

## 1. Che cosa è gratuito e che cosa no

Tutto ciò che gira sui PC è gratuito e aperto (licenza Apache 2.0), anche per uso commerciale e senza limiti di PC.

| | Gratuito, in questo repository | A pagamento |
|---|---|---|
| Programma per Windows ed estensione del browser | sì | |
| Script per installarlo su molti PC, in silenzio e già configurato | sì | |
| Impostazioni bloccate dall'amministratore | sì | |
| Server di inferenza in rete (un PC presta il modello agli altri) | sì | |
| Stato di ogni PC letto dal tuo RMM (`Get-OmissisStatus.ps1`) | sì | |
| **Console centrale**: tutti i PC in una pagina sola, fino a 5 PC di un'azienda | sì, ma non aperta | |
| Console centrale oltre i 5 PC, o per più aziende (MSP) | | sì, con una licenza |

**Che cosa aggiunge la console.** Quanti PC hanno Omissis e quali vanno controllati (protezione spenta, PC che non
si fanno sentire, versioni vecchie), quanti dati sono stati tenuti fuori dai servizi AI in totale, per giorno, per
tipo di dato e per servizio, e gli strumenti AI trovati sui PC. Per un MSP: più aziende separate, con un accesso
in sola lettura per ciascuna azienda. Riceve solo conteggi e nomi di programmi, mai i testi.

**Come si prova e come si passa alla licenza.** Non si installa un'altra versione di Omissis e nei PC non va messo
nessun codice di licenza: il programma dei PC resta quello gratuito. La console è un programma a parte, compilato
(il suo codice non è in questo repository): la guida è in [`../console/README.it.md`](../console/README.it.md).

1. Si scarica `omissis-console-<versione>.zip` dalla
   [pagina delle versioni](https://github.com/francescogruner/omissis/releases/latest) e si installa su un proprio
   computer, anche in rete locale. Alla prima apertura la pagina fa creare l'accesso e accompagna nei primi passi.
2. Per ogni azienda la console dà una **chiave di collegamento** e un file con tre impostazioni: `console_url`,
   `console_key` e, in rete locale, `console_pin`. Vanno nei PC con `Set-OmissisPolicy.ps1`, tutti insieme, oppure
   a mano dal pannello di ciascuno (Impostazioni → Console centrale, nella vista avanzata).
3. Entro un'ora i PC compaiono nella console. Togliendo le tre impostazioni tutto torna com'era.
   Dalla console si possono anche **mandare le regole ai PC** (quali servizi proteggere o bloccare, file,
   aggiornamenti, divieto di spegnere la protezione; per azienda e, dove serve, per singolo PC), ricevere **avvisi** e tenere un **registro di conformità**. Le regole valgono solo sui PC che
   le accettano: `"console_rules": true` nello stesso file. La console non può cambiare a chi i PC mandano i dati.
4. **Oltre i 5 PC, o con più di un'azienda**: nella console, scheda «Licenza» → «Richiedi una licenza». Prepara un
   file con l'identificativo dell'installazione; lo si manda da <https://francescogruner.it/contatti/> e si riceve
   un file di licenza da caricare nella stessa scheda.

## 2. Quale schema scegliere

| Schema | Quando | Che cosa serve |
|---|---|---|
| **A. Ogni PC con il suo modello** (di serie) | I PC hanno almeno 8 GB di memoria | Niente: ogni PC lavora da solo, anche fuori dall'ufficio |
| **B. Un PC presta il modello agli altri** | PC con poca memoria, vecchi, o terminali | Un PC sempre acceso, con l'utente collegato, raggiungibile in rete |
| **C. Misto** | Fissi deboli e portatili che escono | I fissi come B, i portatili come A |

Con lo schema A ogni PC tiene in memoria il modello (da 1,2 a 1,5 GB con quello piccolo) e non dipende da nessuno.
Con lo schema B i PC non caricano e non scaricano il modello, ma **se il server non risponde i loro messaggi verso
i servizi protetti vengono fermati**: non partono in chiaro, e non c'è ripiego sul modello locale. Un portatile
fuori dalla rete dell'ufficio resta fermo finché non rientra (o non usa una VPN).

## 3. Distribuire il programma

Omissis si installa **per il singolo utente**, senza diritti di amministratore: gli script vanno lanciati con
l'utente che usa il PC, non come SYSTEM. L'unica eccezione è `Set-OmissisPolicy.ps1`.

| Metodo | Come |
|---|---|
| A mano | L'utente lancia `Omissis-<versione>-setup.exe`: al primo avvio la configurazione guidata lo accompagna |
| Script da una condivisione | `Install-Omissis.ps1` con l'installer, la sua impronta e il file delle scelte |
| RMM (NinjaOne e simili) | Un'automazione che lancia lo stesso script, eseguita come utente connesso |
| Intune | App Win32 con comportamento di installazione «Utente» e `Get-OmissisStatus.ps1` come regola di rilevamento |
| Criteri di gruppo | Uno script di accesso dell'utente che lancia `Install-Omissis.ps1` |

```powershell
powershell -ExecutionPolicy Bypass -File Install-Omissis.ps1 `
  -Installer "\\server\software\Omissis-0.1.0-setup.exe" -Sha256 "<impronta>" `
  -Settings "\\server\software\cliente.json" -ModelSource "\\server\software\modelli"
```

`-ModelSource` evita che ogni PC scarichi il modello per conto suo; con lo schema B non serve.

## 4. Il server di inferenza, passo per passo

**Sul PC che presta il modello**

1. Installa Omissis come su ogni altro PC e lascia che scarichi il modello.
2. Apri il pannello, accendi «Modalità avanzata», vai in Impostazioni → Riconoscimento → **Server di inferenza in
   rete** e premi «Presta il modello alla rete». La protezione riparte in pochi secondi.
3. La prima volta Windows chiede se consentire l'accesso alla rete: scegli le reti private. In alternativa, da
   amministratore:

   ```powershell
   New-NetFirewallRule -DisplayName "Omissis, server di inferenza" -Direction Inbound -Action Allow `
     -Protocol TCP -LocalPort 8770 -Profile Domain,Private
   ```

4. Premi «Copia la configurazione» e salvala in un file, per esempio `server.json`. Contiene indirizzo, chiave e
   impronta del certificato: **trattala come una password**.

   ```json
   {"engine_url": "https://pc-server:8770", "engine_key": "oms_…", "engine_pin": "…"}
   ```

5. Se in rete il nome del PC non viene trovato, nel file sostituiscilo con il suo indirizzo (la pagina li elenca),
   e in quel caso dai al PC un indirizzo che non cambi.

**Sugli altri PC**, in uno di questi modi:

- **A mano**: nella stessa scheda del pannello incolla la configurazione e premi «Usa questo server». Omissis prova
  a collegarsi prima di salvarla.
- **Con l'installazione**: `Install-Omissis.ps1 -Settings server.json`. Il PC parte senza scaricare il modello.
  L'utente può cambiare l'impostazione dal pannello.
- **Bloccata**: `Set-OmissisPolicy.ps1 -Settings server.json`, da amministratore. L'utente non la può cambiare.

**Controllare.** Sul PC, la pagina Inizio dice «Modello … su un server della rete». Sul server, la scheda elenca i
PC che hanno chiesto il riconoscimento e quanti testi: solo conteggi, da quando la protezione è accesa.

**Da sapere**

- In rete viaggia, cifrato, il testo da controllare, e tornano solo le posizioni dei dati trovati. Segnaposto,
  valori veri, regole ed elenchi restano su ogni PC; il server non scrive nulla di ciò che riceve.
- Omissis non è un servizio di Windows: il server risponde **finché su quel PC l'utente è collegato e Omissis è
  acceso**. Va lasciato acceso, senza sospensione.
- Il server controlla un testo alla volta. Per un ufficio piccolo basta; con molti PC che scrivono insieme le
  richieste si mettono in coda. Non è stato misurato quanti PC regge.
- Per tornare indietro: sul PC «Torna al modello di questo PC» (o togli le tre impostazioni); sul server «Smetti
  di prestarlo».
- Per cambiare la chiave: sul server smetti di prestare, cancella la cartella `server` tra i dati di Omissis
  (`%LOCALAPPDATA%\Omissis\server`) e riaccendi. Cambia anche il certificato: i PC vanno riconfigurati.

## 5. Bloccare le impostazioni

`Set-OmissisPolicy.ps1 -Settings blocco.json`, da amministratore o come SYSTEM, scrive le impostazioni in una zona
del registro che l'utente non può modificare: nel pannello quei comandi restano visibili ma fermi. Si bloccano così
le regole dei servizi (per esempio `"deepseek": "block"`), il modello, gli aggiornamenti, il server di inferenza e
il collegamento alla console. Sui servizi con la regola imposta nemmeno l'estensione del browser si lascia sospendere.

Non è una difesa da chi manomette il programma, che è installato nel profilo dell'utente: per quello servono gli
strumenti di Windows (AppLocker, controllo delle applicazioni).

## 6. L'estensione del browser

Gli script installano il programma, non l'estensione. Finché non è pubblicata sugli store si carica a mano dalla
cartella indicata nel pannello; appena installata apre una pagina con il pulsante «Collega questo browser». Quando
sarà pubblicata si installerà con un clic e si potrà imporre con il criterio `ExtensionInstallForcelist` di Chrome
e di Edge.

## 7. Se qualcosa non va

| Che cosa vedi | Che cosa guardare |
|---|---|
| Sul PC: «Il server di inferenza … non risponde» | Il server è acceso, con l'utente collegato e Omissis attivo? La scheda del server dice «in ascolto»? |
| «Il server non è raggiungibile» mentre incolli la configurazione | Firewall del server (porta 8770), rete del server segnata come «pubblica» in Windows, nome del PC non trovato: prova con l'indirizzo |
| «Il certificato del server non è quello atteso» | L'impronta non è quella del server: ricopia la configurazione per intero |
| «Il server ha rifiutato la chiave» | Chiave sbagliata, o cambiata sul server |
| Sul server: «non in ascolto: la porta è occupata» | Un altro programma usa la porta 8770: cambiala con l'impostazione `serve_port` |
| Un PC non compare nella console | Le tre impostazioni ci sono? Nel pannello del PC, Impostazioni → Console centrale dice che cosa non va |

## 8. Che cosa è provato e che cosa no

Provato con prove automatiche su un solo computer: installazione in silenzio, blocco delle impostazioni, invio del
riepilogo, e il server di inferenza con due copie del programma sullo stesso PC (una senza modello), attraverso
HTTPS con chiave e impronta.

**Non ancora provato**: il server di inferenza tra due PC veri in rete e con il firewall di Windows, più PC
insieme, il lancio da un RMM o da Intune veri, `Set-OmissisPolicy.ps1` come amministratore su un PC con Omissis
installato.
