# Omissis per Windows: installazione con un comando, per l'utente che lo lancia. Non chiede diritti di amministratore.
# Omissis for Windows: one-command installation for the user who runs it. It does not ask for administrator rights.
#
#   irm https://omissis.eu/install.ps1 | iex
#
# Che cosa fa: legge update.json dalla pagina delle versioni, scarica l'installer che vi e' indicato, controlla che
# dimensione e impronta SHA-256 siano quelle pubblicate e lo avvia. L'installer mette il programma in
# %LOCALAPPDATA%\Programs\Omissis; i dati di chi lo usa stanno in %LOCALAPPDATA%\Omissis e non vengono toccati:
# rilanciare il comando aggiorna il programma e basta. Per toglierlo: Impostazioni di Windows > App > Omissis.
# What it does: reads update.json from the releases page, downloads the installer named there, checks that size and
# SHA-256 are the published ones and runs it. Running the command again only updates the program.
#
# Prima di lanciare il comando si possono impostare / Before running the command you may set:
#   $env:OMISSIS_NO_START = '1'       installa senza avviare / install without starting
#   $env:OMISSIS_NO_AUTOSTART = '1'   senza avvio all'accesso a Windows / without starting when you sign in
#   $env:OMISSIS_HOME = 'C:\...'      un'altra cartella per il programma / another folder for the program
#
# Il file e' in soli caratteri ASCII: cosi' arriva intero comunque lo serva la rete. / ASCII only, on purpose.

& {
    $ErrorActionPreference = 'Stop'
    $italian = (Get-UICulture).TwoLetterISOLanguageName -eq 'it'
    $e = [string][char]0xE8
    function Say([string]$it, [string]$en) { if ($italian) { Write-Host $it } else { Write-Host $en } }
    function Fail([string]$it, [string]$en) { if ($italian) { throw $it } else { throw $en } }

    $origin = if ($env:OMISSIS_UPDATES_URL) { $env:OMISSIS_UPDATES_URL.TrimEnd('/') } else { 'https://github.com/francescogruner/omissis/releases/latest/download' }
    $program = if ($env:OMISSIS_HOME) { $env:OMISSIS_HOME } else { Join-Path $env:LOCALAPPDATA 'Programs\Omissis' }
    $work = Join-Path ([IO.Path]::GetTempPath()) ('omissis-install-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    $failed = $false
    try {
        if (-not [Environment]::Is64BitOperatingSystem) { Fail "questo installatore $e per Windows a 64 bit." 'this installer is for 64-bit Windows.' }
        # Omissis si installa nel profilo di chi lancia il comando. Un terminale aperto "come amministratore" con le
        # credenziali di un altro utente lo metterebbe nel profilo sbagliato: in quel caso ci si ferma.
        $me = [Security.Principal.WindowsIdentity]::GetCurrent()
        if ((New-Object Security.Principal.WindowsPrincipal($me)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            $desk = try { [string](Get-CimInstance Win32_ComputerSystem).UserName } catch { '' }
            if ($desk -and $desk -ne $me.Name) {
                Fail "questo terminale $e aperto con un altro utente ($($me.Name)): Omissis finirebbe nel suo profilo, non nel tuo. Apri il Terminale normale e rilancia il comando." `
                     "this terminal runs as another user ($($me.Name)): Omissis would end up in that profile, not yours. Open the regular Terminal and run the command again."
            }
        }
        try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }
        New-Item -ItemType Directory -Force -Path $work | Out-Null
        $quiet = $ProgressPreference
        $ProgressPreference = 'SilentlyContinue'   # la barra di PowerShell rallenta molto gli scaricamenti

        Say "Cerco l'ultima versione di Omissis..." 'Looking for the latest Omissis version...'
        $sheetFile = Join-Path $work 'update.json'
        try { Invoke-WebRequest -Uri "$origin/update.json" -OutFile $sheetFile -UseBasicParsing }
        catch { Fail 'non riesco a leggere la pagina delle versioni: controlla la connessione e riprova.' 'cannot read the releases page: check the connection and try again.' }
        try { $sheet = [IO.File]::ReadAllText($sheetFile, [Text.Encoding]::UTF8) | ConvertFrom-Json } catch { $sheet = $null }
        $name = [string]$sheet.file
        $sum = ([string]$sheet.sha256).ToLower()
        if ($name -notmatch '^Omissis-\d{1,4}(\.\d{1,4}){1,3}-setup\.exe$' -or $sum -notmatch '^[0-9a-f]{64}$') {
            Fail 'la pagina delle versioni non ha un installer per Windows.' 'the releases page has no installer for Windows.'
        }

        $megabyte = [math]::Round([double]$sheet.byte / 1000000)
        Say "Scarico $name ($megabyte MB)..." "Downloading $name ($megabyte MB)..."
        $setup = Join-Path $work $name
        $curl = Join-Path $env:SystemRoot 'System32\curl.exe'
        if (Test-Path -LiteralPath $curl) {
            # curl disegna la sua barra sul canale degli errori: non deve contare come errore dello script
            $ErrorActionPreference = 'Continue'
            & $curl -fL --retry 2 --progress-bar -o $setup "$origin/$name"
            $code = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
            if ($code -ne 0) { Fail "lo scaricamento non $e riuscito." 'the download failed.' }
        } else {
            try { Invoke-WebRequest -Uri "$origin/$name" -OutFile $setup -UseBasicParsing } catch { Fail "lo scaricamento non $e riuscito." 'the download failed.' }
        }
        $ProgressPreference = $quiet
        $found = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLower()
        if ($found -ne $sum -or ($sheet.byte -and (Get-Item -LiteralPath $setup).Length -ne [long]$sheet.byte)) {
            Fail "il file scaricato non $e quello pubblicato (impronta diversa): non lo avvio. Riprova." `
                 'the downloaded file is not the published one (different checksum): not running it. Try again.'
        }

        Say "Installo Omissis $($sheet.version)..." "Installing Omissis $($sheet.version)..."
        $arguments = @('/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
        if ($env:OMISSIS_NO_AUTOSTART -eq '1') { $arguments += '/MERGETASKS="!avvio"' }
        if ($env:OMISSIS_HOME) { $arguments += ('/DIR="' + $program + '"') }
        $run = Start-Process -FilePath $setup -ArgumentList $arguments -Wait -PassThru
        if ($run.ExitCode -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $program 'installed.json'))) {
            Fail "l'installazione non $e riuscita (codice $($run.ExitCode))." "the installation failed (code $($run.ExitCode))."
        }

        if ($env:OMISSIS_NO_START -eq '1') {
            Say "Omissis $($sheet.version) $e installato. Lo trovi nel menu Start." "Omissis $($sheet.version) is installed. You find it in the Start menu."
        } else {
            Start-Process -FilePath (Join-Path $program 'python\Omissis.exe') -ArgumentList ('"' + (Join-Path $program 'app\panel.py') + '"') -WorkingDirectory (Join-Path $program 'app')
            Say "Omissis $($sheet.version) $e installato e si sta aprendo nel browser. Da ora lo trovi nel menu Start." `
                "Omissis $($sheet.version) is installed and is opening in your browser. From now on you find it in the Start menu."
        }
    } catch {
        $failed = $true
        Write-Host ('Omissis: ' + $_.Exception.Message) -ForegroundColor Red
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
    # lanciato da file (powershell -File install.ps1) il codice di uscita dice com'e' andata; incollato nel terminale
    # non si chiude nulla
    if ($failed -and $PSCommandPath) { exit 1 }
}
