# Deploying Omissis to many PCs

Four PowerShell scripts for whoever manages the computers of an organisation or of several customers (an MSP):
install Omissis silently and pre-configured, lock its settings, check its state, remove it. They work with anything that can run a
script: an RMM tool, Intune, a logon script. The full reference of the scripts is in Italian: [README.it.md](README.it.md).

**Where to start**: [`GUIDE-ORGANISATIONS.md`](GUIDE-ORGANISATIONS.md) says what is free and what is not, which
layout to choose (every PC with its own model, or one PC lending it to the others) and how to turn on the
inference server, step by step.

| File | What it is for |
|---|---|
| `Install-Omissis.ps1` | Silent install, customer settings, model from a folder of yours, protection started |
| `Set-OmissisPolicy.ps1` | Locks the chosen settings for every user of the PC. The only one to run **as administrator** |
| `Get-OmissisStatus.ps1` | One line of JSON with the state on that PC; with `-MinVersion` it is a detection rule |
| `Uninstall-Omissis.ps1` | Removes the program; with `-RemoveData` the user's data too |
| `settings.example.json` | Template of the customer's choices (the user can change them) |
| `policy.example.json` | Template of the locked settings (the user cannot change them) |

**Run them as the user who uses the PC**, not as SYSTEM: Omissis installs per user, without administrator rights,
and its vault is encrypted and tied to that user. The one exception is `Set-OmissisPolicy.ps1`, which runs as
administrator or SYSTEM, once per PC.

```powershell
powershell -ExecutionPolicy Bypass -File Install-Omissis.ps1 `
  -Installer "\\server\software\Omissis-0.1.0-setup.exe" -Sha256 "<hash from the signed update.json>" `
  -Settings "\\server\software\customer.json" -ModelSource "\\server\software\models"
```

The installer is refused unless its SHA-256 matches; each model file is accepted only if size and hash match the
list shipped with the program. Exit codes: `0` done, `2` installer not obtained or wrong hash, `3` installation
failed, `4` installed but protection not up yet.

**Locked settings.** `Set-OmissisPolicy.ps1 -Settings policy.json` writes the settings under
`HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Omissis`, which standard users cannot change. Omissis reads that key: what
it finds there wins over the user's choices and shows as locked in the panel. On the services listed under
`policies` the browser extension cannot be paused from its popup either. There is no password: whoever has
administrator rights on the PC decides. It is not a defence against a user who tampers with the program, which
is installed in the user's own profile.

**Central console.** Off by default: Omissis sends nothing to anyone. With `console_url` (https) and
`console_key` set, each PC sends an hourly summary made of counts (version and state, how many values were
replaced per type and per AI service, requests stopped, names and versions of the AI tools found): never texts,
never the replaced values. The panel shows the user where the PC is connected and the exact summary. Per-person
counts can amount to monitoring of employees: check with whoever handles privacy first, or set
`"console_names": false`. The protocol is open (`app/central.py`); the console is a separate program, not open
source: it is downloaded compiled from the releases page and is free up to 5 PCs (see
[`../console/README.md`](../console/README.md)). A console on the local network, with a certificate it made itself and no public name, is recognised
by `console_pin`, the SHA-256 fingerprint of that certificate: the PC connects only to the server presenting it,
and checks before sending the key. Without `console_pin` the certificate must be valid as for a browser.
With `"console_rules": true` the PC applies the rules the console sends back with each summary (per service, files,
attachments, updates, scan, reduced protection, the ban on turning protection off: nothing else). It is off by default,
and whatever is written in this registry key always wins over the console's rules.

`"always_on": true` in the locked settings means protection cannot be stopped from the panel or from the icon next to
the clock, and the program cannot be quit from the icon. It does not stop a user who closes it from Task Manager.

Tested on 14 November 2026 on a single Windows 11 PC with Windows PowerShell 5.1 (silent install in 21 seconds,
state, removal with nothing left behind); `Set-OmissisPolicy.ps1` on a scratch key of the user and, without
administrator rights, on the real key, where it refuses. Not yet tested: `Set-OmissisPolicy.ps1` actually run as
administrator on a PC with Omissis installed, and an actual RMM or Intune.
