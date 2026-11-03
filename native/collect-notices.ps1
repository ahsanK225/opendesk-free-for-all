param([Parameter(Mandatory)][string]$Destination)
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$inventory=@{}
foreach ($entry in @(@('native/engine/Cargo.toml',''),@('native/launcher/Cargo.toml','portable'))) {
    $arguments=@('metadata','--offline','--locked','--format-version','1','--filter-platform','x86_64-pc-windows-msvc','--manifest-path',(Join-Path $repo $entry[0]))
    if ($entry[1]) {$arguments+=@('--features',$entry[1])}
    $raw=& cargo @arguments
    if ($LASTEXITCODE -ne 0) {throw 'Dependency metadata could not be read.'}
    $metadata=$raw|ConvertFrom-Json
    foreach ($package in $metadata.packages) {
        if (!$package.source -or !$package.source.StartsWith('registry+')) {continue}
        $key=$package.name+'-'+$package.version
        $inventory[$key]=[ordered]@{name=$package.name;version=$package.version;license=$package.license;repository=$package.repository;source=('https://crates.io/crates/'+$package.name+'/'+$package.version)}
        $directory=Split-Path -Parent $package.manifest_path
        $files=@(Get-ChildItem -LiteralPath $directory -File | Where-Object {$_.Name -match '^(LICENSE|LICENCE|COPYING|NOTICE|COPYRIGHT)' -and $_.Length -lt 200000})
        if ($package.license_file) {$custom=Join-Path $directory $package.license_file;if(Test-Path -LiteralPath $custom -PathType Leaf){$files+=Get-Item -LiteralPath $custom}}
        if ($files.Count) {$target=Join-Path $Destination $key;New-Item -ItemType Directory -Force -Path $target|Out-Null;$files|Copy-Item -Destination $target -Force}
    }
}
@($inventory.GetEnumerator()|Sort-Object Name|ForEach-Object {$_.Value}) | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Destination 'dependencies.json')
