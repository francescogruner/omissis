# Omissis in an organisation: a practical guide

For whoever has to put Omissis on several PCs of an office or of their own customers. It says what is free and
what is not, which layout to choose, how to roll it out and how to turn on the inference server. The details of
each script are in [`README.md`](README.md); those of the program in [`../app/README.it.md`](../app/README.it.md)
(Italian).

Italiano: [`GUIDA-AZIENDE.it.md`](GUIDA-AZIENDE.it.md).

## 1. What is free and what is not

Everything that runs on the PCs is free and open (Apache 2.0 licence), for commercial use too and with no limit
on the number of PCs.

| | Free, in this repository | Paid |
|---|---|---|
| The Windows program and the browser extension | yes | |
| Scripts to install it on many PCs, silently and pre-configured | yes | |
| Settings locked by the administrator | yes | |
| Inference server on the network (one PC lends its model to the others) | yes | |
| State of each PC read by your RMM (`Get-OmissisStatus.ps1`) | yes | |
| **Central console**: all the PCs on one page, up to 5 PCs of one customer | yes, but not open source | |
| Central console beyond 5 PCs, or for several customers (MSP) | | yes, with a licence |

**What the console adds.** How many PCs have Omissis and which ones need attention (protection off, PCs that
have gone quiet, old versions), how much data was kept away from AI services in total, per day, per type of data
and per service, and the AI tools found on the PCs. For an MSP: several separate customers, with a read-only
login for each customer. It receives counts and program names only, never the texts.

**How to try it and how to move to a licence.** There is no other edition of Omissis to install and no licence
code goes on the PCs: the program for the PCs stays the free one. The console is a separate program, compiled (its
code is not in this repository): its guide is in [`../console/README.md`](../console/README.md).

