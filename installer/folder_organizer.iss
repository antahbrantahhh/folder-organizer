; Inno Setup 6 script — Folder Organizer installer (per-user, no admin rights needed).
; Build: build_installer.bat  (needs build_exe.bat output + Inno Setup 6: https://jrsoftware.org/isinfo.php)
; Output: installer\Output\FolderOrganizer-Setup-<version>.exe

#ifndef AppVersion
  #define AppVersion "3.12.2"
#endif

[Setup]
AppId={{7C6E3B0A-4F2D-4C59-9E61-0F7A1B2C3D10}
AppName=Folder Organizer
AppVersion={#AppVersion}
AppPublisher=Bangke
AppPublisherURL=https://github.com/antahbrantahhh/folder-organizer
AppUpdatesURL=https://github.com/antahbrantahhh/folder-organizer/releases
DefaultDirName={localappdata}\Programs\Folder Organizer
DefaultGroupName=Folder Organizer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=FolderOrganizer-Setup-{#AppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\Folder Organizer.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Only the top-level rules.yaml is excluded ("\" anchors the pattern to the source root), so an upgrade keeps the
; user's own rules. The default in _internal\rules.yaml MUST be installed: the app copies it on first run.
Source: "..\dist\Folder Organizer\*"; DestDir: "{app}"; Excludes: "\rules.yaml"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Folder Organizer"; Filename: "{app}\Folder Organizer.exe"
Name: "{group}\Uninstall Folder Organizer"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Folder Organizer"; Filename: "{app}\Folder Organizer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Folder Organizer.exe"; Description: "{cm:LaunchProgram,Folder Organizer}"; Flags: nowait postinstall skipifsilent
; In-app update runs the installer with /SILENT /RELAUNCH=1. The app is reopened from DeinitializeSetup, also when
; the install fails or is cancelled, so the user is never left without the app (it shows --update-failed).

; Uninstall keeps user data (%APPDATA%\FolderOrganizer: settings, undo history, logs) and the user's rules.yaml.

[Code]
var
  InstallOk: Boolean;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then
    InstallOk := True;
end;

procedure DeinitializeSetup;
var
  Exe, Param: String;
  Code: Integer;
begin
  if ExpandConstant('{param:RELAUNCH|0}') <> '1' then
    exit;
  try
    Exe := ExpandConstant('{app}\Folder Organizer.exe');
  except
    Exe := ExpandConstant('{localappdata}\Programs\Folder Organizer\Folder Organizer.exe');
  end;
  if InstallOk then
    Param := '--updated'
  else
    Param := '--update-failed';
  if FileExists(Exe) then
    Exec(Exe, Param, '', SW_SHOW, ewNoWait, Code);
end;
