#define MyAppName "TelegramDownloader"
#define MyAppVersion "1.25"
#define MyAppExeName "TelegramDownloader_v1.25.exe"

[Setup]
AppId={{7B2A08A3-2C2E-4D4B-9C2A-9C3D6E7E6E31}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=IMC
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..
OutputBaseFilename=TelegramDownloader_Setup_v1.25
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=imagenes\icono.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "imagenes\icono.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar {#MyAppName}"; Flags: nowait postinstall skipifsilent
