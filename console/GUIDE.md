# Putting the Omissis central console into service

For whoever installs the console on a server of their own. At the end there is a page where the customers' PCs
show up, which starts by itself with the server and gets a backup every night.

The console is free up to 5 PCs of a single customer; beyond that a licence is needed (see "The licence", further
down). It is proprietary software, distributed compiled: the terms of use are in `LICENSE.md`.

Italiano: `GUIDA.it.md`.

## Two ways to put it on the network

| | On the local network (default) | Reachable from the Internet |
|---|---|---|
| For whom | Console and PCs on the same network, or joined by a VPN | An MSP following customers in different places from one spot |
| Address | `https://192.168.1.10:8800`, or the server's name | `https://console.yourdomain.com` |
| Certificate | The console makes it itself on first start | A real one, requested and renewed by Caddy |
| What it takes | Nothing: no public name, no ports 80 and 443, no other programs | A name pointing at the server, ports 80 and 443 open (or a tunnel), Caddy |
| How the PCs recognise it | By the **fingerprint** of the certificate, given together with the key | As a browser recognises a site |

In both cases the connection is encrypted: the PCs accept **only** `https://`, because the summary carries the
customer's enrolment key.

You need a server that is always on: Windows Server 2019 or later (or Windows 10/11), or Linux. The console is
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
   you. Right after, the page shows the "First steps": create a customer, give the file to the PCs, wait for the
   first summary.

   If you prefer the terminal, or work without a screen (in an administrator window):

   ```powershell
   C:\OmissisConsole\app\omissis-console.exe --data C:\OmissisConsole\data --add-user yourname --role msp
   ```

4. **From then on you sign in from any PC on the network**: `https://<server name or address>:8800/`, with the
   same certificate warning the first time. To be sure you are talking to the right server, compare the SHA-256
   fingerprint the browser shows in the certificate details with the one printed by the script.

The fingerprint can be read again at any time with `omissis-console.exe --data C:\OmissisConsole\data --show-pin`, and the
page shows it in the customers card. The certificate stays the same for ten years: it needs no renewal. **Do not
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

## On Linux

For Linux and Docker there is a separate package, `omissis-console-<version>-linux.zip`, with the program in
Python: ask for it from <https://francescogruner.it/contatti/>. You need Python 3.10 or later, which recent distributions already have.
As root, from the unzipped folder:

```bash
useradd --system --home /nonexistent --shell /usr/sbin/nologin omissis
install -d /opt/omissis-console && cp -r app /opt/omissis-console/
install -d -o omissis -g omissis -m 750 /var/lib/omissis-console
cp linux/omissis-console*.service linux/omissis-console-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now omissis-console.service omissis-console-backup.timer
sudo -u omissis python3 /opt/omissis-console/app/console.py --data /var/lib/omissis-console --add-user yourname --role msp
```

The service file is written for the "reachable from the Internet" way, with Caddy in front (`Caddyfile.example`
as `/etc/caddy/Caddyfile`). For the local network, in the `ExecStart` line put `--https --host 0.0.0.0` in place
of `--secure-cookie`: making the certificate needs the `openssl` command or the `python3-cryptography` package.

**With Docker**, as an alternative (again with Caddy in front): put the real name in `docker/Caddyfile`, then
`docker compose -f docker/compose.yaml up -d --build`. The login is created with
`docker compose -f docker/compose.yaml exec console python console.py --data /data --add-user yourname --role msp`.

## Connecting the first customer

