# DXF-to-3D-BIM End-to-End Workflow

This document details the operational workflow for agents and users converting 2D DXF floor plans into 3D BIM models.

## Phase 1: Input Discovery & Inspection
* Command: `dxf-to-3d-bim inspect <path-to-dxf>`
* Inspects:
  * DXF version (R12, R2000, R2018, etc.)
  * Drawing units (`$INSUNITS`)
  * Model extents
  * Layer inventory and entity tallies
* Resolution: If units are unspecified (`$INSUNITS = 0`), the agent requests user confirmation before scaling.

## Phase 2: Geometric & Semantic Reconstruction
* Command: `dxf-to-3d-bim prepare <path-to-dxf> [--json <upstream-model.json>]`
* Algorithm:
  * Extract wall linework by layer name/pattern.
  * Detect double-line pairs to establish wall centerlines and measured wall thickness.
  * Form topological intersections (L-, T-, and cross-junctions).
  * Associate openings (doors and windows) with host wall centerlines.
  * Reconstruct closed perimeter loops to define slab boundaries and room envelopes.
* Produces: `intermediate-model.json` with status `awaiting_approval`.

## Phase 3: Mandatory Approval Gate
* The agent presents a structured summary:
  * Building envelope: width, depth, gross floor area.
  * Reconstructed walls: count, interior vs. exterior, thicknesses.
  * Openings: door and window counts, widths, and host wall associations.
  * Proposed vertical parameters: storey heights, wall height, slab thickness, sill heights.
  * Assumptions & Uncertainties: any ambiguous layers or unhosted elements.
* The user approves or provides corrections.
* Command: `dxf-to-3d-bim approve intermediate-model.json` updates status to `approved`.

## Phase 4: BIMCraft Model Generation
* Command: `dxf-to-3d-bim build intermediate-model.json --out output/`
* Enforces `status: "approved"`.
* Invokes `bimcraft-cli run` with sequenced operations:
  1. `level`: Define Level 1 (`0 mm`) and Level 2 (`3000 mm`).
  2. `wall`: Place exterior and interior walls with centerlines and heights.
  3. `floor`: Generate ground slab from perimeter polygon.
  4. `door` / `window`: Insert hosted openings into walls.
  5. `room`: Define spatial zones and tags.
* Saves:
  * `output/model.bimcraft`
  * `output/model.ifc`
  * `output/model.png`

## Phase 5: Independent Verification & Reporting
* Command: `dxf-to-3d-bim validate output/model.ifc --model intermediate-model.json`
* Runs `bimcraft-cli info` on the generated IFC and BIMCraft projects.
* Verifies element counts match intermediate specifications.
* Emits `validation-report.json` and a human-readable summary.

