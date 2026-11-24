# Omissis for Mac (preview) · Omissis per Mac (anteprima)

**English** · [Italiano](#italiano)

The Mac build is out as a **preview** since 20 November 2026 (now version 0.1.12, Apple silicon only): the `.dmg` is on the [releases page](https://github.com/francescogruner/omissis/releases). It is not signed with Apple, so macOS refuses to open it the first time: see «Installing the preview» below. On 20 November 2026 a GitHub Mac (macOS 26, Apple Silicon) built the app and the `.dmg`, started the app and passed the automated tests. The real Keychain, the menu bar icon and the real ChatGPT and Claude apps were tried there too. Nobody has used it on a Mac yet: a message replaced inside an app, with a signed-in account, is still to be seen.

## Installing the preview

These are the usual steps for an app without an Apple signature. They have not been tried on a real Mac with this build.

1. Download `Omissis-0.1.12-mac-arm64.dmg`, open it and drag Omissis to Applications.
2. Open Omissis. macOS says it cannot verify the app: close the message.
3. Open System Settings → Privacy & Security, scroll down to «Security» and press «Open Anyway» next to Omissis. macOS asks for your password or Touch ID.
4. If macOS says the app «is damaged», it is the same refusal in another form: in Terminal run `xattr -dr com.apple.quarantine /Applications/Omissis.app`, then open it again.

From version 0.1.6 the preview updates itself, starts at sign-in, reads scans and has the clipboard shortcuts (see «What the program does in place of an installer»). The first preview, 0.1.5, has none of that and cannot update itself: if you installed it, download the new `.dmg` once. If something does not work, please open an issue.

## How it is built

The app is not frozen, the same as the Windows installer. `Omissis.app` contains:

- a complete Python (python-build-standalone);
- the libraries in `requirements-mac.txt`;
- the code in `app/` and `model/`.

`Contents/MacOS/Omissis` is a small launcher for `panel.py`. The model weights are downloaded at first start.

```
python3 packaging/mac/build_mac.py --version 0.1.12 --smoke-test   # on a Mac: dist/Omissis.app and dist/Omissis-0.1.12-mac-arm64.dmg
bash packaging/mac/ci_tests.sh                                     # automated tests with the app's own Python
```

The workflow `.github/workflows/mac.yml` does the same on a GitHub Mac, and keeps the `.dmg` as a build artifact.

## What changes on a Mac

| | Windows | Mac |
|---|---|---|
| Archive key | Windows data protection (DPAPI) | Keychain (AES-GCM) |
| Proxy certificate | user store | login keychain (macOS asks for the password) |
| Icon and notifications | tray | menu bar; notifications from the system; new AI apps also in the icon menu |
| Desktop apps | ChatGPT/Codex, Copilot, Perplexity (debug port), Kimi (plugin). The Claude app refuses the debug port | ChatGPT/Codex (debug port), Kimi (plugin). The Claude app refuses the debug port. Perplexity and Copilot for Mac are native apps: not covered this way |
| Safari | — | not yet: see «Safari» below. Chrome, Edge, Brave and Arc use the same extension as on Windows |
| Terminal tools | `omissis-hook` in the user PATH | `omissis-hook` added to `~/.zprofile` |
| Global shortcuts | Ctrl+Alt+S, M and R | Control+Option+M and Control+Option+R, for the clipboard. Masking the selected text in place is not available: macOS lets only programs with the Accessibility permission press keys for you |
| Reading scans (OCR) | the Windows engine | the text recognition of macOS (Vision) |
| Automatic updates | signed sheet, silent installer | the same signed sheet, the `.dmg`; see below |
| Start at sign-in | an option of the installer | a switch in the panel, on at first start |
| Removing it | the Windows uninstaller | «Remove Omissis» in the panel settings |

The app is not signed or notarized, so macOS blocks it the first time. To open it: System Settings → Privacy & Security → «Open Anyway».

### What the program does in place of an installer

On Windows an installer puts the program in place, starts it at sign-in, updates it and removes it. On a Mac there is no installer, so the program does those things itself (`app/macapp.py`), from the panel. It is there from version 0.1.6 (20 November 2026); the first preview, 0.1.5, does not have it.

**Updates.** Same rules as on Windows: once a day the app reads a sheet from the releases page (`update-mac-arm64.json`), accepts it only if it carries the author's signature, downloads the `.dmg` named there and checks its size and SHA-256. A sheet for another processor, or one naming a Windows installer, is ignored. Then:

- it mounts the `.dmg` (read-only, not shown in the Finder) and copies the new `Contents` folder next to the one in use, inside `Omissis.app`;
- it checks the copy: bundle identifier, version, and that its Python starts on this Mac and loads its libraries;
- at the next start, or with «Install now», a small shell script waits for the program to close, swaps the two folders and reopens the app;
- the new version has two minutes to say it has started. If it does not, the script puts the previous version back and reopens it, and the panel says which version failed. A version that failed is not tried again by itself.

Only `Contents` inside the app changes, so nothing is asked of the Applications folder, and the data in `~/Library/Application Support/Omissis` is not touched. The sheet is `{"product", "version", "platform": "mac-arm64", "file", "byte", "sha256", "notes"}` with an Ed25519 signature next to it (`.sig`); it is written and signed on the publisher's computer, where the signing key stays.

**First start.** An app opened from the installation disk, or from the temporary copy macOS makes of an app that was never moved, cannot replace itself. The panel says so, on the first page and in the guided setup, and offers «Move to Applications»: it copies the app there (to `~/Applications` if you cannot write to `/Applications`), closes and reopens from the new place. From its own place, at first start, Omissis adds itself to the programs that start at sign-in (`~/Library/LaunchAgents/eu.omissis.app.plist`, which asks macOS to open the app); the switch is in the guided setup and in the settings, and the entry also shows in System Settings → General → Login Items.

**Removing it.** «Remove Omissis» in the settings removes the start at sign-in, the terminal command, the proxy setting and the certificate Omissis added, and moves the app to the Trash. Your data stays unless you tick «Also delete my data».

**Scans and shortcuts.** Scanned PDFs and photos are read with the text recognition of macOS (Vision), on the Mac itself. Control+Option+M masks the clipboard and Control+Option+R restores it.

**How it was tried.** On 20 November 2026, on a GitHub Mac (macOS 26, Apple silicon), with the app just built and throwaway signing keys that only a test copy accepts (`packaging/mac/update_test.py`, 17 checks out of 17). A new version was found, downloaded, unpacked and checked, and «Install now» had it running 4 seconds later with the user's settings intact. A version broken on purpose passed the checks and did not start: the previous one was put back and reopened by itself, the panel named the version that failed, and it was not tried again at the next start. A version that was ready was installed at the next start. The app opened from its disk image said so and moved itself to an Applications folder (a test one) in 6 seconds. The start-at-sign-in entry was written at first start and switched off and on from the panel, and macOS, running it, did start Omissis. «Remove Omissis» moved the app to the Trash, removed the entry, deleted the data and closed the program. The swap and the way back are also tried at every build with a small stand-in app (`app/e2e_macapp.py`, 12 out of 12, on Linux too). In the same job the scans of `app/e2e_documents.py` were read by Vision and masked, and `packaging/mac/keys_test.py` pressed Control+Option+M and Control+Option+R through System Events: the clipboard was masked and restored (4 out of 4).

**Seen once, not explained.** In one of the five runs of that day the program with the menu bar icon aborted two seconds after starting on the GitHub Mac («Abort trap: 6»). It did not happen again in the 29 starts that followed in other runs, 24 of them in a row, and the cause was not found. `ci_tests.sh` now starts it four times before the tests, and if it falls prints what it wrote and macOS's crash report.

**Not tried on a real Mac.** What macOS says when an app approved with «Open Anyway» is reopened after it replaced its own content; whether macOS asks for the «App Management» permission; how the entry is named in Login Items; moving an app that really came from the Internet (on the GitHub Mac the disk image had no quarantine mark).

### ChatGPT for Mac

Since July 2026 the ChatGPT app for Mac is the same Electron app as on Windows (`/Applications/ChatGPT.app`, bundle id `com.openai.codex`). Omissis starts it with the debug port, as it does on Windows. Tried on a GitHub Mac on 20 November 2026 (versions 26.1111.21308 and 26.1117.31558): the app accepts the port and the Omissis code enters its window. Nobody has tried it signed in to an account yet.

The earlier native app is now called «ChatGPT Classic». It has no debug port and it pins its certificates, so Omissis cannot protect it.

### Claude for Mac

The Claude app refuses the debug port, on the Mac and on Windows. Started with it, the app exits at once and writes «Claude: refusing to start — a debugging or network-override switch is present on the command line» (tried on 20 November 2026, versions 5.11492.5 and 6.28899.2). It accepts the port only with a permission signed by Anthropic.

Omissis says so in the panel and does not close the app. What still works with Claude: claude.ai in the browser with the extension, and Claude Code with the plugin.

The other road is the proxy, and the panel takes it with one button (*Connections → Apps → Protect Claude*). The app uses the system proxy and the certificates the system trusts, as it does on company networks: the button installs the Omissis certificate (macOS asks for your password) and gives the system a PAC file that sends only the traffic to claude.ai to the Omissis proxy; an administrator of the Mac needs no further password for the network setting. The app reads the network settings only when it starts, so it must be opened after Omissis: the panel tells when it was not, and reopens it. Through that road the proxy puts the extension's own code into the app's page: on Enter the text is replaced in the writing box, in chat and in the Code tab, and the real values come back on screen. On a GitHub Mac (20 November 2026, 6.28899.2) the panel did the work, the traffic to claude.ai went through Omissis and the sign-in window loaded; no account was used there, so on a Mac no message has been seen being replaced. On Windows it has, with a real sign-in, on 23 November 2026 (6.28899.6). `packaging/ci/proxy_app_trial.py` repeats the trial (workflow «Prova del proxy con l'app di Claude»).

`packaging/mac/desktop_apps_test.sh` repeats this trial on a GitHub Mac (workflow input `only` = `desktop`): it installs the two apps there, without signing in to any account.

### Safari

Safari needs its own build of the extension, inside a Mac app. `packaging/mac/build_safari.sh` converts `app/extension` with Apple's converter and compiles it, signed for the local Mac only. The workflow runs it as a separate job that cannot fail the app build.

- **What Safari supports.** According to the MDN tables, everything the extension uses is supported from Safari 18.4: MV3 service worker, `declarativeNetRequest`, `scripting`, content scripts in the `MAIN` world, `match_origin_as_fallback`.
- **What the trial showed (20 November 2026, Xcode 26.6).** The extension converts and compiles. Apple's converter warns that `world` and `match_origin_as_fallback` are not supported, while the WebKit source reads both keys. This must be settled in a real Safari: if `world` were ignored, the page script would not see the requests of the page, and nothing would be replaced.
- **To be checked on a Mac.** Whether the extension's background can call the local program on `http://127.0.0.1`. If Safari refuses, the call goes through the app with native messaging.
- **Distribution.** Users can install it only if it is signed with an Apple Developer ID and notarized (Safari 18.4 or later accepts that outside the App Store). Without the signature, Safari asks for «Allow unsigned extensions» at every start.
- **Without the extension.** Safari uses the system proxy and the system certificates, so it can also go through the Omissis proxy. Not tried yet.

---

## Italiano

La versione per Mac è pubblicata come **versione di prova** dal 20 novembre 2026 (ora 0.1.12, solo per i Mac con processore Apple): il `.dmg` è nella [pagina delle versioni](https://github.com/francescogruner/omissis/releases). Non è firmata con Apple, quindi la prima volta macOS non la apre: vedi «Come si installa la versione di prova» qui sotto. Il 20 novembre 2026 un Mac di GitHub (macOS 26, Apple Silicon) ha costruito l'app e il `.dmg`, ha avviato l'app e ha passato le prove automatiche. Lì sono stati provati anche il Portachiavi vero, l'icona nella barra dei menu e le app vere di ChatGPT e di Claude. Nessuno l'ha ancora usata su un Mac: un messaggio sostituito dentro un'app, con un account, resta da vedere.

**Come si installa la versione di prova.** Sono i passi soliti per un'app senza la firma Apple. Con questa versione non sono stati provati su un Mac vero.

1. Scarica `Omissis-0.1.12-mac-arm64.dmg`, aprilo e trascina Omissis in Applicazioni.
2. Apri Omissis. macOS dice che non può verificarla: chiudi il messaggio.
3. Apri Impostazioni di Sistema → Privacy e sicurezza, scorri fino a «Sicurezza» e premi «Apri comunque» accanto a Omissis. macOS chiede la password o il Touch ID.
4. Se macOS dice che l'app «è danneggiata», è lo stesso rifiuto in un'altra forma: nel Terminale lancia `xattr -dr com.apple.quarantine /Applications/Omissis.app`, poi riaprila.

Dalla 0.1.6 la versione di prova si aggiorna da sola, parte all'accesso, legge le scansioni e ha le scorciatoie sugli appunti (vedi «Che cosa fa il programma al posto dell'installer»). La prima versione di prova, la 0.1.5, non ha nulla di questo e non sa aggiornarsi: chi l'ha installata riscarica il `.dmg` nuovo una volta. Se qualcosa non va, apri una segnalazione.

**Come si costruisce.** Come l'installer per Windows, l'app non viene «congelata». `Omissis.app` contiene:

- un Python completo;
- le librerie di `requirements-mac.txt`;
- il codice.

Il modello si scarica al primo avvio. I comandi sono quelli qui sopra, e il workflow `.github/workflows/mac.yml` fa lo stesso su un Mac di GitHub.

**Cosa cambia sul Mac**

- **Chiave dell'archivio:** sta nel Portachiavi.
- **Certificato del proxy:** va nel portachiavi di login, e macOS chiede la password.
- **Icona e notifiche:** l'icona sta nella barra dei menu e le notifiche le fa il sistema.
- **App desktop:**
  - coperte: l'app di ChatGPT/Codex (porta di debug), Kimi (plugin);
  - non coperte in questo modo: l'app di Claude, che rifiuta la porta di debug; Perplexity e Copilot per Mac, che sono app native.
- **ChatGPT per Mac:**
  - da luglio 2026 è la stessa app di Windows (`/Applications/ChatGPT.app`), e Omissis la avvia con la porta di debug. Provata su un Mac di GitHub il 20 novembre 2026 (versioni 26.1111.21308 e 26.1117.31558): accetta la porta e il codice di Omissis entra nella finestra. Con un account non l'ha ancora provata nessuno;
  - l'app nativa di prima ora si chiama «ChatGPT Classic»: non ha la porta di debug e fissa i suoi certificati, quindi Omissis non può proteggerla.
- **Claude per Mac:**
  - l'app rifiuta la porta di debug, sul Mac come su Windows: avviata così esce subito (provato il 20 novembre 2026, versioni 5.11492.5 e 6.28899.2). La accetta solo con un permesso firmato da Anthropic;
  - Omissis lo dice nel pannello e non chiude l'app. Con Claude restano claude.ai nel browser, con l'estensione, e Claude Code, con il plugin;
  - l'altra strada è il proxy, e il pannello la prende con un pulsante (*Collegamenti → App → Proteggi Claude*). L'app usa il proxy e i certificati del sistema, come nelle reti aziendali: il pulsante mette il certificato di Omissis (macOS chiede la password) e dà al sistema un file PAC che manda al proxy solo il traffico verso claude.ai; chi amministra il Mac non deve dare altre password per la rete. L'app legge le impostazioni di rete solo quando parte, quindi va aperta dopo Omissis: il pannello dice quando non è così, e la riapre. Da quella strada il proxy porta nella pagina dell'app lo stesso codice dell'estensione: all'Invio il testo viene sostituito nella casella, in chat e nella scheda Code, e a schermo tornano i valori veri. Su un Mac di GitHub (20 novembre 2026, 6.28899.2) il pannello ha fatto tutto, il traffico verso claude.ai è passato da Omissis e la finestra d'ingresso si è caricata; lì senza account, quindi sul Mac un messaggio sostituito non si è ancora visto. Su Windows sì, con un accesso vero, il 23 novembre 2026 (6.28899.6). `packaging/ci/proxy_app_trial.py` rifà la prova (flusso «Prova del proxy con l'app di Claude»);
  - `packaging/mac/desktop_apps_test.sh` rifà questa prova su un Mac di GitHub, senza entrare in nessun account.
- **Safari:**
  - vuole una sua versione dell'estensione, dentro un'app per Mac. `packaging/mac/build_safari.sh` la converte e la compila, con la firma valida solo per quel Mac;
  - secondo le tabelle di MDN, da Safari 18.4 è supportato tutto ciò che l'estensione usa;
  - nella prova del 20 novembre 2026 (Xcode 26.6) l'estensione si converte e si compila. Lo strumento di Apple avvisa che `world` e `match_origin_as_fallback` non sono supportate, mentre il codice di WebKit le legge. Va chiarito in un Safari vero: se `world` venisse ignorata, lo script non vedrebbe le richieste della pagina e non sostituirebbe nulla;
  - resta da verificare su un Mac se l'estensione riesce a chiamare il programma su `http://127.0.0.1`;
  - per darla agli utenti servono un Developer ID di Apple e la notarizzazione. Senza firma, Safari chiede «Consenti estensioni non firmate» a ogni avvio;
  - senza estensione, Safari può passare dal proxy di Omissis, perché usa il proxy e i certificati del sistema. Non è ancora stato provato.
- **Strumenti da terminale:** il comando `omissis-hook` viene aggiunto a `~/.zprofile`.

**Che cosa fa il programma al posto dell'installer.** Su Windows un installer mette il programma al suo posto, lo fa partire all'accesso, lo aggiorna e lo toglie. Sul Mac un installer non c'è, quindi queste cose le fa il programma (`app/macapp.py`), dal pannello. C'è dalla versione 0.1.6 (20 novembre 2026); la prima versione di prova, la 0.1.5, non lo ha.

- **Aggiornamenti:** stesse regole di Windows.
  - Una volta al giorno l'app legge un foglio dalla pagina delle versioni (`update-mac-arm64.json`), lo accetta solo se porta la firma dell'autore, scarica il `.dmg` che il foglio indica e ne controlla dimensione e impronta SHA-256. Un foglio per un altro processore, o che indica un installer di Windows, viene ignorato.
  - Monta il `.dmg` (in sola lettura, senza farlo comparire nel Finder) e copia la cartella `Contents` nuova accanto a quella in uso, dentro `Omissis.app`.
  - Controlla la copia: identificativo, versione, e che il suo Python parta su questo Mac e carichi le sue librerie.
  - Al successivo avvio, o con «Installa ora», un piccolo script aspetta che il programma si chiuda, scambia le due cartelle e riapre l'app.
  - La versione nuova ha due minuti per dire che è partita. Se non lo fa, lo script rimette quella di prima e la riapre, e il pannello dice quale versione non è partita. Una versione fallita non viene ritentata da sola.
  - Cambia solo `Contents` dentro l'app: alla cartella Applicazioni non si chiede nulla, e i dati in `~/Library/Application Support/Omissis` non vengono toccati.
  - Il foglio è `{"product", "version", "platform": "mac-arm64", "file", "byte", "sha256", "notes"}` con accanto la firma Ed25519 (`.sig`). Lo scrive e lo firma chi pubblica, sul suo computer, dove resta la chiave.
- **Primo avvio:**
  - un'app aperta dal disco di installazione, o dalla copia temporanea che macOS fa di un'app mai spostata, non può sostituirsi. Il pannello lo dice, nella prima pagina e nella configurazione guidata, e offre «Sposta in Applicazioni»: copia l'app lì (in `~/Applications` se in `/Applications` non puoi scrivere), si chiude e si riapre dal posto nuovo;
  - dal posto suo, al primo avvio, Omissis si mette tra i programmi che partono all'accesso (`~/Library/LaunchAgents/eu.omissis.app.plist`, che chiede a macOS di aprire l'app). L'interruttore è nella configurazione guidata e nelle impostazioni, e la voce si vede anche in Impostazioni di Sistema → Generali → Elementi login.
- **Toglierla:** «Togli Omissis» nelle impostazioni toglie l'avvio all'accesso, il comando da terminale, l'impostazione del proxy e il certificato messi da Omissis, e sposta l'app nel Cestino. I dati restano, a meno di spuntare «Elimina anche i miei dati».
- **Scansioni e scorciatoie:** PDF scansionati e fotografie si leggono con il riconoscimento del testo di macOS (Vision), sul Mac stesso. Control+Option+M maschera gli appunti e Control+Option+R li ripristina. La scorciatoia che sostituisce il testo selezionato sul posto non c'è: macOS lascia premere i tasti al posto tuo solo ai programmi con il permesso «Accessibilità».
- **Come è stato provato:** il 20 novembre 2026, su un Mac di GitHub (macOS 26, processore Apple), con l'app appena costruita e chiavi di firma usa e getta che solo una copia di prova accetta (`packaging/mac/update_test.py`, 17 controlli su 17). Una versione nuova è stata trovata, scaricata, scompattata e controllata, e con «Installa ora» era accesa 4 secondi dopo, con le impostazioni di prima. Una versione rotta apposta ha passato i controlli e non è partita: è tornata quella di prima, riaperta da sola, il pannello ha detto quale versione non era partita, e al riavvio non è stata ritentata. Una versione pronta è stata installata al successivo avvio. L'app aperta dalla sua immagine disco lo ha detto e si è spostata in una cartella Applicazioni (di prova) in 6 secondi. La voce di avvio all'accesso è stata scritta al primo avvio, spenta e riaccesa dal pannello, e macOS, eseguendola, ha fatto partire Omissis. «Togli Omissis» ha spostato l'app nel Cestino, tolto la voce, cancellato i dati e chiuso il programma. Lo scambio e il ritorno si provano a ogni costruzione anche con una piccola app finta (`app/e2e_macapp.py`, 12 su 12, anche su Linux). Nello stesso lavoro le scansioni di `app/e2e_documents.py` sono state lette da Vision e mascherate, e `packaging/mac/keys_test.py` ha premuto Control+Option+M e Control+Option+R con System Events: gli appunti sono stati mascherati e ripristinati (4 su 4).
- **Visto una volta, senza spiegazione:** in una delle cinque esecuzioni di quel giorno il programma con l'icona nella barra dei menu è caduto due secondi dopo l'avvio sul Mac di GitHub («Abort trap: 6»). Non è più successo nei 29 avvii fatti dopo in altre esecuzioni, 24 dei quali di fila, e la causa non è stata trovata. `ci_tests.sh` ora lo avvia quattro volte prima delle prove e, se cade, stampa ciò che ha scritto e il rapporto di macOS.
- **Non provato su un Mac vero:** che cosa dice macOS quando un'app approvata con «Apri comunque» viene riaperta dopo aver sostituito il proprio contenuto; se macOS chiede il permesso «Gestione app»; con che nome compare la voce tra gli elementi di login; lo spostamento di un'app arrivata davvero da Internet (sul Mac di GitHub l'immagine disco non aveva il segno di quarantena).

L'app non è firmata né notarizzata, quindi al primo avvio macOS la blocca. Per aprirla: Impostazioni di Sistema → Privacy e sicurezza → «Apri comunque».
