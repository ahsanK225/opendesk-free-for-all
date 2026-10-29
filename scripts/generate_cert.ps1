# scripts/generate_cert.ps1
# OpenDesk Code Signing Certificate Generator

[CmdletBinding()]
param(
    [string]$Subject = "CN=OpenDesk Software, O=OpenDesk Project, OU=Engineering, C=US",
    [string]$FriendlyName = "OpenDesk Authenticode Code Signing Certificate",
    [string]$Password = "OpenDesk2026!",
    [int]$ValidityYears = 10
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$CertsDir = Join-Path $RootDir "certs"
if (-not (Test-Path $CertsDir)) {
    New-Item -ItemType Directory -Path $CertsDir -Force | Out-Null
}

$PfxPath = Join-Path $CertsDir "OpenDesk_CodeSigning.pfx"
$CerPath = Join-Path $CertsDir "OpenDesk_CodeSigning.cer"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  OpenDesk Code Signing Certificate Generation Engine" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Subject:       $Subject"
Write-Host "Validity:      $ValidityYears years"
Write-Host "Certificates:  $CertsDir"
Write-Host ""

Write-Host "[1/4] Generating 2048-bit RSA Code Signing Certificate..." -ForegroundColor Yellow
$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -KeySpec Signature `
    -KeyLength 2048 `
    -KeyAlgorithm RSA `
    -HashAlgorithm SHA256 `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -NotAfter (Get-Date).AddYears($ValidityYears) `
    -FriendlyName $FriendlyName

Write-Host "  Thumbprint: $($cert.Thumbprint)" -ForegroundColor Green

Write-Host "[2/4] Exporting Public Certificate (.cer)..." -ForegroundColor Yellow
Export-Certificate -Cert $cert -FilePath $CerPath -Force | Out-Null
Write-Host "  Saved to: $CerPath" -ForegroundColor Green

Write-Host "[3/4] Exporting Private PKCS#12 Bundle (.pfx)..." -ForegroundColor Yellow
$securePassword = ConvertTo-SecureString -String $Password -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath $PfxPath -Password $securePassword -Force | Out-Null
Write-Host "  Saved to: $PfxPath" -ForegroundColor Green

Write-Host "[4/4] Registering Certificate in CurrentUser My and TrustedPublisher..." -ForegroundColor Yellow
try {
    # Install into CurrentUser TrustedPublisher (no UI prompt)
    $pubStore = New-Object System.Security.Cryptography.X509Certificates.X509Store("TrustedPublisher", "CurrentUser")
    $pubStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
    $pubStore.Add($cert)
    $pubStore.Close()
    Write-Host "  Successfully added to CurrentUser TrustedPublisher store." -ForegroundColor Green
} catch {
    Write-Warning "Could not register into TrustedPublisher: $_"
}

Write-Host "  Note: Run 'scripts\install_certificate.bat' to install into Trusted Root Authority." -ForegroundColor Cyan

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  CERTIFICATE READY FOR AUTHENTICODE SIGNING" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