1. Download `omissis-console-<version>.zip` from the
   [releases page](https://github.com/francescogruner/omissis/releases/latest) and install it on a computer of your
   own, on the local network too. On first opening, the page has you create your login and walks you through the
   first steps.
2. For each customer the console gives an **enrolment key** and a file with three settings: `console_url`,
   `console_key` and, on the local network, `console_pin`. They go on the PCs with `Set-OmissisPolicy.ps1`, all at
   once, or by hand from each panel (Settings → Central console, in the advanced view).
3. Within an hour the PCs show up in the console. Remove the three settings and everything is as before.
4. **Beyond 5 PCs, or with more than one customer**: in the console, "Licence" card → "Request a licence". It
   prepares a file with the identifier of the installation; send it from <https://francescogruner.it/contatti/> and
   you get back a licence file to load in the same card.

## 2. Which layout to choose

| Layout | When | What it takes |
|---|---|---|
| **A. Every PC with its own model** (default) | The PCs have at least 8 GB of memory | Nothing: each PC works by itself, out of the office too |
| **B. One PC lends its model to the others** | PCs with little memory, old PCs, terminals | A PC that is always on, with the user signed in, reachable on the network |
| **C. Mixed** | Weak desktops and laptops that travel | Desktops as in B, laptops as in A |

With layout A each PC keeps the model in memory (1.2 to 1.5 GB with the small one) and depends on nobody. With
layout B the PCs neither load nor download the model, but **if the server does not answer, their messages to
protected services are stopped**: they do not leave in clear, and there is no fallback to a local model. A laptop
outside the office network stays blocked until it is back (or uses a VPN).

## 3. Rolling out the program

Omissis installs **for the single user**, without administrator rights: the scripts must run as the user who
uses the PC, not as SYSTEM. The only exception is `Set-OmissisPolicy.ps1`.

| Method | How |
|---|---|
| By hand | The user runs `Omissis-<version>-setup.exe`: on first start the guided setup walks them through |
| Script from a share | `Install-Omissis.ps1` with the installer, its hash and the settings file |
| RMM (NinjaOne and the like) | An automation that runs the same script, executed as the signed-in user |
| Intune | Win32 app with install behaviour "User" and `Get-OmissisStatus.ps1` as detection rule |
| Group Policy | A user logon script that runs `Install-Omissis.ps1` |

```powershell
powershell -ExecutionPolicy Bypass -File Install-Omissis.ps1 `
  -Installer "\\server\software\Omissis-0.1.0-setup.exe" -Sha256 "<hash>" `
  -Settings "\\server\software\customer.json" -ModelSource "\\server\software\models"
```

`-ModelSource` saves each PC from downloading the model by itself; with layout B it is not needed.

## 4. The inference server, step by step

**On the PC that lends the model**

1. Install Omissis as on any other PC and let it download the model.
2. Open the panel, turn on "Advanced mode", go to Settings → Recognition → **Inference server on the network**
   and press "Lend the model to the network". Protection restarts in a few seconds.
3. The first time Windows asks whether to allow network access: choose private networks. Or, as administrator:

   ```powershell
   New-NetFirewallRule -DisplayName "Omissis inference server" -Direction Inbound -Action Allow `
     -Protocol TCP -LocalPort 8770 -Profile Domain,Private
   ```

4. Press "Copy the configuration" and save it to a file, for example `server.json`. It holds the address, the key
   and the certificate fingerprint: **treat it like a password**.

   ```json
   {"engine_url": "https://server-pc:8770", "engine_key": "oms_…", "engine_pin": "…"}
   ```

5. If the PC's name is not found on the network, replace it in the file with its address (the page lists them),
   and in that case give the PC an address that does not change.

**On the other PCs**, in one of these ways:

- **By hand**: in the same card of the panel paste the configuration and press "Use this server". Omissis tries
  to connect before saving it.
- **With the installation**: `Install-Omissis.ps1 -Settings server.json`. The PC starts without downloading the
  model. The user can change the setting from the panel.
- **Locked**: `Set-OmissisPolicy.ps1 -Settings server.json`, as administrator. The user cannot change it.

**Checking.** On the PC, the Home page says "Model … on a server on the network". On the server, the card lists
the PCs that have asked for recognition and how many texts: counts only, since protection was started.

**Good to know**

- The text to check travels over the network, encrypted, and only the positions of the data found come back.
  Placeholders, real values, rules and lists stay on each PC; the server writes nothing of what it receives.
- Omissis is not a Windows service: the server answers **as long as the user is signed in on that PC and
  Omissis is running**. Leave it on, with sleep disabled.
- The server checks one text at a time. For a small office that is enough; with many PCs writing at once the
  requests queue up. How many PCs it can serve has not been measured.
- To go back: on the PC "Go back to this PC's model" (or remove the three settings); on the server "Stop
  lending it".
- To change the key: on the server stop lending, delete the `server` folder in Omissis's data
  (`%LOCALAPPDATA%\Omissis\server`) and turn it on again. The certificate changes too: the PCs must be
  configured again.

## 5. Locking the settings

`Set-OmissisPolicy.ps1 -Settings lock.json`, as administrator or SYSTEM, writes the settings to a part of the
registry the user cannot change: in the panel those controls stay visible but disabled. This is how you lock the
rules for the services (for example `"deepseek": "block"`), the model, the updates, the inference server and the
connection to the console. On the services with an imposed rule the browser extension cannot be paused either.

It is not a defence against someone who tampers with the program, which is installed in the user's profile: for
that, use Windows tools (AppLocker, application control).

## 6. The browser extension

The scripts install the program, not the extension. Until it is published on the stores it is loaded by hand
from the folder shown in the panel; right after installation it opens a page with a "Connect this browser"
button. Once published it will install with one click and can be forced with the `ExtensionInstallForcelist`
policy of Chrome and Edge.

## 7. If something goes wrong

| What you see | What to check |
|---|---|
| On the PC: "The inference server … is not answering" | Is the server on, with the user signed in and Omissis active? Does the server's card say "listening"? |
| "The server cannot be reached" while pasting the configuration | The server's firewall (port 8770), the server's network marked "public" in Windows, the PC's name not found: try the address |
| "The server's certificate is not the expected one" | The fingerprint is not the server's: copy the whole configuration again |
| "The server refused the key" | Wrong key, or changed on the server |
| On the server: "not listening: port is in use" | Another program uses port 8770: change it with the `serve_port` setting |
| A PC does not show up in the console | Are the three settings there? On the PC's panel, Settings → Central console says what is wrong |

## 8. What is tested and what is not

Tested with automatic tests on a single computer: silent installation, locked settings, the summary, and the
inference server with two copies of the program on the same PC (one without a model), over HTTPS with key and
fingerprint.

**Not tested yet**: the inference server between two real PCs on a network and with the Windows firewall,
several PCs at once, an actual RMM or Intune, `Set-OmissisPolicy.ps1` as administrator on a PC with Omissis
installed.
