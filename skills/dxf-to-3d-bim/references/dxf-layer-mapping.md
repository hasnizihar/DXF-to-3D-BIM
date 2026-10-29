# DXF Layer Mapping & Semantic Classification

## Upstream Sketch-to-CAD Standard Layers
When processing DXF files originating from `Sketch-to-CAD`, the standard layer names map directly:

| DXF Layer Name | Semantic Category | BIM Element Target | Typical Thickness |
| :--- | :--- | :--- | :--- |
| `A-WALL-EXTR` | Exterior Wall | BIMCraft `wall` | 200 mm |
| `A-WALL-INTR` | Interior Partition | BIMCraft `wall` | 100 mm |
| `A-DOOR` | Door Leaf / Swing | BIMCraft `door` (hosted) | Host thickness |
| `A-GLAZ` | Window / Glazing | BIMCraft `window` (hosted) | Host thickness |
| `A-FLOR` / `A-SLAB` | Floor Slab | BIMCraft `floor` | 150 mm |
| `A-ANNO-TEXT` | Text / Room Label | BIMCraft `room` name | N/A |
| `A-ANNO-DIMS` | Dimension Lines | Validation checks | N/A |

## Third-Party Layer Fallback Matching
For external DXF drawings that do not follow AIA layer standards, configure pattern regex rules in `config/layer-aliases.json`. If a layer cannot be classified with high confidence, queue it in the model's `assumptions` array and prompt the user for clarification before generating BIM geometry.

