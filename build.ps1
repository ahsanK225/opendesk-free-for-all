param(
    [string]$OutputDir = 'dist',
    [string]$InnoCompiler = $env:ISCC_PATH,
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ([System.IO.Path]::IsPathRooted($OutputDir)) { $outputRoot = [System.IO.Path]::GetFullPath($OutputDir) }
else { $outputRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $OutputDir)) }
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
if (-not $SkipTests) {
    python -m unittest discover -s tests -t .
    if ($LASTEXITCODE -ne 0) { throw 'Python tests failed' }
    if (Get-Command node -ErrorAction SilentlyContinue) {
        node tests/test_web.cjs
        if ($LASTEXITCODE -ne 0) { throw 'Browser tests failed' }
    }
}
python -m tools.fetch_cloudflared
if ($LASTEXITCODE -ne 0) { throw 'Tunnel binary verification failed' }
python -m tools.build_frozen opendesk_maintenance.spec --noconfirm --clean --distpath $outputRoot --workpath (Join-Path $outputRoot '.maintenance-work')
if ($LASTEXITCODE -ne 0) { throw 'Installer shutdown helper build failed' }
python -m tools.build_frozen opendesk.spec --noconfirm --clean --distpath $outputRoot --workpath (Join-Path $outputRoot '.work')
if ($LASTEXITCODE -ne 0) { throw 'Portable build failed' }
$portable = Join-Path $outputRoot 'OpenDesk.exe'
python -m tools.audit_frozen $portable (Join-Path $outputRoot 'OpenDeskSetupHelper.exe')
if ($LASTEXITCODE -ne 0) { throw 'Frozen dependency audit failed' }
if ($env:OPENDESK_SIGN_PFX) {
    if (-not $env:OPENDESK_SIGN_PASSWORD) { throw 'Signing password is missing' }
    & signtool.exe sign /f $env:OPENDESK_SIGN_PFX /p $env:OPENDESK_SIGN_PASSWORD /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 $portable
    if ($LASTEXITCODE -ne 0) { throw 'Authenticode signing failed' }
}
$version = (Get-Content -LiteralPath 'version.json' -Raw | ConvertFrom-Json).version
Copy-Item -LiteralPath $portable -Destination (Join-Path $outputRoot "OpenDesk_v${version}_Portable.exe") -Force
if ($InnoCompiler) {
    $env:OPENDESK_BUILD_ONEDIR = '1'
    try {
        python -m tools.build_frozen opendesk.spec --noconfirm --distpath (Join-Path $outputRoot 'installed') --workpath (Join-Path $outputRoot '.installed-work')
        if ($LASTEXITCODE -ne 0) { throw 'Installed runtime bundle failed' }
    } finally { Remove-Item Env:OPENDESK_BUILD_ONEDIR -ErrorAction SilentlyContinue }
    python -m tools.audit_frozen (Join-Path $outputRoot 'installed\OpenDesk')
    if ($LASTEXITCODE -ne 0) { throw 'Installed dependency audit failed' }
    & $InnoCompiler "/DAppBundleDir=$(Join-Path $outputRoot 'installed\OpenDesk')" "/DMaintenancePath=$(Join-Path $outputRoot 'OpenDeskSetupHelper.exe')" "/O$outputRoot" opendesk_installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
    $installer = Join-Path $outputRoot "OpenDesk_Setup_v${version}.exe"
    if ($env:OPENDESK_SIGN_PFX) {
        & signtool.exe sign /f $env:OPENDESK_SIGN_PFX /p $env:OPENDESK_SIGN_PASSWORD /fd SHA256 /tr https://timestamp.digicert.com /td SHA256 $installer
        if ($LASTEXITCODE -ne 0) { throw 'Installer signing failed' }
    }
    Copy-Item -LiteralPath $installer -Destination (Join-Path $outputRoot "OpenDesk_Setup_v${version}_Installer.exe") -Force
}
$manifest = Get-Content -LiteralPath 'version.json' -Raw | ConvertFrom-Json
$manifest | Add-Member -Force -NotePropertyName sha256 -NotePropertyValue ((Get-FileHash -LiteralPath $portable -Algorithm SHA256).Hash.ToLower())
if ($InnoCompiler) { $manifest | Add-Member -Force -NotePropertyName installer_sha256 -NotePropertyValue ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLower()) }
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $outputRoot 'version.json') -Encoding utf8
Get-ChildItem -LiteralPath $outputRoot -Filter '*.exe' | Get-FileHash -Algorithm SHA256 |
    ForEach-Object { "$($_.Hash.ToLower())  $([System.IO.Path]::GetFileName($_.Path))" } |
    Set-Content -LiteralPath (Join-Path $outputRoot 'SHA256SUMS.txt') -Encoding ascii
Write-Output "Build complete: $outputRoot"
if (-not $env:OPENDESK_SIGN_PFX) { Write-Output 'Binaries are unsigned. No trusted publisher certificate was provided.' }
