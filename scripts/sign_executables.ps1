# scripts/sign_executables.ps1
# OpenDesk Authenticode Digital Signing & Verification Engine

[CmdletBinding()]
param(
    [string[]]$Files,
    [string]$Password = "OpenDesk2026!",
    [string[]]$TimestampServers = @(
        "http://timestamp.digicert.com",
        "http://timestamp.sectigo.com",
        "http://tsa.starfieldtech.com"
    )
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$CertsDir = Join-Path $RootDir "certs"
$PfxPath = Join-Path $CertsDir "OpenDesk_CodeSigning.pfx"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  OpenDesk Authenticode Digital Signing Engine" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# Step 1: Ensure certificate exists
if (-not (Test-Path $PfxPath)) {
    Write-Host "[!] Code signing certificate not found. Generating now..." -ForegroundColor Yellow
    $genScript = Join-Path $PSScriptRoot "generate_cert.ps1"
    & $genScript -Password $Password
    if (-not (Test-Path $PfxPath)) {
        Write-Error "Failed to locate or generate certificate at $PfxPath"
        exit 1
    }
}

# Step 2: Load Certificate from PFX
Write-Host "[+] Loading code signing certificate from $PfxPath..." -ForegroundColor Cyan
$securePassword = ConvertTo-SecureString -String $Password -Force -AsPlainText
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($PfxPath, $securePassword, [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::Exportable)

Write-Host "  Signer Subject: $($cert.Subject)" -ForegroundColor Green
Write-Host "  Thumbprint:     $($cert.Thumbprint)" -ForegroundColor Green
Write-Host "  Expires:        $($cert.NotAfter)" -ForegroundColor Green
Write-Host ""

# Step 3: Determine targets
if (-not $Files -or $Files.Count -eq 0) {
    $defaultFiles = @(
        (Join-Path $RootDir "OpenDesk.exe"),
        (Join-Path $RootDir "OpenDesk_Setup.exe"),
        (Join-Path $RootDir "dist\OpenDesk.exe"),
        (Join-Path $RootDir "installer_output\OpenDesk_Setup_v1.1.0.exe")
    )
    $Files = $defaultFiles | Where-Object { Test-Path $_ }
}

if ($Files.Count -eq 0) {
    Write-Warning "No target executable files found to sign!"
    exit 0
}

Write-Host "[+] Found $($Files.Count) file(s) to sign:" -ForegroundColor Cyan
foreach ($f in $Files) {
    Write-Host "  - $f"
}
Write-Host ""

# Step 4: Sign each file
$allSuccessful = $true

foreach ($file in $Files) {
    if (-not (Test-Path $file)) {
        Write-Warning "File not found: $file"
        continue
    }

    Write-Host ">>> Signing: $(Split-Path $file -Leaf)..." -ForegroundColor Yellow
    $signed = $false

    # Try timestamp servers
    foreach ($tsUrl in $TimestampServers) {
        Write-Host "    Attempting timestamp with $tsUrl..." -NoNewline
        try {
            $result = Set-AuthenticodeSignature -FilePath $file -Certificate $cert -HashAlgorithm SHA256 -TimestampServer $tsUrl -ErrorAction Stop
            if ($result.Status -eq "Valid" -or $result.Status -eq "UnknownError" -or $result.Status -ne "Error") {
                Write-Host " [OK]" -ForegroundColor Green
                $signed = $true
                break
            } else {
                Write-Host " [Status: $($result.Status)]" -ForegroundColor DarkYellow
            }
        } catch {
            Write-Host " [FAILED: $($_.Exception.Message)]" -ForegroundColor DarkRed
        }
    }

    # Fallback to no timestamp if offline
    if (-not $signed) {
        Write-Host "    Falling back to signing without timestamp..." -NoNewline
        try {
            $result = Set-AuthenticodeSignature -FilePath $file -Certificate $cert -HashAlgorithm SHA256 -ErrorAction Stop
            Write-Host " [OK]" -ForegroundColor Yellow
            $signed = $true
        } catch {
            Write-Host " [FAILED: $($_.Exception.Message)]" -ForegroundColor Red
            $allSuccessful = $false
        }
    }

    # Verify signature
    $sig = Get-AuthenticodeSignature -FilePath $file
    Write-Host "    Status:         $($sig.Status)" -ForegroundColor $(if ($sig.Status -eq "Valid") { "Green" } else { "Yellow" })
    Write-Host "    StatusMessage:  $($sig.StatusMessage)"
    if ($sig.SignerCertificate) {
        Write-Host "    Signer:         $($sig.SignerCertificate.Subject)" -ForegroundColor Gray
    }
    if ($sig.TimeStamperCertificate) {
        Write-Host "    Timestamp:      $($sig.TimeStamperCertificate.Subject)" -ForegroundColor Gray
    }
    Write-Host ""
}

Write-Host "========================================================" -ForegroundColor Cyan
if ($allSuccessful) {
    Write-Host "  AUTHENTICODE SIGNING COMPLETED SUCCESSFULLY!" -ForegroundColor Green
} else {
    Write-Host "  COMPLETED WITH WARNINGS OR ERRORS" -ForegroundColor Yellow
}
Write-Host "========================================================" -ForegroundColor Cyan

if (-not $allSuccessful) {
    exit 1
}
