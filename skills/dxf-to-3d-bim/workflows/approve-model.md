# Workflow: Approve Model (Mandatory Gate)

## Purpose
Enforce user review and approval of the proposed 3D building parameters before issuing construction commands to BIMCraft.

## Steps
1. Present a concise summary of the intermediate model to the user:
   - Footprint dimensions and area
   - Number of exterior and interior walls
   - Opening counts (doors, windows)
   - Inferred vertical parameters (storey height, sill heights)
   - Explicit uncertainty and assumptions log
2. Ask for explicit approval or adjustments.
3. Upon approval:
   - Calculate SHA-256 hash of intermediate model.
   - Update model status to `approved`.
   - Record approval timestamp and notes conforming to `approval.schema.json`.
4. **DO NOT proceed to BIM generation without this approval.**
