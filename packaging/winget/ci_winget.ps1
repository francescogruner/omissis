# Prova la scheda di Omissis per winget su un Windows pulito (quello di GitHub Actions), come fara' il controllo
# dell'archivio di Microsoft: scrive la scheda dalla versione pubblicata, la controlla (winget validate), installa con
# winget dalla scheda e guarda che il programma ci sia, carichi librerie e codice, sia registrato in Windows con nome,
# versione e autore della scheda, e che nulla sia stato avviato; poi lo toglie con winget. Con -Previous prova anche
# l'aggiornamento: installa quella versione con il suo installer, la aggiorna con winget dalla scheda e guarda che alla
# fine Omissis sia stato riaperto. Ogni comando di winget ha un tempo massimo: se resta fermo, la prova dice che cosa
# c'e' in esecuzione e quali finestre aspettano. Non invia nulla a Microsoft.
#
#   pwsh packaging\winget\ci_winget.ps1 -Version 0.1.11 [-Previous 0.1.10]
param([Parameter(Mandatory = $true)] [string]$Version, [string]$Previous = '')

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = Split-Path (Split-Path $here)
$results = @()
function Mark([string]$name, [bool]$ok, [string]$note = '') {
    $script:results += $ok
    Write-Host ("{0} {1}{2}" -f $(if ($ok) { 'OK    ' } else { 'ERRORE' }), $name, $(if ($note) { "   $note" } else { '' }))
}

# winget c'e' gia' sui Windows recenti, ma puo' essere piu' vecchio dello schema della scheda: lo si porta all'ultima
# versione con il modulo ufficiale di Microsoft. Se non riesce si va avanti con quello che c'e'
$before = if (Get-Command winget -ErrorAction SilentlyContinue) { (winget --version | Out-String).Trim() } else { 'assente' }
try {
    Install-Module -Name Microsoft.WinGet.Client -Force -Scope CurrentUser -Repository PSGallery
    Repair-WinGetPackageManager -Latest -Force
} catch { Write-Host "winget non aggiornato: $($_.Exception.Message)" }
# il comando sta tra le app dell'utente: in questa sessione la cartella puo' non essere ancora nel percorso
$apps = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'
if (-not (Get-Command winget -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath (Join-Path $apps 'winget.exe'))) { $env:PATH = "$apps;$env:PATH" }
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Write-Host 'winget non c''e'' e non si lascia installare su questa macchina'; exit 1 }
$said = (winget --version | Out-String).Trim()
Mark 'winget risponde' ($LASTEXITCODE -eq 0) "$said (sulla macchina: $before)"

python (Join-Path $here 'make_manifest.py') --version $Version --out (Join-Path $root 'build\winget')
if ($LASTEXITCODE) { Write-Host 'scheda non scritta'; exit 1 }
$folder = Join-Path $root "build\winget\manifests\f\FrancescoGruner\Omissis\$Version"
Get-ChildItem -LiteralPath $folder -Filter *.yaml | ForEach-Object { Write-Host "----- $($_.Name)"; Get-Content -LiteralPath $_.FullName -Encoding utf8 | Write-Host }

$code = ((Get-Content -LiteralPath (Join-Path $folder 'FrancescoGruner.Omissis.installer.yaml') -Encoding utf8) -match '^ProductCode:')[0] -replace "^ProductCode:\s*'?([^']+)'?\s*$", '$1'
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$code"
$program = Join-Path $env:LOCALAPPDATA 'Programs\Omissis'
$exe = Join-Path $program 'python\Omissis.exe'
function Registered { if (Test-Path -LiteralPath $key) { Get-ItemProperty -LiteralPath $key } }
function Running { @(Get-Process | Where-Object { $_.Path -like "$program\*" }) }
function Wait-Until([scriptblock]$test, [int]$seconds) {
    foreach ($i in 1..($seconds * 2)) { if (& $test) { return $true }; Start-Sleep -Milliseconds 500 }
    return [bool](& $test)
}

