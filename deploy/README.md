# Deploying Omissis to many PCs

Three PowerShell scripts for whoever manages the computers of an organisation or of several customers (an MSP):
install Omissis silently and pre-configured, check its state, remove it. They work with anything that can run a
script: an RMM tool, Intune, a logon script. The full guide is in Italian: [README.it.md](README.it.md).

| File | What it is for |
|---|---|
| `Install-Omissis.ps1` | Silent install, customer settings, model from a folder of yours, protection started |
| `Get-OmissisStatus.ps1` | One line of JSON with the state on that PC; with `-MinVersion` it is a detection rule |
| `Uninstall-Omissis.ps1` | Removes the program; with `-RemoveData` the user's data too |
| `settings.example.json` | Template of the customer's choices |

**Run them as the user who uses the PC**, not as SYSTEM: Omissis installs per user, without administrator rights,
and its vault is encrypted and tied to that user.

```powershell
powershell -ExecutionPolicy Bypass -File Install-Omissis.ps1 `
  -Installer "\\server\software\Omissis-0.1.0-setup.exe" -Sha256 "<hash from the signed update.json>" `
  -Settings "\\server\software\customer.json" -ModelSource "\\server\software\models"
```

The installer is refused unless its SHA-256 matches; each model file is accepted only if size and hash match the
list shipped with the program. Exit codes: `0` done, `2` installer not obtained or wrong hash, `3` installation
failed, `4` installed but protection not up yet.

Tested on 14 November 2026 on a single Windows 11 PC with Windows PowerShell 5.1 (silent install in 21 seconds,
state, removal with nothing left behind). Not yet tested through an actual RMM or Intune.
