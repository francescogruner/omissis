# Installing Omissis: instructions for an AI agent

You are an AI agent with a shell on a Windows PC, and the person you work for asked you to install
[Omissis](https://omissis.eu). Follow the steps below in order. Talk to the person in their own language.

Omissis is a program that runs on the PC and replaces personal data with placeholders before text reaches an AI
service, then puts the real values back in the answer. It also keeps an inventory of the AI tools used on the PC and
lets the person protect, record or block each service. Everything runs locally: nothing is sent to the author.

## Ground rules

1. **Ask before every step marked ASK**, and say in one line what the step changes on the computer.
2. **Never use administrator rights.** Omissis installs per user, in the user's profile. If something asks for
   elevation, stop and tell the person.
3. **Never work around a failed check.** If a hash does not match, a download fails or a script exits with an
   error, stop and report the exact output. Do not retry with a different source.
4. **Use made-up data only** for tests. Never paste the person's real data into an AI service to "see if it works".
5. **Do not read the vault.** The files `vault.sqlite`, `vault_key.bin`, `token.txt` and `token_extension.txt` in
   `%LOCALAPPDATA%\Omissis` hold the real values and the local codes: do not open them, do not print them.
6. **Do not turn protection off** and do not change settings the panel shows as locked: someone manages this PC.
7. Run everything **as the person who uses the PC**, in PowerShell, not as SYSTEM.

## Step 0. Check the computer

```powershell
$os = Get-CimInstance Win32_OperatingSystem
"{0} {1}-bit, {2} GB of memory" -f $os.Caption, $os.OSArchitecture, [math]::Round($os.TotalVisibleMemorySize / 1MB)
"free on the system disk: {0} GB" -f [math]::Round((Get-PSDrive $env:SystemDrive[0]).Free / 1GB)
Test-Path "$env:LOCALAPPDATA\Programs\Omissis\installed.json"
```

Needed: Windows 10 or 11, 64-bit, 8 GB of memory, 2 GB of free disk. No graphics card is needed.
If the last line prints `True`, Omissis is already installed: go to step 3.

## Step 1. Download and verify

```powershell
$ProgressPreference = 'SilentlyContinue'
$base = "https://github.com/francescogruner/omissis/releases/latest/download"
$dir = Join-Path $env:TEMP "omissis-install"
New-Item -ItemType Directory -Force $dir | Out-Null
Invoke-WebRequest "$base/update.json" -OutFile "$dir\update.json"
$sheet = Get-Content "$dir\update.json" -Raw | ConvertFrom-Json
Invoke-WebRequest "$base/$($sheet.file)" -OutFile "$dir\$($sheet.file)"
$hash = (Get-FileHash "$dir\$($sheet.file)" -Algorithm SHA256).Hash.ToLower()
"version $($sheet.version), hash matches: $($hash -eq $sheet.sha256)"
```

`update.json` names the installer and gives its SHA-256. If the last line does not end with `True`, **stop**.
The installer is about 53 MB. It is not code-signed yet: that is why the hash check matters.

## Step 2. Install (ASK)

Tell the person: "I am about to install Omissis for your Windows user, in your profile, without administrator
rights. On first start it downloads its model, about 540 MB."

```powershell
$raw = "https://raw.githubusercontent.com/francescogruner/omissis/main/deploy"
Invoke-WebRequest "$raw/Install-Omissis.ps1" -OutFile "$dir\Install-Omissis.ps1"
Invoke-WebRequest "$raw/Get-OmissisStatus.ps1" -OutFile "$dir\Get-OmissisStatus.ps1"
powershell -ExecutionPolicy Bypass -File "$dir\Install-Omissis.ps1" -Installer "$dir\$($sheet.file)" -Sha256 $sheet.sha256
"exit code: $LASTEXITCODE"
```

The script checks the hash again, installs silently, starts Omissis and waits for protection to come up.

| Exit code | Meaning | What to do |
|---|---|---|
| 0 | Installed, protection is on | Go to step 3 |
| 4 | Installed, protection not up yet | The model is still downloading: wait a few minutes, then step 3 |
| 2 | Installer missing or wrong hash | Stop and report |
| 3 | Installation failed | Stop and report the output |

## Step 3. Check that it works

```powershell
powershell -ExecutionPolicy Bypass -File "$dir\Get-OmissisStatus.ps1"
"exit code: $LASTEXITCODE"
```

One line of JSON with version, model and state. Exit code `0` means protection is on, `1` installed but off,
`2` not installed. If it is `1` right after installing, wait for the model and run it again.

The panel is at <http://127.0.0.1:8766>. Tell the person to open it: on first start it shows a short guided setup.
Do not go through that setup for them.

## Step 4. Connect the tools (ASK for each one)

Omissis protects only what passes through it. Ask the person which of these they use, and connect only those.

**The browser.** The extension is installed by the person, from the panel: Connections, Browser. You cannot do it
for them. Say so.

**The tool you are running in.** If you are one of the tools below, connect yourself. First ask the person to
press **Install the command** in the panel (Connections, Desktop apps, "Plugins for AI apps and tools"): it puts the
`omissis-hook` command on their PATH. Then, in a new terminal:

| Tool | Command |
|---|---|
| Claude Code | `claude plugin marketplace add francescogruner/omissis-plugin` then `claude plugin install omissis@omissis` |
| Codex | `codex plugin marketplace add francescogruner/omissis-plugin`, enable Omissis among the plugins, then have the person approve its hook with `/hooks` |
| Gemini CLI | `gemini extensions install https://github.com/francescogruner/omissis-plugin` |
| Kimi | `/plugins install https://github.com/francescogruner/omissis-plugin` |

A plugin checks every message before it is sent and stops those that hold personal data: the protected version
goes to the clipboard, to paste. Claude Code and Codex can instead be sent through the Omissis gateway, which
replaces the data for real: the exact line is in the panel, Connections, Terminal. Use one or the other, not both.

**Desktop apps** (ChatGPT, Claude, Copilot). They are started protected from the panel: Connections, Desktop apps.
Starting one closes and reopens it: the person does it, when the app is not working on something.

## Step 5. What gets protected

By default Omissis replaces people and contacts, identifiers (tax codes, documents), payments and IT data
(passwords, keys, IP addresses, domains, accounts). Company names stay in clear, because they are not personal data.
Ask the person whether they want more, and tell them where to choose: panel, Settings, Recognition, **Profile**.

| Profile | Adds |
|---|---|
| Essential (default) | people, identifiers, payments, IT data |
| Confidential | company and organisation names |
| Special categories | health, religion, political opinions, orientation, origin |
| Maximum | everything the model recognises: dates, age, profession, places |

Each AI service has a rule: Protect, Record, Block or Ignore (panel, AI services). Only Claude, ChatGPT and their
APIs start on Protect: the others start on Record until the person chooses.

## Step 6. Test with made-up data (ASK)

Ask the person to paste this sentence, as it is, into one of the tools you connected:

```
Write to Giulia Ferraresi (giulia.ferraresi@nevatek.example, mobile 347 5551234): the refund goes to
IBAN IT60X0542811101000000123456.
```

What must happen: the name, the address, the number and the IBAN are replaced by placeholders such as
`[PERSONA_1]` before the message leaves, or, with a plugin, the message is stopped and the protected version is on
the clipboard. The panel, under Activity, shows a row with the count of replaced data. If the real values reach
the service, the test **failed**: say so plainly and do not call the installation done.

## Step 7. Report

End with a short report, in the person's language:

- the version installed and whether protection is on;
- which tools you connected, and how (plugin or gateway);
- which steps are left to the person (the browser extension, the desktop apps, the test if they skipped it);
- anything that failed, with the exact output.

## For an organisation

To install on many PCs, lock settings for every user and follow the PCs from one page, do not repeat this
procedure by hand: use the deployment kit and its guide,
<https://github.com/francescogruner/omissis/blob/main/deploy/GUIDE-ORGANISATIONS.md>.

## Removing

```powershell
Invoke-WebRequest "$raw/Uninstall-Omissis.ps1" -OutFile "$dir\Uninstall-Omissis.ps1"
powershell -ExecutionPolicy Bypass -File "$dir\Uninstall-Omissis.ps1"
```

It removes the program and keeps the person's data. Add `-RemoveData` only if they ask to delete the vault too:
it cannot be undone.
