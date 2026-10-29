# DXF-to-3D-BIM

[![Antigravity Skill](https://img.shields.io/badge/Antigravity-Skill-blue.svg)](https://github.com/google/antigravity)
[![BIM Engine](https://img.shields.io/badge/BIMCraft-0.9.0-green.svg)](https://github.com/IPedrax/BIMCraft)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-yellow.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-82%20Passed-brightgreen.svg)]()

An autonomous AI agent skill that transforms 2D architectural DXF floor plans into semantically structured, editable 3D Building Information Models using BIMCraft 0.9.0.

---

## Key Features

- **Universal Preflight Analyzer**: Audits arbitrary CAD files for version, units, modelspace vs paperspace, scale confidence, XREFs, degenerate lines, and AIA layer classifications before BIM construction.
- **Configurable Multi-Storey Reconstruction**: Reconstructs multi-storey buildings ($N \ge 1$) via Mode A (explicit DXF layers `L1-`, `L2-`, `STOREY_2_`, `FL01-`) or Mode B (user-configured storeys, custom storey heights, ground elevation, and repeated floor options).
- **Parametric Roof Generation**: Generates 3D **Gable**, **Hip**, **Flat**, and **Shed** roofs with configurable pitch, eave overhang, thickness, and elevation. Automatically detects short-edge gable ends on rotated or axis-aligned buildings, hosts roofs atop the top occupied storey, and isolates non-occupied roof datums.
- **Guided Human Approval Gate**: Clear architectural review (Units/Scale, Walls, Openings, Slab, Storeys & Roof, Warnings, Deliverables). Locks approved parameters with deterministic SHA-256 snapshots.
- **One-Command End-to-End Execution**: Full CLI pipeline (`dxf-to-3d-bim run`) supporting interactive terminal guidance and headless automated CI/CD execution (`--non-interactive`).
- **Semantic Reconstruction**: Reconstructs genuine architectural elements (Levels, Exterior/Interior Walls, Hosted Doors & Windows, Floor Slabs, Roofs, Rooms) rather than CAD line extrusions. Collinear walls are automatically merged across opening gaps.
- **BIMCraft CLI 0.9.0 Integration**: Headless construction producing native `.bimcraft` projects and standard `IFC4` models (`IFCROOF`, `IFCWALL`, `IFCDOOR`, etc.).
- **Visual Verification Suite**: Generates 3D axonometric views, orthographic elevations (South, East), building cross-sections (Section A-A), per-level floor plans, and CAD-to-BIM comparison overlays with explicit deviation metrics.
- **Independent STEP IFC Parser & Validator**: Pure-Python ISO-10303-21 parser verifying `IFCROOF` predefined types, `IfcRelVoidsElement`, `IfcRelFillsElement`, `IfcRelContainedInSpatialStructure`, opening host alignment, and boundary containment.
- **Structured Deliverables Package & Manifest**: Packages outputs into `analysis/`, `models/`, `previews/`, `reports/`, and a top-level `manifest.json`.

---

## Deliverables Structure

Each completed run produces an organized, auditable directory tree:

```
output_dir/
├── manifest.json                       # Run status, toolchain version, artifact SHA-256 hashes
├── analysis/
│   ├── preflight_report.json           # Machine-readable preflight audit
│   ├── preflight_report.md             # Human-readable Markdown preflight report
│   ├── intermediate-model.json         # Normalized intermediate BIM specification
│   └── approval_record.json            # Version-locked SHA-256 approval snapshot
├── models/
│   ├── <project>.bimcraft              # Native editable BIMCraft project
│   └── <project>.ifc                   # Standard IFC4 Coordination View
├── previews/
│   ├── <project>.png                   # 2D Orthographic floor plan
│   ├── <project>_3d.png                # 3D Axonometric isometric render
│   ├── <project>_elev_south.png        # South elevation
│   ├── <project>_elev_east.png         # East elevation
│   ├── <project>_section_a.png         # Longitudinal building section A-A
│   └── <project>_comparison_overlay.png # CAD linework (cyan) vs BIM (magenta) overlay
└── reports/
    ├── validation-report.json          # Independent validation checks
    └── review_summary.md               # Human review summary & engineering notice
```

---

## CLI Usage & Commands

### 1. Preflight Inspection
Audit an arbitrary DXF drawing before generating BIM:
```powershell
dxf-to-3d-bim inspect path\to\plan.dxf
# Save preflight reports
dxf-to-3d-bim inspect path\to\plan.dxf --out-json preflight.json --out-md preflight.md
# Explicit unit override
dxf-to-3d-bim inspect path\to\plan.dxf --unit m
```

### 2. Guided One-Command Workflow (Interactive)
Runs preflight, presents the 7-section proposal, prompts for user confirmation/edits, constructs the model, validates deliverables, and generates manifests:
```powershell
dxf-to-3d-bim run path\to\plan.dxf --out deliverables
```

### 3. Headless Automated Execution (Non-Interactive)
For CI/CD scripts or automated agent workflows:
```powershell
dxf-to-3d-bim run path\to\plan.dxf --out deliverables --non-interactive --config path\to\approved-config.json
# Or auto-approve for testing
dxf-to-3d-bim run path\to\plan.dxf --out deliverables --non-interactive --auto-approve
```

### 4. Step-by-Step Individual Commands
```powershell
# Prepare intermediate model
dxf-to-3d-bim prepare path\to\plan.dxf --out intermediate-model.json

# Approve and lock model version
dxf-to-3d-bim approve intermediate-model.json --by "Architect Name" --notes "Approved"

# Build BIMCraft, IFC4, and renders
dxf-to-3d-bim build intermediate-model.json --out output

# Generate CAD-to-BIM visual comparison overlay
dxf-to-3d-bim compare path\to\plan.dxf intermediate-model.json --overlay comparison.png
```

---

## Configuration Reference

Configuration overrides can be provided via `--config path/to/config.json`, conforming to `project-config.schema.json`:

```json
{
  "version": "1.0.0",
  "units": {
    "source_unit": "mm",
    "dxf_default_if_unspecified": "mm"
  },
  "levels": {
    "default_storeys": 1,
    "floor_to_floor_height": 3000.0
  },
  "walls": {
    "exterior_thickness": 200.0,
    "interior_thickness": 100.0,
    "height": 3000.0
  },
  "openings": {
    "door_width": 900.0,
    "door_height": 2100.0,
    "window_width": 1200.0,
    "window_height": 1200.0,
    "window_sill_height": 900.0
  },
  "slab": {
    "thickness": 150.0,
    "elevation": 0.0
  }
}
```

---

## Testing & Quality Assurance

Run the automated test suite (82 tests):
```powershell
.venv\Scripts\pytest.exe -v
```

### Test Coverage Highlights
- **Preflight (11 tests)**: Missing files, empty drawings, corrupt DXFs, annotations-only, ambiguous units, non-mm units, unknown layers, degenerate geometry.
- **Guided Approval (7 tests)**: Interactive accept/edit/reject, DXF tamper detection, config tamper detection, stale approval detection.
- **Multi-Storey Reconstruction (8 tests)**: Mode A layers, repeated ground floor, unequal heights, rotated stacking, parameter validation, IFC storey containment.
- **Parametric Roof Generation (8 tests)**: Gable & hip calculations, rotated buildings, flat/shed types, parameter rejections, approval tamper detection, BIMCraft CLI generation, and IFC4 validation.
- **Pipeline Workflow (8 tests)**: One-command run, structured directory generation, manifest hash verification, non-interactive validation.
- **Geometric & IFC Robustness (40 tests)**: Collinear wall merging, opening voiding/filling relationships, spatial containment, ISO-10303-21 STEP tokenizer.

---

## Professional Engineering Notice

> [!NOTE] Professional Review Required
> All 3D BIM elements, materials, thicknesses, and structural representations generated by this skill are architectural and conceptual for spatial coordination. Structural engineering calculations, local building code compliance, egress verification, and licensed sign-off must be independently performed by a licensed professional.
