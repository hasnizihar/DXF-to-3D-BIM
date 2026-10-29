# Workflow: Validate BIM

## Purpose
Perform independent geometric, topological, and count validation on the generated BIM outputs.

## Steps
1. Re-open native `.bimcraft` file using `bimcraft-cli info <project.bimcraft>` to verify file integrity.
2. Inspect exported IFC file using `bimcraft-cli info <model.ifc>`.
3. Verify that element counts (walls, doors, windows, levels) in IFC match the approved intermediate model.
4. Verify non-zero file sizes for `.bimcraft`, `.ifc`, and preview `.png`.
5. Assemble findings into a validation report conforming to `validation-report.schema.json`.
6. Categorize each check as `PASSED`, `WARNING`, or `UNVERIFIED`.
