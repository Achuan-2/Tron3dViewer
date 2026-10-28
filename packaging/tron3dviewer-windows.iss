#ifndef MyAppVersion
#define MyAppVersion "0.0.0"
#endif

#define MyAppName "Tron 3D viewer"
#define MyAppPublisher "Achuan-2"
#define MyAppURL "https://github.com/Achuan-2/Tron3dViewer"
#define MyAppExeName "tron3dviewer.exe"

[Setup]
AppId={{F8EDF271-CE9C-4730-9E46-42AEA997EA15}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=tron3dviewer-{#MyAppVersion}-Windows-x86_64-Setup
SetupIconFile=build\tron3dviewer.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,Tron 3D viewer}"; Flags: nowait postinstall skipifsilent unchecked
