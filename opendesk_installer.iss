; Script generated for Inno Setup Compiler
; OpenDesk Professional Standalone Installer Script

#define MyAppName "OpenDesk"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "OpenDesk Project"
#define MyAppURL "https://github.com/ahsanK225/opendesk-free-for-all"
#define MyAppExeName "OpenDesk.exe"
#ifndef PortablePath
  #define PortablePath "dist\OpenDesk.exe"
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
OutputBaseFilename=OpenDesk_Setup_v2.0.0
SetupIconFile=opendesk.ico

; Compression & Modern Visual Style
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

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
