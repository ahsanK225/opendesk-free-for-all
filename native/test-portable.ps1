param([Parameter(Mandatory)][string]$PortablePath,[Parameter(Mandatory)][string]$EvidenceDir)
$ErrorActionPreference='Stop'
$caseRoot=Join-Path ([IO.Path]::GetFullPath($EvidenceDir)) ('p-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Force -Path $caseRoot | Out-Null
$oldLocal=$env:LOCALAPPDATA
$oldPath=$env:PATH
$oldRuntime=$env:OPENDESK_RUNTIME_DIR
$results=@()
try {
    $env:LOCALAPPDATA=Join-Path $caseRoot 'appdata'
    $env:PATH="$env:SystemRoot\System32;$env:SystemRoot"
    Remove-Item Env:QT_PLUGIN_PATH,Env:QML_IMPORT_PATH,Env:QML2_IMPORT_PATH,Env:QT_SCALE_FACTOR -ErrorAction SilentlyContinue
    $env:QT_FORCE_STDERR_LOGGING='1';$env:OPENDESK_DEV_NO_TUNNEL='1'
    $env:OPENDESK_RUNTIME_DIR=Join-Path $caseRoot ('deep-'+('x'*180))
    $invalidLog=Join-Path $caseRoot 'overlong-path-stderr.log'
    $invalid=Start-Process -FilePath $PortablePath -ArgumentList @('--no-error-dialog','--config-dir',('"'+$caseRoot+'\profile"')) -WindowStyle Hidden -PassThru -RedirectStandardError $invalidLog
    if (!$invalid.WaitForExit(15000) -or $invalid.ExitCode -ne 1 -or (Get-Content -LiteralPath $invalidLog -Raw) -notmatch 'cache path is too long') {throw 'Long-path preflight did not provide an actionable error.'}
    Remove-Item Env:OPENDESK_RUNTIME_DIR -ErrorAction SilentlyContinue
    foreach ($mode in @('first-launch','cached-launch','missing-dll-repair','explicit-repair')) {
        if ($mode -eq 'missing-dll-repair') {
            $cache=@(Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'OpenDesk/runtimes') -Directory | Where-Object Name -Like '3.0.0-*')
            if ($cache.Count -ne 1) {throw 'Expected exactly one isolated portable cache.'}
            $dll=Join-Path $cache[0].FullName 'Qt6Svg.dll'
            if (!(Test-Path -LiteralPath $dll)) {throw 'The repair fixture DLL is missing.'}
            Remove-Item -LiteralPath $dll
        }
        $state=Join-Path $caseRoot ($mode+'.json')
        $arguments=@('--no-error-dialog','--smoke-test','--config-dir',('"'+$caseRoot+'\profile"'),'--smoke-output',('"'+$state+'"'))
        if ($mode -eq 'explicit-repair') {$arguments+='--repair'}
        $watch=[Diagnostics.Stopwatch]::StartNew()
        $process=Start-Process -FilePath $PortablePath -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $caseRoot ($mode+'-stderr.log'))
        if (!$process.WaitForExit(60000) -or $process.ExitCode -ne 0) {throw ('Portable '+$mode+' failed.')}
        $watch.Stop()
        if (!(Test-Path -LiteralPath $state)) {throw 'The native child did not produce startup evidence.'}
        $view=Get-Content -LiteralPath $state -Raw|ConvertFrom-Json
        if ($view.version -ne '3.0.0-alpha.2') {throw 'The launcher did not run the native application.'}
        $warnings=@(Get-Content -LiteralPath (Join-Path $caseRoot ($mode+'-stderr.log')) | Where-Object {$_ -and $_ -ne 'qt.qpa.mime: Retrying to obtain clipboard.'})
        if ($warnings) {throw $warnings}
        $results+=[pscustomobject]@{mode=$mode;passed=$true;seconds=$watch.Elapsed.TotalSeconds;deviceId=$view.deviceId}
    }
    if (@($results.deviceId|Select-Object -Unique).Count -ne 1) {throw 'Portable repair changed the device ID.'}
    $results|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $caseRoot 'results.json')
    Get-Content -LiteralPath (Join-Path $caseRoot 'results.json')
} finally {$env:LOCALAPPDATA=$oldLocal;$env:PATH=$oldPath;$env:OPENDESK_RUNTIME_DIR=$oldRuntime}
