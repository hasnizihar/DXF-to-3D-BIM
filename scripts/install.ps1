# Installation script for DXF-to-3D-BIM skill
param(
    [switch]$DryRun = $false,
    [string]$SkillsDir = "$env:USERPROFILE\.gemini\config\skills"
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  DXF-to-3D-BIM Skill Installation Script " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Check Python
$pythonCmd = Get-Command "python.exe" -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "Python was not found in PATH. Python 3.11+ is required."
    exit 1
}

$pyVersion = python --version
Write-Host "[OK] Detected Python: $pyVersion" -ForegroundColor Green

# 2. Check Virtual Environment
$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment at .venv..." -ForegroundColor Yellow
    if (-not $DryRun) {
        python -m venv (Join-Path $PSScriptRoot "..\.venv")
    }
} else {
    Write-Host "[OK] Virtual environment found at .venv" -ForegroundColor Green
}

# 3. Check / Install Python Dependencies
Write-Host "Checking Python dependencies..." -ForegroundColor Yellow
$packages = @("ezdxf", "shapely", "pydantic", "pytest", "pillow", "rich", "typer")
if (-not $DryRun) {
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet $packages
    & $venvPython -m pip install --quiet -e (Join-Path $PSScriptRoot "..")
    Write-Host "[OK] Python dependencies verified and installed." -ForegroundColor Green
} else {
    Write-Host "[DRY RUN] Would install dependencies: $($packages -join ', ')" -ForegroundColor Cyan
}

# 4. Check BIMCraft CLI
$bimcraftPath = "C:\Program Files\BIMCraft\bimcraft-cli.exe"
if (Test-Path $bimcraftPath) {
    $bimcraftVer = & $bimcraftPath --version
    Write-Host "[OK] BIMCraft CLI verified: $bimcraftPath ($bimcraftVer)" -ForegroundColor Green
} else {
    $foundCmd = Get-Command "bimcraft-cli.exe" -ErrorAction SilentlyContinue
    if ($foundCmd) {
        Write-Host "[OK] BIMCraft CLI found in PATH: $($foundCmd.Source)" -ForegroundColor Green
    } else {
        Write-Warning "BIMCraft CLI was not found at standard path '$bimcraftPath' or in PATH."
        Write-Warning "Please install BIMCraft or configure its path in config/defaults.json."
    }
}

# 5. Link / Copy Skill to Antigravity Skills Directory
$targetSkillDir = Join-Path $SkillsDir "dxf-to-3d-bim"
$sourceSkillDir = Join-Path $PSScriptRoot "..\skills\dxf-to-3d-bim"

Write-Host "Configuring skill in Antigravity skills directory: $targetSkillDir" -ForegroundColor Yellow

if ($DryRun) {
    Write-Host "[DRY RUN] Would copy skill files from $sourceSkillDir to $targetSkillDir" -ForegroundColor Cyan
} else {
    if (-not (Test-Path $SkillsDir)) {
        New-Item -ItemType Directory -Path $SkillsDir -Force | Out-Null
    }
    if (-not (Test-Path $targetSkillDir)) {
        New-Item -ItemType Directory -Path $targetSkillDir -Force | Out-Null
    }

    Copy-Item -Path (Join-Path $sourceSkillDir "*") -Destination $targetSkillDir -Recurse -Force
    Write-Host "[OK] Skill files successfully copied to $targetSkillDir" -ForegroundColor Green
}

Write-Host ""
Write-Host "Installation completed successfully!" -ForegroundColor Green
exit 0
