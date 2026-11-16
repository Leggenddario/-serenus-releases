#define AppName "Serenus"
#define AppVersion "1.0.0"
[Setup]
AppId={{B637FC94-9660-49C9-95AC-7180B27D6894}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Serenus
DefaultDirName={localappdata}\Serenus
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=dist
OutputBaseFilename=Serenus_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=serenus.ico
Uninstallable=no
DisableWelcomePage=no
[Files]
Source: "updater\*.py"; DestDir: "{app}\launcher\updater"; Flags: ignoreversion
Source: "release-public-key.txt"; DestDir: "{app}\launcher"; Flags: ignoreversion
Source: "release-config.txt"; DestDir: "{app}\launcher"; Flags: ignoreversion
Source: "serenus.ico"; DestDir: "{app}\launcher"; Flags: ignoreversion
Source: "SetupBootstrap.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "Apri_Serenus.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Controlla_Aggiornamenti.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Ripristina_Serenus.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "python-3.12.10-amd64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
[Icons]
Name: "{autoprograms}\Serenus"; Filename: "{app}\Apri_Serenus.bat"; IconFilename: "{app}\launcher\serenus.ico"
Name: "{userdesktop}\Serenus"; Filename: "{app}\Apri_Serenus.bat"; IconFilename: "{app}\launcher\serenus.ico"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Crea icona sul desktop"; Flags: checkedonce
[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  if FileExists(ExpandConstant('{localappdata}\Serenus\state\update-state.json')) or
     FileExists(ExpandConstant('{localappdata}\Serenus\app\app.py')) then
  begin
    MsgBox('Serenus e gia installato. Utilizza Serenus Updater, non questo installer.', mbInformation, MB_OK);
    Result := False;
  end;
end;
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Command: String;
begin
  if CurStep = ssPostInstall then
  begin
    Command := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\SetupBootstrap.ps1') + '" -Root "' + ExpandConstant('{app}') + '" -PythonInstaller "' + ExpandConstant('{tmp}\python-3.12.10-amd64.exe') + '"';
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Command, '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
      RaiseException('Impossibile avviare la procedura di installazione Serenus');
    if ResultCode <> 0 then
      RaiseException('Installazione di Serenus non completata. Controlla il messaggio nella finestra PowerShell.');
  end;
end;
