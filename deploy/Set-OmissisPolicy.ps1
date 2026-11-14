<#
.SYNOPSIS
    Locks Omissis settings for every user of this PC, or removes the lock.

.DESCRIPTION
    Writes the settings of a JSON file under HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Omissis. Omissis reads that key:
    the settings found there win over the user's own and show as locked in the panel. Standard users cannot write
    to that key, so this script must run AS AN ADMINISTRATOR (or as SYSTEM, which is how RMM tools and Intune run
    scripts by default). It is the only script of the kit that does not run as the user.

    The key mirrors the file: a setting that is no longer in the file is unlocked. Keys starting with an underscore
    are ignored. "policies" locks only the services written in it; every other setting is locked as a whole.

    What it is not: a defence against a user who tampers with the program. Omissis is installed in the user's
    profile, so its files belong to the user; the lock stops changes made from the panel and from the settings file.

    -Remove   deletes the key: every setting goes back to the user.
    -Hive     CurrentUser writes under HKEY_CURRENT_USER instead. Only to try the script: Omissis does not read it.

    Exit codes: 0 done, 3 settings file missing or not valid, 5 not allowed (not running as administrator).

.EXAMPLE
    .\Set-OmissisPolicy.ps1 -Settings \\server\software\acme-policy.json
#>
[CmdletBinding()]
param(
    [string]$Settings,
    [switch]$Remove,
    [ValidateSet('LocalMachine', 'CurrentUser')] [string]$Hive = 'LocalMachine',
    [string]$Key = 'SOFTWARE\Policies\Omissis'
)

function Finish([int]$code, [string]$outcome, [hashtable]$more = @{}) {
    $result = [ordered]@{ outcome = $outcome; computer = $env:COMPUTERNAME }
    foreach ($name in $more.Keys) { $result[$name] = $more[$name] }
    Write-Output ($result | ConvertTo-Json -Compress)
    exit $code
}

# always the 64-bit view of the registry, even when the deployment tool starts a 32-bit PowerShell
$base = [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]$Hive, [Microsoft.Win32.RegistryView]::Registry64)
try {
    if ($Remove) {
        $base.DeleteSubKeyTree($Key, $false)
        Finish 0 'lock removed'
    }
    if (-not $Settings -or -not (Test-Path -LiteralPath $Settings)) { Finish 3 'settings file not found' @{ detail = $Settings } }
    try { $wanted = Get-Content -LiteralPath $Settings -Raw -Encoding UTF8 | ConvertFrom-Json } catch { Finish 3 'settings file is not valid JSON' @{ detail = $_.Exception.Message } }

    $target = $base.CreateSubKey($Key)
    $written = @()
    foreach ($entry in $wanted.PSObject.Properties) {
        if ($entry.Name -match '^_') { continue }
        $value = $entry.Value
        if ($value -is [bool]) { $target.SetValue($entry.Name, [int]$value, [Microsoft.Win32.RegistryValueKind]::DWord) }
        elseif ($value -is [int] -or $value -is [long]) { $target.SetValue($entry.Name, [int]$value, [Microsoft.Win32.RegistryValueKind]::DWord) }
        elseif ($value -is [string]) { $target.SetValue($entry.Name, $value, [Microsoft.Win32.RegistryValueKind]::String) }
        elseif ($null -eq $value) { continue }
        else {
            # lists and tables travel as JSON text (an empty list too: "[]")
            $text = if ($value -is [array]) { if ($value.Count) { ConvertTo-Json -InputObject @($value) -Compress -Depth 8 } else { '[]' } } else { $value | ConvertTo-Json -Compress -Depth 8 }
            $target.SetValue($entry.Name, $text, [Microsoft.Win32.RegistryValueKind]::String)
        }
        $written += $entry.Name
    }
    foreach ($old in $target.GetValueNames()) { if ($old -and $written -notcontains $old) { $target.DeleteValue($old, $false) } }
    $target.Close()
    Finish 0 'settings locked' @{ locked = $written }
}
catch [System.UnauthorizedAccessException] { Finish 5 'not allowed: run as administrator or as SYSTEM' }
catch [System.Security.SecurityException] { Finish 5 'not allowed: run as administrator or as SYSTEM' }
finally { $base.Close() }
