# Costruisce l'installer di Omissis per Windows e lo prova su un Windows pulito (quello di GitHub Actions): lo installa
# con il comando di installazione (install.ps1) da una pagina delle versioni finta servita in locale, controlla che il
# programma installato carichi librerie e codice, poi lo disinstalla. Controlla anche che un file diverso da quello
# pubblicato venga rifiutato. Non avvia Omissis e non tocca l'avvio all'accesso.
#
#   pwsh packaging\windows\ci_windows.ps1 -Version 0.1.13 [-Port 8797] [-SkipBuild]
param([Parameter(Mandatory = $true)] [string]$Version, [int]$Port = 8797, [switch]$SkipBuild)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = Split-Path (Split-Path $here)
$results = @()
function Mark([string]$name, [bool]$ok, [string]$note = '') {
    $script:results += $ok
    Write-Host ("{0} {1}{2}" -f $(if ($ok) { 'OK    ' } else { 'ERRORE' }), $name, $(if ($note) { "   $note" } else { '' }))
}

if (-not $SkipBuild) {
    python (Join-Path $here 'build_windows.py') --version $Version --smoke-test
    if ($LASTEXITCODE) { Write-Host 'costruzione fallita'; exit 1 }
}
$setup = Join-Path $root "dist\Omissis-$Version-setup.exe"
if (-not (Test-Path -LiteralPath $setup)) { Write-Host "manca $setup"; exit 1 }
$sum = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLower()
Write-Host ("installer: {0} byte, sha256 {1}" -f (Get-Item -LiteralPath $setup).Length, $sum)

$temp = Join-Path ([IO.Path]::GetTempPath()) ('omissis-ci-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$page = Join-Path $temp 'pagina'
$wrong = Join-Path $temp 'pagina\guasta'
$home1 = Join-Path $temp 'programma'
New-Item -ItemType Directory -Force -Path $wrong | Out-Null
Copy-Item -LiteralPath $setup -Destination $page
Copy-Item -LiteralPath $setup -Destination $wrong
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Sheet([string]$hash) { [ordered]@{ product = 'omissis'; version = $Version; file = (Split-Path $setup -Leaf); byte = (Get-Item -LiteralPath $setup).Length; sha256 = $hash; notes = '' } | ConvertTo-Json }
[IO.File]::WriteAllText((Join-Path $page 'update.json'), (Sheet $sum), $utf8)
[IO.File]::WriteAllText((Join-Path $wrong 'update.json'), (Sheet ('0' * 64)), $utf8)

$server = Start-Process -FilePath python -ArgumentList '-m', 'http.server', $Port, '--bind', '127.0.0.1', '--directory', $page -PassThru -WindowStyle Hidden
try {
    $up = $false
    foreach ($i in 1..40) {
        try { Invoke-WebRequest -Uri "http://127.0.0.1:$Port/update.json" -UseBasicParsing | Out-Null; $up = $true; break } catch { Start-Sleep -Milliseconds 250 }
    }
    Mark 'la pagina delle versioni di prova risponde' $up
    $env:OMISSIS_HOME = $home1
    $env:OMISSIS_NO_START = '1'
    $env:OMISSIS_NO_AUTOSTART = '1'

    # un file che non e' quello pubblicato non deve essere avviato
    $env:OMISSIS_UPDATES_URL = "http://127.0.0.1:$Port/guasta"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $here 'install.ps1')
    Mark 'un file con impronta diversa viene rifiutato' (($LASTEXITCODE -eq 1) -and -not (Test-Path -LiteralPath (Join-Path $home1 'installed.json')))

    # l'installazione vera, con Windows PowerShell 5.1 (quello che c'e' su ogni PC)
    $env:OMISSIS_UPDATES_URL = "http://127.0.0.1:$Port"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $here 'install.ps1')
    Mark 'il comando di installazione finisce senza errori' ($LASTEXITCODE -eq 0)
    $card = Join-Path $home1 'installed.json'
    $found = if (Test-Path -LiteralPath $card) { (Get-Content -LiteralPath $card -Raw | ConvertFrom-Json).version } else { '' }
    Mark 'il programma e'' installato nella versione costruita' ($found -eq $Version) "versione $found"
    $py = Join-Path $home1 'python\python.exe'
    if (Test-Path -LiteralPath $py) {
        $code = "import ssl, sqlite3, onnxruntime, tokenizers, mitmproxy.version, docx, openpyxl, pptx, pypdf, PIL; import version, paths, settings, weights, updates; print(version.VERSION)"
        Push-Location (Join-Path $home1 'app')
        $said = (& $py -I -B -c $code 2>&1 | Out-String).Trim()
        Pop-Location
        Mark 'il programma installato carica librerie e codice' ($said -eq $Version) $said
    } else { Mark 'il programma installato carica librerie e codice' $false 'manca python.exe' }
    Mark 'nessuna copia di Omissis e'' stata avviata' (-not @(Get-Process | Where-Object { $_.Path -like "$home1\*" }))

    $remove = Get-ChildItem -LiteralPath $home1 -Filter 'unins*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($remove) {
        Start-Process -FilePath $remove.FullName -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait
        Start-Sleep -Seconds 4
    }
    Mark 'la disinstallazione toglie il programma' ($remove -and -not (Test-Path -LiteralPath (Join-Path $home1 'python\Omissis.exe')))
} finally {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
$good = @($results | Where-Object { $_ }).Count
Write-Host "$good su $($results.Count)"
if ($good -ne $results.Count) { exit 1 }
