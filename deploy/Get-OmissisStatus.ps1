<#
.SYNOPSIS
    Reports the state of Omissis for the current user, as one line of JSON. For monitoring and for detection rules.

.DESCRIPTION
    Run it as the user. It reads only names, versions and counts: the activity log of Omissis never contains text.

    -MinVersion  with it the script is a detection rule: exit 0 and one line of output if that version (or a later one)
                 is installed, exit 1 and no output otherwise. This is the form Intune expects.
    Without it:  exit 0 if protection is on, 1 if Omissis is installed but protection is off, 2 if it is not installed.
#>
[CmdletBinding()]
param([string]$MinVersion, [int]$Days = 7)

$program = Join-Path $env:LOCALAPPDATA 'Programs\Omissis'
$data = Join-Path $env:LOCALAPPDATA 'Omissis'
$installed = Join-Path $program 'installed.json'

function Listening([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $port); return $true } catch { return $false } finally { $client.Close() }
}

$version = $null
if (Test-Path -LiteralPath $installed) { try { $version = (Get-Content -LiteralPath $installed -Raw | ConvertFrom-Json).version } catch { } }
if ($MinVersion) {
    if ($version -and ([version]$version -ge [version]$MinVersion)) { Write-Output "Omissis $version"; exit 0 }
    exit 1
}
if (-not $version) { Write-Output (@{ installed = $false; computer = $env:COMPUTERNAME; user = $env:USERNAME } | ConvertTo-Json -Compress); exit 2 }

$settings = @{}
$file = Join-Path $data 'settings.json'
if (Test-Path -LiteralPath $file) { try { (Get-Content -LiteralPath $file -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $settings[$_.Name] = $_.Value } } catch { } }
$model = if ($settings['model']) { [string]$settings['model'] } else { 'omissis-small' }

# activity of the last days: how many requests had data replaced, how many values, how many were stopped
$since = (Get-Date).AddDays(-$Days).ToString('yyyy-MM-dd HH:mm:ss')
$requests = 0; $values = 0; $stopped = 0
$log = Join-Path $data 'activity.jsonl'
if (Test-Path -LiteralPath $log) {
    # the running program keeps the log open for writing: open it without asking for exclusive access
    $stream = $null
    try {
        $stream = New-Object System.IO.FileStream($log, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        while ($null -ne ($line = $reader.ReadLine())) {
            try { $entry = $line | ConvertFrom-Json } catch { continue }
            if (-not $entry.stamp -or $entry.stamp -lt $since) { continue }
            if ($entry.event -match 'masked' -and $entry.replacements) {
                $n = 0; $entry.replacements.PSObject.Properties | ForEach-Object { $n += [int]$_.Value }
                if ($n -gt 0) { $requests++; $values += $n }
            }
            if ($entry.event -match 'block') { $stopped++ }
        }
    } catch { } finally { if ($stream) { $stream.Dispose() } }
}
# settings locked by the administrator (Set-OmissisPolicy.ps1) win over the user's own
$locked = @()
foreach ($view in 'Registry64', 'Registry32') {
    try {
        $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', $view)
        $policy = $base.OpenSubKey('SOFTWARE\Policies\Omissis')
        if ($policy) {
            foreach ($name in $policy.GetValueNames()) {
                if (-not $name) { continue }
                if ($locked -notcontains $name) { $locked += $name }
                if ($name -notin 'policies', 'console_key') { $settings[$name] = $policy.GetValue($name) }
            }
            $policy.Close()
        }
        $base.Close()
    } catch { }
}
if ($settings['groups_off'] -is [string]) { try { $settings['groups_off'] = @($settings['groups_off'] | ConvertFrom-Json) } catch { $settings['groups_off'] = @() } }
if ($settings['model']) { $model = [string]$settings['model'] }
$on = Listening 8765
$run = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -ErrorAction SilentlyContinue).Omissis
$state = [ordered]@{
    installed = $true; version = $version; computer = $env:COMPUTERNAME; user = $env:USERNAME
    protectionOn = $on; panelUp = (Listening 8766); startsWithWindows = [bool]$run
    model = $model; modelPresent = (Test-Path -LiteralPath (Join-Path $data ('models\' + $model + '\model.onnx')))
    updates = if ($settings['updates']) { [string]$settings['updates'] } else { 'automatic' }
    groupsOff = @($settings['groups_off'] | Where-Object { $_ })
    locked = @($locked | Sort-Object); console = [bool]$settings['console_url']
    days = $Days; requestsWithReplacements = $requests; valuesReplaced = $values; stopped = $stopped
}
Write-Output ($state | ConvertTo-Json -Compress)
if ($on) { exit 0 } else { exit 1 }
