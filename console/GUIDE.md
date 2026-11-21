# Putting the Omissis central console into service

For whoever installs the console on a server of their own. At the end there is a page where the organisations' PCs
show up, which starts by itself with the server and gets a backup every night.

The console is free up to 3 PCs of a single organisation; beyond that a licence is needed (see "The licence", further
down). It is proprietary software, distributed compiled: the terms of use are in `LICENSE.md`.

Italiano: `GUIDA.it.md`.

## Two ways to put it on the network

| | On the local network (default) | Reachable from the Internet |
|---|---|---|
| For whom | Console and PCs on the same network, or joined by a VPN | An MSP following organisations in different places from one spot |
| Address | `https://192.168.1.10:8800`, or the server's name | `https://console.yourdomain.com` |
| Certificate | The console makes it itself on first start | A real one, requested and renewed by Caddy |
| What it takes | Nothing: no public name, no ports 80 and 443, no other programs | A name pointing at the server, ports 80 and 443 open (or a tunnel), Caddy |
| How the PCs recognise it | By the **fingerprint** of the certificate, given together with the key | As a browser recognises a site |

In both cases the connection is encrypted: the PCs accept **only** `https://`, because the summary carries the
organisation's enrolment key.

You need a server that is always on: Windows Server 2019 or later (or Windows 10/11). The console is
light: 1 processor and 1 GB of memory are enough for hundreds of PCs.

## On the local network, on Windows

1. **Unzip** the package `omissis-console-<version>.zip` into any folder on the server.
2. **Install**, from PowerShell opened as administrator, in the unzipped folder:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\Install-Console.ps1
   ```

   The script:
   - copies the program to `C:\OmissisConsole` and closes the folder to ordinary users of the server;
   - registers two scheduled tasks under the low-privilege account LOCAL SERVICE: the console (it starts with the
     server and is restarted if it stops) and the nightly backup of the archive;
   - opens port 8800 in the Windows firewall, for domain and private networks only, never for public ones (if
     Windows treats the server's network as "public", the script says so under `warning`: until the network
     profile becomes "private", the other PCs cannot reach the console);
   - starts the console, which makes its certificate on first start, and at the end prints the address and the
     **fingerprint**.

   The program is compiled and complete (`app\omissis-console.exe`): there is nothing else to install. `-Root D:\Other` changes the folder,
   `-Port` the port, and with `-PruneDays 400` the nightly backup also removes counts older than 400 days.
3. **Create your login**: on the server itself open `https://127.0.0.1:8800/` in a browser. The browser warns that
   it does not know the certificate: that is expected, because no authority signed it; go on ("Advanced", then
   "Proceed"). Seeing that no login exists yet, the page asks for a name and a password (at least 12 characters)
   and lets you in. **It works only from the console's own computer**: nobody on the network can get there before
   you. Right after, a one-minute **guided tour** starts by itself, lighting up the parts of the page one at a time,
   and the "First steps" appear: create an organisation, give the file to the PCs, wait for the first summary.

   If you prefer the terminal, or work without a screen (in an administrator window):

   ```powershell
   C:\OmissisConsole\app\omissis-console.exe --data C:\OmissisConsole\data --add-user yourname --role msp
   ```

4. **From then on you sign in from any PC on the network**: `https://<server name or address>:8800/`, with the
   same certificate warning the first time. To be sure you are talking to the right server, compare the SHA-256
   fingerprint the browser shows in the certificate details with the one printed by the script.

The fingerprint can be read again at any time with `omissis-console.exe --data C:\OmissisConsole\data --show-pin`, and the
page shows it in the organisations card. The certificate stays the same for ten years: it needs no renewal. **Do not
delete the `data\tls` folder**: a new certificate would have a new fingerprint, and every PC would have to be
connected again.

## Reachable from the Internet

This way the console speaks plain HTTP only with the server itself, and a service doing HTTPS with a real
certificate goes in front of it.

