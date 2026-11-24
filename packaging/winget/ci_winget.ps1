# Prova la scheda di Omissis per winget su un Windows pulito (quello di GitHub Actions), come fara' il controllo
# dell'archivio di Microsoft: scrive la scheda dalla versione pubblicata, la controlla (winget validate), installa con
# winget dalla scheda e guarda che il programma ci sia, carichi librerie e codice, sia registrato in Windows con nome,
# versione e autore della scheda, e che nulla sia stato avviato; poi lo toglie con winget. Con -Previous prova anche
# l'aggiornamento: installa quella versione con il suo installer, la aggiorna con winget dalla scheda e guarda che alla
# fine Omissis sia stato riaperto. Non invia nulla a Microsoft.
#
#   pwsh packaging\winget\ci_winget.ps1 -Version 0.1.10 [-Previous 0.1.9]
param([Parameter(Mandatory = $true)] [string]$Version, [string]$Previous = '')

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = Split-Path (Split-Path $here)
$results = @()
function Mark([string]$name, [bool]$ok, [string]$note = '') {
    $script:results += $ok
    Write-Host ("{0} {1}{2}" -f $(if ($ok) { 'OK    ' } else { 'ERRORE' }), $name, $(if ($note) { "   $note" } else { '' }))
}

# winget c'e' gia' sui Windows recenti; dove manca lo mette il modulo ufficiale di Microsoft
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host 'winget non c''e'': lo installo con Microsoft.WinGet.Client'
    Install-Module -Name Microsoft.WinGet.Client -Force -Scope CurrentUser -Repository PSGallery
    Repair-WinGetPackageManager -Latest -Force
    # il comando sta tra le app dell'utente: in questa sessione la cartella puo' non essere ancora nel percorso
    $apps = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath (Join-Path $apps 'winget.exe'))) { $env:PATH = "$apps;$env:PATH" }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { Write-Host 'winget non si lascia installare su questa macchina'; exit 1 }
}
$said = (winget --version | Out-String).Trim()
Mark 'winget risponde' ($LASTEXITCODE -eq 0) $said

python (Join-Path $here 'make_manifest.py') --version $Version --out (Join-Path $root 'build\winget')
if ($LASTEXITCODE) { Write-Host 'scheda non scritta'; exit 1 }
$folder = Join-Path $root "build\winget\manifests\f\FrancescoGruner\Omissis\$Version"
Get-ChildItem -LiteralPath $folder -Filter *.yaml | ForEach-Object { Write-Host "----- $($_.Name)"; Get-Content -LiteralPath $_.FullName -Encoding utf8 | Write-Host }

winget validate --manifest $folder --disable-interactivity
Mark 'la scheda supera winget validate' ($LASTEXITCODE -eq 0)

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
function Remove-WithWinget([string]$name) {
    winget uninstall --manifest $folder --silent --disable-interactivity --accept-source-agreements
    $done = $LASTEXITCODE -eq 0
    $gone = Wait-Until { -not (Test-Path -LiteralPath $exe) -and -not (Test-Path -LiteralPath $key) } 40
    Mark $name ($done -and $gone) "esito $LASTEXITCODE"
}

winget settings --enable LocalManifestFiles
Mark 'winget accetta le schede locali' ($LASTEXITCODE -eq 0)

# --- installazione da zero, nel modo in cui la fa «winget install» senza altre opzioni
winget install --manifest $folder --disable-interactivity --accept-package-agreements --accept-source-agreements
Mark 'winget installa dalla scheda senza chiedere nulla' ($LASTEXITCODE -eq 0) "esito $LASTEXITCODE"
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
Remove-WithWinget 'winget toglie il programma'

# --- aggiornamento da una versione precedente
if ($Previous) {
    $old = Join-Path ([IO.Path]::GetTempPath()) "Omissis-$Previous-setup.exe"
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri "https://github.com/francescogruner/omissis/releases/download/v$Previous/Omissis-$Previous-setup.exe" -OutFile $old -UseBasicParsing
    Start-Process -FilePath $old -ArgumentList '/SP-', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait
    $r = Registered
    Mark "la versione $Previous e' installata" ($r -and $r.DisplayVersion -eq $Previous) $(if ($r) { $r.DisplayVersion } else { 'voce assente' })
    winget upgrade --manifest $folder --silent --disable-interactivity --accept-package-agreements --accept-source-agreements
    Mark 'winget aggiorna dalla scheda' ($LASTEXITCODE -eq 0) "esito $LASTEXITCODE"
    $r = Registered
    Mark 'dopo l''aggiornamento la versione e'' quella della scheda' ($r -and $r.DisplayVersion -eq $Version) $(if ($r) { $r.DisplayVersion } else { 'voce assente' })
    Mark 'dopo l''aggiornamento Omissis e'' stato riaperto' (Wait-Until { [bool](Running) } 30)
    Remove-WithWinget 'winget toglie il programma aggiornato'
    Mark 'dopo la rimozione non resta nessuna copia accesa' (Wait-Until { -not (Running) } 20)
    Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue
}

$good = @($results | Where-Object { $_ }).Count
Write-Host "$good su $($results.Count)"
if ($good -ne $results.Count) {
    # in caso di errore, le ultime righe del registro di winget aiutano a capire
    $logs = Join-Path $env:LOCALAPPDATA 'Packages\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe\LocalState\DiagOutputDir'
    Get-ChildItem -LiteralPath $logs -Filter *.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 3 |
        ForEach-Object { Write-Host "----- $($_.Name)"; Get-Content -LiteralPath $_.FullName -Tail 40 | Write-Host }
    exit 1
}
exit 0
