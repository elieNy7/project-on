; ═══════════════════════════════════════════════════════════════════
;  Project-On — Modern Installer (Inno Setup 6)
; ═══════════════════════════════════════════════════════════════════

#define MyAppName "Project-On"
#define MyAppVersion "1.8.2"
#define MyAppPublisher "Elie Nyembo"
#define MyAppURL "https://github.com/elieNy7/project-on"
#define MyAppExeName "Project-On.exe"
#define MyAppDescription "Logiciel de projection pour églises — Bible, Cantiques, Sermons, Exposés"

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

; Modern style
WizardStyle=modern
WizardSizePercent=120,120
DisableProgramGroupPage=yes
DisableWelcomePage=no

; Permissions
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest
CloseApplications=force
AppMutex=ProjectOnMutex

; Output
OutputDir=Output
OutputBaseFilename=ProjectOn_{#MyAppVersion}_Setup
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

; Compression
Compression=lzma2/fast
SolidCompression=yes
LZMANumBlockThreads=4



; Version info embedded in the setup exe
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppDescription}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; dist\Project-On is already curated by project_on.spec; copy that output only.
Source: "..\dist\Project-On\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; Refresh application binaries while preserving user data in AppData.
; Inno Setup upgrades the same AppId in place; never invoke the previous
; uninstaller here because older uninstallers removed the user's database.
Type: filesandordirs; Name: "{app}\*"

[Registry]
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "DataPath"; ValueData: "{userappdata}\{#MyAppName}\data"; Flags: uninsdeletekey

[Messages]
french.WelcomeLabel1=Bienvenue dans l'assistant d'installation de {#MyAppName}
french.WelcomeLabel2=Ce programme va installer {#MyAppName} {#MyAppVersion} sur votre ordinateur.%n%n{#MyAppDescription}%n%nCliquez sur Suivant pour continuer.
english.WelcomeLabel1=Welcome to the {#MyAppName} Setup Wizard
english.WelcomeLabel2=This will install {#MyAppName} {#MyAppVersion} on your computer.%n%n{#MyAppDescription}%n%nClick Next to continue.

[Code]
// Show accurate progress messages during an in-place, data-preserving upgrade.
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Installation des nouveaux fichiers...';
  end;
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Configuration finale...';
  end;
end;
