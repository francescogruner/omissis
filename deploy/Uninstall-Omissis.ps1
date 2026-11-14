<#
.SYNOPSIS
    Removes Omissis for the current user, silently.

.DESCRIPTION
    Run it as the user. Without -RemoveData the user's data stays (the vault of replaced values, settings, personal
    lists, the downloaded model): a later installation finds everything again. With -RemoveData it is deleted, and the
    proxy certificate, if it was installed, is removed from the user's Windows store.

    Careful: without the vault, placeholders in old conversations can no longer be turned back into the real values.

    Exit codes: 0 removed (or it was not installed), 3 the uninstaller failed.
#>
[CmdletBinding()]
param([switch]$RemoveData)

$program = Join-Path $env:LOCALAPPDATA 'Programs\Omissis'
$data = Join-Path $env:LOCALAPPDATA 'Omissis'
$uninstaller = Join-Path $program 'unins000.exe'
$outcome = 'was not installed'
if (Test-Path -LiteralPath $uninstaller) {
    # The uninstaller hands the work to a copy of itself and returns at once, so its exit code says nothing:
    # what counts is whether the program is gone.
    Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait
    $deadline = (Get-Date).AddSeconds(90)
    while ((Test-Path -LiteralPath (Join-Path $program 'installed.json')) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 1 }
    if (Test-Path -LiteralPath (Join-Path $program 'installed.json')) {
        Write-Output (@{ outcome = 'uninstaller failed' } | ConvertTo-Json -Compress); exit 3
    }
    $outcome = 'removed'
}
$dataRemoved = $false
if ($RemoveData -and (Test-Path -LiteralPath $data)) {
    & certutil.exe -user -delstore Root mitmproxy 2>$null | Out-Null
    Remove-Item -LiteralPath $data -Recurse -Force -ErrorAction SilentlyContinue
    $dataRemoved = -not (Test-Path -LiteralPath $data)
}
Write-Output ([ordered]@{ outcome = $outcome; dataRemoved = $dataRemoved; computer = $env:COMPUTERNAME; user = $env:USERNAME } | ConvertTo-Json -Compress)
exit 0
