param([Parameter(Mandatory)][string]$BinaryDir,[Parameter(Mandatory)][string]$EvidenceDir)
$ErrorActionPreference = 'Stop'
$binaryRoot = [IO.Path]::GetFullPath($BinaryDir)
$evidenceRoot = [IO.Path]::GetFullPath($EvidenceDir)
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
$probe = Join-Path $binaryRoot 'OpenDeskLauncherProbe.exe'
$helper = Join-Path $binaryRoot 'OpenDeskSetupHelper.exe'
if (!(Test-Path -LiteralPath $probe) -or !(Test-Path -LiteralPath $helper)) { throw 'Build launcher with --features fixtures first.' }
$results = @()
foreach ($mode in @('cooperative','unresponsive')) {
    $caseRoot = Join-Path $evidenceRoot ($mode + '-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $caseRoot | Out-Null
    $app = Join-Path $caseRoot 'OpenDesk.exe'
    Copy-Item -LiteralPath $probe -Destination $app
    $state = Join-Path $caseRoot 'state.json'
    $suffix = 'fixture-' + [Guid]::NewGuid().ToString('N')
    $arguments = @('--suffix', $suffix, '--output', ('"' + $state + '"'))
    if ($mode -eq 'unresponsive') { $arguments += '--ignore-shutdown' }
    $process = Start-Process -FilePath $app -ArgumentList $arguments -WindowStyle Hidden -PassThru
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        while (!(Test-Path -LiteralPath $state) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
        if (!(Test-Path -LiteralPath $state)) { throw 'Probe did not start.' }
        $watch = [Diagnostics.Stopwatch]::StartNew()
        $report = Join-Path $caseRoot 'shutdown.json'
        $stopper = Start-Process -FilePath $helper -ArgumentList @('--shutdown','--force','--timeout','6','--install-dir',('"'+$caseRoot+'"'),'--instance-suffix',$suffix,'--result-file',('"'+$report+'"')) -WindowStyle Hidden -PassThru
        if (!$stopper.WaitForExit(10000)) { throw 'Shutdown exceeded its bounded deadline.' }
        if ($stopper.ExitCode -ne 0 -or !$process.WaitForExit(2000)) { throw 'The application remained running.' }
        $watch.Stop()
        $results += [pscustomobject]@{mode=$mode;closed=$true;seconds=$watch.Elapsed.TotalSeconds;helperExit=$stopper.ExitCode}
    } finally {
        $process.Refresh()
        if (!$process.HasExited) { $process.Kill(); $process.WaitForExit() }
        $process.Dispose()
    }
}
$results | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidenceRoot 'launcher-results.json')
$results | Format-Table
