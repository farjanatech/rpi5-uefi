#Requires -Version 5.1
param()

$ErrorActionPreference = 'Stop'
$ExpectedVersion = '2026.8.18.6'
$ExpectedProvider = 'RPi5 UEFI Community'
$FanDeviceId = 'ACPI\RPI000F\0'
$TempDeviceId = 'ACPI\RPI0010\0'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$FanDir = Join-Path $Root 'Drivers\Rpi5Fan'
$TempDir = Join-Path $Root 'Drivers\Rpi5Temp'
$GuiExe = Join-Path $Root 'GUI\Rpi5FanControl.exe'
$LogPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'RPi5Fan-exp6-install.log'

function Test-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    $args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"'))
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $args
    exit 0
}

function Write-Step([string]$Message) {
    Write-Host "`n===== $Message ====="
}

function Get-DeviceProblemCode([string]$InstanceId) {
    $property = Get-PnpDeviceProperty -InstanceId $InstanceId -KeyName 'DEVPKEY_Device_ProblemCode' -ErrorAction SilentlyContinue
    if ($null -eq $property) { return -1 }
    return [int]$property.Data
}

function Get-DeviceDriverState([string]$InstanceId) {
    $inf = Get-PnpDeviceProperty -InstanceId $InstanceId -KeyName 'DEVPKEY_Device_DriverInfPath' -ErrorAction SilentlyContinue
    $ver = Get-PnpDeviceProperty -InstanceId $InstanceId -KeyName 'DEVPKEY_Device_DriverVersion' -ErrorAction SilentlyContinue
    $provider = Get-PnpDeviceProperty -InstanceId $InstanceId -KeyName 'DEVPKEY_Device_DriverProvider' -ErrorAction SilentlyContinue
    [pscustomobject]@{
        InfPath = if ($null -eq $inf) { $null } else { [string]$inf.Data }
        Version = if ($null -eq $ver) { $null } else { [string]$ver.Data }
        Provider = if ($null -eq $provider) { $null } else { [string]$provider.Data }
    }
}

function Install-Certificate([string]$Path) {
    Import-Certificate -FilePath $Path -CertStoreLocation 'Cert:\LocalMachine\Root' | Out-Null
    Import-Certificate -FilePath $Path -CertStoreLocation 'Cert:\LocalMachine\TrustedPublisher' | Out-Null
}

function Invoke-PnpInstall([string]$InfPath) {
    $output = & pnputil.exe /add-driver $InfPath /install 2>&1
    $code = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    if ($code -notin 0,259) {
        throw "PnPUtil failed for $InfPath with exit code $code."
    }
}

function Remove-StaleSelectedPackage([string]$InstanceId) {
    $state = Get-DeviceDriverState $InstanceId
    if ($state.Provider -eq $ExpectedProvider -and
        -not [string]::IsNullOrWhiteSpace($state.InfPath) -and
        $state.InfPath -match '^oem\d+\.inf$' -and
        $state.Version -ne $ExpectedVersion) {
        Write-Warning "Removing stale selected package $($state.InfPath) version $($state.Version) from $InstanceId"
        & pnputil.exe /delete-driver $state.InfPath /uninstall /force | Out-Host
        if ($LASTEXITCODE -notin 0,259) {
            throw "Unable to remove stale package $($state.InfPath)."
        }
    }
}

function Assert-Healthy([string]$InstanceId,[string]$Name) {
    $device = Get-PnpDevice -InstanceId $InstanceId -ErrorAction SilentlyContinue
    if ($null -eq $device) {
        throw "$Name device $InstanceId was not found. Install the matching exp.5B/exp.6 UEFI first."
    }
    $problem = Get-DeviceProblemCode $InstanceId
    $state = Get-DeviceDriverState $InstanceId
    Write-Host "$Name status:       $($device.Status)"
    Write-Host "$Name problem code: $problem"
    Write-Host "$Name INF:          $($state.InfPath)"
    Write-Host "$Name version:      $($state.Version)"
    if ($problem -eq 12) {
        throw "$Name still has Code 12. Do not continue; the exp.5B/exp.6 UEFI split-resource layout is not active."
    }
    if ($problem -ne 0 -or $device.Status -ne 'OK') {
        throw "$Name failed to start (status=$($device.Status), problem=$problem)."
    }
    if ($state.Version -ne $ExpectedVersion) {
        throw "$Name selected version '$($state.Version)' instead of '$ExpectedVersion'."
    }
}

