param([Parameter(Mandatory)][string]$InstallerPath,[Parameter(Mandatory)][string]$BinaryDir,[Parameter(Mandatory)][string]$EvidenceDir)
$ErrorActionPreference='Stop'
if ([IO.Path]::GetFileNameWithoutExtension($InstallerPath) -notlike '*_Smoke') {throw 'Use the separately compiled SmokeScopedShutdown installer with its isolated AppId.'}
$caseRoot=Join-Path ([IO.Path]::GetFullPath($EvidenceDir)) ('install-'+[Guid]::NewGuid().ToString('N'))
$appRoot=Join-Path $caseRoot 'OpenDesk'
$profile=Join-Path $caseRoot 'profile'
New-Item -ItemType Directory -Force -Path $appRoot,$profile,(Join-Path $appRoot '_internal') | Out-Null
Set-Content -LiteralPath (Join-Path $appRoot '_internal/python311.dll') -Value 'owned legacy runtime fixture'
Set-Content -LiteralPath (Join-Path $profile 'config.json') -Value '{"host_id":"123 456 789","sentinel":"preserve-me","native_settings":{"publicAccess":false,"micEnabled":false}}'
$probe=Join-Path ([IO.Path]::GetFullPath($BinaryDir)) 'OpenDeskLauncherProbe.exe'
$app=Join-Path $appRoot 'OpenDesk.exe'
Copy-Item -LiteralPath $probe -Destination $app
$state=Join-Path $caseRoot 'old-process.json'
$old=Start-Process -FilePath $app -ArgumentList @('--ignore-shutdown','--suffix','installer-smoke','--output',('"'+$state+'"')) -WindowStyle Hidden -PassThru
try {
    $deadline=[DateTime]::UtcNow.AddSeconds(10)
    while (!(Test-Path -LiteralPath $state) -and [DateTime]::UtcNow -lt $deadline) {Start-Sleep -Milliseconds 100}
    if (!(Test-Path -LiteralPath $state)) {throw 'Locked legacy application fixture failed to start.'}
    $watch=[Diagnostics.Stopwatch]::StartNew()
    $install=Start-Process -FilePath $InstallerPath -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/TASKS=',('/DIR="'+$appRoot+'"'),('/LOG="'+$caseRoot+'\installer.log"')) -WindowStyle Hidden -PassThru
    if (!$install.WaitForExit(60000) -or $install.ExitCode -ne 0) {throw 'The native installer did not finish successfully within its deadline.'}
    $watch.Stop()
    if (!$old.WaitForExit(1000)) {throw 'The locked old process survived installation.'}
    if (Test-Path -LiteralPath (Join-Path $appRoot '_internal')) {throw 'The recognized old Python runtime was not removed.'}
    $env:PATH="$env:SystemRoot\System32;$env:SystemRoot"
    Remove-Item Env:QT_PLUGIN_PATH,Env:QML_IMPORT_PATH,Env:QML2_IMPORT_PATH -ErrorAction SilentlyContinue
    $env:QT_FORCE_STDERR_LOGGING='1';$env:OPENDESK_DEV_NO_TUNNEL='1'
    $evidence=Join-Path $caseRoot 'state.json'
    $native=Start-Process -FilePath $app -ArgumentList @('--smoke-test','--config-dir',('"'+$profile+'"'),'--smoke-output',('"'+$evidence+'"'),'--screenshot',('"'+$caseRoot+'\installed.png"')) -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $caseRoot 'stderr.log')
    if (!$native.WaitForExit(30000) -or $native.ExitCode -ne 0) {throw 'The installed native application failed to launch.'}
    $saved=Get-Content (Join-Path $profile 'config.json') -Raw|ConvertFrom-Json
    $view=Get-Content $evidence -Raw|ConvertFrom-Json
    if ($saved.sentinel -ne 'preserve-me' -or $view.deviceId -ne '123 456 789') {throw 'Configuration or device ID was not preserved.'}
    $warnings=Get-Content (Join-Path $caseRoot 'stderr.log') -Raw
    if ($warnings) {throw ('Native startup logged unexpected warnings: '+$warnings)}
    [pscustomobject]@{passed=$true;lockedUpgradeSeconds=$watch.Elapsed.TotalSeconds;oldProcessClosed=$true;legacyRuntimeRemoved=$true;deviceIdPreserved=$true;configurationPreserved=$true;installedStartup=$true;directory=$caseRoot}|ConvertTo-Json|Set-Content (Join-Path $caseRoot 'result.json')
    Get-Content (Join-Path $caseRoot 'result.json')
} finally {
    $old.Refresh();if (!$old.HasExited) {$old.Kill();$old.WaitForExit()};$old.Dispose()
    $uninstaller=Join-Path $appRoot 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {$cleanup=Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -WindowStyle Hidden -PassThru;[void]$cleanup.WaitForExit(30000)}
}
