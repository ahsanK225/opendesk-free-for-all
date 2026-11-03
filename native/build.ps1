param(
    [Parameter(Mandatory)][string]$QtRoot,
    [Parameter(Mandatory)][string]$TurboJpegRoot,
    [string]$BuildRoot = (Join-Path $PSScriptRoot '../../native-build'),
    [string]$OutputDir = (Join-Path $PSScriptRoot '../dist/native'),
    [string]$CMake = 'cmake',
    [Parameter(Mandatory)][string]$VcRuntimeDir,
    [string]$InnoCompiler,
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $repo
$releaseManifest=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'version.json') -Raw|ConvertFrom-Json
$releaseVersion=$releaseManifest.version
if ($releaseVersion -notmatch '^\d+\.[0-9]$' -or $releaseManifest.channel -ne 'stable') {throw 'Use the stable sequential version (2.8, 2.9, 3.0, ...).'}
foreach($crate in @('engine','launcher')) {
    $cargo=Get-Content -LiteralPath (Join-Path $PSScriptRoot "$crate/Cargo.toml") -Raw
    if ($cargo -notmatch ('(?m)^version = "'+[regex]::Escape($releaseVersion)+'\.0"\r?$')) {throw "Cargo version must match release $releaseVersion.0"}
}
$build = [IO.Path]::GetFullPath($BuildRoot)
$output = [IO.Path]::GetFullPath($OutputDir)
$qt = (Resolve-Path -LiteralPath $QtRoot).Path
$crt = (Resolve-Path -LiteralPath $VcRuntimeDir).Path
if (!(Test-Path -LiteralPath (Join-Path $qt 'bin/windeployqt.exe'))) { throw 'Qt 6.8.3 MSVC 2022 x64 is required.' }
if (!(Test-Path -LiteralPath (Join-Path $crt 'vcruntime140.dll'))) { throw 'Use the Visual Studio Desktop x64 Microsoft.VC143.CRT directory.' }
function Invoke-BuildTool([string]$Executable,[string[]]$ToolArguments) {
    & $Executable @ToolArguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}
