# Check BIMCraft installation and CLI capabilities
param(
    [string]$BimcraftPath = "C:\Program Files\BIMCraft\bimcraft-cli.exe"
)

Write-Host "=== BIMCraft Environment Check ===" -ForegroundColor Cyan

# 1. Check executable
if (-not (Test-Path $BimcraftPath)) {
    # Check PATH as fallback
    $pathCmd = Get-Command "bimcraft-cli.exe" -ErrorAction SilentlyContinue
    if ($pathCmd) {
        $BimcraftPath = $pathCmd.Source
    } else {
        Write-Error "BIMCraft CLI not found at '$BimcraftPath' or in PATH."
        exit 1
    }
}

Write-Host "[OK] BIMCraft CLI found: $BimcraftPath" -ForegroundColor Green

# 2. Check version
$version = & $BimcraftPath --version
Write-Host "[OK] BIMCraft version: $version" -ForegroundColor Green

# 3. Test running a sample model and verifying IFC & PNG exports
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "bimcraft_check_$(Get-Random)"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

try {
    $sampleBimcraft = Join-Path $tempDir "sample.bimcraft"
    $sampleIfc = Join-Path $tempDir "sample.ifc"
    $samplePng = Join-Path $tempDir "sample.png"

    Write-Host "Running test sample generation..." -ForegroundColor Yellow
    $output = & $BimcraftPath run --sample --save $sampleBimcraft --save $sampleIfc --save $samplePng

    if ((Test-Path $sampleBimcraft) -and (Test-Path $sampleIfc) -and (Test-Path $samplePng)) {
        $bimcraftSize = (Get-Item $sampleBimcraft).Length
        $ifcSize = (Get-Item $sampleIfc).Length
        $pngSize = (Get-Item $samplePng).Length
        Write-Host "[OK] Sample project generated successfully!" -ForegroundColor Green
        Write-Host "     - .bimcraft: $bimcraftSize bytes"
        Write-Host "     - .ifc:      $ifcSize bytes"
        Write-Host "     - .png:      $pngSize bytes"
    } else {
        Write-Error "Sample generation failed to produce expected files."
        exit 1
    }
} finally {
    if (Test-Path $tempDir) {
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
    }
}

Write-Host "=== All BIMCraft checks passed ===" -ForegroundColor Green
exit 0

