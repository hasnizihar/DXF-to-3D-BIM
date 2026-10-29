# Workflow: Reconstruct Geometry

## Purpose
Convert raw 2D line and polyline entities into normalized architectural walls, host openings, slabs, and rooms.

## Steps
1. Filter entities by architectural layer (e.g. `A-WALL-EXTR`, `A-WALL-INTR`).
2. Pair parallel wall faces to compute wall centerlines and measured wall thicknesses.
3. Detect doors and windows on opening layers (`A-DOOR`, `A-GLAZ`) or opening gaps.
4. Project openings onto the closest wall centerline to establish host relationships and offset distances.
5. Identify closed wall perimeter loops to form floor slab boundaries.
6. When enabled (`--roof-type`), invoke `ParametricRoofEngine` to derive top occupied storey footprint, bearing elevations, ridge orientations, and gable/hip profiles.
7. Assemble the intermediate model conforming to `bim-model.schema.json`.
8. Output `intermediate-model.json` with status `awaiting_approval`.

