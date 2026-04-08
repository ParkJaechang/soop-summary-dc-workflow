#define MyAppName "SOOP WebApp"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "PJC"
#define MyAppExeName "SOOPWebApp.exe"

[Setup]
AppId={{D5D6C48A-8648-4D1B-BF97-E2EAC1C9F001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SOOP WebApp
DefaultGroupName=SOOP WebApp
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=SOOPWebAppSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\SOOPWebApp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SOOP WebApp"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\SOOP WebApp"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch SOOP WebApp"; Flags: nowait postinstall skipifsilent
