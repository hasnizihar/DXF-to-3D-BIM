# DXF-to-3D-BIM

[![Antigravity Skill](https://img.shields.io/badge/Antigravity-Skill-blue.svg)](https://github.com/google/antigravity)
[![BIM Engine](https://img.shields.io/badge/BIMCraft-0.9.0-green.svg)](https://github.com/IPedrax/BIMCraft)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-yellow.svg)](https://www.python.org/)

An autonomous AI agent skill that transforms 2D architectural DXF floor plans into semantically structured, editable 3D Building Information Models using BIMCraft.

## Features
- **Semantic Reconstruction**: Reconstructs genuine architectural elements (walls, hosted doors, windows, slabs, rooms, levels) rather than simple CAD line extrusions.
- **Mandatory Approval Gate**: Transparently calculates and presents 3D vertical parameters (wall height, sill height, slab thickness) for user confirmation before generation.
- **BIMCraft Integration**: Direct headless construction via `bimcraft-cli` producing native `.bimcraft` projects and standard `IFC4` models.
- **Independent Validation**: Automated verification of element counts, levels, types, and visual plan alignment.
- **Sketch-to-CAD Compatible**: Works standalone on any standard 2D DXF or integrates seamlessly with upstream `floor-plan-model.json` files.

## Directory Structure
```
dxf-to-3d-bim/
├── skills/
│   └── dxf-to-3d-bim/
│       ├── SKILL.md                 # Antigravity skill definition
│       ├── references/              # Rules, standards, and checklists
│       ├── workflows/               # Step-by-step procedures
│       ├── schemas/                 # Versioned JSON validation schemas
│       └── examples/                # Reference fixtures
├── src/
│   └── dxf_to_3d_bim/               # Core Python modules
├── config/                          # Configurable aliases, tolerances, defaults
├── scripts/                         # Install and validation scripts
├── docs/                            # In-depth architectural & capability docs
└── tests/                           # Pytest test suite
```

## Quick Start
```powershell
# 1. Run automated installation and skill registration
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1

# 2. Validate environment and run automated tests
powershell -ExecutionPolicy Bypass -File .\scripts\validate-skill.ps1
```

