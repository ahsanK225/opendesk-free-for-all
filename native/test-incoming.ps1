param([Parameter(Mandatory)][string]$ApplicationPath,[Parameter(Mandatory)][string]$EvidenceDir)
$ErrorActionPreference='Stop'
$evidence=[IO.Path]::GetFullPath($EvidenceDir)
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$node=(Get-Command node).Source
$previousPath=$env:PATH
$previousScale=$env:QT_SCALE_FACTOR
$previousTunnel=$env:OPENDESK_DEV_NO_TUNNEL
try {
    $env:PATH="$env:SystemRoot\System32;$env:SystemRoot"
    $env:OPENDESK_DEV_NO_TUNNEL='1';$env:QT_FORCE_STDERR_LOGGING='1'
    Remove-Item Env:QT_PLUGIN_PATH,Env:QML_IMPORT_PATH,Env:QML2_IMPORT_PATH -ErrorAction SilentlyContinue
    foreach($mode in @('pending','cancel')) {
        $case=Join-Path $evidence ($mode+'-'+[Guid]::NewGuid().ToString('N').Substring(0,6))
        New-Item -ItemType Directory -Force -Path $case | Out-Null
        '{"host_id":"123456789","native_settings":{"publicAccess":false,"micEnabled":false}}' | Set-Content -LiteralPath (Join-Path $case 'config.json')
        $env:QT_SCALE_FACTOR=if($mode -eq 'pending'){'1.5'}else{'1'}
        $state=Join-Path $case 'state.json'
        $process=Start-Process -FilePath $ApplicationPath -ArgumentList @('--smoke-test','--smoke-minimized','--smoke-delay-ms','10000','--config-dir',('"'+$case+'"'),'--smoke-output',('"'+$state+'"'),'--screenshot',('"'+(Join-Path $case 'window.png')+'"')) -WindowStyle Normal -PassThru -RedirectStandardError (Join-Path $case 'stderr.log')
        try {
            # Discover the port owned by this fixture rather than predicting a
            # free port while another isolated host is shutting down.
            $limit=[DateTime]::UtcNow.AddSeconds(8)
            do {
                $listener=Get-NetTCPConnection -OwningProcess $process.Id -State Listen -ErrorAction SilentlyContinue | Where-Object {$_.LocalPort -ge 8080 -and $_.LocalPort -lt 8100} | Select-Object -First 1
                if(!$listener){Start-Sleep -Milliseconds 100}
            }while(!$listener -and [DateTime]::UtcNow -lt $limit)
            if(!$listener){throw 'Native fixture listener unavailable'}
            $port=$listener.LocalPort
            & $node "$PSScriptRoot/../tests/test_incoming.cjs" "ws://127.0.0.1:$port/ws" '123456789' $state $mode
            if($LASTEXITCODE -ne 0){throw "Incoming $mode probe failed"}
            if(!$process.WaitForExit(15000) -or $process.ExitCode -ne 0){throw 'Native host did not complete'}
            $warnings=@(Get-Content -LiteralPath (Join-Path $case 'stderr.log') | Where-Object {$_ -and $_ -ne 'qt.qpa.mime: Retrying to obtain clipboard.'})
            if($warnings){throw $warnings}
        }finally {if(!$process.HasExited){$process.Kill();$process.WaitForExit()}}
    }
}finally {$env:PATH=$previousPath;$env:QT_SCALE_FACTOR=$previousScale;$env:OPENDESK_DEV_NO_TUNNEL=$previousTunnel}
