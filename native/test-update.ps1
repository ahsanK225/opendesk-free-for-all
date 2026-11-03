param([Parameter(Mandatory)][string]$BinaryDir,[Parameter(Mandatory)][string]$EvidenceDir)
$ErrorActionPreference='Stop'
$caseRoot=Join-Path ([IO.Path]::GetFullPath($EvidenceDir)) ('update-'+[Guid]::NewGuid().ToString('N'))
$parentRoot=Join-Path $caseRoot 'parent'
$stage=Join-Path $caseRoot 'stage'
New-Item -ItemType Directory -Force -Path $parentRoot,$stage | Out-Null
$helper=Join-Path ([IO.Path]::GetFullPath($BinaryDir)) 'OpenDeskSetupHelper.exe'
$probe=Join-Path ([IO.Path]::GetFullPath($BinaryDir)) 'OpenDeskLauncherProbe.exe'
$app=Join-Path $parentRoot 'OpenDesk.exe'
$target=Join-Path $caseRoot 'portable.exe'
$source=Join-Path $stage 'release.exe'
$updater=Join-Path $stage 'OpenDeskSetupHelper.exe'
Copy-Item -LiteralPath $probe -Destination $app
Copy-Item -LiteralPath $probe -Destination $source
Copy-Item -LiteralPath $helper -Destination $updater
Copy-Item -LiteralPath $helper -Destination $target
Set-Content -LiteralPath (Join-Path $caseRoot '.update-fixture') -Value 'owned native update test'
$suffix='update-fixture-'+[Guid]::NewGuid().ToString('N')
$hash=(Get-FileHash -LiteralPath $source).Hash.ToLowerInvariant()
$parent=Start-Process -FilePath $app -ArgumentList @('--suffix',$suffix) -WindowStyle Hidden -PassThru
try {
    $apply=Start-Process -FilePath $updater -ArgumentList @('--apply','--no-error-dialog','--parent-pid',$parent.Id,'--source',('"'+$source+'"'),'--sha256',$hash,'--portable-target',('"'+$target+'"')) -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 300
    if ($apply.HasExited) { throw 'The update did not wait for the running application.' }
    $stop=Start-Process -FilePath $helper -ArgumentList @('--shutdown','--force','--timeout','6','--install-dir',('"'+$parentRoot+'"'),'--instance-suffix',$suffix) -WindowStyle Hidden -PassThru
    if (!$stop.WaitForExit(10000) -or $stop.ExitCode -ne 0) { throw 'The fixture parent did not close.' }
    if (!$apply.WaitForExit(10000) -or $apply.ExitCode -ne 0) { throw 'Native portable replacement failed.' }
    $deadline=[DateTime]::UtcNow.AddSeconds(5)
    $ready=Join-Path $caseRoot 'updated-ready.txt'
    while (!(Test-Path -LiteralPath $ready) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    if (!(Test-Path -LiteralPath $ready) -or (Get-FileHash -LiteralPath $target).Hash.ToLowerInvariant() -ne $hash) { throw 'The verified replacement did not launch.' }
    if (!(Test-Path -LiteralPath (Join-Path $stage 'previous-portable.exe'))) { throw 'The rollback copy is missing.' }
    [pscustomobject]@{passed=$true;waitedForParent=$true;verifiedReplacement=$true;replacementLaunched=$true;rollbackPreserved=$true;directory=$caseRoot} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $caseRoot 'result.json')
    Get-Content -LiteralPath (Join-Path $caseRoot 'result.json')
} finally {
    $parent.Refresh();if (!$parent.HasExited) { $parent.Kill();$parent.WaitForExit() };$parent.Dispose()
}
