# Workflow: Generate BIM

## Purpose
Execute verified BIMCraft commands to build the 3D model from the approved intermediate representation.

## Steps
1. Verify that `intermediate-model.json` has `status: "approved"`. Reject unapproved models.
2. Initialize an isolated project via `bimcraft-cli run`.
3. Construct building elements in topological order:
   - Levels (`level`)
   - Exterior & interior walls (`wall`)
   - Floor slabs (`floor`)
   - Hosted doors & windows (`door`, `window`)
   - Rooms (`room`)
   - Roofs (`roof`, if approved)
4. Execute and stream command batch.
5. Save the native project (`.bimcraft`).
6. Export IFC4 model (`.ifc`).
7. Export plan preview image (`.png`).

