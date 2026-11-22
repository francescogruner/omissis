<#
.SYNOPSIS
    Installs Omissis silently for the current user and applies a customer configuration.

.DESCRIPTION
    For managed deployment (an RMM tool, Intune, a logon script). Omissis installs per user and needs no administrator
    rights, so this script must run AS THE USER who will use the PC, not as SYSTEM.

    What it does, in order:
      1. gets the installer (a local path, a share or an https address) and refuses it unless its SHA-256 is the one
         expected (take it from update.json, which is published signed next to the installer);
      2. runs it silently;
      3. writes the customer's choices into the user's settings (the keys of the template replace the user's ones,
         every other setting is left as it is);
      4. optionally copies the model from a folder you provide, so that every PC does not download it again. Each file
         is accepted only if size and SHA-256 match the list shipped with the program;
      5. starts Omissis and waits for protection to come up.

    Exit codes: 0 done, 2 installer not obtained or wrong hash, 3 installation failed, 4 installed but protection did
    not start in time (it may still be downloading the model).

.EXAMPLE
    .\Install-Omissis.ps1 -Installer \\server\software\Omissis-0.1.0-setup.exe -Sha256 <hash> -Settings \\server\software\acme.json -ModelSource \\server\software\models
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$Installer,
    [Parameter(Mandatory = $true)] [string]$Sha256,
    [string]$Settings,
    [string]$ModelSource,
    [switch]$NoAutostart,
    [switch]$NoStart,
    [int]$WaitSeconds = 180
)

$ErrorActionPreference = 'Stop'
$program = Join-Path $env:LOCALAPPDATA 'Programs\Omissis'
$data = Join-Path $env:LOCALAPPDATA 'Omissis'
$utf8 = New-Object System.Text.UTF8Encoding($false)   # no byte-order mark: the program would not read the file

function Finish([int]$code, [string]$outcome, [hashtable]$more = @{}) {
    $result = [ordered]@{ outcome = $outcome; computer = $env:COMPUTERNAME; user = $env:USERNAME }
    foreach ($key in $more.Keys) { $result[$key] = $more[$key] }
    Write-Output ($result | ConvertTo-Json -Compress)
    exit $code
}

function Listening([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $port); return $true } catch { return $false } finally { $client.Close() }
}

# 1. the installer, checked before anything runs
$file = $Installer
if ($Installer -match '^https://') {
    $file = Join-Path $env:TEMP ('Omissis-setup-' + [guid]::NewGuid().ToString('N') + '.exe')
    try { Invoke-WebRequest -Uri $Installer -OutFile $file -UseBasicParsing } catch { Finish 2 'installer not downloaded' @{ detail = $_.Exception.Message } }
}
if (-not (Test-Path -LiteralPath $file)) { Finish 2 'installer not found' @{ detail = $Installer } }
$found = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
if ($found -ne $Sha256.Trim()) { Finish 2 'installer refused: SHA-256 does not match' @{ expected = $Sha256.Trim().ToUpper(); found = $found } }

# 2. silent installation (it closes a running copy of Omissis from the same folder by itself)
$arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
if ($NoAutostart) { $arguments += '/MERGETASKS="!avvio"' }
$setup = Start-Process -FilePath $file -ArgumentList $arguments -Wait -PassThru
if ($Installer -match '^https://') { Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue }
$installed = Join-Path $program 'installed.json'
if ($setup.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $installed)) { Finish 3 'installation failed' @{ exitCode = $setup.ExitCode } }
$version = (Get-Content -LiteralPath $installed -Raw | ConvertFrom-Json).version

# 3. the customer's settings: its keys win, the rest of the user's settings stays
New-Item -ItemType Directory -Force -Path $data | Out-Null
$settingsFile = Join-Path $data 'settings.json'
$current = @{}
if (Test-Path -LiteralPath $settingsFile) {
    try { (Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $current[$_.Name] = $_.Value } } catch { $current = @{} }
}
if ($Settings) {
    if (-not (Test-Path -LiteralPath $Settings)) { Finish 3 'settings template not found' @{ detail = $Settings } }
    (Get-Content -LiteralPath $Settings -Raw | ConvertFrom-Json).PSObject.Properties | Where-Object { $_.Name -notmatch '^_' } | ForEach-Object { $current[$_.Name] = $_.Value }
    [System.IO.File]::WriteAllText($settingsFile, ($current | ConvertTo-Json -Depth 8), $utf8)
}
$model = if ($current['model']) { [string]$current['model'] }
    elseif ((Test-Path -LiteralPath (Join-Path $data 'models\omissis-small\model.onnx')) -and -not (Test-Path -LiteralPath (Join-Path $data 'models\omissis-light\model.onnx'))) { 'omissis-small' }
    else { 'omissis-light' }

# 4. the model from a folder of yours, each file checked against the list that ships with the program
$copied = $null
if ($ModelSource) {
    $wanted = (Get-Content -LiteralPath (Join-Path $program 'app\weights.json') -Raw | ConvertFrom-Json).models.$model.file
    $from = Join-Path $ModelSource $model
    $to = Join-Path $data ('models\' + $model)
    if ($wanted -and (Test-Path -LiteralPath $from)) {
        New-Item -ItemType Directory -Force -Path $to | Out-Null
        $copied = $true
        foreach ($entry in $wanted.PSObject.Properties) {
            $source = Join-Path $from $entry.Name
            $target = Join-Path $to $entry.Name
            $good = (Test-Path -LiteralPath $target) -and ((Get-Item -LiteralPath $target).Length -eq $entry.Value.byte)
            if (-not $good) {
                if (-not (Test-Path -LiteralPath $source) -or (Get-Item -LiteralPath $source).Length -ne $entry.Value.byte -or
                    (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $entry.Value.sha256.ToUpper()) { $copied = $false; break }
                Copy-Item -LiteralPath $source -Destination $target -Force
            }
        }
        if (-not $copied) { Remove-Item -LiteralPath $to -Recurse -Force -ErrorAction SilentlyContinue }   # the program will download it itself
    } else { $copied = $false }
}

# 5. start it and wait for protection (the engine answers on 127.0.0.1:8765)
$more = @{ version = $version; model = $model; modelCopied = $copied; settingsApplied = [bool]$Settings }
if ($NoStart) { Finish 0 'installed, not started' $more }
if (-not (Listening 8766)) {
    Start-Process -FilePath (Join-Path $program 'python\Omissis.exe') -ArgumentList ('"' + (Join-Path $program 'app\panel.py') + '"'), '--no-browser' -WorkingDirectory (Join-Path $program 'app')
}
$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline) {
    if (Listening 8765) { Finish 0 'installed, protection on' $more }
    Start-Sleep -Seconds 3
}
Finish 4 'installed, protection not up yet' $more