1. Install with `.\Install-Console.ps1 -BehindProxy` (it listens only on `127.0.0.1:8800`, no port opened in the
   firewall) and create your login **from the terminal**, with the command above: through the service put in
   front, the page will not create it, because from there it cannot tell you from anyone coming from the Internet.
2. Put [Caddy](https://caddyserver.com/download) in front, a single file: in `C:\Caddy` together with
   `Caddyfile.example` renamed to `Caddyfile`, with your name in place of `console.example.it`. Then, as
   administrator:

   ```powershell
   sc.exe create caddy start= auto binPath= "C:\Caddy\caddy.exe run --config C:\Caddy\Caddyfile"
   sc.exe start caddy
   ```

   Caddy requests the certificate and renews it by itself. If you would rather not open ports, use a tunnel
   (Cloudflare Tunnel or the like) that forwards the name to `http://127.0.0.1:8800`.
3. Open `https://console.yourdomain.com/`: no warning, and the PCs need no fingerprint.

## Connecting the first organisation

1. In the console, **New organisation**: type the name. The address appears, with the **enrolment key** (once only:
   the console keeps just its fingerprint) and, on the local network, the certificate fingerprint.
2. Press **"Download the file for the PCs"**: it is `omissis-console.json`, with those three things already in
   it. To lock other choices too, add them there (the names are in `policy.example.json` of the deployment kit):

   ```json
   {
    "console_url": "https://192.168.1.10:8800",
    "console_key": "omk_...",
    "console_pin": "3f9a...",
    "updates": "never",
    "policies": { "deepseek": "block" }
   }
   ```

3. From your RMM, on each of the organisation's PCs:
   - `Set-OmissisPolicy.ps1 -Settings omissis-console.json` run **as SYSTEM**: it locks the settings and connects
     the PC;
   - `Install-Omissis.ps1 ...` run **as the signed-in user**: it installs the program.
4. Within an hour (or at once, from the PC's panel: Settings, Central console, "Send now") the PC shows up.

To try with a single PC, without an RMM: in that PC's panel, Settings, Central console (in advanced mode), type
the address, the key and the fingerprint by hand.

If the organisation wants to see their own numbers, create a read-only login for them:
`console --data ... --add-user name --role customer --tenant "Organisation name"`.

**Before connecting an organisation** talk to whoever handles privacy there: with the names of computers and users
the console shows how much each person uses AI services, and that can amount to remote monitoring of employees.
With `"console_names": false` in the file only the totals arrive.

## The guide inside the page

At the top right there is the **"Guide"** button. Inside:

- **"Take the tour of the console"**: the same tour as the first sign-in, whenever you want. To anyone signing in for
  the first time from a browser the page offers it by itself, and "Not now" removes the offer.
- **"How far your console is"**: six things to do, marked as done by looking at the real data (an organisation created, a
  PC connected, PCs accepting rules, rules imposed, a destination for alerts, a second login).
- **The topics**, with a search box: connecting PCs, blocking an AI service, preventing protection from being turned
  off, rules for a single PC, alerts, logins, Microsoft sign-in, the log, the licence, backups and passwords. In each
  one **"Show me"** takes you to the right spot on the page and lights it up, one step at a time; where needed it
  picks an organisation by itself, or goes back to "All organisations".

While a tour is open the page underneath stays live: you can click, type and choose without closing it. The arrow keys
move back and forth, and Esc closes it. An organisation with read-only access sees a shorter tour and guide, without what
concerns management.

## Managing the PCs from the console

Four more things, all on the page, for those who follow many PCs. Only the role that manages the console sees and uses
them; an organisation with read-only access sees its own alerts and nothing else.

### Rules for an organisation's PCs

Choose an organisation at the top: the card "Rules for this organisation's PCs" appears. There you set the rules per service
(protect, record, block, ignore), file uploads, attachments, replacement in the writing box, updates, the scan for AI
tools, the **data profile** (what to replace: "Essential", "Confidential", "Special categories" or "Maximum"; fixed
from here, whoever uses the PC cannot change it or reduce protection), and you can forbid turning protection off. "Save and send to the PCs": each PC receives
them in the answer to its next summary, so within an hour, and at once with "Send now" from its panel. With "All
organisations" the card is not there: rules belong to one organisation.

**A PC that must differ from the others.** In the table of PCs every row has a "Rules" button: it opens the rules of
that PC alone, which start from its organisation's. Each item can stay "Same as the organisation", have a value of its own,
which wins over the organisation's, or be "Free on this PC": the PC is exempted from that rule of the organisation, and there
whoever uses it decides again. It is for the technician's PC that must be able to stop protection, for example, or
for someone who works with a service that is blocked for everyone else. The PC's row carries the mark "own rules";
"Back to the organisation's rules" removes them. Every change goes into the compliance log, with the PC's name.

**"Turning protection off: Forbidden".** On the PC the panel's "Stop" button stays disabled, the icon next to the
clock neither stops protection nor quits the program, and if protection is stopped the program starts it again by
itself. It is not a lock: Omissis runs as the user who uses it, and whoever closes it from Task Manager, or uninstalls
it, succeeds. In that case the console says so, with the alert "Protection off" or "Gone quiet".

Three things to know:

- **The PC must have chosen to accept them.** By default a PC ignores the console's rules. It is turned on from the
  panel (Settings → Central console → "Accept rules from this console") or, for all the PCs together, by putting
  `"console_rules": true` in the file you give to `Set-OmissisPolicy.ps1`. The card says how many PCs accept them and
  how many have already applied them.
- **The console cannot move the data.** The list of what can be imposed is closed, and lives both in the console and in
  the program: the address of the console and of the inference server, gateways, folders, and the computer and user
  name in the summary stay out of it. Someone getting into the console without the right could loosen the rules of the
  PCs that accept them, not have their data sent elsewhere.
- **The PC's administrator wins.** A rule written in the PC's Windows registry (`Set-OmissisPolicy.ps1`) counts more
  than the console's. To forbid the console's rules on a PC altogether: `"console_rules": false`, imposed.

### Alerts

The "Alerts" card lists what needs attention: a PC that turned protection off, one that has been quiet for three
days, an AI tool that showed up on a PC that did not have it before. The first two close by themselves when the PC is
fine again; any alert can be closed with "Seen".

With "Where to send them" new alerts also leave the page, within a minute and in a single message:

- to a **web address** (webhook): the message is in the `text` field, the shape accepted by Slack, Mattermost and the
  Teams connectors; the address must start with `https://`;
- by **e-mail**, through an SMTP server (STARTTLS or SSL). The password stays in the console's data, in clear because
  it is needed to send: one more reason to keep the data folder closed. A dedicated mailbox is a good idea.

The message carries the organisation, the computer name and what happened: never the user's name, never counts or texts.
"Send a test alert" tells you at once whether the destination answers. If a send fails the page says so and the
console retries by itself.

### Compliance log

At the bottom of the page: who signed in (or tried), who created or removed logins and organisations, who changed the PC
rules (with the old ones and the new ones), licences loaded, alert destinations, every export. For each row: when,
who, from which address. It downloads as CSV, also for a single organisation.

Rows cannot be changed or deleted from the console, and each one carries a fingerprint that depends on the previous
one: if someone alters or removes a row in the database, the page (and `console --data <data> --verify-audit`) says
from which row the chain breaks. **The limit**: someone with access to the server who rewrites the whole log from
scratch is not caught from here. That is why the page shows the fingerprint of the last row, and every CSV carries it:
noted down now and then outside the server (in a ticket, in an e-mail), it proves what the log was on that day.

The log is never cleaned up automatically, not even by `--prune`. The one from earlier versions (`audit.jsonl`) is
brought in at the first start and the file renamed `audit-importato.jsonl`.

### Logins, and signing in with a Microsoft account

In the "Logins" card you create and remove the console's logins without going through the terminal.

To let people sign in with the organisation's Microsoft account (Entra ID) instead of a name and password:

1. in the Entra admin centre, **App registrations → New registration**, accounts "in this organisation only",
   platform **Web**, with the redirect address the console shows under "Sign-in with Microsoft" (it is the console's
   address followed by `/auth/microsoft/callback`);
2. under **Certificates & secrets** create a client secret;
3. in the console, "Sign-in with Microsoft": paste the directory ID, the application ID and the secret, and enable it;
4. add a login "With a Microsoft account" for each person, with their address. **Only those on that list get in**:
   having an account in the organisation is not enough.

At the first sign-in the login is tied to that exact account: another account that one day took the same address
does not get in. Always keep at least one login with a password, for when Microsoft cannot be reached. The
application secret expires: when it does, create a new one and paste it again. It needs an `https://` address that
Microsoft accepts: with the console on the local network and its self-made certificate the browser will show its
warning.

## The licence

Without a licence the console works, and follows up to **3 PCs of a single organisation**. To follow more you need a
licence file: it says who it is issued to, how many PCs and organisations it covers, and until when. It is signed:
change a number and it stops being valid.

- **Asking for it**: in the "Licence" card press "Request a licence", say who it should be issued to and how many
  PCs and organisations it must cover, and download the file `richiesta-licenza-omissis.json`. Send it to whoever gave
  you the console. Nothing is sent from the page: you send the file.
- The file carries the **installation identifier** (`OMC-XXXX-XXXX-XXXX-XXXX`, shown in the same card and by
  `--licence-info`): the licence you receive is valid on this installation only.
- **Loading it**: from the page, "Licence" card → "Load a licence file"; or from the terminal with
  `--licence <file>`. It applies at once, with no restart.
- **If the server changes** (new computer, system reinstalled) the identifier changes and the licence stops being
  valid: the page says so, and a new one must be requested with the new identifier. No data is lost.
- **Seeing how much is used**: in the same card, or with `--licence-info`.
- **PCs beyond the number covered**: the console keeps the first ones that arrived and does not accept the
  summaries of the others; the page says so at the top. Nothing is deleted: with a wider licence they pick up
  where they were.
- **Expiry**: from thirty days before, the page reminds you. After expiry the licence stays in force for 14 days;
  then the console goes back to 3 PCs and one organisation, until a new one is loaded.

## Day to day

| What | How |
|---|---|
| See organisations and logins | `console --data <data> --list` |
| Change a password | `console --data <data> --set-password name` (it closes the open sessions of that login) |
| Remove a login | `console --data <data> --remove-user name` (or from the "Logins" card) |
| Create a login that signs in with a Microsoft account | `console --data <data> --add-user name@company.com --microsoft` |
| Read the certificate fingerprint again | `console --data <data> --show-pin` |
| Install a licence, see how much is used | `console --data <data> --licence <file>`, `console --data <data> --licence-info` |
| Who signed in and what they changed | The "Compliance log" card on the page, with the CSV to download |
| Check that the log has not been altered | `console --data <data> --verify-audit` |
| Make a backup now | `console --data <data> --backup <folder>` (it works with the console running) |
| Remove old data | `console --data <data> --prune 400` |

Here `console` stands for `C:\OmissisConsole\app\omissis-console.exe` and `<data>` for `C:\OmissisConsole\data`. In a script the password
can be given with `--password-file <file>` instead of typing it. The messages of the terminal are in Italian.

## Backups and restore

Every night at 02:30 a consistent copy of the archive goes to `C:\OmissisConsole\backup`; the last 14 are kept. **Take them off the server too**, with the backup tool
you already use: they are ordinary files. On the local network also save the `data\tls` folder, once: it holds
the certificate, and with it the fingerprint the PCs know.

The licence lives in the data folder (`licence.json`): keep the file you received as well.

To restore: stop the console (the "Omissis Console" scheduled task),
copy the chosen file over `console.sqlite` in the data folder, remove any `console.sqlite-wal` and
`console.sqlite-shm`, start it again.

## Updating and removing

- **Updating**: unzip the new package and run `Install-Console.ps1` again with the same options. It replaces the
  program; data, logins, certificate and backups stay.
- **Removing**: `Install-Console.ps1 -Remove`. It removes the tasks, the firewall rule and the program; `data`
  and `backup` stay where they are, to be deleted by hand when no longer needed.

## If something goes wrong

| What you see | What to check |
|---|---|
| The page does not open from another PC | Does the server answer `ping`? Is the server's network "private" or "domain" for Windows (on a "public" network the port stays closed)? From the server, does `https://127.0.0.1:8800/` open? |
| In the PC's panel: "The console certificate is not the expected one" | The fingerprint on the PC is not the console's (`--show-pin`), or it is missing: on the local network it is always needed |
| In the PC's panel: "Key not accepted" | Wrong key, or a new one was created |
| In the PC's panel: "Console unreachable" | Wrong address or port, firewall, server off |
| "Too many attempts" at sign-in | After five wrong passwords you wait a quarter of an hour |
| Forgotten password | See below, "Forgotten password" |
| All the PCs of an organisation disappear | A new key was created: the old one no longer works, the PCs must be connected again |

### Forgotten password

The console does not e-mail passwords and does not keep them in a form that can be read back: a lost password is not
recovered, **a new one is set**. Whoever has administrator rights on the console's computer does it, the same person
who could reinstall it anyway.

1. On the console's computer open PowerShell **as administrator**.
2. If you do not remember the login's name either: `C:\OmissisConsole\app\omissis-console.exe --data C:\OmissisConsole\data --list`
3. Set the new password (at least 12 characters; it is asked twice and not shown while you type):
   `C:\OmissisConsole\app\omissis-console.exe --data C:\OmissisConsole\data --set-password name`

There is no need to stop the console. That login's open sessions are closed, and the compliance log records that the
password was changed from the terminal. It also works after "Too many attempts": wait the quarter of an hour, or
restart the console.

If nobody can get in any more (the only login used a Microsoft account and Microsoft cannot be reached, or the login
was removed by mistake), a new one is created from the same terminal: `... --add-user new.name --role msp`. Data,
organisations and the licence are not touched.

Someone with a read-only organisation login asks whoever manages the console for a new password.

## What has been tested

On 15 and 16 November 2026: the console's calls (101 checks, including the rules for a single PC); the built-in HTTPS with the real
Omissis program (right fingerprint: the summary arrives; wrong or missing: nothing leaves); the page over HTTPS
with the file to download; the unzipped package, with the **compiled** program, installed in a test folder
**without** registering tasks (`-NoTasks`), started, connected, licensed, backed up, updated and removed (21
checks); the first login created from the page, only from the console's own computer; the licence: free threshold, signed file, tampered file refused, licence of another installation
refused, expiry.

Also on 15 November 2026, `Install-Console.ps1` run as administrator on a Windows 11 in Italian: the console
starts under the service account, the folder is closed to ordinary users, the firewall rule is there (domain and
private networks), the console answers over HTTPS on the PC's network address with the fingerprint printed by the
script, and does not answer in plain HTTP.

That test was made with the earlier package, which carried Python: with the compiled program the installation as
administrator has to be repeated.

The guided tour and the guide are tested automatically in a browser, in Italian and in English (the lit spot is the
right one, the page underneath stays live, "How far your console is" matches the data). The parts of "Managing the PCs from the console" are tested automatically, on the same computer: the rules reach the
real program, which applies them only if it chose to accept them; alerts reach a fake web address and a fake mail
server; the log catches a changed or removed row. **Sign-in with a Microsoft account is tested only against a fake
sign-in service**: it has not yet been tried with a real organisation on Entra ID, nor have alerts towards a real
Teams, Slack or mail server.

**Not tested yet**: a restart of the server and the nightly backup made by the scheduled task; a PC connecting
from another machine on the network; an update over a running installation; Caddy and the real certificate.
