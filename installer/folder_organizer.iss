; Inno Setup 6 script — Folder Organizer installer (per-user, no admin rights needed).
; Build: build_installer.bat  (needs build_exe.bat output + Inno Setup 6: https://jrsoftware.org/isinfo.php)
; Output: installer\Output\FolderOrganizer-Setup-<version>.exe

#ifndef AppVersion
  #define AppVersion "3.12.0"
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
; In-app update runs the installer with /SILENT /RELAUNCH=1: reopen the app when done.
Filename: "{app}\Folder Organizer.exe"; Parameters: "--updated"; Flags: nowait; Check: ShouldRelaunch

; Uninstall keeps user data (%APPDATA%\FolderOrganizer: settings, undo history, logs) and the user's rules.yaml.

[Code]
function ShouldRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;
