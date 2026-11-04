#ifndef AppBundleDir
  #error AppBundleDir must point to the verified native runtime bundle
#endif
#ifndef MaintenancePath
  #error MaintenancePath must point to the native setup helper
#endif
#ifndef BuildAppId
  #define BuildAppId "{{5C16C978-B541-4E65-8A5B-A47E53B25091}"
#endif
#ifndef BuildAppName
  #define BuildAppName "OpenDesk"
#endif
#ifndef BuildFilePrefix
  #define BuildFilePrefix "OpenDesk"
#endif
#ifndef BuildVersion
  #error BuildVersion must be supplied by the version-aligned build script
#endif

[Setup]
AppId={#BuildAppId}
AppName={#BuildAppName}
AppVersion={#BuildVersion}
AppPublisher=OpenDesk Project
AppPublisherURL=https://github.com/ahsanK225/opendesk-free-for-all
DefaultDirName={autopf}\{#BuildAppName}
DefaultGroupName={#BuildAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\installer_output
OutputBaseFilename={#BuildFilePrefix}_Setup_v{#BuildVersion}_Installer
SetupIconFile=..\assets\brand\opendesk-native.ico
UninstallDisplayIcon={app}\OpenDesk.exe
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
SetupMutex={#BuildFilePrefix}.Setup

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: checkedonce
Name: startupicon; Description: "Launch OpenDesk when Windows starts"; Flags: unchecked

[Files]
Source: "{#MaintenancePath}"; DestDir: "{tmp}"; Flags: dontcopy
Source: "{#AppBundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Only the known, managed Python runtime of earlier installed OpenDesk builds.
Type: filesandordirs; Name: "{app}\_internal"; Check: HasLegacyRuntime

[Icons]
#ifndef SmokeScopedShutdown
Name: "{group}\{#BuildAppName}"; Filename: "{app}\OpenDesk.exe"
Name: "{autodesktop}\{#BuildAppName}"; Filename: "{app}\OpenDesk.exe"; Tasks: desktopicon
Name: "{userstartup}\{#BuildAppName}"; Filename: "{app}\OpenDesk.exe"; Tasks: startupicon
#endif

[Run]
Filename: "{app}\OpenDesk.exe"; Description: "Launch OpenDesk"; Flags: nowait postinstall skipifsilent

[Code]
function HasLegacyRuntime: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\OpenDesk.exe')) and
            FileExists(ExpandConstant('{app}\_internal\python311.dll'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var ResultCode: Integer; Parameters: String;
begin
  Result := '';
  WizardForm.StatusLabel.Caption := 'Closing OpenDesk before upgrade...';
  ExtractTemporaryFile('OpenDeskSetupHelper.exe');
  Parameters := '--shutdown --force --timeout 8';
  #ifdef SmokeScopedShutdown
    Parameters := Parameters + ' --install-dir "' + ExpandConstant('{app}') + '" --instance-suffix installer-smoke';
  #endif
  if not Exec(ExpandConstant('{tmp}\OpenDeskSetupHelper.exe'), Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := 'The native shutdown helper could not start. Close OpenDesk and retry.'
  else if ResultCode <> 0 then
    Result := 'OpenDesk is running with different permissions. Close that instance, or run this installer with matching permissions.';
end;
