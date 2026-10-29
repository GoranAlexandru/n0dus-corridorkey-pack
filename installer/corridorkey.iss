// CorridorKey Pack installer (Inno Setup 6.7+). Built by scripts\build_installer.py, which
// passes /DAppVersion=... /DStageDir=... /DOutDir=... and refuses to run unless the stage
// verifies against its file list. Design: PACK_PLAN.md sections 2, 4-7, 10.
//
// Comments in this file use // (never ';' inside [Code]).

#ifndef AppVersion
  #error Build with scripts\build_installer.py (AppVersion not defined)
#endif
#ifndef StageDir
  #error Build with scripts\build_installer.py (StageDir not defined)
#endif
#ifndef OutDir
  #define OutDir "..\out"
#endif

[Setup]
AppId={{E05F8F94-2508-48F7-BE4A-00FA6FC7C01C}
AppName=CorridorKey
AppVersion={#AppVersion}
AppVerName=CorridorKey (Pack {#AppVersion})
AppPublisher=Studio-internal pack of CorridorKey 2.0 by Corridor Digital LLC
VersionInfoDescription=CorridorKey Pack installer (studio-internal)
DefaultDirName={code:DefaultInstallDir}
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
// The precise Windows check (22H2 / 11, with a plain message) is in InitializeSetup.
MinVersion=10.0
// Two files, one folder: CorridorKey-Setup.exe + CorridorKey-Setup-1.bin (ruling Q1 a).
DiskSpanning=yes
DiskSliceSize=max
SlicesPerDisk=1
Compression=lzma2/fast
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=8
SolidCompression=no
OutputDir={#OutDir}
OutputBaseFilename=CorridorKey-Setup
SetupIconFile={#StageDir}\app\corridorkey.ico
UninstallDisplayIcon={app}\app\corridorkey.ico
UninstallDisplayName=CorridorKey
AppMutex=CorridorKeyPack.App
SetupLogging=yes
WizardStyle=modern
// Room for temp files and caches beyond the installed files themselves.
ExtraDiskSpaceRequired=1500000000
LicenseFile={#StageDir}\licences\INSTALLER_NOTICE.txt

[Messages]
SetupAppRunningError=CorridorKey is open. Please close its window (and any running keying job), then click OK.
UninstallAppRunningError=CorridorKey is open. Please close its window (and any running keying job), then click OK.

[InstallDelete]
// Upgrade: replace everything except data\ (settings + logs, ruling: upgrades keep them).
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\corridorkey"
Type: filesandordirs; Name: "{app}\third_party"
Type: filesandordirs; Name: "{app}\scripts"
Type: filesandordirs; Name: "{app}\weights"
Type: filesandordirs; Name: "{app}\vfms"
Type: filesandordirs; Name: "{app}\ffmpeg"
Type: filesandordirs; Name: "{app}\licences"
Type: filesandordirs; Name: "{app}\selftest"
Type: filesandordirs; Name: "{app}\manifest"
Type: filesandordirs; Name: "{app}\tmp"
Type: filesandordirs; Name: "{app}\.cache"
Type: filesandordirs; Name: "{app}\data\install"
Type: filesandordirs; Name: "{app}\data\selftest"

[Files]
// Models are already dense float data: stored, not recompressed (saves minutes, costs ~nothing).
Source: "{#StageDir}\weights\*"; DestDir: "{app}\weights"; Flags: ignoreversion recursesubdirs createallsubdirs nocompression
Source: "{#StageDir}\vfms\*"; DestDir: "{app}\vfms"; Flags: ignoreversion recursesubdirs createallsubdirs nocompression
Source: "{#StageDir}\*"; DestDir: "{app}"; Excludes: "\weights\*,\vfms\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CorridorKey"; Filename: "{app}\python\pythonw.exe"; Parameters: "-I ""{app}\app\ck_gui.py"""; WorkingDir: "{app}"; IconFilename: "{app}\app\corridorkey.ico"; Comment: "CorridorKey: AI green/blue-screen keyer (studio-internal)"

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-I ""{app}\app\ck_gui.py"""; WorkingDir: "{app}"; Description: "Open CorridorKey now"; Flags: postinstall nowait skipifsilent
Filename: "{app}\data\install\selftest.log"; Description: "Show the self-test log"; Flags: postinstall shellexec skipifsilent; Check: SelfTestFailed

[UninstallRun]
// Removes %LOCALAPPDATA%\CorridorKey\install.json, but only if it points at THIS install.
Filename: "{app}\python\python.exe"; Parameters: "-I ""{app}\app\selftest.py"" --step uninstall"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveDiscovery"

[UninstallDelete]
// Only the folders the pack itself creates, BY NAME. The install folder is never deleted
// wholesale (the user's output files can never be reached); it goes only if empty after.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\corridorkey"
Type: filesandordirs; Name: "{app}\third_party"
Type: filesandordirs; Name: "{app}\scripts"
Type: filesandordirs; Name: "{app}\weights"
Type: filesandordirs; Name: "{app}\vfms"
Type: filesandordirs; Name: "{app}\ffmpeg"
Type: filesandordirs; Name: "{app}\licences"
Type: filesandordirs; Name: "{app}\selftest"
Type: filesandordirs; Name: "{app}\manifest"
Type: filesandordirs; Name: "{app}\tmp"
Type: filesandordirs; Name: "{app}\.cache"
// Ruling Q7 a: settings and logs go too.
Type: filesandordirs; Name: "{app}\data"
Type: dirifempty; Name: "{app}"

[Code]
const
  MinDriverMajor = 570;
  MinDriverMinor = 65;
  MinComputeX10 = 86;        // compute capability 8.6 = RTX 30-series
  RefuseBelowMiB = 5900;     // "6 GB" cards report 6144 MiB (ruling Q4 b)
  WarnBelowMiB = 7900;       // "8 GB" cards report 8192 MiB
  NeedFreeGB = 12;
  MaxPathLen = 90;

var
  SelfTestOK: Boolean;
  SelfTestSummary: String;

// ---------------------------------------------------------------- helpers
function Simulate(const What: String): Boolean;
begin
  // Test hook only: CorridorKey-Setup.exe /CKSIMULATE=olddriver makes that check fail
  // through the real message path. Never used by colleagues.
  Result := Pos(',' + What + ',', ',' + Lowercase(ExpandConstant('{param:CKSIMULATE|}')) + ',') > 0;
end;

function IsPlainAscii(const S: String): Boolean;
var
  I: Integer;
  C: Char;
begin
  Result := True;
  for I := 1 to Length(S) do
  begin
    C := S[I];
    if not (((C >= 'A') and (C <= 'Z')) or ((C >= 'a') and (C <= 'z')) or ((C >= '0') and (C <= '9'))
            or (C = '\') or (C = ':') or (C = '_') or (C = '-') or (C = '.') or (C = ' ')) then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

function DefaultInstallDir(Param: String): String;
begin
  // Ruling Q5 a: per-user like N0DUS, unless the user's profile path is not plain ASCII.
  Result := ExpandConstant('{localappdata}\Programs\CorridorKey');
  if (not IsPlainAscii(Result)) or (Length(Result) > 60) or Simulate('unicodeuser') then
    Result := 'C:\CorridorKey';
end;

function SplitCsv(const Line: String; var Parts: TArrayOfString): Integer;
var
  S: String;
  P, N: Integer;
begin
  S := Line;
  N := 0;
  SetArrayLength(Parts, 0);
  repeat
    P := Pos(',', S);
    SetArrayLength(Parts, N + 1);
    if P > 0 then
    begin
      Parts[N] := Trim(Copy(S, 1, P - 1));
      Delete(S, 1, P);
    end else
      Parts[N] := Trim(S);
    N := N + 1;
  until P = 0;
  Result := N;
end;

// "8.6" -> 86, "12.0" -> 120, "610.62" -> major 610 / minor 62
procedure SplitVersion(const V: String; var Major, Minor: Integer);
var
  P: Integer;
begin
  P := Pos('.', V);
  if P = 0 then
  begin
    Major := StrToIntDef(V, -1);
    Minor := 0;
  end else
  begin
    Major := StrToIntDef(Copy(V, 1, P - 1), -1);
    Minor := StrToIntDef(Copy(V, P + 1, 2), 0);
  end;
end;

// ---------------------------------------------------------------- pre-checks
function CheckWindows(var Msg: String): Boolean;
var
  V: TWindowsVersion;
begin
  GetWindowsVersionEx(V);
  if Simulate('oldwindows') then
    V.Build := 19044;
  Result := (V.Major = 10) and (V.Build >= 19045);
  if not Result then
    Msg := Format('CorridorKey needs Windows 10 (version 22H2) or Windows 11, 64-bit.' + #13#10 +
                  'This PC runs Windows %d.%d build %d.' + #13#10#13#10 +
                  'Please update Windows, then run this installer again. Nothing was installed.',
                  [V.Major, V.Minor, V.Build]);
end;

function CheckGpu(var Msg: String; var Warning: String): Boolean;
var
  Smi, Name: String;
  Out: TExecOutput;
  RC, N, CompMaj, CompMin, Comp, DrvMaj, DrvMin, MiB: Integer;
  F: TArrayOfString;
begin
  Result := False;
  Warning := '';
  Smi := ExpandConstant('{sys}\nvidia-smi.exe');
  if not FileExists(Smi) then
    Smi := ExpandConstant('{commonpf64}\NVIDIA Corporation\NVSMI\nvidia-smi.exe');
  if Simulate('nogpu') or (not FileExists(Smi)) or
     (not ExecAndCaptureOutput(Smi, '--query-gpu=name,compute_cap,driver_version,memory.total --format=csv,noheader,nounits',
                               '', SW_HIDE, ewWaitUntilTerminated, RC, Out)) or (RC <> 0) or (GetArrayLength(Out.StdOut) = 0) then
  begin
    Msg := 'No NVIDIA graphics card (or no NVIDIA driver) was found on this PC.' + #13#10#13#10 +
           'CorridorKey needs an NVIDIA RTX 30-series graphics card or newer, with its driver installed. ' +
           'Nothing was installed.';
    Exit;
  end;
  Log('nvidia-smi: ' + Out.StdOut[0]);
  // The first line is GPU 0, the card CorridorKey uses (the app sets CUDA_DEVICE_ORDER=PCI_BUS_ID).
  N := SplitCsv(Out.StdOut[0], F);
  if N < 4 then
  begin
    Msg := 'The NVIDIA driver answered in an unexpected way (' + Out.StdOut[0] + '). ' +
           'Please update the NVIDIA driver and try again. Nothing was installed.';
    Exit;
  end;
  Name := F[0];
  SplitVersion(F[1], CompMaj, CompMin);
  Comp := CompMaj * 10 + CompMin;
  SplitVersion(F[2], DrvMaj, DrvMin);
  MiB := StrToIntDef(F[3], 0);
  if Simulate('oldgpu') then Comp := 75;
  if Simulate('olddriver') then begin DrvMaj := 560; DrvMin := 94; end;
  if Simulate('lowvram') then MiB := 4096;
  if Simulate('smallvram') then MiB := 6144;
  if Comp < MinComputeX10 then
  begin
    Msg := 'This PC''s graphics card (' + Name + ') is older than an RTX 30-series.' + #13#10#13#10 +
           'CorridorKey needs an NVIDIA RTX 30-series card or newer. Nothing was installed.';
    if GetArrayLength(Out.StdOut) > 1 then
      Msg := Msg + #13#10#13#10 + 'Note: this PC has more than one NVIDIA card; CorridorKey uses the first one (' + Name + ').';
    Exit;
  end;
  if (DrvMaj < MinDriverMajor) or ((DrvMaj = MinDriverMajor) and (DrvMin < MinDriverMinor)) then
  begin
    Msg := Format('The NVIDIA driver on this PC is version %d.%.2d. CorridorKey needs %d.%.2d or newer.' + #13#10#13#10 +
                  'Update it from nvidia.com or the NVIDIA app, then run this installer again. Nothing was installed.',
                  [DrvMaj, DrvMin, MinDriverMajor, MinDriverMinor]);
    Exit;
  end;
  if MiB < RefuseBelowMiB then
  begin
    Msg := Format('%s has %d GB of graphics memory; CorridorKey needs at least 6 GB. Nothing was installed.',
                  [Name, (MiB + 512) div 1024]);
    Exit;
  end;
  if MiB < WarnBelowMiB then
    Warning := Format('%s has %d GB of graphics memory.' + #13#10#13#10 +
                      'CorridorKey will work, but only for small clips: larger clips will be refused, or keyed ' +
                      'with a smaller time window (slightly softer edges).' + #13#10#13#10 + 'Install anyway?',
                      [Name, (MiB + 512) div 1024]);
  Result := True;
end;

function CheckFolder(const Dir: String; var Msg: String): Boolean;
var
  FreeMB, TotalMB: Cardinal;
  Drive: String;
begin
  Result := False;
  if (not IsPlainAscii(Dir)) or Simulate('unicodedir') then
  begin
    Msg := 'Please choose a folder whose path uses only plain English letters, numbers, spaces and - _ . ' +
           '(no accents or other alphabets), for example C:\CorridorKey.' + #13#10#13#10 + 'Chosen: ' + Dir;
    Exit;
  end;
  if Length(Dir) > MaxPathLen then
  begin
    Msg := Format('Please choose a shorter folder path (at most %d characters; this one has %d), for example C:\CorridorKey.',
                  [MaxPathLen, Length(Dir)]);
    Exit;
  end;
  Drive := ExtractFileDrive(Dir);
  if (not GetSpaceOnDisk(Drive, True, FreeMB, TotalMB)) then
    FreeMB := 0;
  if Simulate('lowdisk') then FreeMB := 3000;
  // An upgrade over an existing install frees the old copy first: count it as available.
  if FileExists(AddBackslash(Dir) + 'manifest\payload.sha256') then
    FreeMB := FreeMB + 10000;
  if FreeMB < NeedFreeGB * 1024 then
  begin
    Msg := Format('The drive %s has %d GB free; CorridorKey needs %d GB.' + #13#10#13#10 +
                  'Free some space or choose a folder on another drive. Nothing was installed.',
                  [Drive, FreeMB div 1024, NeedFreeGB]);
    Exit;
  end;
  Result := True;
end;

function InitializeSetup(): Boolean;
var
  Msg, Warning: String;
begin
  Result := False;
  if not CheckWindows(Msg) then
  begin
    SuppressibleMsgBox(Msg, mbCriticalError, MB_OK, IDOK);
    Log('pre-check failed: ' + Msg);
    Exit;
  end;
  if not CheckGpu(Msg, Warning) then
  begin
    SuppressibleMsgBox(Msg, mbCriticalError, MB_OK, IDOK);
    Log('pre-check failed: ' + Msg);
    Exit;
  end;
  if Warning <> '' then
  begin
    Log('pre-check warning: ' + Warning);
    if SuppressibleMsgBox(Warning, mbConfirmation, MB_YESNO, IDYES) <> IDYES then
      Exit;
  end;
  Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Msg: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
    if not CheckFolder(WizardDirValue, Msg) then
    begin
      SuppressibleMsgBox(Msg, mbError, MB_OK, IDOK);
      Result := False;
    end;
end;

// The hard gate, also in silent installs: nothing is written before this passes.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Msg: String;
begin
  Result := '';
  if not CheckFolder(ExpandConstant('{app}'), Msg) then
  begin
    Log('pre-check failed: ' + Msg);
    Result := Msg;
  end;
end;

// ---------------------------------------------------------------- self-test
function RunStep(const Step: String): Boolean;
var
  RC: Integer;
begin
  Result := Exec(ExpandConstant('{app}\python\python.exe'),
                 '-I "' + ExpandConstant('{app}\app\selftest.py') + '" --step ' + Step,
                 ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, RC) and (RC = 0);
  Log(Format('self-test step %s: exit %d', [Step, RC]));
end;

procedure RunSelfTest();
var
  Page: TOutputProgressWizardPage;
  Summary: AnsiString;
begin
  Page := CreateOutputProgressPage('Testing CorridorKey',
    'Checking the installed files, then keying a test image on this PC''s graphics card. This takes about a minute.');
  Page.Show;
  try
    RunStep('reset');
    Page.SetText('Checking every installed file against the pack''s list…', '');
    Page.SetProgress(0, 4);
    RunStep('verify');
    Page.SetText('Loading CorridorKey''s model onto the graphics card…', '');
    Page.SetProgress(1, 4);
    RunStep('smoke');
    Page.SetText('Keying the test image…', '');
    Page.SetProgress(2, 4);
    RunStep('key');
    Page.SetProgress(3, 4);
    SelfTestOK := RunStep('finish');
    Page.SetProgress(4, 4);
  finally
    Page.Hide;
  end;
  if LoadStringFromFile(ExpandConstant('{app}\data\install\selftest_summary.txt'), Summary) then
    SelfTestSummary := String(Summary)
  else
    SelfTestSummary := 'FAIL: the self-test did not report a result.';
  Log('self-test: ' + SelfTestSummary);
end;

function SelfTestFailed(): Boolean;
begin
  Result := not SelfTestOK;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    RunSelfTest();
  if CurStep = ssDone then
    // Keep Setup's own log with the install, beside the self-test log.
    FileCopy(ExpandConstant('{log}'), ExpandConstant('{app}\data\install\setup.log'), False);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
  begin
    if SelfTestOK then
    begin
      WizardForm.FinishedHeadingLabel.Caption := 'CorridorKey is installed and its self-test PASSED';
      WizardForm.FinishedLabel.Caption := SelfTestSummary + #13#10#13#10 +
        'Open it from the Start menu: CorridorKey.';
    end else
    begin
      WizardForm.FinishedHeadingLabel.Caption := 'CorridorKey is installed, but its self-test FAILED';
      WizardForm.FinishedHeadingLabel.Font.Color := clRed;
      WizardForm.FinishedLabel.Caption := SelfTestSummary + #13#10#13#10 +
        'Please send the self-test log (tick the box below to open it) to the person who gave you this installer.';
    end;
  end;
end;
