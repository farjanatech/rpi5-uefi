#Requires -Version 5.1
param()

$ErrorActionPreference = 'Stop'
$DeviceId = 'ACPI\RPI000F\0'
$ExpectedDriverVersion = '2026.8.17.4'
$ExpectedProvider = 'RPi5 UEFI Community'
$LogPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'RPi5Fan-install.log'
$PackageDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RebootRequired = $false

function Write-Step([string]$Message) {
    Write-Host "`n===== $Message ====="
}

function Invoke-NativeAllowed {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][int[]]$AllowedExitCodes,
        [Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    $code = $LASTEXITCODE
    if ($AllowedExitCodes -notcontains $code) {
        throw "$FilePath failed with exit code $code"
    }
    return $code
}

function Get-DevicePropertyData([string]$KeyName) {
    $property = Get-PnpDeviceProperty -InstanceId $DeviceId -KeyName $KeyName -ErrorAction SilentlyContinue
    if ($null -eq $property) {
        return $null
    }
    return [string]$property.Data
}

function Get-SelectedDriverState {
    [pscustomobject]@{
        InfPath  = Get-DevicePropertyData 'DEVPKEY_Device_DriverInfPath'
        Version  = Get-DevicePropertyData 'DEVPKEY_Device_DriverVersion'
        Provider = Get-DevicePropertyData 'DEVPKEY_Device_DriverProvider'
    }
}

function Test-IsRpi5FanInf([string]$InfName) {
    if ([string]::IsNullOrWhiteSpace($InfName) -or $InfName -notmatch '^oem\d+\.inf$') {
        return $false
    }

    $installedInf = Join-Path $env:windir ("INF\" + $InfName)
    if (-not (Test-Path -LiteralPath $installedInf)) {
        return $false
    }

    $text = Get-Content -LiteralPath $installedInf -Raw -ErrorAction SilentlyContinue
    return ($text -match 'ACPI\\RPI000F' -and $text -match 'RPi5 UEFI Community')
}

function Invoke-PnpDriverInstall {
    Push-Location $PackageDir
    try {
        $output = & pnputil.exe /add-driver Rpi5Fan.inf /install 2>&1
        $code = $LASTEXITCODE
        foreach ($line in $output) {
            Write-Host $line
        }
        return [pscustomobject]@{
            ExitCode = $code
            Output   = ($output -join [Environment]::NewLine)
        }
    }
    finally {
        Pop-Location
    }
}

Start-Transcript -Path $LogPath -Append | Out-Null
try {
    Write-Step 'Checking administrator privileges'
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'This installer must run as Administrator.'
    }

    Write-Step 'Checking driver package files'
    foreach ($name in 'Rpi5Fan.inf','Rpi5Fan.sys','rpi5fan.cat','Rpi5Fan.cer') {
        $path = Join-Path $PackageDir $name
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Missing driver package file: $path"
        }
    }

    Write-Step 'Installing test certificate'
    $certificate = Join-Path $PackageDir 'Rpi5Fan.cer'
    Import-Certificate -FilePath $certificate -CertStoreLocation 'Cert:\LocalMachine\Root' | Out-Null
    Import-Certificate -FilePath $certificate -CertStoreLocation 'Cert:\LocalMachine\TrustedPublisher' | Out-Null

    Write-Step 'Checking Windows test-signing mode'
    $testSigning = (& bcdedit.exe /enum '{current}' 2>&1 | Out-String)
    if ($testSigning -notmatch '(?im)^testsigning\s+Yes\s*$') {
        Write-Host 'Test-signing is not enabled. Enabling it now...'
        Invoke-NativeAllowed bcdedit.exe @(0) /set testsigning on | Out-Null
        $RebootRequired = $true
    }

    if ($RebootRequired) {
        Write-Warning 'Windows must reboot before it can load this test-signed driver.'
        Write-Host 'Reboot Windows, then run this same installer again.'
        return
    }

    Write-Step 'Installing/updating RPi5Fan driver'
    $install = Invoke-PnpDriverInstall
    if ($install.ExitCode -notin 0, 259) {
        throw "PnPUtil failed with exit code $($install.ExitCode)."
    }

    Start-Sleep -Seconds 2
    & pnputil.exe /scan-devices | Out-Host
    Start-Sleep -Seconds 2

    $state = Get-SelectedDriverState
    Write-Host "Selected INF:      $($state.InfPath)"
    Write-Host "Selected version:  $($state.Version)"
    Write-Host "Selected provider: $($state.Provider)"

    if ($state.Version -ne $ExpectedDriverVersion -and
        $state.Provider -eq $ExpectedProvider -and
        (Test-IsRpi5FanInf $state.InfPath)) {
        Write-Warning "Windows is still selecting stale RPi5Fan package $($state.InfPath) version $($state.Version)."
        Write-Step 'Removing selected stale RPi5Fan package'
        Invoke-NativeAllowed pnputil.exe @(0, 259) /delete-driver $state.InfPath /uninstall /force | Out-Null
        & pnputil.exe /scan-devices | Out-Host
        Start-Sleep -Seconds 2

        Write-Step 'Retrying verified RPi5Fan package installation'
        $install = Invoke-PnpDriverInstall
        if ($install.ExitCode -notin 0, 259) {
            throw "PnPUtil retry failed with exit code $($install.ExitCode)."
        }
        & pnputil.exe /scan-devices | Out-Host
        Start-Sleep -Seconds 2
        $state = Get-SelectedDriverState
        Write-Host "Selected INF after retry:      $($state.InfPath)"
        Write-Host "Selected version after retry:  $($state.Version)"
        Write-Host "Selected provider after retry: $($state.Provider)"
    }

    if ($state.Version -ne $ExpectedDriverVersion) {
        throw "Windows selected driver version '$($state.Version)' instead of expected '$ExpectedDriverVersion'."
    }

    Write-Step 'Checking final PnP device state'
    $device = Get-PnpDevice -InstanceId $DeviceId -ErrorAction SilentlyContinue
    if ($null -eq $device) {
        throw "Device $DeviceId was not found. The matching UEFI ACPI fan patch must be installed first."
    }

    $problem = Get-PnpDeviceProperty -InstanceId $DeviceId -KeyName 'DEVPKEY_Device_ProblemCode' -ErrorAction SilentlyContinue
    $problemCode = if ($null -eq $problem) { -1 } else { [int]$problem.Data }
    Write-Host "Device status: $($device.Status)"
    Write-Host "Problem code:  $problemCode"

    if ($problemCode -ne 0 -or $device.Status -ne 'OK') {
        Write-Warning 'The verified exp.4 package is selected, but the device is not healthy yet.'
        Write-Host 'Collecting SetupAPI diagnostics...'
        $setupApi = Join-Path $env:windir 'INF\setupapi.dev.log'
        if (Test-Path -LiteralPath $setupApi) {
            Select-String -Path $setupApi -Pattern 'RPI000F','Rpi5Fan' -Context 8,16 | Select-Object -Last 20 | Out-Host
        }
        throw "RPi5Fan device failed to start (status=$($device.Status), problem=$problemCode)."
    }

    Write-Step 'Installation successful'
    Write-Host "Raspberry Pi 5 fan driver $ExpectedDriverVersion is active and Device Manager reports Code 0."
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
    Write-Host "Installer log: $LogPath"
}
