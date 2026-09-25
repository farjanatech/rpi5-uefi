#Requires -Version 5.1
# SPDX-License-Identifier: BSD-2-Clause-Patent
param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$ResultFile)
$ErrorActionPreference='Stop'
Set-StrictMode -Version 2
$Root=[IO.Path]::GetFullPath($Root)
. (Join-Path $Root 'DeviceDetection.ps1')
$Version='2026.8.18.6'; $Provider='RPi5 UEFI Community'
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $Root 'Install-OneShot.ps1'),[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($name in @('Get-Selected','Test-DriverPlan')) {
    $f=$ast.Find({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name},$true)
    if (!$f) { throw "Production function missing: $name" }
    Invoke-Expression $f.Extent.Text
}
$script:count=0
function Check([bool]$Condition,[string]$Message) {
    if (!$Condition) { throw "REGRESSION: $Message" }
    $script:count++
}
function ExpectFailure([scriptblock]$Action,[string]$Pattern) {
    $message=''
    try { & $Action | Out-Null } catch { $message=$_.Exception.Message }
    Check (![string]::IsNullOrEmpty($message) -and $message -like $Pattern) "Expected '$Pattern', got '$message'"
}
function New-Device([string]$Hid,[string]$Suffix='0',[int]$Problem=28) {
    [pscustomobject]@{
        Name=$null; PNPDeviceID="ACPI\$Hid\$Suffix"; Present=$true
        ConfigManagerErrorCode=$Problem
        HardwareID=@(('ACPI\VEN_RPI&DEV_'+$Hid.Substring(3)),"ACPI\$Hid","*$Hid")
    }
}
function Reset-Fixture {
    $script:inventory=@((New-Device 'RPI000F'),(New-Device 'RPI0010'))
    $script:enumError=$false; $script:propertyError=$false; $script:signedError=$false
    $script:properties=@(); $script:records=@(); $script:propertyCalls=0; $script:signedCalls=0
}
function Get-CimInstance {
    [CmdletBinding()]param([string]$ClassName,[int]$OperationTimeoutSec)
    if ($ClassName -eq 'Win32_PnPEntity') {
        if ($script:enumError) { throw 'simulated CIM access failure' }
        return $script:inventory
    }
    if ($ClassName -eq 'Win32_PnPSignedDriver') {
        $script:signedCalls++
        if ($script:signedError) { throw 'simulated signed-driver provider failure' }
        return $script:records
    }
    throw "Unexpected mocked CIM class: $ClassName"
}
function Invoke-CimMethod {
    [CmdletBinding()]param($InputObject,[string]$MethodName,[hashtable]$Arguments,[int]$OperationTimeoutSec)
    $script:propertyCalls++
    if ($script:propertyError) { throw 'simulated unavailable GetDeviceProperties' }
    if ($MethodName -ne 'GetDeviceProperties' -or $Arguments.devicePropertyKeys.Count -ne 3) { throw 'Unexpected property call' }
    [pscustomobject]@{ ReturnValue=0; deviceProperties=$script:properties }
}
# A dependency on the legacy PnpDevice cmdlets must make the regression fail.
function Get-PnpDevice { throw 'Legacy PnpDevice cmdlet must not be used' }
function Get-PnpDeviceProperty { throw 'Legacy PnpDevice property cmdlet must not be used' }
function Set-Properties([string]$DriverVersion='2026.8.18.6',[string]$DriverProvider='RPi5 UEFI Community') {
    $script:properties=@(
        [pscustomobject]@{KeyName='DEVPKEY_Device_DriverVersion'; Data=$DriverVersion},
        [pscustomobject]@{KeyName='DEVPKEY_Device_DriverProvider'; Data=$DriverProvider},
        [pscustomobject]@{KeyName='DEVPKEY_Device_DriverInfPath'; Data='oem17.inf'})
}
try {
    Reset-Fixture
    # Exact diagnostic-record shape supplied by the user: no Name, Present=True,
    # hardware IDs present, Code 28 for both devices, no selected driver metadata.
    foreach ($hid in @('RPI0010','RPI000F')) {
        $s=Get-Selected "ACPI\$hid\0"
        Check ($s.Id -eq "ACPI\$hid\0" -and $s.Problem -eq 28) "Present nameless Code-28 $hid must be detected"
        Check ((Test-DriverPlan $s.Version $s.Provider $s.Problem) -eq 'Install') "Code 28 must plan installation for $hid"
    }
    Check ($script:propertyCalls -eq 0 -and $script:signedCalls -eq 0) 'Fresh devices must not require nonexistent driver metadata'
    Reset-Fixture
    $script:inventory[1].PNPDeviceID='ACPI\RPI0010\7&ABC&0'
    $s=Get-Selected 'RPI0010'
    Check ($s.Id -eq 'ACPI\RPI0010\7&ABC&0') 'Use discovered instance ID, not a fixed suffix'
    Reset-Fixture
    $script:inventory[1].Name=''
    $script:inventory[1].HardwareID=@('acpi\ven_rpi&dev_0010')
    Check ((Get-Selected 'RPI0010').Problem -eq 28) 'Vendor hardware-ID form and empty name must work'
    Reset-Fixture
    $ghost=New-Device 'RPI0010' 'OLD'; $ghost.Present=$false
    $script:inventory+=@($ghost)
    Check ((Get-Selected 'RPI0010').Id -eq 'ACPI\RPI0010\0') 'Ignore non-present duplicates'
    Reset-Fixture
    $script:inventory[1].Present=$false
    ExpectFailure {Get-Selected 'RPI0010'} '*Required present ACPI device not found*'
    Reset-Fixture
    $script:inventory[1].Present=$null
    ExpectFailure {Get-Selected 'RPI0010'} '*presence could not be determined*'
    Reset-Fixture
    $script:inventory+=@((New-Device 'RPI0010' 'SECOND'))
    ExpectFailure {Get-Selected 'RPI0010'} '*Ambiguous RPI0010*'
    Reset-Fixture
    $script:inventory[1].HardwareID=@('ACPI\RPI00100')
    ExpectFailure {Get-Selected 'RPI0010'} '*Required present ACPI device not found*'
    Reset-Fixture
    $script:inventory[1].PNPDeviceID='ROOT\RPI0010\0'
    ExpectFailure {Get-Selected 'RPI0010'} '*Required present ACPI device not found*'
    Reset-Fixture
    $script:inventory[1].ConfigManagerErrorCode=$null
    ExpectFailure {Get-Selected 'RPI0010'} '*problem code could not be read*'
    Reset-Fixture
    $script:enumError=$true
    ExpectFailure {Get-Selected 'RPI0010'} '*Device enumeration failed*simulated CIM access failure*'
    Reset-Fixture
    $script:inventory=@()
    ExpectFailure {Get-Selected 'RPI0010'} '*after a successful CIM inventory*'
    foreach ($problem in @(12,22)) {
        Reset-Fixture
        $script:inventory[1].ConfigManagerErrorCode=$problem
        $s=Get-Selected 'RPI0010'
        ExpectFailure {Test-DriverPlan $s.Version $s.Provider $s.Problem} $(if ($problem -eq 12) {'*Code 12*'} else {'*device is disabled*'})
        Check ($script:propertyCalls -eq 0) 'Safety-blocked devices must not need driver metadata'
    }
    Reset-Fixture
    $script:inventory[1].ConfigManagerErrorCode=0; Set-Properties
    $s=Get-Selected 'RPI0010'
    Check ((Test-DriverPlan $s.Version $s.Provider $s.Problem) -eq 'Skip') 'Healthy original driver must be skipped'
    Check ($s.Inf -eq 'oem17.inf' -and $script:signedCalls -eq 0) 'Use primary selected-driver properties'
    Set-Properties '2027.1.1.0'
    $s=Get-Selected 'RPI0010'
    ExpectFailure {Test-DriverPlan $s.Version $s.Provider $s.Problem} '*newer driver*'
    Set-Properties '2026.8.18.6' 'Other Provider'
    $s=Get-Selected 'RPI0010'
    ExpectFailure {Test-DriverPlan $s.Version $s.Provider $s.Problem} '*different driver provider*'
    Reset-Fixture
    $script:inventory[1].ConfigManagerErrorCode=0; $script:propertyError=$true
    $script:records=@([pscustomobject]@{DeviceID='ACPI\RPI0010\0'; DriverVersion=$Version; DriverProviderName=$Provider; InfName='oem18.inf'})
    $s=Get-Selected 'RPI0010'
    Check ($s.Inf -eq 'oem18.inf' -and (Test-DriverPlan $s.Version $s.Provider $s.Problem) -eq 'Skip') 'Fallback must work without the PnpDevice module'
    $script:records=@()
    ExpectFailure {Get-Selected 'RPI0010'} '*present*selected driver is unknown or ambiguous*'
    $script:signedError=$true
    ExpectFailure {Get-Selected 'RPI0010'} '*present*metadata cannot be read*simulated signed-driver provider failure*'
    Reset-Fixture
    ExpectFailure {Get-Selected 'PCI\FAKE\0'} '*Unsupported fan-suite hardware identifier*'
} finally {
    Remove-Item function:Get-CimInstance,function:Invoke-CimMethod,function:Get-PnpDevice,function:Get-PnpDeviceProperty
}
# Exercise the real Windows read-only property APIs on an existing healthy device.
$live=@(CimCmdlets\Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction Stop |
    Where-Object { $_.Present -eq $true -and $_.ConfigManagerErrorCode -eq 0 })
$drivers=@(CimCmdlets\Get-CimInstance -ClassName Win32_PnPSignedDriver -ErrorAction Stop |
    Where-Object { $_.DriverVersion -and $_.DriverProviderName -and $_.InfName })
$chosen=$null; $driver=$null
foreach ($entry in $live) {
    $match=@($drivers | Where-Object { $_.DeviceID -eq $entry.PNPDeviceID })
    if ($match.Count -eq 1) { $chosen=$entry; $driver=$match[0]; break }
}
if (!$chosen) { throw 'No live device available to validate read-only driver-property lookup' }
$binding=Get-RpiDriverBinding -Device $chosen
Check ($binding.Version -eq $driver.DriverVersion -and $binding.Inf -eq $driver.InfName) 'Live selected-driver properties must agree with the signed-driver inventory'
$text="PASS: $script:count device-detection regression checks, including the user's nameless Present=True / Code-28 pair, hardware-ID resolution, failure reporting, healthy-driver skip and live read-only driver metadata. No driver, BCD, certificate or task writes."
[IO.File]::WriteAllText($ResultFile,$text,[Text.UTF8Encoding]::new($false))
Write-Host $text
