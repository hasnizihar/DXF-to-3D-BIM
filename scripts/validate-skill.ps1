# Validation script for DXF-to-3D-BIM skill integrity
param(
    [switch]$RunTests = $true
)

$ErrorActionPreference = "Stop"
Write-Host "=== Validating DXF-to-3D-BIM Skill Repository ===" -ForegroundColor Cyan

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$skillsDir = Join-Path $root "skills\dxf-to-3d-bim"
$skillMd = Join-Path $skillsDir "SKILL.md"

# 1. Validate SKILL.md presence and frontmatter
if (-not (Test-Path $skillMd)) {
    Write-Error "SKILL.md not found at $skillMd"
    exit 1
}

$content = Get-Content -Raw $skillMd
if (-not ($content -match "^---\s*[\r\n]+([\s\S]*?)[\r\n]+---")) {
    Write-Error "SKILL.md is missing YAML frontmatter delimiters (---)"
    exit 1
}

$frontmatter = $matches[1]
if (-not ($frontmatter -match "name:\s*dxf-to-3d-bim")) {
    Write-Error "SKILL.md frontmatter does not define name: dxf-to-3d-bim"
    exit 1
}
if (-not ($frontmatter -match "description:\s*.+")) {
    Write-Error "SKILL.md frontmatter is missing a description"
    exit 1
}
Write-Host "[OK] SKILL.md frontmatter is valid." -ForegroundColor Green

# 2. Validate JSON files syntax in config and schemas
$jsonFiles = Get-ChildItem -Path (Join-Path $root "config"), (Join-Path $skillsDir "schemas") -Filter "*.json" -Recurse
foreach ($file in $jsonFiles) {
    try {
        Get-Content -Raw $file.FullName | ConvertFrom-Json | Out-Null
        Write-Host "[OK] JSON syntax valid: $($file.Name)" -ForegroundColor Green
    } catch {
        Write-Error "Invalid JSON in $($file.FullName): $_"
        exit 1
    }
}

# 3. Validate BIMCraft CLI connection
$bimcraftScript = Join-Path $PSScriptRoot "check-bimcraft.ps1"
if (Test-Path $bimcraftScript) {
    & powershell -ExecutionPolicy Bypass -File $bimcraftScript
    if ($LASTEXITCODE -ne 0) {
        Write-Error "BIMCraft check script failed."
        exit 1
    }
}

# 4. Run Pytest if requested
if ($RunTests) {
    $pytestPath = Join-Path $root ".venv\Scripts\pytest.exe"
    if (Test-Path $pytestPath) {
        Write-Host "Running pytest suite..." -ForegroundColor Yellow
        & $pytestPath
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Pytest test suite failed."
            exit 1
        }
        Write-Host "[OK] Pytest test suite passed." -ForegroundColor Green
    } else {
        Write-Warning "Pytest not found at $pytestPath. Skipping automated tests."
    }
}

Write-Host "=== Skill validation successful! ===" -ForegroundColor Green
exit 0
