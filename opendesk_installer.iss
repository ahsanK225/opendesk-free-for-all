; Script generated for Inno Setup Compiler
; OpenDesk Professional Standalone Installer Script

#define MyAppName "OpenDesk"
#define MyAppVersion "2.0.1"
#define MyAppPublisher "OpenDesk Project"
#define MyAppURL "https://github.com/ahsanK225/opendesk-free-for-all"
#define MyAppExeName "OpenDesk.exe"
#ifndef PortablePath
  #define PortablePath "dist\OpenDesk.exe"
#endif
#ifndef MaintenancePath
  #define MaintenancePath "dist\OpenDeskSetupHelper.exe"
#endif

#ifndef BuildAppId
  #define BuildAppId "{{5C16C978-B541-4E65-8A5B-A47E53B25091}"
#endif

[Setup]
; Basic Application Info
AppId={#BuildAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Destination Directories
; Uses modern installation (automatically selects Program Files or User Programs)
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Output configuration
OutputDir=installer_output
OutputBaseFilename=OpenDesk_Setup_v2.0.1
SetupIconFile=opendesk.ico

; Compression & Modern Visual Style
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Avoid Restart Manager's unbounded "closing applications" wait.
CloseApplications=no
RestartApplications=no
SetupMutex=OpenDesk.Setup

; Branding & Windows Add/Remove Programs metadata
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} Remote Desktop

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startupicon"; Description: "Launch OpenDesk automatically when Windows starts"; GroupDescription: "Windows Startup:"; Flags: unchecked

[Files]
Source: "{#MaintenancePath}"; DestDir: "{tmp}"; Flags: dontcopy
Source: "{#PortablePath}"; DestDir: "{app}"; Flags: ignoreversion
Source: "opendesk.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\opendesk.ico"; Tasks: startmenuicon
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\opendesk.ico"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\opendesk.ico"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  Parameters: String;
begin
  Result := '';
  WizardForm.StatusLabel.Caption := 'Closing OpenDesk before upgrade...';
  ExtractTemporaryFile('OpenDeskSetupHelper.exe');
  Parameters := '--shutdown --force --timeout 8';
  #ifdef SmokeScopedShutdown
    Parameters := Parameters + ' --install-dir "' + ExpandConstant('{app}') + '" --instance-suffix installer-smoke';
  #endif
  if not Exec(ExpandConstant('{tmp}\OpenDeskSetupHelper.exe'), Parameters, '',
              SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := 'The OpenDesk shutdown helper could not start. Please close OpenDesk and retry.'
  else if ResultCode <> 0 then
    Result := 'OpenDesk is still running or is elevated. Close it manually, or run this installer as administrator.';
end;