Start-Transcript -Path $LogPath -Append | Out-Null
try {
    Write-Step 'Checking exp.6 package contents'
    $required = @(
        (Join-Path $TempDir 'Rpi5Temp.inf'),
        (Join-Path $TempDir 'Rpi5Temp.sys'),
        (Join-Path $TempDir 'rpi5temp.cat'),
        (Join-Path $TempDir 'Rpi5Temp.cer'),
        (Join-Path $FanDir 'Rpi5Fan.inf'),
        (Join-Path $FanDir 'Rpi5Fan.sys'),
        (Join-Path $FanDir 'rpi5fan.cat'),
        (Join-Path $FanDir 'Rpi5Fan.cer'),
        $GuiExe
    )
    foreach ($path in $required) {
        if (-not (Test-Path -LiteralPath $path)) { throw "Missing package file: $path" }
    }

    Write-Step 'Checking ACPI devices and resource-conflict baseline'
    foreach ($id in @($FanDeviceId,$TempDeviceId)) {
        $device = Get-PnpDevice -InstanceId $id -ErrorAction SilentlyContinue
        if ($null -eq $device) { throw "Required ACPI device not found: $id" }
        $problem = Get-DeviceProblemCode $id
        Write-Host "$id pre-install status=$($device.Status) problem=$problem"
        if ($problem -eq 12) {
            throw "$id has Code 12. Stop and restore the validated exp.5B/exp.6 UEFI before installing drivers."
        }
    }

    Write-Step 'Installing test-signing certificates'
    Install-Certificate (Join-Path $TempDir 'Rpi5Temp.cer')
    Install-Certificate (Join-Path $FanDir 'Rpi5Fan.cer')

    Write-Step 'Checking Windows test-signing mode'
    $testSigning = (& bcdedit.exe /enum '{current}' 2>&1 | Out-String)
    if ($testSigning -notmatch '(?im)^testsigning\s+Yes\s*$') {
        Write-Warning 'Test-signing is not enabled. Enabling it now.'
        & bcdedit.exe /set testsigning on | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Unable to enable Windows test-signing mode.' }
        Write-Warning 'REBOOT REQUIRED. Reboot Windows, then run Install.cmd again. No driver installation was attempted yet.'
        exit 3010
    }

    Write-Step 'Removing any stale selected RPi5 packages'
    Remove-StaleSelectedPackage $TempDeviceId
    Remove-StaleSelectedPackage $FanDeviceId
    & pnputil.exe /scan-devices | Out-Host
    Start-Sleep -Seconds 2

    Write-Step 'Installing Rpi5Temp provider first'
    Invoke-PnpInstall (Join-Path $TempDir 'Rpi5Temp.inf')
    & pnputil.exe /scan-devices | Out-Host
    Start-Sleep -Seconds 2
    Assert-Healthy $TempDeviceId 'Rpi5Temp'

    Write-Step 'Installing Rpi5Fan PWM driver'
    Invoke-PnpInstall (Join-Path $FanDir 'Rpi5Fan.inf')
    & pnputil.exe /scan-devices | Out-Host
    Start-Sleep -Seconds 3
    Assert-Healthy $FanDeviceId 'Rpi5Fan'

    Write-Step 'Creating desktop shortcut'
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'Raspberry Pi 5 Fan Control.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $GuiExe
    $shortcut.WorkingDirectory = Split-Path -Parent $GuiExe
    $shortcut.Description = 'Raspberry Pi 5 Active Cooler Control (exp.6)'
    $shortcut.Save()

    Write-Step 'exp.6 installation successful'
    Write-Host 'Rpi5Temp and Rpi5Fan both report Code 0 with driver version 2026.8.18.6.'
    Write-Host "GUI: $GuiExe"
    Write-Host 'The fan driver starts at 100% and remains at 100% until valid temperature telemetry is received.'
    Write-Host 'Manual control is restricted to 30-100%; temperature/provider failures and >=85 C force 100%.'
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
    Write-Host "Installer log: $LogPath"
}
