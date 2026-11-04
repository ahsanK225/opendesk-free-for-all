param(
    [Parameter(Mandatory)][string]$QtRoot,
    [Parameter(Mandatory)][string]$TurboJpegRoot,
    [Parameter(Mandatory)][string]$VcRuntimeDir,
    [string]$BuildRoot,
    [string]$OutputDir,
    [string]$CMake='cmake',
    [string]$InnoCompiler,
    [ValidateSet('Full','Lite')][string]$Edition='Full',
    [switch]$SkipTests
)
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'native/build.ps1') @PSBoundParameters
