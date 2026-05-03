; Inno Setup script for DockMeow Windows installer.
; Produces: DockMeow-Setup-0.1.0-x64.exe in dist\installers\

#define MyAppName "DockMeow"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "DockMeow Team"
#define MyAppExeName "DockMeow.exe"

[Setup]
AppId={{F5A3B8E2-4D2C-4A7B-9E1D-DockMeowApp1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/dockmeow/dockmeow
AppSupportURL=https://github.com/dockmeow/dockmeow/issues
AppUpdatesURL=https://github.com/dockmeow/dockmeow/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64os
OutputDir=..\..\dist\installers
OutputBaseFilename=DockMeow-Setup-{#MyAppVersion}-x64
SetupIconFile=DockMeow.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

[Languages]
Name: "english";      MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\DockMeow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";          Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";    Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
