# Omissis for winget: the package manifest

*[Italiano più sotto](#italiano)*

winget is the package manager that ships with Windows 10 and 11. Its public catalogue lives in
[microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs): one folder of YAML files (a "manifest") per version
of each program, with the address of the installer and its SHA-256. This folder holds what writes and tests the
manifest of Omissis.

- [`make_manifest.py`](make_manifest.py) writes the manifest of a published version: the installer comes from the
  [releases page](https://github.com/francescogruner/omissis/releases), its SHA-256 and date are read from there, the
  texts are in English and Italian.

  ```powershell
  python packaging\winget\make_manifest.py --version 0.1.13
  winget validate --manifest build\winget\manifests\f\FrancescoGruner\Omissis\0.1.13
  ```

- [`ci_winget.ps1`](ci_winget.ps1) tests it on a clean Windows (the "Scheda per winget" workflow, started by hand):
  winget installs from the manifest without asking anything, the installed program loads its libraries, Windows lists
  it with the name, version and publisher of the manifest, winget removes it; then an upgrade from the previous
  version, after which Omissis is running again.

The manifest uses the same installer as the other two ways of installing (see [`../windows`](../windows/README.md)):
for the current user, in `%LOCALAPPDATA%\Programs\Omissis`, without administrator rights. During an upgrade winget
passes `/RIAVVIA=1`, so the installer reopens Omissis when it has finished.

<a name="italiano"></a>

## Italiano

winget è il gestore di pacchetti che arriva con Windows 10 e 11. Il suo catalogo pubblico sta in
[microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs): per ogni versione di ogni programma una cartella di
file YAML (la «scheda»), con l'indirizzo dell'installer e la sua impronta SHA-256. In questa cartella c'è ciò che
scrive e prova la scheda di Omissis.

- [`make_manifest.py`](make_manifest.py) scrive la scheda di una versione pubblicata: l'installer è quello della
  [pagina delle versioni](https://github.com/francescogruner/omissis/releases), impronta e data si leggono da lì, i
  testi sono in inglese e in italiano.
- [`ci_winget.ps1`](ci_winget.ps1) la prova su un Windows pulito (il flusso «Scheda per winget», che parte a mano):
  winget installa dalla scheda senza chiedere nulla, il programma installato carica le sue librerie, Windows lo elenca
  con nome, versione e autore della scheda, winget lo toglie; poi un aggiornamento dalla versione precedente, dopo il
  quale Omissis è di nuovo acceso.

La scheda usa lo stesso installer degli altri due modi di installare (vedi [`../windows`](../windows/README.md)): per
l'utente corrente, in `%LOCALAPPDATA%\Programs\Omissis`, senza diritti di amministratore. In un aggiornamento winget
passa `/RIAVVIA=1`, così l'installer alla fine riapre Omissis.
