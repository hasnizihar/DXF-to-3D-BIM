# Milestone 11 Verification & Engineering Audit

**Milestone:** 11 — Configurable Multi-Storey Building Reconstruction  
**Date:** 30 October 2026  
**Toolchain:** Python 3.12.10, BIMCraft CLI 0.9.0, ezdxf 1.4.3, Shapely 2.1.2, Pydantic 2.12.5  
**Test Suite:** 74/74 Passed (100% Green)

---

## 1. Executive Summary

Milestone 11 extends the DXF-to-3D-BIM pipeline from single-storey floor plans to full **configurable multi-storey buildings** ($N \ge 1$), assigning architectural elements (`wall`, `door`, `window`, `floor`/`slab`) to their respective levels, producing verified native `.bimcraft` projects, exporting standard `IFC4` models with deep spatial structure containment, and rendering multi-storey visual deliverables (3D isometric perspectives, multi-storey cross-sections, and per-level floor plans).

Zero regressions were introduced: the baseline single-storey workflow and all 66 prior tests remain fully passing, bringing the total suite to **74 passing tests**.

---

## 2. Architectural Design & Implementation

### 2.1 Dual Multi-Storey Input Modes

1. **Mode A — Explicit DXF Storey Layers**:
   - `LayerClassifier` detects layer prefixes and suffixes including `L1-`, `L2-`, `LEVEL_1_`, `STOREY_2_`, `FL01-`, etc.
   - Geometry, openings, and slabs are segregated per storey without cross-contamination.
   - Supports different architectural footprints per floor (e.g. stepped or set-back upper storeys).

2. **Mode B — User-Configured / Repeated Storeys**:
   - CLI flags: `--storeys <N>`, `--storey-height <mm>`, `--ground-elevation <mm>`, `--repeat-ground-floor`, `--storey-config <path.json>`.
   - Replicates ground-floor walls, doors, windows, and floor boundaries onto upper levels with scoped unique IDs (e.g. `wall_L2_1`, `door_L2_1`).
   - Storey elevations and slab levels are computed deterministically ($E_i = E_0 + \sum H_k$).
   - **Safety Boundary**: Silent unapproved replication of single-storey CAD plans is strictly prevented. In headless runs, `--repeat-ground-floor` or `--storey-config` is required; in interactive mode, explicit confirmation is requested.

### 2.2 BIMCraft Adapter Multi-Level Mechanics

- BIMCraft project starts with default `Level 1` (0) and `Level 2` (3000).
- Level elevations are dynamically adjusted using `modify {"id": 100000, "elevation": E0}` and `modify {"id": 100001, "elevation": E1}`.
- Additional storeys and roof datums (`Level 3`, `Level 4`, ...) are created with `level {"name": "...", "elevation": ...}`.
- Hosted elements specify their host level: `door {"at": [...], "level": "Level 2"}` and `window {"at": [...], "level": "Level 2"}` ensuring accurate wall hosting for vertically stacked openings.

### 2.3 Deep IFC4 Spatial Containment Verification

- `PureIfcParser` verifies that each inhabited storey has an `IfcBuildingStorey` entity.
- Checks `IfcRelContainedInSpatialStructure` relationships to guarantee that upper-floor elements are formally assigned to their respective storeys, rather than lumped into Level 1.
- Validates that wall voiding (`IfcRelVoidsElement`) and filling (`IfcRelFillsElement`) relationships hold across all storeys.

### 2.4 Visual Verification Suite

- **3D Axonometric Render**: Isometric perspective showing all stacked storeys (`_3d.png`).
- **Full-Building Section A-A**: Longitudinal section cutting through both ground and upper floors (`_section_a.png`).
- **Per-Level Floor Plans**: Orthographic plans for Ground (`<project>.png`) and upper storeys (`<project>_plan_level_2.png`).
- **CAD/BIM Comparison Overlay**: Preserved for ground footprint alignment.

---

## 3. Test Fixtures & Coverage Summary (74 Tests)

| Fixture / Test | Scenario | Verified Outcome |
| :--- | :--- | :--- |
| `test_multi_storey_single_storey_baseline_regression` | Single-storey backward compatibility | Level 1 & Level 2 datum created; 0 upper elements; 100% regression safe |
| `test_multi_storey_repeated_ground_floor` | 2-storey building with repeated footprint | 8 walls, 4 openings, 2 slabs; base elevation 3000 mm; Level 3 datum created |
| `test_multi_storey_unequal_storey_heights` | Ground 3500 mm + Upper 2800 mm + Ground elev 500 mm | Level 1: 500 mm, Level 2: 4000 mm, Level 3: 6800 mm |
| `test_mode_a_dxf_layers_different_footprints` | Mode A DXF with `L1-` (8x6m) and `L2-` (5x4m) | Stepped footprint accurately reconstructed per storey |
| `test_multi_storey_rotated_geometry` | 45-degree rotated multi-storey geometry | Rotated coordinates preserved and stacked vertically |
| `test_multi_storey_invalid_parameters` | `storeys=0`, `storey_height=500`, unapproved repeat | Rejected with clear, structured validation errors |
| `test_multi_storey_approval_tamper_detection` | Elevation altered after human approval | Invalidation triggered; SHA-256 tamper lock enforced |
| `test_multi_storey_end_to_end_bimcraft_and_ifc` | Live BIMCraft CLI build & deep IFC parsing | Native `.bimcraft`, IFC4, 3D render, section, and per-level plans verified |
| Baseline Tests (66) | Prior milestones (preflight, units, geometry, approval, IFC) | 66/66 Passed |

---

## 4. End-to-End Real-World Run Evidence (`deliverables_milestone11`)

Executed command:
```powershell
python -m dxf_to_3d_bim.cli run residential-floor-plan.dxf --storeys 2 --repeat-ground-floor --auto-approve --out deliverables_milestone11
```

Generated Deliverables:
- **Manifest**: `deliverables_milestone11/manifest.json`
- **Native Model**: `deliverables_milestone11/models/residential-floor-plan.bimcraft` (179,517 bytes)
- **Standard IFC4**: `deliverables_milestone11/models/residential-floor-plan.ifc` (69,155 bytes)
- **2D Plan Preview (Ground)**: `deliverables_milestone11/previews/residential-floor-plan.png` (143,703 bytes)
- **2D Plan Preview (Level 2)**: `deliverables_milestone11/previews/residential-floor-plan_plan_level_2.png` (143,745 bytes)
- **3D Axonometric Render**: `deliverables_milestone11/previews/residential-floor-plan_3d.png` (171,007 bytes)
- **Full Cross-Section A-A**: `deliverables_milestone11/previews/residential-floor-plan_section_a.png` (164,863 bytes)
- **South Elevation**: `deliverables_milestone11/previews/residential-floor-plan_elev_south.png` (80,318 bytes)
- **East Elevation**: `deliverables_milestone11/previews/residential-floor-plan_elev_east.png` (106,000 bytes)
- **Validation Report**: `deliverables_milestone11/reports/validation-report.json` (`overallStatus: "PASSED"`)
- **Review Summary**: `deliverables_milestone11/reports/review_summary.md`