1. In the console, **New customer**: type the name. The address appears, with the **enrolment key** (once only:
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

3. From your RMM, on each of the customer's PCs:
   - `Set-OmissisPolicy.ps1 -Settings omissis-console.json` run **as SYSTEM**: it locks the settings and connects
     the PC;
   - `Install-Omissis.ps1 ...` run **as the signed-in user**: it installs the program.
4. Within an hour (or at once, from the PC's panel: Settings, Central console, "Send now") the PC shows up.

To try with a single PC, without an RMM: in that PC's panel, Settings, Central console (in advanced mode), type
the address, the key and the fingerprint by hand.

If the customer wants to see their own numbers, create a read-only login for them:
`console --data ... --add-user name --role customer --tenant "Customer name"`.

**Before connecting a customer** talk to whoever handles privacy there: with the names of computers and users
the console shows how much each person uses AI services, and that can amount to remote monitoring of employees.
With `"console_names": false` in the file only the totals arrive.

## The licence

Without a licence the console works, and follows up to **5 PCs of a single customer**. To follow more you need a
licence file: it says who it is issued to, how many PCs and customers it covers, and until when. It is signed:
change a number and it stops being valid.

- **Asking for it**: in the "Licence" card press "Request a licence", say who it should be issued to and how many
  PCs and customers it must cover, and download the file `richiesta-licenza-omissis.json`. Send it to whoever gave
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
  then the console goes back to 5 PCs and one customer, until a new one is loaded.

## Day to day

| What | How |
|---|---|
| See customers and logins | `console --data <data> --list` |
| Change a password | `console --data <data> --set-password name` (it closes the open sessions of that login) |
| Remove a login | `console --data <data> --remove-user name` |
| Read the certificate fingerprint again | `console --data <data> --show-pin` |
| Install a licence, see how much is used | `console --data <data> --licence <file>`, `console --data <data> --licence-info` |
| Who signed in and what they changed | `<data>\audit.jsonl`: successful and failed sign-ins, customers created, keys changed, PCs removed, licences loaded |
| Make a backup now | `console --data <data> --backup <folder>` (it works with the console running) |
| Remove old data | `console --data <data> --prune 400` |

Here `console` stands for `C:\OmissisConsole\app\omissis-console.exe` on Windows (where `<data>` is
`C:\OmissisConsole\data`) and for `python3 /opt/omissis-console/app/console.py` on Linux. In a script the password
can be given with `--password-file <file>` instead of typing it. The messages of the terminal are in Italian.

## Backups and restore

Every night at 02:30 a consistent copy of the archive goes to `C:\OmissisConsole\backup` (on Linux
`/var/lib/omissis-console/backup`); the last 14 are kept. **Take them off the server too**, with the backup tool
you already use: they are ordinary files. On the local network also save the `data\tls` folder, once: it holds
the certificate, and with it the fingerprint the PCs know.

The licence lives in the data folder (`licence.json`): keep the file you received as well.

To restore: stop the console (on Windows the "Omissis Console" task; on Linux `systemctl stop omissis-console`),
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
| All the PCs of a customer disappear | A new key was created: the old one no longer works, the PCs must be connected again |

## What has been tested

On 15 November 2026: the console's calls (39 checks) on Windows and on Linux; the built-in HTTPS with the real
Omissis program (right fingerprint: the summary arrives; wrong or missing: nothing leaves); the page over HTTPS
with the file to download; the unzipped package, with the **compiled** program, installed in a test folder
**without** registering tasks (`-NoTasks`), started, connected, licensed, backed up, updated and removed (22
checks); the first login created from the page, only from the console's own computer; the licence: free threshold, signed file, tampered file refused, licence of another installation
refused, expiry.

Also on 15 November 2026, `Install-Console.ps1` run as administrator on a Windows 11 in Italian: the console
starts under the service account, the folder is closed to ordinary users, the firewall rule is there (domain and
private networks), the console answers over HTTPS on the PC's network address with the fingerprint printed by the
script, and does not answer in plain HTTP.

That test was made with the earlier package, which carried Python: with the compiled program the installation as
administrator has to be repeated.

**Not tested yet**: a restart of the server and the nightly backup made by the scheduled task; a PC connecting
from another machine on the network; an update over a running installation; Caddy and the real certificate; the
files for systemd and for Docker.
