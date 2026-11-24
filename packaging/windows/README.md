# Omissis for Windows: installer, one-command install, build

*[Italiano più sotto](#italiano)*

## Installing

Two ways, same installer:

- download `Omissis-<version>-setup.exe` from the [releases page](https://github.com/francescogruner/omissis/releases/latest)
  and run it;
- or, in Windows Terminal:

  ```powershell
  irm https://omissis.eu/install.ps1 | iex
  ```

Both install for the current user, in `%LOCALAPPDATA%\Programs\Omissis`, without administrator rights. The data of the
person who uses it stays in `%LOCALAPPDATA%\Omissis` and is never touched by the installer.

The command runs [`install.ps1`](install.ps1): it reads `update.json` from the releases page, downloads the installer
named there, checks that size and SHA-256 are the published ones and runs it. Before running the command you may set
`$env:OMISSIS_NO_START = '1'` (install without starting), `$env:OMISSIS_NO_AUTOSTART = '1'` (do not start when you sign
in) or `$env:OMISSIS_HOME` (another folder for the program).

### The blue "Windows protected your PC" window

The installer is not code-signed yet. Windows shows that window for programs it does not know when the file carries the
mark a browser puts on what it downloads from the Internet. With a browser download: click "More info", then "Run
anyway". A file downloaded from the command line does not carry that mark, so with the command above the window does
not appear. On a PC where Smart App Control is on, an unsigned installer can be blocked either way.

## Building

```powershell
python -m pip install pillow
python packaging\windows\build_windows.py --version 0.1.12 --smoke-test
```

Needs Windows, Python 3.12 and Inno Setup 6 (`winget install JRSoftware.InnoSetup`). The script prepares the whole
program in `build\windows\Omissis` (the official "embeddable" Python, the libraries of
[`requirements-windows.txt`](requirements-windows.txt), the code of `app\` and the part of `model\` that recognises
the data) and compiles [`omissis.iss`](omissis.iss) into `dist\Omissis-<version>-setup.exe`. The model weights are not
inside: the program downloads them on first start.

[`ci_windows.ps1`](ci_windows.ps1) builds and then tests on the machine it runs on: it installs with `install.ps1`
from a local, made-up releases page into a throwaway folder, checks that the installed program loads its libraries and
code, checks that a file with a different checksum is refused, and uninstalls. The
[`windows.yml`](../../.github/workflows/windows.yml) workflow runs it on a clean GitHub Windows machine; the installer
stays among the results of the run, it is not published.

The signed update sheet (`update.json` with its signature) is written by whoever publishes, on their own computer,
where the signing key is.

---

<a name="italiano"></a>

# Omissis per Windows: installer, installazione con un comando, costruzione

## Installazione

Due strade, lo stesso installer:

- scaricare `Omissis-<versione>-setup.exe` dalla [pagina delle versioni](https://github.com/francescogruner/omissis/releases/latest)
  e avviarlo;
- oppure, nel Terminale di Windows:

  ```powershell
  irm https://omissis.eu/install.ps1 | iex
  ```

Tutte e due installano per l'utente corrente, in `%LOCALAPPDATA%\Programs\Omissis`, senza diritti di amministratore. I
dati di chi lo usa stanno in `%LOCALAPPDATA%\Omissis` e l'installer non li tocca mai.

Il comando lancia [`install.ps1`](install.ps1): legge `update.json` dalla pagina delle versioni, scarica l'installer
che vi è indicato, controlla che dimensione e impronta SHA-256 siano quelle pubblicate e lo avvia. Prima di lanciare il
comando si possono impostare `$env:OMISSIS_NO_START = '1'` (installa senza avviare), `$env:OMISSIS_NO_AUTOSTART = '1'`
(niente avvio all'accesso a Windows) oppure `$env:OMISSIS_HOME` (un'altra cartella per il programma).

### La finestra blu «PC protetto da Windows»

L'installer non ha ancora la firma del codice. Windows mostra quella finestra per i programmi che non conosce quando il
file porta il segno che il browser mette su ciò che scarica da Internet. Scaricando dal browser: «Ulteriori
informazioni», poi «Esegui comunque». Un file scaricato da riga di comando quel segno non ce l'ha, quindi con il
comando qui sopra la finestra non compare. Su un PC con il «Controllo intelligente delle app» acceso, un installer non
firmato può essere bloccato in tutti e due i casi.

## Costruzione

```powershell
python -m pip install pillow
python packaging\windows\build_windows.py --version 0.1.12 --smoke-test
```

Servono Windows, Python 3.12 e Inno Setup 6 (`winget install JRSoftware.InnoSetup`). Lo script prepara il programma
completo in `build\windows\Omissis` (il Python ufficiale in versione «embeddable», le librerie di
[`requirements-windows.txt`](requirements-windows.txt), il codice di `app\` e la parte di `model\` che riconosce i
dati) e compila [`omissis.iss`](omissis.iss) in `dist\Omissis-<versione>-setup.exe`. I pesi del modello non ci sono: il
programma li scarica al primo avvio.

[`ci_windows.ps1`](ci_windows.ps1) costruisce e poi prova sulla macchina su cui gira: installa con `install.ps1` da una
pagina delle versioni finta servita in locale, in una cartella provvisoria, controlla che il programma installato
carichi librerie e codice, controlla che un file con impronta diversa venga rifiutato, e disinstalla. Il flusso
[`windows.yml`](../../.github/workflows/windows.yml) lo lancia su un Windows pulito di GitHub; l'installer resta tra i
risultati dell'esecuzione, non viene pubblicato.

Il foglio firmato degli aggiornamenti (`update.json` con la sua firma) lo scrive chi pubblica, sul suo computer, dove
sta la chiave delle firme.