# Che cosa c'e' in esecuzione quando un comando resta fermo: i processi dell'installazione e le finestre aperte
function Show-Stuck {
    Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^Omissis|setup|\.tmp$|smartscreen|consent|winget|WindowsPackageManager|AppInstaller' } | ForEach-Object {
        $line = ($_.CommandLine -replace '\s+', ' ')
        Write-Host ("   processo {0} {1} (padre {2}) {3}" -f $_.ProcessId, $_.Name, $_.ParentProcessId, $line.Substring(0, [Math]::Min(220, $line.Length)))
    }
    Get-Process | Where-Object { $_.MainWindowTitle } | ForEach-Object { Write-Host ("   finestra {0}: {1}" -f $_.ProcessName, $_.MainWindowTitle) }
}
function Stop-Installers {
    $temp = [IO.Path]::GetTempPath()
    Get-Process | Where-Object { $_.ProcessName -match '^Omissis-.*setup' -or $_.Path -like "$program\*" -or $_.Path -like (Join-Path $temp 'WinGet\*') -or $_.Path -like (Join-Path $temp 'is-*.tmp\*') } |
        Stop-Process -Force -ErrorAction SilentlyContinue
}
# Un programma con un tempo massimo. Restituisce il codice di uscita, oppure -1 se e' stato fermato perche' non finiva
function Invoke-Limited([string]$file, [string[]]$arguments, [int]$minutes) {
    $line = ($arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
    $out = Join-Path ([IO.Path]::GetTempPath()) ("prova-" + [guid]::NewGuid().ToString('N') + '.txt')
    $p = Start-Process -FilePath $file -ArgumentList $line -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError "$out.err"
    $null = $p.Handle
    $ended = $p.WaitForExit($minutes * 60000)
    if (-not $ended) {
        Write-Host "fermo da $minutes minuti: $(Split-Path $file -Leaf) $line"
        Show-Stuck
        & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null
        Stop-Installers
    }
    foreach ($f in $out, "$out.err") {
        if (Test-Path -LiteralPath $f) {
            # senza le righe della barra di avanzamento
            Get-Content -LiteralPath $f -Encoding utf8 | Where-Object { $_ -match '[A-Za-z]{3}' -and $_ -notmatch '^\s*[█▒ ]+\s+[\d.]+ [KMG]?B / ' } | ForEach-Object { Write-Host "   $_" }
            Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
        }
    }
    if ($ended) { return $p.ExitCode }
    return -1
}
$winget = (Get-Command winget).Source
function Invoke-Winget([string[]]$arguments, [int]$minutes = 6) { Invoke-Limited $winget ($arguments + '--disable-interactivity') $minutes }
function Remove-WithWinget([string]$name) {
    $done = Invoke-Winget @('uninstall', '--manifest', $folder, '--silent', '--accept-source-agreements')
    $gone = Wait-Until { -not (Test-Path -LiteralPath $exe) -and -not (Test-Path -LiteralPath $key) } 40
    Mark $name (($done -eq 0) -and $gone) "esito $done"
}

# un winget piu' vecchio dello schema avvisa soltanto di non conoscerne l'indirizzo: quell'avviso non e' un errore della scheda
$said = (winget validate --manifest $folder --disable-interactivity | Out-String)
$valid = $LASTEXITCODE -eq 0
$warnings = @($said -split "`n" | Where-Object { $_ -match 'Manifest (Warning|Error)' })
$onlySchema = $said -match 'Manifest validation succeeded' -and -not ($warnings | Where-Object { $_ -notmatch 'schema header URL' })
Write-Host $said.Trim()
Mark 'la scheda supera winget validate' ($valid -or $onlySchema) $(if ($valid) { '' } else { 'con il solo avviso di uno schema che questo winget non conosce' })

winget settings --enable LocalManifestFiles
Mark 'winget accetta le schede locali' ($LASTEXITCODE -eq 0)

# --- installazione da zero, nel modo in cui la fa «winget install» senza altre opzioni
$done = Invoke-Winget @('install', '--manifest', $folder, '--accept-package-agreements', '--accept-source-agreements')
Mark 'winget installa dalla scheda senza chiedere nulla' ($done -eq 0) "esito $done"
$stuck = $done -eq -1
if ($stuck) {
    # che cosa lo ferma? L'installer che winget ha scaricato porta il segno dei file venuti da Internet: lo si lancia come
    # farebbe un doppio clic, prima cosi' com'e' e poi senza quel segno. Dopo, la stessa installazione con winget ma del tutto silenziosa
    Write-Host "   SmartScreen (Explorer): $((Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer' -Name SmartScreenEnabled -ErrorAction SilentlyContinue).SmartScreenEnabled)"
    Write-Host "   SmartScreen (criterio): $((Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\System' -Name EnableSmartScreen -ErrorAction SilentlyContinue).EnableSmartScreen)"
    $downloaded = Get-ChildItem -Path (Join-Path ([IO.Path]::GetTempPath()) 'WinGet') -Recurse -Filter '*.exe' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($downloaded) {
        $zone = (Get-Content -LiteralPath $downloaded.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue) -join ' '
        Write-Host "   scaricato da winget: $($downloaded.FullName)   segno di Internet: $(if ($zone) { $zone } else { 'assente' })"
        # il lancio «come un doppio clic» sta in un processo a parte: se Windows apre una finestra e aspetta, si ferma solo lui
        $double = Join-Path ([IO.Path]::GetTempPath()) 'doppio-clic.ps1'
        Set-Content -LiteralPath $double -Encoding utf8 -Value @'
param([string]$File, [string]$Line)
$p = Start-Process -FilePath $File -ArgumentList $Line -PassThru
$null = $p.Handle
$p.WaitForExit()
exit $p.ExitCode
'@
        $pwsh = (Get-Process -Id $PID).Path
        $switches = '/SP- /SILENT /SUPPRESSMSGBOXES /NORESTART'
        $marked = Invoke-Limited $pwsh @('-NoProfile', '-File', $double, $downloaded.FullName, $switches) 3
        Write-Host "   lo stesso file lanciato a mano, con il segno di Internet: esito $marked"
        if (Test-Path -LiteralPath $exe) { & (Join-Path $program 'unins000.exe') /VERYSILENT /SUPPRESSMSGBOXES /NORESTART | Out-Null; Start-Sleep -Seconds 5 }
        Unblock-File -LiteralPath $downloaded.FullName
        $clean = Invoke-Limited $pwsh @('-NoProfile', '-File', $double, $downloaded.FullName, $switches) 3
        Write-Host "   lo stesso file lanciato a mano, senza il segno: esito $clean"
        if (Test-Path -LiteralPath $exe) { & (Join-Path $program 'unins000.exe') /VERYSILENT /SUPPRESSMSGBOXES /NORESTART | Out-Null; Start-Sleep -Seconds 5 }
    } else { Write-Host '   l''installer scaricato da winget non si trova piu''' }
    $done = Invoke-Winget @('install', '--manifest', $folder, '--silent', '--accept-package-agreements', '--accept-source-agreements')
    Mark 'winget installa dalla scheda in modo del tutto silenzioso' ($done -eq 0) "esito $done"
    $stuck = $done -eq -1
}
Mark 'il programma e'' nella cartella dell''utente' (Test-Path -LiteralPath $exe)
$py = Join-Path $program 'python\python.exe'
if (Test-Path -LiteralPath $py) {
    $load = "import ssl, sqlite3, onnxruntime, tokenizers, mitmproxy.version, docx, openpyxl, pptx, pypdf, PIL; import version, paths, settings, weights, updates; print(version.VERSION)"
    Push-Location (Join-Path $program 'app')
    $said = (& $py -I -B -c $load 2>&1 | Out-String).Trim()
    Pop-Location
    Mark 'il programma installato carica librerie e codice' ($said -eq $Version) $said
} else { Mark 'il programma installato carica librerie e codice' $false 'manca python.exe' }
$r = Registered
Mark 'Windows lo registra con nome, versione e autore della scheda' ($r -and $r.DisplayName -eq 'Omissis' -and $r.DisplayVersion -eq $Version -and $r.Publisher -eq 'Francesco Gruner') $(if ($r) { "$($r.DisplayName) | $($r.DisplayVersion) | $($r.Publisher)" } else { 'voce assente' })
Mark 'nessuna copia di Omissis e'' stata avviata' (-not (Running))
if (Test-Path -LiteralPath $exe) { Remove-WithWinget 'winget toglie il programma' } else { Mark 'winget toglie il programma' $false 'non c''e'' nulla da togliere' }

# --- aggiornamento da una versione precedente (non ha senso se winget non riesce nemmeno a installare)
if ($Previous -and -not $stuck) {
    $old = Join-Path ([IO.Path]::GetTempPath()) "Omissis-$Previous-setup.exe"
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri "https://github.com/francescogruner/omissis/releases/download/v$Previous/Omissis-$Previous-setup.exe" -OutFile $old -UseBasicParsing
    $done = Invoke-Limited $old @('/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') 5
    $r = Registered
    Mark "la versione $Previous e' installata" ($r -and $r.DisplayVersion -eq $Previous) $(if ($r) { $r.DisplayVersion } else { "voce assente, esito $done" })
    $done = Invoke-Winget @('upgrade', '--manifest', $folder, '--silent', '--accept-package-agreements', '--accept-source-agreements')
    Mark 'winget aggiorna dalla scheda' ($done -eq 0) "esito $done"
    $r = Registered
    Mark 'dopo l''aggiornamento la versione e'' quella della scheda' ($r -and $r.DisplayVersion -eq $Version) $(if ($r) { $r.DisplayVersion } else { 'voce assente' })
    Mark 'dopo l''aggiornamento Omissis e'' stato riaperto' (Wait-Until { [bool](Running) } 30)
    Remove-WithWinget 'winget toglie il programma aggiornato'
    Mark 'dopo la rimozione non resta nessuna copia accesa' (Wait-Until { -not (Running) } 20)
    Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue
}
Stop-Installers   # nulla deve restare acceso sulla macchina: terrebbe aperto il passo

$good = @($results | Where-Object { $_ }).Count
Write-Host "$good su $($results.Count)"
if ($good -ne $results.Count) {
    # in caso di errore, le ultime righe del registro di winget aiutano a capire
    $logs = Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\LocalState\DiagOutputDir'
    Get-ChildItem -LiteralPath $logs -Filter *.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 4 |
        ForEach-Object { Write-Host "----- $($_.Name)"; Get-Content -LiteralPath $_.FullName -Tail 30 | ForEach-Object { Write-Host ($_.Substring(0, [Math]::Min(300, $_.Length))) } }
    exit 1
}
exit 0
