# DXF-to-3D-BIM Installation & Setup Guide

## Requirements
* **OS**: Windows 10 or 11 (64-bit)
* **Python**: 3.11 or 3.12 (Python 3.12 verified)
* **BIM Engine**: BIMCraft CLI 0.9.0+ (`C:\Program Files\BIMCraft\bimcraft-cli.exe`)

## Quick Setup
Run the automated PowerShell installer:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

This will:
1. Verify Python 3.11+ is installed.
2. Create or verify the local `.venv`.
3. Install required Python libraries (`ezdxf`, `shapely`, `pydantic`, `pytest`, `pillow`, `rich`, `typer`).
4. Install `dxf-to-3d-bim` in editable mode.
5. Verify BIMCraft CLI availability.
6. Register the skill in Antigravity's skills directory (`~/.gemini/config/skills/dxf-to-3d-bim`).

## Verifying the Installation
Run the skill verification script:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate-skill.ps1
```
All schema checks, BIMCraft checks, and automated pytest tests will run and report results.
