param([string]$Destination=(Join-Path $PSScriptRoot '../bin/cloudflared.exe'))
$ErrorActionPreference='Stop'
$expected='f096265ec2fcbe9bb6e2d64268db167ced3fcbb83d894bdb9e2fcdb26f2ea7e2'
$path=[IO.Path]::GetFullPath($Destination)
if ((Test-Path -LiteralPath $path) -and (Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -eq $expected) {Write-Output 'Pinned cloudflared 2026.9.3 is ready.';return}
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path)|Out-Null
$temporary=$path+'.download-'+[Guid]::NewGuid().ToString('N')
try {
    & curl.exe --fail --location --silent --show-error --max-time 180 'https://github.com/cloudflare/cloudflared/releases/download/2026.9.3/cloudflared-windows-amd64.exe' -o $temporary
    if ($LASTEXITCODE -ne 0 -or (Get-FileHash -LiteralPath $temporary).Hash.ToLowerInvariant() -ne $expected) {throw 'The official tunnel download failed checksum verification.'}
    Move-Item -LiteralPath $temporary -Destination $path -Force
    Write-Output 'Pinned cloudflared 2026.9.3 is ready.'
} finally {if(Test-Path -LiteralPath $temporary){Remove-Item -LiteralPath $temporary}}