New-Item -ItemType Directory -Force -Path $build,$output | Out-Null
$env:CARGO_TARGET_DIR = Join-Path $build 'engine'
if (!$SkipTests) {
    Invoke-BuildTool cargo @('test','--locked','--release','--lib','--manifest-path','native/engine/Cargo.toml','--','--test-threads=1')
    Invoke-BuildTool node @('tests/test_web.cjs')
    Invoke-BuildTool node @('tests/test_release_versions.cjs')
}
Invoke-BuildTool cargo @('build','--locked','--release','--lib','--manifest-path','native/engine/Cargo.toml')
$desktop = Join-Path $build 'desktop'
Invoke-BuildTool $CMake @('-S','native/desktop','-B',$desktop,'-G','Visual Studio 17 2022','-A','x64',"-DCMAKE_PREFIX_PATH=$qt",("-DTURBOJPEG_ROOT="+[IO.Path]::GetFullPath($TurboJpegRoot)),("-DOPENDESK_ENGINE_LIB="+(Join-Path $env:CARGO_TARGET_DIR 'release/opendesk_engine.lib')))
Invoke-BuildTool $CMake @('--build',$desktop,'--config','Release','--parallel','2')
# A fresh staging directory prevents stale plugins or legacy Python files from entering a package.
$bundle = Join-Path $output ('runtime-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $bundle | Out-Null
Copy-Item -LiteralPath (Join-Path $desktop 'Release/OpenDesk.exe') -Destination $bundle
Invoke-BuildTool (Join-Path $qt 'bin/windeployqt.exe') @('--release','--no-compiler-runtime','--no-translations','--qmldir','native/desktop/qml',(Join-Path $bundle 'OpenDesk.exe'))
Copy-Item -LiteralPath (Join-Path $TurboJpegRoot "bin/turbojpeg.dll") -Destination $bundle
New-Item -ItemType Directory -Path (Join-Path $bundle "licenses") -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $TurboJpegRoot "doc/LICENSE.md") -Destination (Join-Path $bundle "licenses/libjpeg-turbo.txt")
Get-ChildItem -LiteralPath $crt -Filter *.dll | Copy-Item -Destination $bundle
Copy-Item -LiteralPath 'web' -Destination (Join-Path $bundle 'web') -Recurse
New-Item -ItemType Directory -Path (Join-Path $bundle 'bin') | Out-Null
$tunnel = Join-Path $repo 'bin/cloudflared.exe'
if ((Get-FileHash -LiteralPath $tunnel -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'f096265ec2fcbe9bb6e2d64268db167ced3fcbb83d894bdb9e2fcdb26f2ea7e2') { throw 'The pinned cloudflared 2026.9.3 binary is missing or has changed.' }
Copy-Item -LiteralPath $tunnel -Destination (Join-Path $bundle 'bin/cloudflared.exe')
Copy-Item -LiteralPath 'LICENSE' -Destination (Join-Path $bundle 'LICENSE.txt')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'RUNTIME_README.md') -Destination (Join-Path $bundle 'README.md')
Copy-Item -Path (Join-Path $PSScriptRoot 'licenses/*') -Destination (Join-Path $bundle 'licenses') -Recurse -Force
$forbidden = Get-ChildItem -LiteralPath $bundle -File -Recurse | Where-Object { $_.Name -match '^(ucrtbase|api-ms-|ext-ms-|python\d|Qt6.*d\.dll)' -or $_.Extension -in @('.py','.pyc','.pyd') }
if ($forbidden) { throw ('Unexpected operating system, debug or Python runtime files: '+($forbidden.Name -join ', ')) }
if (!$SkipTests) {
    & "$PSScriptRoot/test-incoming.ps1" -ApplicationPath (Join-Path $bundle 'OpenDesk.exe') -EvidenceDir (Join-Path $output 'incoming-tests')
}
$env:CARGO_TARGET_DIR = Join-Path $build 'launcher'
$previousFlags = $env:RUSTFLAGS
try {
    $env:RUSTFLAGS = '-Ctarget-feature=+crt-static'
    $resource=Join-Path $build 'launcher.res'
    Copy-Item -LiteralPath (Join-Path $desktop 'OpenDeskNative.dir/Release/opendesk.res') -Destination $resource -Force
    $env:OPENDESK_RESOURCE_RES=$resource
    Invoke-BuildTool cargo @('build','--locked','--release','--manifest-path','native/launcher/Cargo.toml','--target','x86_64-pc-windows-msvc','--features','fixtures')
    $launcher = Join-Path $env:CARGO_TARGET_DIR 'x86_64-pc-windows-msvc/release'
    $helper = Join-Path $launcher 'OpenDeskSetupHelper.exe'
    Copy-Item -LiteralPath $helper -Destination $bundle
    if (!$SkipTests) {
        & "$PSScriptRoot/test-launcher.ps1" -BinaryDir $launcher -EvidenceDir (Join-Path $output 'launcher-tests')
        & "$PSScriptRoot/test-update.ps1" -BinaryDir $launcher -EvidenceDir (Join-Path $output 'update-tests')
    }
    $payload = Join-Path $output 'native-payload.zip'
    if (Test-Path -LiteralPath $payload) { Remove-Item -LiteralPath $payload -Force }
    Compress-Archive -Path (Join-Path $bundle '*') -DestinationPath $payload -CompressionLevel Optimal
    $env:OPENDESK_PAYLOAD_ZIP = $payload
    Invoke-BuildTool cargo @('build','--locked','--release','--manifest-path','native/launcher/Cargo.toml','--target','x86_64-pc-windows-msvc','--features','portable','--bin','OpenDeskPortable')
    Copy-Item -LiteralPath (Join-Path $launcher 'OpenDeskPortable.exe') -Destination (Join-Path $output ("OpenDesk_v"+$releaseVersion+"_Portable.exe")) -Force
    if (!$SkipTests) { & "$PSScriptRoot/test-portable.ps1" -PortablePath (Join-Path $output ("OpenDesk_v"+$releaseVersion+"_Portable.exe")) -EvidenceDir (Join-Path $output 'portable-tests') }
    if ($InnoCompiler) { Invoke-BuildTool $InnoCompiler @("/DBuildVersion=$releaseVersion","/DAppBundleDir=$bundle","/DMaintenancePath=$helper","/O$output",'native/installer.iss') }
} finally { $env:RUSTFLAGS = $previousFlags; Remove-Item Env:OPENDESK_PAYLOAD_ZIP,Env:OPENDESK_RESOURCE_RES -ErrorAction SilentlyContinue }
$manifest=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'version.json') -Raw|ConvertFrom-Json
$portableArtifact=Join-Path $output ("OpenDesk_v"+$releaseVersion+"_Portable.exe")
$manifest.sha256=(Get-FileHash -LiteralPath $portableArtifact -Algorithm SHA256).Hash.ToLowerInvariant()
$installerArtifact=Join-Path $output ("OpenDesk_Setup_v"+$releaseVersion+"_Installer.exe")
$artifacts=@($portableArtifact)
if ($InnoCompiler -and (Test-Path -LiteralPath $installerArtifact)) {
    $manifest.installer_sha256=(Get-FileHash -LiteralPath $installerArtifact -Algorithm SHA256).Hash.ToLowerInvariant()
    $artifacts+=$installerArtifact
} else { $manifest.installer_sha256=$null }
$manifestArtifact=Join-Path $output 'version.json'
$manifest|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $manifestArtifact
$artifacts+=$manifestArtifact
@($artifacts|ForEach-Object{(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()+'  '+[IO.Path]::GetFileName($_)})|Set-Content -LiteralPath (Join-Path $output 'SHA256SUMS.txt')
Write-Output "Native runtime: $bundle"
Write-Output "Artifacts: $output"
