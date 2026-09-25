; SPDX-License-Identifier: BSD-2-Clause-Patent
#ifndef PayloadDir
  #define PayloadDir "stage"
#endif
#ifndef OutputPath
  #define OutputPath "dist"
#endif
[Setup]
AppId={{C649BA4E-F8E2-4FD1-8E49-53D9F573A202}
AppName=Raspberry Pi 5 Fan Control
AppVersion=0.2.0-beta.2
AppVerName=Raspberry Pi 5 Fan Control One-Shot Setup 0.2.0-beta.2
AppPublisher=RPi5 UEFI Community
DefaultDirName={autopf}\RPi5FanControl-OneShot
DisableDirPage=yes
DisableProgramGroupPage=yes
UsePreviousAppDir=no
DefaultGroupName=Raspberry Pi 5 Fan Control
PrivilegesRequired=admin
ArchitecturesAllowed=arm64
ArchitecturesInstallIn64BitMode=arm64
MinVersion=10.0.22000
WizardStyle=modern
OutputBaseFilename=Rpi5FanControl-OneShot-ARM64-Setup
OutputDir={#OutputPath}
Compression=lzma2
SolidCompression=yes
SetupIconFile={#PayloadDir}\fan.ico
UninstallDisplayIcon={app}\Rpi5FanControl-ARM64.exe
InfoBeforeFile={#PayloadDir}\INSTALL-FIRST.txt
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
[Files]
Source: "{#PayloadDir}\Rpi5FanControl-ARM64.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\Drivers\*"; DestDir: "{app}\Drivers"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#PayloadDir}\Install-OneShot.ps1"; DestDir: "{app}\Setup"; Flags: ignoreversion
Source: "{#PayloadDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\PROVENANCE.json"; DestDir: "{app}\Setup"; Flags: ignoreversion
Source: "{#PayloadDir}\INSTALL-FIRST.txt"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{commondesktop}\Raspberry Pi 5 Fan Control"; Filename: "{app}\Rpi5FanControl-ARM64.exe"; WorkingDir: "{app}"
Name: "{commonprograms}\Raspberry Pi 5 Fan Control\Fan Control"; Filename: "{app}\Rpi5FanControl-ARM64.exe"; WorkingDir: "{app}"
Name: "{commonprograms}\Raspberry Pi 5 Fan Control\Installation instructions"; Filename: "{app}\INSTALL-FIRST.txt"
[Run]
Filename: "{app}\Rpi5FanControl-ARM64.exe"; Description: "Open Fan Control"; Flags: postinstall nowait skipifsilent; Check: InstallationReady
[UninstallRun]
Filename: "{sys}\schtasks.exe"; Parameters: "/delete /tn ""RPi5Fan-OneShot-beta2-Resume"" /f"; Flags: runhidden; RunOnceId: "RemoveResumeTask"
[Code]
var
  ConsentPage: TInputOptionWizardPage;
  RestartPending, DriverFailed: Boolean;
  LastResult: String;
function PowerShell: String;
begin
  Result := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
end;
function ReadResult(const Path: String): String;
var Text: AnsiString;
begin
  if LoadStringFromFile(Path, Text) then Result := UTF8ToString(Text)
  else Result := 'No result was returned. Review the setup log; driver installation is not confirmed.';
end;
procedure InitializeWizard;
begin
  ConsentPage := CreateInputOptionPage(wpInfoBefore, 'Driver and boot-policy consent',
    'This package installs experimental test-signed kernel drivers.',
    'Setup installs the original Rpi5Temp and Rpi5Fan drivers and their test certificate. ' +
    'It enables system-wide Windows test signing ONLY when required. This allows test-signed drivers and may show a Test Mode watermark. ' +
    'A required restart is offered, never forced. After restart, setup can continue at the next sign-in of this administrator. ' +
    'Secure Boot, BitLocker, Memory Integrity and UEFI firmware are not changed.', False, False);
  ConsentPage.Add('I approve these driver, certificate, and test-signing changes.');
  ConsentPage.Values[0] := ExpandConstant('{param:ACCEPTTESTSIGNING|0}') = '1';
end;
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = ConsentPage.ID) and not ConsentPage.Values[0] then begin
    if not WizardSilent then MsgBox('Approval is required to install the test-signed drivers.', mbInformation, MB_OK);
    Result := False;
  end;
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer; ScriptPath, ResultPath, Args: String;
begin
  Result := '';
  if not ConsentPage.Values[0] then begin Result := 'Explicit test-signing consent was not given.'; Exit; end;
  if CompareText(WizardDirValue, ExpandConstant('{autopf}\RPi5FanControl-OneShot')) <> 0 then begin
    Result := 'This installer uses a fixed protected Program Files directory. Remove any /DIR override.'; Exit;
  end;
  ExtractTemporaryFile('Install-OneShot.ps1');
  ScriptPath := ExpandConstant('{tmp}\Install-OneShot.ps1');
  ResultPath := ExpandConstant('{tmp}\preflight-result.txt');
  Args := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ScriptPath +
    '" -Phase Preflight -PackageRoot "' + WizardDirValue + '" -ResultFile "' + ResultPath + '"';
  if not Exec(PowerShell, Args, '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Result := 'Could not start native Windows PowerShell for read-only preflight checks.'
  else if Code <> 0 then Result := ReadResult(ResultPath);
end;
procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer; Args, ResultPath: String;
begin
  if CurStep = ssPostInstall then begin
    ResultPath := ExpandConstant('{app}\Setup\LastResult.txt');
    Args := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\Setup\Install-OneShot.ps1') +
      '" -Phase Install -PackageRoot "' + ExpandConstant('{app}') + '" -ResultFile "' + ResultPath + '" -Consent';
    if not Exec(PowerShell, Args, '', SW_HIDE, ewWaitUntilTerminated, Code) then Code := 1;
    LastResult := ReadResult(ResultPath);
    RestartPending := Code = 3010;
    DriverFailed := (Code <> 0) and not RestartPending;
    Log(LastResult);
    if DriverFailed and not WizardSilent then MsgBox(LastResult, mbError, MB_OK);
  end;
end;
function InstallationReady: Boolean;
begin Result := not DriverFailed and not RestartPending; end;
function NeedRestart: Boolean;
begin Result := RestartPending; end;
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then begin
    WizardForm.FinishedLabel.Caption := LastResult;
    if DriverFailed then WizardForm.FinishedHeadingLabel.Caption := 'Driver installation did not complete'
    else if RestartPending then WizardForm.FinishedHeadingLabel.Caption := 'Restart required to finish setup';
  end;
end;
function GetCustomSetupExitCode: Integer;
begin
  if DriverFailed then Result := 1
  else if RestartPending then Result := 3010
  else Result := 0;
end;
