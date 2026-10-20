# fetch-bins.ps1 - Download and verify OpenROM binaries on Windows / PowerShell 5.1 & 7
# Exit codes:
#   0 - Success
#   1 - Invalid arguments or missing dependency
#   2 - Manifest or checksum error / tool not found
#   3 - Download failed (HTTP 404 / connection error)
#   4 - SHA-256 or size verification mismatch

[CmdletBinding()]
param(
    [string]$Os = "",
    [string]$Arch = "",
    [string]$Tool = "",
    [string]$TargetDir = "."
)

$ErrorActionPreference = "Stop"

$baseUrl = $env:OPENROM_BINS_BASE_URL
if ([string]::IsNullOrWhiteSpace($baseUrl)) {
    $baseUrl = "https://downloads.sourceforge.net/project/openrom-binaries"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = Split-Path -Parent $scriptDir
$manifestPath = Join-Path $repoRoot "manifest.json"

if (-not (Test-Path $manifestPath)) {
    Write-Error "Error: manifest.json not found at $manifestPath"
    exit 2
}

try {
    $manifestJson = Get-Content -Raw -Path $manifestPath | ConvertFrom-Json
} catch {
    Write-Error "Error reading manifest.json: $_"
    exit 2
}

$matched = @()
$toolsObj = $manifestJson.tools

foreach ($tProperties in $toolsObj.PSObject.Properties) {
    $toolName = $tProperties.Name
    if ($Tool -and ($toolName.ToLower() -ne $Tool.ToLower())) {
        continue
    }

    $toolData = $tProperties.Value
    $platformsObj = $toolData.platforms

    foreach ($pProperties in $platformsObj.PSObject.Properties) {
        $platKey = $pProperties.Name
        $parts = $platKey.Split('/')
        $platOs = $parts[0]
        $platArch = if ($parts.Length -gt 1) { $parts[1] } else { "" }

        if ($Os -and ($platOs.ToLower() -ne $Os.ToLower())) {
            continue
        }
        if ($Arch -and ($platArch.ToLower() -ne $Arch.ToLower())) {
            continue
        }

        $platData = $pProperties.Value
        $matched += [PSCustomObject]@{
            Tool     = $toolName
            Platform = $platKey
            Path     = $platData.path
            Sha256   = $platData.sha256
            Size     = $platData.size
        }
    }
}

if ($matched.Count -eq 0) {
    Write-Error "No binaries found matching constraints (os='$Os', arch='$Arch', tool='$Tool')"
    exit 2
}

Write-Host "Fetching $($matched.Count) binary/binaries to target directory: $TargetDir"

if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir | Out-Null
}

foreach ($item in $matched) {
    $relPath = $item.Path
    $expSha = $item.Sha256
    $expSize = $item.Size
    $url = "$baseUrl/$relPath"
    $filename = Split-Path -Leaf $relPath
    $outFile = Join-Path $TargetDir $filename

    Write-Host "Downloading $relPath -> $outFile ..."

    try {
        Invoke-WebRequest -Uri $url -OutFile $outFile -UseBasicParsing
    } catch {
        Write-Error "Error downloading $url: $_"
        exit 3
    }

    $fileStream = [System.IO.File]::OpenRead((Convert-Path $outFile))
    try {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $hashBytes = $sha.ComputeHash($fileStream)
        $actSha = [System.BitConverter]::ToString($hashBytes).Replace("-", "").ToLower()
    } finally {
        $fileStream.Close()
    }

    $actSize = (Get-Item $outFile).Length

    if ($actSha -ne $expSha) {
        Write-Error "SHA-256 mismatch for $relPath!`n  Expected: $expSha`n  Actual:   $actSha"
        Remove-Item -Force $outFile -ErrorAction SilentlyContinue
        exit 4
    }

    if ($expSize -gt 0 -and $actSize -ne $expSize) {
        Write-Error "Size mismatch for $relPath!`n  Expected: $expSize bytes`n  Actual:   $actSize bytes"
        Remove-Item -Force $outFile -ErrorAction SilentlyContinue
        exit 4
    }

    Write-Host "Verified $filename successfully."
}
