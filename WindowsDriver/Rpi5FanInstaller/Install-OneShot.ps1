#Requires -Version 5.1
# SPDX-License-Identifier: BSD-2-Clause-Patent
[CmdletBinding()]
param(
    [ValidateSet('Preflight','Install','Resume','SelfTest')][string]$Phase = 'Preflight',
    [Parameter(Mandatory=$true)][string]$PackageRoot,
    [Parameter(Mandatory=$true)][string]$ResultFile,
    [switch]$Consent
)
Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
$Version = '2026.8.18.6'
$Provider = 'RPi5 UEFI Community'
# Keep the existing task name for safe continuation/cleanup of earlier installs.
$TaskName = 'RPi5Fan-OneShot-beta2-Resume'
$Transcript = $false
$Mutex = $null
$OwnMutex = $false
$script:State = @{ SigningRestart = ''; DriverRestart = ''; Attempts = 0 }
$script:RestartNeeded = $false
$Hashes = [ordered]@{
 'Rpi5FanControl-ARM64.exe' = 'd4c037dfd4530923ef75ecd730d37c837793080cd53bc3e1e2d6cc9377eff8d5'
 'Drivers\Rpi5Temp\Rpi5Temp.inf' = 'cee0592c33f1e0770be590b7e58fc1ccf99dced390657736071c2641431f1b33'
 'Drivers\Rpi5Temp\Rpi5Temp.sys' = '4ad264385368621c9e0610a608342ec60db7928e4de9bd702999c47127685ba1'
 'Drivers\Rpi5Temp\rpi5temp.cat' = 'f79ba09ca8130312ec5740cd3593645f44ee14db4e5ff8a144ee3052f513dd78'
 'Drivers\Rpi5Temp\Rpi5Temp.cer' = '5ef07c5838716826d72cd4c52d4da04305e1d78cc32fc7c0d6329abfadc24acb'
 'Drivers\Rpi5Fan\Rpi5Fan.inf' = 'a2486b6613243b770b0f39ba33592dacd777c82486c0394ac3fd8ebceb484678'
 'Drivers\Rpi5Fan\Rpi5Fan.sys' = 'd73b52b5268484927021b391428cfc4074fa4e8ed7d957839e3def3ae0599e5c'
 'Drivers\Rpi5Fan\rpi5fan.cat' = '6763cada797a98320b02c8b8ead62ebd59d5cfc3953a23c8b7fb6aca615c2901'
 'Drivers\Rpi5Fan\Rpi5Fan.cer' = '5ef07c5838716826d72cd4c52d4da04305e1d78cc32fc7c0d6329abfadc24acb'
}
function Write-Result([string]$Text) {
    [IO.File]::WriteAllText($ResultFile,$Text,[Text.UTF8Encoding]::new($false))
    Write-Host $Text
}
function Test-SigningPlan([bool]$Active,[bool]$Configured,[bool]$SecureBoot,[int]$BitLocker) {
    if ($Active -and $Configured) { return 'Skip' }
    if ($SecureBoot) { throw 'Secure Boot blocks this test-signing configuration. No security setting was changed. Review firmware policy separately.' }
    if ($Configured) { return 'Restart' }
    if ($BitLocker -ne 0) { throw 'BCD change blocked: BitLocker/device-encryption protection is active or unknown. Save your recovery key and review protection before changing boot settings. This installer does not suspend encryption.' }
    if ($Active) { return 'Enable' }
    return 'EnableRestart'
}
function Test-DriverPlan([string]$SelectedVersion,[string]$SelectedProvider,[int]$Problem) {
    if ($Problem -eq 12) { throw 'Code 12 resource conflict. Matching split-resource UEFI is required; no firmware is installed by this setup.' }
    if ($Problem -eq 22) { throw 'The device is disabled. Review Device Manager before installing; setup will not enable a deliberately disabled device.' }
    if ($SelectedVersion -and $SelectedProvider -ne $Provider) { throw 'A different driver provider is selected. Setup will not replace an unknown driver automatically.' }
    if ($SelectedVersion -and ([version]$SelectedVersion -gt [version]$Version)) { throw 'A newer driver is selected. Setup will not downgrade it.' }
    if ($SelectedVersion -eq $Version -and $SelectedProvider -eq $Provider -and $Problem -eq 0) { return 'Skip' }
    return 'Install'
}
function Initialize-Native {
    if ('Rpi5OneShotNative' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class Rpi5OneShotNative {
    [StructLayout(LayoutKind.Sequential)] struct CI { public uint Length; public uint Options; }
    [DllImport("ntdll.dll")] static extern int NtQuerySystemInformation(int c,ref CI info,uint size,out uint returned);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool IsWow64Process2(IntPtr process,out ushort processMachine,out ushort nativeMachine);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern SafeFileHandle CreateFileW(string n,uint access,uint share,IntPtr s,uint disposition,uint flags,IntPtr t);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool DeviceIoControl(SafeFileHandle h,uint code,IntPtr input,uint inputSize,[Out]uint[] output,uint outputSize,out uint returned,IntPtr overlapped);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int MessageBoxW(IntPtr window,string text,string title,uint flags);
    public static ushort Machine() {
        ushort process,native;
        if (!IsWow64Process2(Process.GetCurrentProcess().Handle,out process,out native)) throw new Win32Exception();
        return native;
    }
    public static uint Integrity() {
        CI ci=new CI(); ci.Length=8; uint returned;
        int status=NtQuerySystemInformation(103,ref ci,8,out returned);
        if (status!=0) throw new InvalidOperationException("Cannot query active Code Integrity: 0x"+status.ToString("X8"));
        return ci.Options;
    }
    public static uint[] FanStatus() {
        using(SafeFileHandle h=CreateFileW(@"\\.\Rpi5Fan",0x80000000,3,IntPtr.Zero,3,0,IntPtr.Zero)) {
            if(h.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
            uint[] s=new uint[16]; uint got;
            if(!DeviceIoControl(h,0x83376000,IntPtr.Zero,0,s,64,out got,IntPtr.Zero)) throw new Win32Exception(Marshal.GetLastWin32Error());
            if(got<64 || s[0]<64 || s[1]!=2 || s[2]>1 || s[3]>100) throw new InvalidOperationException("Incompatible fan driver status; exp.6 API v2 required.");
            return s;
        }
    }
}
'@
}
function Assert-SafePath([string]$Path) {
    $p = [IO.Path]::GetFullPath($Path)
    while ($p) {
        if (Test-Path -LiteralPath $p) {
            if (((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse point is not allowed in the installation path: $p" }
        }
        $parent = Split-Path -Parent $p
        if ($parent -eq $p) { break }
        $p = $parent
    }
}
function Test-Payload {
    foreach ($entry in $Hashes.GetEnumerator()) {
        $file = Join-Path $PackageRoot $entry.Key
        Assert-SafePath $file
        if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing embedded payload: $($entry.Key)" }
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.Value) { throw "Payload checksum mismatch: $($entry.Key). Nothing should be installed from this copy." }
    }
    Write-Host 'All nine payload files match the original driver and GUI SHA-256 pins.'
}
function Get-Selected([string]$Id) {
    Get-SelectedCimDevice -Id $Id
}
function Get-BcdSigning {
    # /v emits GUIDs, so no localized Yes/No text needs to be parsed.
    $text = & "$env:windir\System32\bcdedit.exe" /enum '{current}' /v 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read the current BCD entry.' }
    $id = [regex]::Match($text,'(?i)\{[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\}').Value
    if (!$id) { throw 'Cannot resolve the current boot-entry GUID.' }
    $class = [wmiclass]'root\wmi:BcdStore'
    $class.psbase.Scope.Options.EnablePrivileges = $true
    $opened = $class.OpenStore('')
    if (!$opened.ReturnValue) { throw 'Cannot open the system BCD store.' }
    $store = [wmi]'root\wmi:BcdStore.FilePath=""'
    $store.psbase.Scope.Options.EnablePrivileges = $true
    function Read-Boolean($Store,[string]$ObjectId,[int]$Depth) {
        if ($Depth -gt 8) { throw 'Unexpected BCD inheritance depth.' }
        if ($ObjectId -notmatch '(?i)^\{[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\}$') { throw 'Invalid BCD object identifier.' }
        $openedObject = $Store.OpenObject($ObjectId)
        if (!$openedObject.ReturnValue) { throw "Cannot read BCD object $ObjectId" }
        $objectPath = 'root\wmi:BcdObject.Id="' + $ObjectId + '",StoreFilePath=""'
        $object = [wmi]$objectPath
        $object.psbase.Scope.Options.EnablePrivileges = $true
        $elements = $object.EnumerateElements()
        if (!$elements.ReturnValue) { throw 'Cannot enumerate BCD elements.' }
        $own = @($elements.Elements | Where-Object { $_.Type -eq 0x16000049 })
        if ($own.Count) { return [bool]$own[0].Boolean }
        $parents = @($elements.Elements | Where-Object { $_.Type -eq 0x14000006 })
        $found = @()
        foreach ($parent in $parents) {
            foreach ($parentId in $parent.Ids) {
                $value = Read-Boolean $Store $parentId ($Depth+1)
                if ($null -ne $value) { $found += $value }
            }
        }
        $unique = @($found | Select-Object -Unique)
        if ($unique.Count -gt 1) { throw 'Conflicting inherited test-signing settings; review BCD manually.' }
        if ($unique.Count -eq 1) { return [bool]$unique[0] }
        return $null
    }
    [pscustomobject]@{ Id=$id; Enabled=[bool](Read-Boolean $store $id 0) }
}
function Get-BitLockerProtection {
    try {
        $volumes = @(Get-CimInstance -Namespace 'root\CIMV2\Security\MicrosoftVolumeEncryption' -ClassName Win32_EncryptableVolume -Filter "DriveLetter='$env:SystemDrive'" -ErrorAction Stop)
        if ($volumes.Count -eq 0) { return 0 }
        if ($volumes.Count -ne 1) { return -1 }
        $status = Invoke-CimMethod -InputObject $volumes[0] -MethodName GetProtectionStatus
        if ($status.ReturnValue -ne 0) { return -1 }
        return [int]$status.ProtectionStatus
    } catch { return -1 }
}
function Get-Preflight {
    Initialize-Native
    if ([Rpi5OneShotNative]::Machine() -ne 0xAA64 -or [IntPtr]::Size -ne 8) { throw 'This package requires Windows 11 ARM64 and native 64-bit Windows PowerShell.' }
    if ([int](Get-CimInstance Win32_OperatingSystem).BuildNumber -lt 22000) { throw 'Windows 11 (build 22000 or newer) is required.' }
    $temp = Get-Selected 'RPI0010'
    $fan = Get-Selected 'RPI000F'
    foreach ($device in @($temp,$fan)) {
        $plan = Test-DriverPlan $device.Version $device.Provider $device.Problem
        Write-Host "$($device.Id): version=$($device.Version) problem=$($device.Problem) action=$plan"
    }
    $ci = [Rpi5OneShotNative]::Integrity()
    $active = ($ci -band 2) -ne 0
    $bcd = Get-BcdSigning
    $secure = $false
    if (!($active -and $bcd.Enabled)) {
        try { $secure = [bool](Confirm-SecureBootUEFI -ErrorAction Stop) }
        catch {
            $record = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\SecureBoot\State' -Name UEFISecureBootEnabled -ErrorAction SilentlyContinue
            if ($null -eq $record -or $record.UEFISecureBootEnabled -notin @(0,1)) { throw 'Cannot determine Secure Boot state. Setup will not change boot policy when both firmware and Windows state checks are unavailable.' }
            $secure = [bool]$record.UEFISecureBootEnabled
        }
    }
    $protection = 0
    if (!$bcd.Enabled) { $protection = Get-BitLockerProtection }
    $action = Test-SigningPlan $active $bcd.Enabled $secure $protection
    Write-Host "Test signing active=$active configured=$($bcd.Enabled) action=$action; HVCI=$([bool]($ci -band 0x400))"
    [pscustomobject]@{ Action=$action; BcdId=$bcd.Id; Temp=$temp; Fan=$fan }
}
function Save-State {
    $path = Join-Path $PackageRoot 'Setup\State.json'
    $script:State | ConvertTo-Json | Set-Content -LiteralPath $path -Encoding UTF8
}
function Remove-Resume {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop }
}
function Register-Resume {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $scriptPath = Join-Path $PackageRoot 'Setup\Install-OneShot.ps1'
    $args = '-NoProfile -ExecutionPolicy Bypass -File "' + $scriptPath + '" -Phase Resume -PackageRoot "' + $PackageRoot + '" -ResultFile "' + (Join-Path $PackageRoot 'Setup\LastResult.txt') + '" -Consent'
    $action = New-ScheduledTaskAction -Execute "$env:windir\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument $args -WorkingDirectory $PackageRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $sid
    $principal = New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Continue the explicitly approved RPi5 fan installation after restart; removed after completion or failure.' -Force | Out-Null
    Save-State
}
function Import-DriverCertificate {
    $path = Join-Path $PackageRoot 'Drivers\Rpi5Fan\Rpi5Fan.cer'
    $cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new($path)
    if ($cert.Thumbprint -ne 'F59169D1D4E34BD3628141CCFCB74382608C17AF') { throw 'Unexpected driver certificate.' }
    if ((Get-Date) -lt $cert.NotBefore -or (Get-Date) -gt $cert.NotAfter) { throw 'The driver certificate is not valid at the current system date. Correct the Pi clock before installing.' }
    foreach ($store in @('Root','TrustedPublisher')) {
        if (Test-Path "Cert:\LocalMachine\$store\$($cert.Thumbprint)") { Write-Host "SKIP: driver certificate already present in $store" }
        else { Import-Certificate -FilePath $path -CertStoreLocation "Cert:\LocalMachine\$store" | Out-Null; Write-Host "Installed exact test certificate in $store" }
    }
    foreach ($name in @('Rpi5Temp','Rpi5Fan')) {
        foreach ($file in @("$name.sys",("$name.cat".ToLowerInvariant()))) {
            $signature = Get-AuthenticodeSignature (Join-Path $PackageRoot "Drivers\$name\$file")
            if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Thumbprint -ne $cert.Thumbprint) { throw "Driver signature validation failed: $file ($($signature.Status))" }
        }
    }
}
function Install-Device([string]$Id,[string]$Name) {
    $selected = Get-Selected $Id
    if ((Test-DriverPlan $selected.Version $selected.Provider $selected.Problem) -eq 'Skip') { Write-Host "SKIP: $Name $Version is already healthy."; return }
    $inf = Join-Path $PackageRoot "Drivers\$Name\$Name.inf"
    Write-Host "Installing $Name through PnPUtil (no forced removal/downgrade)."
    & "$env:windir\System32\pnputil.exe" /add-driver $inf /install | Out-Host
    $code = $LASTEXITCODE
    if ($code -notin @(0,259,3010,1641)) { throw "PnPUtil failed for $Name, code $code. No old driver package was deleted." }
    if ($code -in @(3010,1641)) { $script:RestartNeeded = $true; return }
    Start-Sleep -Seconds 2
    $selected = Get-Selected $Id
    if ($selected.Problem -eq 14) { $script:RestartNeeded = $true; return }
    if ($selected.Problem -ne 0 -or $selected.Status -ne 'OK' -or $selected.Version -ne $Version -or $selected.Provider -ne $Provider) {
        throw "$Name is not healthy/selected after installation: INF=$($selected.Inf), version=$($selected.Version), problem=$($selected.Problem). Inspect Device Manager and SetupAPI.dev.log. Setup does not claim success or force-delete competing packages."
    }
}
function Invoke-SelfTest {
    Initialize-Native
    $tests = 0
    foreach ($active in @($false,$true)) {
        foreach ($configured in @($false,$true)) {
            foreach ($secure in @($false,$true)) {
                foreach ($bl in @(0,1,-1)) {
                    $expected = if ($active -and $configured) {'Skip'} elseif ($secure) {'Block'} elseif ($configured) {'Restart'} elseif ($bl -ne 0) {'Block'} elseif ($active) {'Enable'} else {'EnableRestart'}
                    try { $actual = Test-SigningPlan $active $configured $secure $bl } catch { $actual = 'Block' }
                    if ($actual -ne $expected) { throw "Signing policy failed: $active/$configured/$secure/$bl" }
                    $tests++
                }
            }
        }
    }
    if ((Test-DriverPlan $Version $Provider 0) -ne 'Skip') { throw 'Healthy-driver skip failed.' }; $tests++
    if ((Test-DriverPlan '' '' 28) -ne 'Install') { throw 'Fresh-driver install failed.' }; $tests++
    if ((Test-DriverPlan '2026.8.17.3' $Provider 0) -ne 'Install') { throw 'Older-driver update failed.' }; $tests++
    foreach ($case in @(@($Version,$Provider,12),@($Version,$Provider,22),@('2027.1.1.0',$Provider,0),@($Version,'Unknown Provider',0))) {
        $blocked=$false; try { $null=Test-DriverPlan $case[0] $case[1] $case[2] } catch { $blocked=$true }
        if (!$blocked) { throw 'Unsafe driver replacement was not blocked.' }; $tests++
    }
    Test-Payload
    $null=[Rpi5OneShotNative]::Integrity()
    Write-Result "PASS: $tests policy tests; nine pinned payload hashes; live read-only integrity query. No BCD/certificate/driver/task changes. Native machine=$([Rpi5OneShotNative]::Machine())."
}
$exitCode = 0
try {
    $PackageRoot = [IO.Path]::GetFullPath($PackageRoot).TrimEnd('\')
    . (Join-Path $PSScriptRoot 'DeviceDetection.ps1')
    if ($Phase -eq 'SelfTest') { Invoke-SelfTest; exit 0 }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $admin = [Security.Principal.WindowsPrincipal]::new($identity)
    if (!$admin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator permission is required. Run the OneShot Setup EXE.' }
    Assert-SafePath $PackageRoot
    $Mutex = [Threading.Mutex]::new($false,'Global\RPi5Fan-OneShot-Install')
    try { $OwnMutex=$Mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $OwnMutex=$true }
    if (!$OwnMutex) { throw 'Another RPi5 fan installation is already running.' }
    if ($Phase -eq 'Preflight') {
        $check=Get-Preflight
        Write-Result "Preflight passed. Temperature: $($check.Temp.Id), Code $($check.Temp.Problem). Fan: $($check.Fan.Id), Code $($check.Fan.Problem). Code 28 is accepted as a present device awaiting driver installation. Test-signing plan: $($check.Action)."
        exit 0
    }
    if (!$Consent) { throw 'Explicit test-signing/certificate consent is required.' }
    $expectedRoot = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'RPi5FanControl-OneShot'
    if ($PackageRoot -ne $expectedRoot) { throw 'Driver installation must run from the protected Program Files installation directory.' }
    Test-Payload
    $logDir = Join-Path $PackageRoot 'Setup\Logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    Start-Transcript -Path (Join-Path $logDir ('install-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')) -Force | Out-Null
    $Transcript=$true
    Write-Host "OneShot beta.3 Phase=$Phase; identity=$($identity.User.Value)"
    $statePath = Join-Path $PackageRoot 'Setup\State.json'
    if (Test-Path $statePath) {
        $saved=Get-Content $statePath -Raw | ConvertFrom-Json
        foreach ($key in @('SigningRestart','DriverRestart','Attempts')) { $script:State[$key]=$saved.$key }
    }
    if ($Phase -eq 'Resume') {
        Remove-Resume
        $script:State.Attempts = [int]$script:State.Attempts + 1
        if ($script:State.Attempts -gt 2) { throw 'Automatic continuation limit reached. No reboot loop will be scheduled; review the installer log.' }
    } else { $script:State.Attempts=0 }
    $boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('O')
    $preflight=Get-Preflight
    if ($preflight.Action -in @('Restart','EnableRestart')) {
        if ($script:State.SigningRestart -and $script:State.SigningRestart -ne $boot) { throw 'Test signing is still inactive after restarting. Setup stopped instead of repeatedly rebooting or disabling security features.' }
        $script:State.SigningRestart=$boot
        Register-Resume
        if ($preflight.Action -eq 'EnableRestart') {
            & "$env:windir\System32\bcdedit.exe" /set $preflight.BcdId testsigning on | Out-Host
            if ($LASTEXITCODE -ne 0 -or !(Get-BcdSigning).Enabled) { throw 'Could not enable test signing. No driver was installed.' }
        }
        Write-Result 'RESTART REQUIRED: test signing is configured but not active yet. No driver was installed during this phase. Restart Windows and sign in to the same installing administrator account; setup continues automatically. Save your work before restarting.'
        $exitCode=3010
    } else {
        if ($preflight.Action -eq 'Enable') {
            & "$env:windir\System32\bcdedit.exe" /set $preflight.BcdId testsigning on | Out-Host
            if ($LASTEXITCODE -ne 0 -or !(Get-BcdSigning).Enabled) { throw 'Could not preserve test signing for the next boot.' }
        } else { Write-Host 'SKIP: test signing is already configured AND active; BCD not changed.' }
        Import-DriverCertificate
        Install-Device 'RPI0010' 'Rpi5Temp'
        if (!$script:RestartNeeded) { Install-Device 'RPI000F' 'Rpi5Fan' }
        if ($script:RestartNeeded) {
            if ($script:State.DriverRestart -and $script:State.DriverRestart -ne $boot) { throw 'Driver installation still requests a reboot after the driver restart. Stopping automatic continuation; check the log.' }
            $script:State.DriverRestart=$boot; Register-Resume
            Write-Result 'RESTART REQUIRED: Windows deferred a driver start. Restart and sign in to the same installing administrator account to finish verification automatically. The GUI is installed, but driver readiness is not yet confirmed.'
            $exitCode=3010
        } else {
            $ready=$false; $detail=''
            for ($i=0;$i -lt 6;$i++) {
                try {
                    $s=[Rpi5OneShotNative]::FanStatus()
                    if ($s[7] -ne 0 -and $s[13] -ne 0 -and $s[6] -ne 0) { $ready=$true; break }
                    $detail="hardware=$($s[7]), temperature provider=$($s[13]), temperature valid=$($s[6])"
                } catch { $detail=$_.Exception.Message }
                Start-Sleep -Seconds 2
            }
            if (!$ready) { throw "Drivers were processed, but live API v2 readiness was not confirmed: $detail. Check the physical cooler and the installer log." }
            Remove-Resume
            $script:State=@{ SigningRestart=''; DriverRestart=''; Attempts=0 }; Save-State
            Write-Result "INSTALLATION COMPLETE: Rpi5Temp and Rpi5Fan $Version are healthy, and the fan API v2 reports hardware and valid temperature telemetry. Use the desktop/start-menu shortcut. The driver's existing mode is preserved; select Automatic in the GUI for temperature-managed cooling. Verify the physical fan is spinning."
        }
    }
} catch {
    $exitCode=1
    if ($Phase -ne 'Preflight' -and $Phase -ne 'SelfTest' -and $OwnMutex) {
        try { Remove-Resume } catch { Write-Warning 'Could not remove the resume task; remove RPi5Fan-OneShot-beta2-Resume in Task Scheduler.' }
    }
    if ($Phase -eq 'Preflight') {
        Write-Result ("PREFLIGHT STOPPED: " + $_.Exception.Message + "`r`nNo driver, certificate or boot-policy changes were made by this preflight. Details are also recorded in the Inno Setup log in your Windows temporary folder.")
    } else {
        Write-Result ("INSTALLATION NOT COMPLETE: " + $_.Exception.Message + "`r`nNo forced removal of existing drivers, firmware update, Secure Boot change, BitLocker suspension, or Memory Integrity change was performed. Review Setup\Logs in the installation folder. A previously completed BCD/certificate/driver change is not automatically rolled back.")
    }
} finally {
    if ($Transcript) { Stop-Transcript -ErrorAction SilentlyContinue | Out-Null }
    if ($OwnMutex) { $Mutex.ReleaseMutex() }
    if ($Mutex) { $Mutex.Dispose() }
}
if ($Phase -eq 'Resume') {
    Initialize-Native
    $message=[IO.File]::ReadAllText($ResultFile)
    if ($exitCode -eq 3010) {
        $answer=[Rpi5OneShotNative]::MessageBoxW([IntPtr]::Zero,$message+"`r`n`r`nRestart now?",'RPi5 Fan OneShot Setup',0x134)
        if ($answer -eq 6) { & "$env:windir\System32\shutdown.exe" /r /t 0 }
    } else { $null=[Rpi5OneShotNative]::MessageBoxW([IntPtr]::Zero,$message,'RPi5 Fan OneShot Setup',0x40) }
}
exit $exitCode
