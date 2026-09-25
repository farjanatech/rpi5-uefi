#Requires -Version 5.1
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Read-only device discovery. Do not require a friendly name or installed driver.
function Get-RpiDeviceInventory {
    try {
        @(Get-CimInstance -ClassName Win32_PnPEntity -ErrorAction Stop -OperationTimeoutSec 45)
    } catch {
        throw "Device enumeration failed (Win32_PnPEntity): $($_.Exception.Message). This does not establish that a firmware device is missing."
    }
}
function Select-RpiDevice {
    param([Parameter(Mandatory=$true)][string]$Id,
          [AllowEmptyCollection()][object[]]$Inventory = @())
    # Accept the old caller's full ID, but match hardware, not its instance suffix.
    if ($Id -match '^(?:ACPI\\)?(RPI000F|RPI0010)(?:\\[^\\]+)?$') {
        $hid = $Matches[1].ToUpperInvariant()
    } else { throw "Unsupported fan-suite hardware identifier: $Id" }
    $accepted = @("ACPI\$hid", ('ACPI\VEN_RPI&DEV_' + $hid.Substring(3)), "*$hid")
    $candidates = @()
    foreach ($device in $Inventory) {
        if ($null -eq $device) { continue }
        $instance = [string]$device.PNPDeviceID
        if ($instance -notmatch '^ACPI\\[^\\]+\\[^\\]+$') { continue }
        $hardwareMatch = $false
        foreach ($hardware in @($device.HardwareID)) {
            if ($accepted -contains [string]$hardware) { $hardwareMatch = $true; break }
        }
        if (!$hardwareMatch) { continue }
        if ($null -eq $device.Present) {
            throw "A matching $hid device was returned, but its presence could not be determined: $instance"
        }
        if ($device.Present -eq $true) { $candidates += $device }
    }
    if ($candidates.Count -eq 0) {
        throw "Required present ACPI device not found for hardware $hid after a successful CIM inventory. Firmware is not modified by setup."
    }
    if ($candidates.Count -gt 1) {
        throw "Ambiguous $hid devices: $($candidates.PNPDeviceID -join ', '). Setup will not choose one automatically."
    }
    return $candidates[0]
}
function Get-RpiDriverBinding {
    param([Parameter(Mandatory=$true)]$Device)
    $id = [string]$Device.PNPDeviceID
    $detail = ''
    try {
        $keys = [string[]]@('DEVPKEY_Device_DriverVersion','DEVPKEY_Device_DriverProvider','DEVPKEY_Device_DriverInfPath')
        $result = Invoke-CimMethod -InputObject $Device -MethodName GetDeviceProperties -Arguments @{devicePropertyKeys=$keys} -ErrorAction Stop -OperationTimeoutSec 45
        if ($result.ReturnValue -ne 0) { throw "GetDeviceProperties returned $($result.ReturnValue)" }
        $values = @{}
        foreach ($property in @($result.deviceProperties)) {
            if ($null -ne $property -and $null -ne $property.PSObject.Properties['Data']) {
                $values[[string]$property.KeyName] = [string]$property.Data
            }
        }
        $version = [string]$values[$keys[0]]
        $provider = [string]$values[$keys[1]]
        $inf = [string]$values[$keys[2]]
        if ($version -and $provider -and $inf) {
            return [pscustomobject]@{ Version=$version; Provider=$provider; Inf=$inf; Source='CIM GetDeviceProperties' }
        }
        $detail = 'Selected-driver properties were incomplete.'
    } catch { $detail = $_.Exception.Message }
    # Some Windows installations do not expose GetDeviceProperties correctly.
    # Query a second read-only source, never assume that missing metadata is healthy.
    try {
        $records = @(Get-CimInstance -ClassName Win32_PnPSignedDriver -ErrorAction Stop -OperationTimeoutSec 45 |
            Where-Object { $_.DeviceID -eq $id })
    } catch {
        throw "Device $id is present, but selected-driver metadata cannot be read. Properties: $detail Signed-driver query: $($_.Exception.Message)"
    }
    if ($records.Count -eq 1 -and $records[0].DriverVersion -and $records[0].DriverProviderName -and $records[0].InfName) {
        Write-Host "Driver-property fallback for $id : $detail"
        return [pscustomobject]@{ Version=[string]$records[0].DriverVersion; Provider=[string]$records[0].DriverProviderName; Inf=[string]$records[0].InfName; Source='CIM Win32_PnPSignedDriver' }
    }
    throw "Device $id is present, but its selected driver is unknown or ambiguous. Properties: $detail Matching driver records: $($records.Count). Setup will not overwrite an unidentified driver."
}
function Get-SelectedCimDevice {
    param([Parameter(Mandatory=$true)][string]$Id)
    $inventory = @(Get-RpiDeviceInventory)
    $device = Select-RpiDevice -Id $Id -Inventory $inventory
    $instance = [string]$device.PNPDeviceID
    $problem = 0
    if ($null -eq $device.ConfigManagerErrorCode -or
        ![int]::TryParse([string]$device.ConfigManagerErrorCode,[ref]$problem) -or $problem -lt 0) {
        throw "Device $instance is present, but its problem code could not be read."
    }
    $binding = [pscustomobject]@{ Version=''; Provider=''; Inf=''; Source='No selected driver (Code 28)' }
    # Code 28 is a normal fresh installation: the device is present without a
    # selected driver and may have no Name or driver-property records at all.
    # Code 12/22 are returned for the existing safety policy to reject explicitly.
    if ($problem -notin @(28,12,22)) { $binding = Get-RpiDriverBinding -Device $device }
    if ($problem -in @(12,22)) { $binding.Source='Device blocked by problem code' }
    Write-Host "CIM device: $instance; present=True; problem=$problem; metadata=$($binding.Source)"
    [pscustomobject]@{
        Id=$instance; Problem=$problem; Status=$(if ($problem -eq 0) {'OK'} else {'ERROR'})
        Version=$binding.Version; Provider=$binding.Provider; Inf=$binding.Inf
    }
}
