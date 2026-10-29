# Architectural & Technical Limitations

## 1. Scope Boundaries (v0.1.0 MVP)
* **Single Storey Orthogonal Plans**: The initial release focuses on single-storey orthogonal residential floor plans. Curved walls and multi-storey vertical stacking are scheduled for subsequent iterations (v0.3.0).
* **Hosted Openings Only**: Doors and windows must be located along a host wall. Detached or freestanding opening geometry is logged as unhosted in the intermediate model.

## 2. Inferred Dimensions
* **2D DXF Information Limits**: Standard 2D CAD floor plans do not contain wall heights, window sill elevations, header heights, or roof slopes.
* **Approval Requirement**: All vertical dimensions are proposed based on regional architectural defaults in `config/defaults.json` and must be confirmed during the mandatory human approval gate.

## 3. Engineering Boundaries
* **Structural Safety**: The skill places conceptual architectural and structural elements. It does not perform structural calculations, load path modeling, or seismic/wind engineering.
* **Code Compliance**: Building code compliance (fire egress, ADA accessibility, thermal envelopes) is not evaluated and remains the responsibility of licensed design professionals.
