# BIM Validation Checklist

Every generated model must pass this checklist before delivery:

- [ ] **DXF Parsing**:
  - Drawing units detected or explicitly confirmed by user.
  - Geometry bounding extents non-zero.
- [ ] **Reconstruction**:
  - Centerlines extracted from double-line walls without duplicate overlapping lines.
  - Wall junctions (L & T) properly snapped.
  - All doors and windows successfully hosted onto continuous wall segments.
- [ ] **Approval Gate**:
  - Model proposal presented with wall counts, door/window counts, and vertical parameters.
  - Explicit user approval recorded in intermediate JSON.
- [ ] **BIMCraft Construction**:
  - All JSON commands executed without error.
  - Native `.bimcraft` saved successfully and re-readable.
- [ ] **Export & Quality Assurance**:
  - IFC4 file generated, non-zero size, and verified via `bimcraft-cli info`.
  - Element counts in IFC match intermediate model.
  - Plan preview image (`.png`) generated and visually verifiable.
  - Final validation report generated distinguishing PASSED, WARNING, and UNVERIFIED items.
