# Omissis for Mac (preview) · Omissis per Mac (anteprima)

**English** · [Italiano](#italiano)

The Mac build is out as a **preview** since 20 November 2026 (version 0.1.5, Apple silicon only): the `.dmg` is on the [releases page](https://github.com/francescogruner/omissis/releases). It is not signed with Apple, so macOS refuses to open it the first time: see «Installing the preview» below. On 20 November 2026 a GitHub Mac (macOS 26, Apple Silicon) built the app and the `.dmg`, started the app and passed the automated tests. The real Keychain, the menu bar icon and the real ChatGPT and Claude apps were tried there too. Nobody has used it on a Mac yet: a message replaced inside an app, with a signed-in account, is still to be seen.

## Installing the preview

These are the usual steps for an app without an Apple signature. They have not been tried on a real Mac with this build.

1. Download `Omissis-0.1.5-mac-arm64.dmg`, open it and drag Omissis to Applications.
2. Open Omissis. macOS says it cannot verify the app: close the message.
3. Open System Settings → Privacy & Security, scroll down to «Security» and press «Open Anyway» next to Omissis. macOS asks for your password or Touch ID.
4. If macOS says the app «is damaged», it is the same refusal in another form: in Terminal run `xattr -dr com.apple.quarantine /Applications/Omissis.app`, then open it again.

Missing compared with Windows: keyboard shortcuts, reading scanned documents, automatic updates (when a new `.dmg` comes out you download it again). If something does not work, please open an issue.

## How it is built

The app is not frozen, the same as the Windows installer. `Omissis.app` contains:

- a complete Python (python-build-standalone);
- the libraries in `requirements-mac.txt`;
- the code in `app/` and `model/`.

`Contents/MacOS/Omissis` is a small launcher for `panel.py`. The model weights are downloaded at first start.

```
python3 packaging/mac/build_mac.py --version 0.1.5 --smoke-test   # on a Mac: dist/Omissis.app and dist/Omissis-0.1.5-mac-arm64.dmg
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
| Global shortcuts (Ctrl+Alt+M…) | yes | not yet: use the icon menu |
| Reading scans (OCR) | yes | not yet |
| Automatic updates | yes | not yet: the panel links to the release page |

The app is not signed or notarized, so macOS blocks it the first time. To open it: System Settings → Privacy & Security → «Open Anyway».

### ChatGPT for Mac

Since July 2026 the ChatGPT app for Mac is the same Electron app as on Windows (`/Applications/ChatGPT.app`, bundle id `com.openai.codex`). Omissis starts it with the debug port, as it does on Windows. Tried on a GitHub Mac on 20 November 2026 (versions 26.1111.21308 and 26.1117.31558): the app accepts the port and the Omissis code enters its window. Nobody has tried it signed in to an account yet.

The earlier native app is now called «ChatGPT Classic». It has no debug port and it pins its certificates, so Omissis cannot protect it.

### Claude for Mac

The Claude app refuses the debug port, on the Mac and on Windows. Started with it, the app exits at once and writes «Claude: refusing to start — a debugging or network-override switch is present on the command line» (tried on 20 November 2026, versions 5.11492.5 and 6.28899.2). It accepts the port only with a permission signed by Anthropic.

Omissis says so in the panel and does not close the app. What still works with Claude: claude.ai in the browser with the extension, and Claude Code with the plugin.

The other road is the proxy, and the panel takes it with one button (*Connections → Apps → Protect Claude*). The app uses the system proxy and the certificates the system trusts, as it does on company networks: the button installs the Omissis certificate (macOS asks for your password) and gives the system a PAC file that sends only the traffic to claude.ai to the Omissis proxy; an administrator of the Mac needs no further password for the network setting. The app reads the network settings only when it starts, so it must be opened after Omissis: the panel tells when it was not, and reopens it. Tried on a GitHub Mac and on a GitHub Windows machine on 20 November 2026 (6.28899.2) with the panel doing the work: the traffic to claude.ai goes through Omissis and the sign-in window loads. No account was used, so no message was seen being replaced. `packaging/ci/proxy_app_trial.py` repeats the trial (workflow «Prova del proxy con l'app di Claude»).

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

La versione per Mac è pubblicata come **versione di prova** dal 20 novembre 2026 (0.1.5, solo per i Mac con processore Apple): il `.dmg` è nella [pagina delle versioni](https://github.com/francescogruner/omissis/releases). Non è firmata con Apple, quindi la prima volta macOS non la apre: vedi «Come si installa la versione di prova» qui sotto. Il 20 novembre 2026 un Mac di GitHub (macOS 26, Apple Silicon) ha costruito l'app e il `.dmg`, ha avviato l'app e ha passato le prove automatiche. Lì sono stati provati anche il Portachiavi vero, l'icona nella barra dei menu e le app vere di ChatGPT e di Claude. Nessuno l'ha ancora usata su un Mac: un messaggio sostituito dentro un'app, con un account, resta da vedere.

**Come si installa la versione di prova.** Sono i passi soliti per un'app senza la firma Apple. Con questa versione non sono stati provati su un Mac vero.

1. Scarica `Omissis-0.1.5-mac-arm64.dmg`, aprilo e trascina Omissis in Applicazioni.
2. Apri Omissis. macOS dice che non può verificarla: chiudi il messaggio.
3. Apri Impostazioni di Sistema → Privacy e sicurezza, scorri fino a «Sicurezza» e premi «Apri comunque» accanto a Omissis. macOS chiede la password o il Touch ID.
4. Se macOS dice che l'app «è danneggiata», è lo stesso rifiuto in un'altra forma: nel Terminale lancia `xattr -dr com.apple.quarantine /Applications/Omissis.app`, poi riaprila.

Rispetto a Windows mancano: scorciatoie da tastiera, lettura delle scansioni, aggiornamenti automatici (quando esce un `.dmg` nuovo lo riscarichi). Se qualcosa non va, apri una segnalazione.

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
  - l'altra strada è il proxy, e il pannello la prende con un pulsante (*Collegamenti → App → Proteggi Claude*). L'app usa il proxy e i certificati del sistema, come nelle reti aziendali: il pulsante mette il certificato di Omissis (macOS chiede la password) e dà al sistema un file PAC che manda al proxy solo il traffico verso claude.ai; chi amministra il Mac non deve dare altre password per la rete. L'app legge le impostazioni di rete solo quando parte, quindi va aperta dopo Omissis: il pannello dice quando non è così, e la riapre. Provato il 20 novembre 2026 su un Mac e su un Windows di GitHub (6.28899.2), con il pannello a fare tutto: il traffico verso claude.ai passa da Omissis e la finestra d'ingresso si carica. Senza account: un messaggio sostituito non si è visto. `packaging/ci/proxy_app_trial.py` rifà la prova (flusso «Prova del proxy con l'app di Claude»);
  - `packaging/mac/desktop_apps_test.sh` rifà questa prova su un Mac di GitHub, senza entrare in nessun account.
- **Safari:**
  - vuole una sua versione dell'estensione, dentro un'app per Mac. `packaging/mac/build_safari.sh` la converte e la compila, con la firma valida solo per quel Mac;
  - secondo le tabelle di MDN, da Safari 18.4 è supportato tutto ciò che l'estensione usa;
  - nella prova del 20 novembre 2026 (Xcode 26.6) l'estensione si converte e si compila. Lo strumento di Apple avvisa che `world` e `match_origin_as_fallback` non sono supportate, mentre il codice di WebKit le legge. Va chiarito in un Safari vero: se `world` venisse ignorata, lo script non vedrebbe le richieste della pagina e non sostituirebbe nulla;
  - resta da verificare su un Mac se l'estensione riesce a chiamare il programma su `http://127.0.0.1`;
  - per darla agli utenti servono un Developer ID di Apple e la notarizzazione. Senza firma, Safari chiede «Consenti estensioni non firmate» a ogni avvio;
  - senza estensione, Safari può passare dal proxy di Omissis, perché usa il proxy e i certificati del sistema. Non è ancora stato provato.
- **Strumenti da terminale:** il comando `omissis-hook` viene aggiunto a `~/.zprofile`.
- **Non ancora disponibili:**
  - le scorciatoie da tastiera;
  - la lettura delle scansioni;
  - gli aggiornamenti automatici.

L'app non è firmata né notarizzata, quindi al primo avvio macOS la blocca. Per aprirla: Impostazioni di Sistema → Privacy e sicurezza → «Apri comunque».
