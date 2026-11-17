; Music Player Pro — instalador Inno Setup
; Compilar con: ISCC.exe installer\MusicPlayerPro.iss
; Requiere que el ejecutable ya esté compilado por PyInstaller en dist\.

#define AppName "Music Player Pro"
#define AppShortName "MusicPlayerPro"
#define AppVersion "1.2.0"
#define AppPublisher "Music Player Pro"
#define AppURL "https://github.com/musicplayerpro/musicplayerpro"
#define AppExeName "MusicPlayerPro.exe"

[Setup]
AppId={{8B5A4D2E-1C7F-4E3A-9E1B-6A5D0C7E9F21}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\{#AppShortName}
DefaultGroupName={#AppShortName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=MusicPlayerPro-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
UninstallDisplayIcon={app}\{#AppExeName}
ChangesAssociations=yes
PrivilegesRequired=admin
; Al desinstalar se conservan los datos del usuario (biblioteca, ajustes, sincronización).
Uninstallable=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "quicklaunchicon"; Description: "Crear acceso rápido en la barra de tareas"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\MusicPlayerPro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Iconos y metadatos del programa
Source: "..\resources\*"; DestDir: "{app}\resources"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#AppShortName}"; Filename: "{app}\{#AppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Caché descargable: se puede regenerar.
Type: filesandordirs; Name: "{userappdata}\MusicPlayerPro\cache"
Type: filesandordirs; Name: "{userappdata}\MusicPlayerPro\logs"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    { Comprobar que la aplicación arranca tras instalar (si el usuario la cerró). }
    if not WizardSilent then
    begin
      if Exec(ExpandConstant('{app}\{#AppExeName}'), '--verify-startup', '', SW_HIDE,
             ewWaitUntilTerminated, ResultCode) then
      begin
        if ResultCode = 0 then
          Log('Verificación de arranque correcta.');
      end;
    end;
  end;
end;
