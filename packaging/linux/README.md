# Omissis for Linux (preview) · Omissis per Linux (versione di prova)

**English** · [Italiano](#italiano)

The Linux build is a **preview** (now version 0.1.12), on the [releases page](https://github.com/francescogruner/omissis/releases/latest) since 21 November 2026. It was built and tested automatically on Ubuntu 22.04 (a GitHub machine) and in Ubuntu 24.04 (inside Windows, with WSL). **Nobody has used it on a real Linux desktop yet**: what depends on the desktop (the icon, the entry in the applications menu, the start at sign-in, the keyring prompt) has been checked file by file, not by eye.

## Installing

One command, as the user who will use it. It does not ask for administrator rights and refuses to run as root.

```
curl -fsSL https://github.com/francescogruner/omissis/releases/latest/download/install.sh | sh
```

The command downloads the installer from the releases page and runs it. If you prefer to read it first, download `install.sh` from the same page and then:

```
sh install.sh                                     # downloads the latest version from the releases page
sh install.sh Omissis-0.1.12-linux-x86_64.tar.gz   # installs an archive you already have, also without a network
```

What it does:

1. unpacks the program into `~/.local/lib/omissis` (another folder with `OMISSIS_HOME`);
2. checks that it starts on this computer **before** replacing a version already installed;
3. starts it. At first start Omissis adds by itself the entry in the applications menu, the `omissis` command (in `~/.local/bin`) and the start at sign-in, which you turn off from the panel.

Your data (vault, settings, lists, the model) stays in `~/.local/share/omissis`, in a folder only your user can read. Running the installer again updates the program and leaves the data alone.

It needs a 64-bit distribution with glibc, at least as recent as the one the package was built on (Ubuntu 22.04, Debian 12, Fedora 36). Alpine (musl) is not supported. The arm64 package can be built but has never been tried.

## What it covers on Linux

| | |
|---|---|
| Browser | the same extension as on Windows: Chrome, Edge, Brave, Chromium |
| Terminal tools | Claude Code, Codex, Antigravity CLI, opencode, aider: gateway and plugins, with `omissis-hook` in the user's PATH |
| Antigravity (the app) | reopened through the gateway from the panel. The code finds it wherever it was unpacked; **never tried with the real app on Linux** |
| Documents | Word, Excel, PowerPoint and PDF. Scans are read with Tesseract, if it is installed (see below) |
| MCP server | documents inside the AI tools that speak MCP |
| ChatGPT, Claude, Copilot, Perplexity | they have no official Linux app: use them in the browser, which is covered |

## What changes on Linux

| | Windows | Linux |
|---|---|---|
| Installing | installer (.exe) | `install.sh`, for the current user, no administrator rights |
| Vault key | Windows data protection (DPAPI) | the desktop keyring (Secret Service: GNOME Keyring, KWallet, KeePassXC), AES-GCM. Where there is no keyring the vault is **not encrypted** and the panel says so: it is protected only by the data folder, which only your user can read |
| Icon | tray | only where the desktop has an icon area reachable from X11 (KDE, Xfce, Cinnamon, MATE). On GNOME without extensions, or in a Wayland-only session, there is no icon: you reopen Omissis from the applications menu or with `omissis`, and quit it from the panel (Settings) or with `omissis --quit` |
| Notifications | from the icon | `notify-send`, if it is there |
| Start at sign-in | an option of the installer | a switch in the panel, on at first start (a file in `~/.config/autostart`, which your desktop's «Startup applications» also shows) |
| Automatic updates | signed sheet, silent installer | the same signed sheet (`update-linux-x86_64.json`) and the `.tar.gz`; if the new version does not start, the previous one comes back |
| Terminal tools | `omissis-hook` in the user PATH | a line in `~/.profile` (and in `~/.bashrc`, `~/.bash_profile`, `~/.zshrc`, `~/.zprofile` if they exist), removed on request |
| Reading scans (OCR) | the Windows engine | Tesseract with Italian, if installed: `tesseract-ocr`, `tesseract-ocr-ita`, and `poppler-utils` for PDFs made of images. Without them the panel says what is missing |
| Clipboard | Windows clipboard | `wl-clipboard` on Wayland, `xclip` or `xsel` on X11, if installed (in the code, not tried yet) |
| Global keyboard shortcuts | Ctrl+Alt+S, M and R | **not available** |
| Proxy certificate and system proxy | user store, system proxy settings | **not available**: Omissis does not touch the system certificates or the system proxy on Linux. The separate browser window that goes through the proxy uses a Chromium browser found on the computer (not tried yet on Linux) |
| Settings imposed by an administrator | registry (policies) | the file `/etc/omissis/managed.json`, which only the administrator can write |
| Removing it | the Windows uninstaller | «Remove Omissis from this computer» in the panel settings: the program goes to the trash, the menu entry, the command and the start at sign-in are removed; the data stays unless you ask to delete it |

## How it is built

The package is not frozen. The archive contains one folder, `Omissis.app`, made like the Mac app and built by the same code (`packaging/mac/build_mac.py`): a complete Python (python-build-standalone), the libraries in `packaging/mac/requirements-mac.txt` and the code in `app/` and `model/`. The folder keeps the Mac name on purpose: installing, starting at sign-in and updating use on Linux the code already tested on the Mac (`app/macapp.py`). The model weights are downloaded at first start.

```
python3 packaging/linux/build_linux.py --version 0.1.12 --smoke-test   # dist/Omissis.app and dist/Omissis-0.1.12-linux-x86_64.tar.gz
bash packaging/linux/ci_linux.sh 0.1.12                                 # build and all the tests, as a normal user
```

The workflow `.github/workflows/linux.yml` does the same on a GitHub Ubuntu and keeps the archive as a build artifact. It starts only by hand and publishes nothing.

To publish a Linux version, three files go on the releases page, attached to the version «releases/latest» points to: the `.tar.gz`, `update-linux-x86_64.json` and `update-linux-x86_64.json.sig` (the signed sheet, written by whoever publishes, where the signing key is), plus `install.sh`.

## What has been tested

On 21 November 2026, in Ubuntu 24.04 under WSL, with the built package and a normal user:

- **260 automated checks, none failed** (`ci_linux.sh`): 213 in the series shared with the Mac (vault, central console, inventory, MCP server, gateway, proxy, plugins, documents with scans read by Tesseract, the app folder), 11 on updates (new version installed, broken version rolled back to the previous one, update at start) and 36 in the Linux test.
- The Linux test (`linux_test.py`) installs with `install.sh` into a throwaway home folder and checks: the installer in Italian and English, a damaged archive refused, the menu entry (validated with `desktop-file-validate`), the icon, the `omissis` command, the start at sign-in (on at first start, off and on from the panel, off from the desktop settings), the data folder readable only by its user, a second launch that does not start a duplicate, the search for AI programs and browser extensions, `omissis-hook` in and out of the PATH, the trash, scans, protection switching on with the model already on disk, `omissis --quit` and the quit button leaving no process behind, installing over a running copy, removal with and without the data.
- With a real keyring (GNOME Keyring in a test D-Bus session): 6 checks out of 6. The vault key goes into the keyring, the vault is encrypted with it, and without the keyring the same vault is refused instead of being read wrongly.
- The installer refuses root; the settings in `/etc/omissis/managed.json` are applied.
- The panel, opened from a browser that reports Linux, shows the Linux wording in Italian and English on the pages checked (Home, Text, Guide, Settings, Connections, Vault).

Not verified: any real Linux desktop (GNOME, KDE and the others), the icon, the keyring prompt when the keyring is locked, the real Antigravity app, the workflow on GitHub (written, never run), the arm64 package, distributions other than Ubuntu.

---

<a id="italiano"></a>

# Italiano

La versione per Linux è una **versione di prova** (ora la 0.1.12), nella [pagina delle versioni](https://github.com/francescogruner/omissis/releases/latest) dal 21 novembre 2026. È stata costruita e provata in automatico su Ubuntu 22.04 (una macchina di GitHub) e in Ubuntu 24.04 (dentro Windows, con WSL). **Nessuno l'ha ancora usato su un desktop Linux vero**: ciò che dipende dal desktop (l'icona, la voce nel menu delle applicazioni, l'avvio all'accesso, la richiesta del portachiavi) è stato controllato file per file, non a occhio.

## Installazione

Un comando, dall'utente che lo userà. Non chiede diritti di amministratore e si rifiuta di partire come root.

```
curl -fsSL https://github.com/francescogruner/omissis/releases/latest/download/install.sh | sh
```

Il comando scarica l'installatore dalla pagina delle versioni e lo esegue. Se preferisci leggerlo prima, scarica `install.sh` dalla stessa pagina e poi:

```
sh install.sh                                     # scarica l'ultima versione dalla pagina delle versioni
sh install.sh Omissis-0.1.12-linux-x86_64.tar.gz   # installa un archivio che hai già, anche senza rete
```

Che cosa fa:

1. scompatta il programma in `~/.local/lib/omissis` (un'altra cartella con `OMISSIS_HOME`);
2. controlla che parta su questo computer **prima** di sostituire una versione già installata;
3. lo avvia. Al primo avvio Omissis aggiunge da solo la voce nel menu delle applicazioni, il comando `omissis` (in `~/.local/bin`) e l'avvio all'accesso, che si spegne dal pannello.

I tuoi dati (archivio, impostazioni, liste, modello) stanno in `~/.local/share/omissis`, in una cartella che può leggere solo il tuo utente. Rilanciare l'installatore aggiorna il programma e lascia stare i dati.

Serve una distribuzione a 64 bit con glibc, recente almeno quanto quella su cui il pacchetto è stato costruito (Ubuntu 22.04, Debian 12, Fedora 36). Alpine (musl) non è prevista. Il pacchetto per arm64 si può costruire ma non è mai stato provato.

## Che cosa copre su Linux

| | |
|---|---|
| Browser | la stessa estensione di Windows: Chrome, Edge, Brave, Chromium |
| Strumenti da terminale | Claude Code, Codex, Antigravity CLI, opencode, aider: gateway e plugin, con `omissis-hook` nel PATH dell'utente |
| Antigravity (l'app) | riaperta dal pannello attraverso il gateway. Il codice la trova ovunque sia stata scompattata; **mai provata con l'app vera su Linux** |
| Documenti | Word, Excel, PowerPoint e PDF. Le scansioni si leggono con Tesseract, se è installato (vedi sotto) |
| Server MCP | i documenti dentro gli strumenti AI che parlano MCP |
| ChatGPT, Claude, Copilot, Perplexity | non hanno un'app ufficiale per Linux: si usano dal browser, che è coperto |

## Che cosa cambia su Linux

| | Windows | Linux |
|---|---|---|
| Installazione | installer (.exe) | `install.sh`, per l'utente corrente, senza diritti di amministratore |
| Chiave dell'archivio | protezione dei dati di Windows (DPAPI) | il portachiavi del desktop (Secret Service: GNOME Keyring, KWallet, KeePassXC), AES-GCM. Dove il portachiavi non c'è l'archivio **non è cifrato** e il pannello lo dice: lo protegge solo la cartella dei dati, che può leggere solo il tuo utente |
| Icona | vicino all'orologio | solo dove il desktop ha un'area per le icone raggiungibile da X11 (KDE, Xfce, Cinnamon, MATE). Su GNOME senza estensioni, o in una sessione solo Wayland, l'icona non c'è: Omissis si riapre dal menu delle applicazioni o con `omissis`, e si chiude dal pannello (Impostazioni) o con `omissis --quit` |
| Notifiche | dall'icona | `notify-send`, se c'è |
| Avvio all'accesso | una casella dell'installer | un interruttore nel pannello, acceso al primo avvio (un file in `~/.config/autostart`, che si vede anche tra le «Applicazioni d'avvio» del desktop) |
| Aggiornamenti automatici | foglio firmato, installer silenzioso | lo stesso foglio firmato (`update-linux-x86_64.json`) e il `.tar.gz`; se la versione nuova non parte torna quella di prima |
| Strumenti da terminale | `omissis-hook` nel PATH dell'utente | una riga in `~/.profile` (e in `~/.bashrc`, `~/.bash_profile`, `~/.zshrc`, `~/.zprofile` se ci sono), che si toglie a richiesta |
| Lettura delle scansioni (OCR) | il motore di Windows | Tesseract con l'italiano, se installato: `tesseract-ocr`, `tesseract-ocr-ita`, e `poppler-utils` per i PDF fatti di immagini. Senza, il pannello dice che cosa manca |
| Appunti | appunti di Windows | `wl-clipboard` su Wayland, `xclip` o `xsel` su X11, se installati (nel codice, non ancora provato) |
| Scorciatoie da tastiera di sistema | Ctrl+Alt+S, M e R | **non ci sono** |
| Certificato del proxy e proxy del sistema | archivio dell'utente, impostazioni di proxy | **non ci sono**: su Linux Omissis non tocca i certificati né il proxy del sistema. La finestra separata del browser che passa dal proxy usa un browser Chromium trovato sul computer (su Linux non ancora provata) |
| Impostazioni imposte da chi amministra | registro (criteri) | il file `/etc/omissis/managed.json`, che può scrivere solo chi amministra il computer |
| Toglierlo | il disinstallatore di Windows | «Togli Omissis da questo computer» nelle impostazioni del pannello: il programma va nel cestino, spariscono la voce di menu, il comando e l'avvio all'accesso; i dati restano, a meno che tu chieda di cancellarli |

## Come si costruisce

Il pacchetto non è «congelato». L'archivio contiene una cartella sola, `Omissis.app`, fatta come l'app del Mac e costruita dallo stesso codice (`packaging/mac/build_mac.py`): un Python completo (python-build-standalone), le librerie di `packaging/mac/requirements-mac.txt` e il codice di `app/` e `model/`. La cartella tiene il nome del Mac di proposito: installazione, avvio all'accesso e aggiornamenti usano su Linux il codice già provato sul Mac (`app/macapp.py`). I pesi del modello si scaricano al primo avvio.

```
python3 packaging/linux/build_linux.py --version 0.1.12 --smoke-test   # dist/Omissis.app e dist/Omissis-0.1.12-linux-x86_64.tar.gz
bash packaging/linux/ci_linux.sh 0.1.12                                 # costruzione e tutte le prove, da un utente normale
```

Il flusso `.github/workflows/linux.yml` fa lo stesso su un Ubuntu di GitHub e tiene l'archivio tra i risultati della costruzione. Parte solo a mano e non pubblica nulla.

Per pubblicare una versione per Linux si caricano nella pagina delle versioni, come allegati della versione che «releases/latest» indica: il `.tar.gz`, `update-linux-x86_64.json` e `update-linux-x86_64.json.sig` (il foglio firmato, scritto da chi pubblica, dove sta la chiave delle firme), più `install.sh`.

## Che cosa è stato provato

Il 21 novembre 2026, in Ubuntu 24.04 sotto WSL, con il pacchetto costruito e un utente normale:

- **260 controlli automatici, nessuno mancato** (`ci_linux.sh`): 213 nella serie comune al Mac (archivio, console centrale, inventario, server MCP, gateway, proxy, plugin, documenti con le scansioni lette da Tesseract, la cartella dell'app), 11 sugli aggiornamenti (versione nuova installata, versione rotta sostituita da quella di prima, aggiornamento all'avvio) e 36 nella prova di Linux.
- La prova di Linux (`linux_test.py`) installa con `install.sh` in una cartella utente usa e getta e controlla: l'installatore in italiano e in inglese, un archivio rovinato rifiutato, la voce di menu (verificata con `desktop-file-validate`), l'icona, il comando `omissis`, l'avvio all'accesso (acceso al primo avvio, spento e riacceso dal pannello, spento dalle impostazioni del desktop), la cartella dei dati leggibile solo dal suo utente, un secondo avvio che non fa un doppione, la ricerca dei programmi AI e delle estensioni dei browser, `omissis-hook` dentro e fuori dal PATH, il cestino, le scansioni, la protezione che si accende con il modello già sul disco, `omissis --quit` e il pulsante di chiusura che non lasciano processi accesi, l'installazione sopra una copia accesa, la disinstallazione con e senza i dati.
- Con un portachiavi vero (GNOME Keyring in una sessione D-Bus di prova): 6 controlli su 6. La chiave dell'archivio entra nel portachiavi, l'archivio viene cifrato con quella, e senza il portachiavi lo stesso archivio viene rifiutato invece di essere letto male.
- L'installatore rifiuta root; le impostazioni in `/etc/omissis/managed.json` vengono applicate.
- Il pannello, aperto da un browser che dichiara Linux, mostra le frasi per Linux in italiano e in inglese nelle pagine controllate (Inizio, Testo, Guida, Impostazioni, Collegamenti, Archivio).

Non verificato: nessun desktop Linux vero (GNOME, KDE e gli altri), l'icona, la richiesta del portachiavi quando è chiuso a chiave, l'app vera di Antigravity, il flusso su GitHub (scritto, mai lanciato), il pacchetto per arm64, le distribuzioni diverse da Ubuntu.
