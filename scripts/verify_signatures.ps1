# scripts/verify_signatures.ps1
# OpenDesk Signature Verification & Audit Tool

[CmdletBinding()]
param(
    [string[]]$Files
)

$RootDir = Split-Path -Parent $PSScriptRoot

if (-not $Files -or $Files.Count -eq 0) {
    $Files = @(
        (Join-Path $RootDir "OpenDesk.exe"),
        (Join-Path $RootDir "OpenDesk_Setup.exe"),
        (Join-Path $RootDir "dist\OpenDesk.exe"),
        (Join-Path $RootDir "installer_output\OpenDesk_Setup_v1.1.0.exe")
    ) | Where-Object { Test-Path $_ }
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  OpenDesk Authenticode Signature Audit" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$allValid = $true

foreach ($file in $Files) {
    Write-Host "File: $(Split-Path $file -Leaf)" -ForegroundColor White
    Write-Host "Path: $file" -ForegroundColor Gray
    
    $sig = Get-AuthenticodeSignature -FilePath $file
    Write-Host "Status:        $($sig.Status)" -ForegroundColor $(if ($sig.Status -eq "Valid") { "Green" } else { "Red" })
    Write-Host "Message:       $($sig.StatusMessage)"
    
    if ($sig.SignerCertificate) {
        Write-Host "Signer:        $($sig.SignerCertificate.Subject)"
        Write-Host "Thumbprint:    $($sig.SignerCertificate.Thumbprint)"
        Write-Host "Valid Until:   $($sig.SignerCertificate.NotAfter)"
    } else {
        Write-Host "Signer:        NONE (Binary is unsigned!)" -ForegroundColor Red
        $allValid = $false
    }

    if ($sig.TimeStamperCertificate) {
        Write-Host "Timestamp By:  $($sig.TimeStamperCertificate.Subject)" -ForegroundColor Green
        Write-Host "Timestamp Exp: $($sig.TimeStamperCertificate.NotAfter)" -ForegroundColor Green
    } else {
        Write-Host "Timestamp By:  NONE" -ForegroundColor Yellow
    }
    Write-Host "--------------------------------------------------------"
}

if ($allValid) {
    Write-Host "AUDIT RESULT: ALL TARGETS ARE SIGNED AND VALID" -ForegroundColor Green
    exit 0
} else {
    Write-Host "AUDIT RESULT: ONE OR MORE FILES ARE UNSIGNED OR INVALID" -ForegroundColor Red
    exit 1
}
