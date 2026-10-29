# Workflow: Inspect DXF

## Purpose
Examine the incoming 2D DXF file to determine layer structure, drawing units, bounding extents, and supported entity types.

## Steps
1. Run `dxf-to-3d-bim inspect <input.dxf>`.
2. Review the inspection report:
   - Check `$INSUNITS` or dimension measurements. If ambiguous, prompt the user for drawing units (mm, m, ft, in).
   - Check available layers against `config/layer-aliases.json`.
   - Record skipped or non-architectural entities (e.g. title blocks, hatches).
3. If an upstream `floor-plan-model.json` is provided, compare layer and wall counts with the JSON model.
