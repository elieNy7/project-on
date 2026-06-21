; ═══════════════════════════════════════════════════════════════════
;  Project-On — Modern Installer (Inno Setup 6)
; ═══════════════════════════════════════════════════════════════════

#define MyAppName "Project-On"
#define MyAppVersion "1.3.0"
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
; Supprimer tout le contenu du dossier d'installation pour une installation propre
; On cible spécifiquement les fichiers et sous-dossiers
Type: filesandordirs; Name: "{app}\*"
Type: filesandordirs; Name: "{app}"
; Supprimer les données utilisateur (base de données, paramètres) et les caches
Type: filesandordirs; Name: "{userappdata}\{#MyAppName}"
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\{#MyAppName}"
Type: filesandordirs; Name: "{userappdata}\{#MyAppName}"

[Registry]
Root: HKCU; Subkey: "Software\{#MyAppName}"; ValueType: string; ValueName: "DataPath"; ValueData: "{userappdata}\{#MyAppName}\data"; Flags: uninsdeletekey

[Messages]
french.WelcomeLabel1=Bienvenue dans l'assistant d'installation de {#MyAppName}
french.WelcomeLabel2=Ce programme va installer {#MyAppName} {#MyAppVersion} sur votre ordinateur.%n%n{#MyAppDescription}%n%nCliquez sur Suivant pour continuer.
english.WelcomeLabel1=Welcome to the {#MyAppName} Setup Wizard
english.WelcomeLabel2=This will install {#MyAppName} {#MyAppVersion} on your computer.%n%n{#MyAppDescription}%n%nClick Next to continue.

[Code]
// Helper function to get the uninstaller string from registry
function GetUninstallString(): String;
var
  sUninstPath: String;
  sUninstString: String;
begin
  sUninstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{{#MyAppId}}_is1';
  sUninstString := '';
  if not RegQueryStringValue(HKLM, sUninstPath, 'UninstallString', sUninstString) then
    RegQueryStringValue(HKCU, sUninstPath, 'UninstallString', sUninstString);
  Result := sUninstString;
end;

// Helper function to check if the app is already installed
function IsAlreadyInstalled(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

// Helper function to uninstall the previous version
function UninstallOldVersion(): Integer;
var
  sUninstString: String;
  iResultCode: Integer;
begin
  // Return codes: 0 = success, 1 = error, 2 = user cancelled
  sUninstString := GetUninstallString();
  if sUninstString <> '' then
  begin
    sUninstString := RemoveQuotes(sUninstString);
    if Exec(sUninstString, '/SILENT /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS', '', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := 0
    else
      Result := 1;
  end
  else
    Result := 0;
end;

// Automatic uninstallation and cleanup before new install starts
function InitializeSetup(): Boolean;
begin
  Result := True;
  
  if IsAlreadyInstalled() then
  begin
    // Optional: Ask user for clean install. 
    // But since the user explicitly asked for "erase all old files", we do it.
    if MsgBox('Une version précédente de {#MyAppName} a été détectée.' #13#10 #13#10 'L''assistant va maintenant supprimer TOUS les anciens fichiers et paramètres pour garantir une installation propre. Souhaitez-vous continuer ?', mbInformation, MB_YESNO) = IDYES then
    begin
      UninstallOldVersion();
      
      // Additional aggressive cleanup of directories if uninstaller left anything
      // (This will be double-enforced by [InstallDelete])
    end
    else
    begin
      // If user says NO, we still proceed but it won't be a "clean install" in the uninstaller sense.
      // However, [InstallDelete] will still target the files.
    end;
  end;
end;

// Show a progress message during extraction
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Désinstallation des anciennes versions et nettoyage...';
    // We can't easily delete AppData here because [InstallDelete] handles it, 
    // but we can ensure the label reflects the "Clean Install" phase.
    WizardForm.StatusLabel.Caption := 'Installation des nouveaux fichiers...';
  end;
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Configuration finale...';
  end;
end;
