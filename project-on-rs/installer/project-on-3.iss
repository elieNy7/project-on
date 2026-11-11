; ═══════════════════════════════════════════════════════════════════
; Project-On 3.0 — l'installateur de la BASCULE (phase 8).
;
; Il REMPLACE la 2.x : même identifiant d'application (AppId) que l'installateur de la 2.x
; (installer\setup.iss), donc Inno Setup met à jour l'installation existante, au même endroit, et
; « Project-On » reste une seule application dans Windows. Les données de l'utilisateur
; (%APPDATA%\Project-On : base, playlists, réglages) ne sont JAMAIS touchées : la 3.0 travaille
; directement dessus (migrations additives seulement), sur le port Web 8080 de la 2.x.
;
; Construit par : construire-beta.ps1 -Bascule
; NE PAS PUBLIER sans l'accord de l'utilisateur.
; ═══════════════════════════════════════════════════════════════════

#define MyAppName "Project-On"
#ifndef MyAppVersion
  #define MyAppVersion "3.0.0"
#endif
#define MyAppPublisher "Elie Nyembo"
#define MyAppURL "https://github.com/elieNy7/project-on"
#define MyAppExeName "Project-On.exe"
#define MyAppDescription "Logiciel de projection pour églises — Bible, Cantiques, Prédications, Livres"
; L'identifiant de la 2.x : la 3.0 la remplace en place.
#define MyAppId "D3B3B3B3-B3B3-B3B3-B3B3-B3B3B3B3B3B3"

[Setup]
AppId={{{#MyAppId}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest
CloseApplications=force
; Le même verrou que la 2.x : l'installation attend que Project-On (2.x ou 3.0) soit fermé.
AppMutex=ProjectOnMutex
OutputDir=Output
OutputBaseFilename=ProjectOn_{#MyAppVersion}_Setup
SetupIconFile=..\..\assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
LicenseFile=..\..\LICENSE.txt

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Raccourcis :"

[InstallDelete]
; Les fichiers de la 2.x (Python) sont retirés du dossier du programme ; les données, dans
; %APPDATA%, restent. Comme la 2.x : jamais l'ancien désinstallateur (il effaçait la base).
Type: filesandordirs; Name: "{app}\*"

[Files]
Source: "..\dist\Project-On-3\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "DataPath"; ValueData: "{userappdata}\{#MyAppName}\data"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
