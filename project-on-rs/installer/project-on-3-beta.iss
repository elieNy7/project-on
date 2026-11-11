; ═══════════════════════════════════════════════════════════════════
;  Project-On 3.0 bêta — installateur Windows (Inno Setup 7)
;
;  La bêta s'installe À CÔTÉ de Project-On 2.8, sans la remplacer :
;  - son propre identifiant, son propre dossier (dans les programmes de
;    l'utilisateur, sans droits d'administrateur) et son entrée de menu ;
;  - ses données dans %APPDATA%\Project-On 3 (bêta) : au premier lancement,
;    l'application y COPIE la base et les réglages de la 2.x, ou la base
;    fournie (data\project_on.db, celle de l'installateur de la 2.8) ; la 2.x
;    n'est jamais modifiée.
;  La désinstallation retire le programme seulement : la copie des données
;  reste, comme celles de la 2.8.
;
;  Construction : powershell -ExecutionPolicy Bypass -File project-on-rs\construire-beta.ps1
; ═══════════════════════════════════════════════════════════════════

#define MyAppName "Project-On 3 (bêta)"
#ifndef MyAppVersion
  #define MyAppVersion "3.0.0-beta.1"
#endif
#define MyAppPublisher "ParaTech Sarl"
#define MyAppExeName "Project-On-3-beta.exe"
; Un identifiant à elle : jamais celui de la 2.x (qui serait alors désinstallée ou écrasée).
#define MyAppId "768682FF-11C9-4C56-98C6-5FACA5882924"

[Setup]
AppId={{{#MyAppId}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppComments=Régie de projection pour les églises — version d'essai, à côté de la 2.8
DefaultDirName={autopf}\Project-On 3 beta
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=Output
OutputBaseFilename=Project-On_{#MyAppVersion}_Setup
SetupIconFile=..\..\assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
LicenseFile=..\..\LICENSE.txt

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\dist\Project-On-3-beta\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
