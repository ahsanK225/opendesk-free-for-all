param([Parameter(Mandatory)][string]$BackupDir,[switch]$Apply)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot
$mapping=Get-Content (Join-Path $repo 'docs/RELEASE_MAPPING.json') -Raw|ConvertFrom-Json
if(!$Apply){$mapping.historicalMapping|Select-Object oldTag,newTag,sourceCommit;return}
$backup=[IO.Path]::GetFullPath($BackupDir)
New-Item -ItemType Directory -Force -Path $backup|Out-Null
function Api([string[]]$Arguments){
    $raw=& gh api @Arguments
    if($LASTEXITCODE -ne 0){throw "GitHub request failed: $($Arguments[0])"}
    if($raw){$raw|ConvertFrom-Json}
}
$canonical=$mapping.canonicalRepository
$mirror=$mapping.mirrorRepository
foreach($target in @($canonical,$mirror)){
    $stable=Api -Arguments @("repos/$target/releases/tags/$($mapping.nextStableRelease.tag)")
    if($stable.draft -or $stable.prerelease){throw 'Publish the new stable release before migrating archived release URLs'}
}
$sourceBackup=Join-Path $backup 'canonical-before.json'
if(!(Test-Path $sourceBackup)){
    @(Api -Arguments @("repos/$canonical/releases?per_page=100"))|ConvertTo-Json -Depth 30|Set-Content $sourceBackup
    @(Api -Arguments @("repos/$mirror/releases?per_page=100"))|ConvertTo-Json -Depth 30|Set-Content (Join-Path $backup 'mirror-before.json')
}
$original=@(Get-Content $sourceBackup -Raw|ConvertFrom-Json)
foreach($row in $mapping.historicalMapping){
    $oldCommit=git rev-list -n 1 $row.oldTag
    if($LASTEXITCODE -ne 0 -or $oldCommit -ne $row.sourceCommit){throw "Original source changed: $($row.oldTag)"}
    $exists=git tag --list $row.newTag
    if($exists){if((git rev-list -n 1 $row.newTag) -ne $row.sourceCommit){throw "Conflicting tag: $($row.newTag)"}}
    else{git tag -a $row.newTag $row.sourceCommit -m "OpenDesk $($row.newDisplayVersion), original source $($row.oldTag)";if($LASTEXITCODE -ne 0){throw 'Tag creation failed'}}
}
foreach($remote in @('origin','portfolio')){git push $remote --tags;if($LASTEXITCODE -ne 0){throw "Tag push failed: $remote"}}
$payloadPath=Join-Path $backup 'request.json'
$results=@()
foreach($row in $mapping.historicalMapping){
    $old=$original|Where-Object tag_name -eq $row.oldTag|Select-Object -First 1
    $links=@()
    if($old){foreach($asset in $old.assets){$url="https://github.com/$canonical/releases/download/$($row.newTag)/$([Uri]::EscapeDataString($asset.name))";$links+='- ['+$asset.name+']('+$url+')'}}
    else{$links+='This historical version has a source tag only; no executable was originally published.'}
    $body=@("# OpenDesk $($row.newDisplayVersion)",'',"Sequential release number: **$($row.newDisplayVersion)**. Original build/source: **$($row.oldTag)**.",'',"Original source tag and commit are preserved: [$($row.oldTag)](https://github.com/$canonical/tree/$($row.oldTag)). Historical executables retain their original embedded build versions and unchanged bytes.",'','## Downloads','')+$links+@('','Historical manifests are archived artifacts. Use the current stable release and root version.json for updates.','','[Complete ascending history](https://github.com/'+$canonical+'/blob/main/docs/VERSION_HISTORY.md)')
    if($old.body){$body+=@('','---','','## Original release notes','',$old.body)}
    $bodyText=$body -join "`n"
    foreach($target in @($canonical,$mirror)){
        $releases=@(Api -Arguments @("repos/$target/releases?per_page=100"))
        $existing=$releases|Where-Object {$_.tag_name -eq $row.oldTag -or $_.tag_name -eq $row.newTag}|Select-Object -First 1
        $payload=@{tag_name=$row.newTag;target_commitish=$row.sourceCommit;name="OpenDesk $($row.newTag)";body=$bodyText;draft=$false;prerelease=$false;make_latest='false'}
        $payload|ConvertTo-Json -Depth 6|Set-Content $payloadPath
        if($existing){$updated=Api -Arguments @("repos/$target/releases/$($existing.id)",'--method','PATCH','--input',$payloadPath)}
        else{$updated=Api -Arguments @("repos/$target/releases",'--method','POST','--input',$payloadPath)}
        if($updated.tag_name -ne $row.newTag -or $updated.draft -or $updated.prerelease){throw 'Release state verification failed'}
        if($target -eq $canonical -and $old){
            foreach($asset in $old.assets){$after=$updated.assets|Where-Object id -eq $asset.id;if(!$after -or $after.size -ne $asset.size -or $after.digest -ne $asset.digest){throw "Historical asset changed: $($asset.name)"}}
        }
        $results+=[pscustomobject]@{repository=$target;oldTag=$row.oldTag;newTag=$row.newTag;url=$updated.html_url;assets=$updated.assets.Count;canonicalDownloadsPreserved=$true}
        $results|ConvertTo-Json -Depth 5|Set-Content (Join-Path $backup 'results.json')
        Write-Output "$target : $($row.oldTag) -> $($row.newTag)"
    }
}
foreach($target in @($canonical,$mirror)){
    & gh release edit $mapping.nextStableRelease.tag --repo $target --latest
    if($LASTEXITCODE -ne 0){throw 'Latest release designation failed'}
    $latest=Api -Arguments @("repos/$target/releases/latest")
    if($latest.tag_name -ne $mapping.nextStableRelease.tag){throw 'Latest release mismatch'}
}
Write-Output 'History synchronized; original source tags and canonical historical assets preserved.'
