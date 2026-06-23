; Inno Setup script for DockMeow Windows installer.
; Produces: DockMeow-Setup-<version>-x64.exe in dist\installers\
;
; Build via build_win.ps1 (version is passed as /DMyAppVersion=x.y.z).
; Manual build: iscc /DMyAppVersion=2.3.2 packaging\windows\installer.iss

#define MyAppName "DockMeow"
; Allow version override from command line: iscc /DMyAppVersion=0.2.0 ...
#ifndef MyAppVersion
  #define MyAppVersion "2.3.2"
#endif
#ifndef MyAppSourceDir
  #define MyAppSourceDir "..\..\dist\windows-x64\DockMeow"
#endif
#define MyAppPublisher "DockMeow Team"
#define MyAppExeName "DockMeow.exe"

[Setup]
AppId={{F5A3B8E2-4D2C-4A7B-9E1D-DockMeowApp1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/jiamingf09-tech/DockMeow
AppSupportURL=https://github.com/jiamingf09-tech/DockMeow/issues
AppUpdatesURL=https://github.com/jiamingf09-tech/DockMeow/releases
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
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";          Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";    Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
