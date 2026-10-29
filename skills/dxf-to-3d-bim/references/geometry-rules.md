# Geometry Reconstruction Rules & Tolerances

## Principles
1. **Double-Line to Centerline Conversion**:
   * Architectural 2D plans draft walls as double lines (inner and outer faces).
   * BIMCraft walls are constructed from a centerline with an assigned thickness.
   * Reconstruct centerlines by pairing parallel line segments within the thickness tolerance (60 mm to 450 mm).
2. **Endpoint Snapping & Junctions**:
   * Snap endpoints within the `endpoint_snap` tolerance (default: 25 mm).
   * Preserve orthogonal L-junctions and T-junctions.
3. **Opening Cuts vs. Wall Continuity**:
   * Doors and windows interrupt double lines in 2D drafting.
   * In BIM, walls are continuous between structural corners, and openings are hosted elements that punch cuts into the wall automatically.
   * Bridge wall gaps where doors or windows are hosted.
4. **Coordinate Transformation**:
   * Transform DXF model coordinates into positive Cartesian coordinates with `(0, 0)` at the bottom-left of the building footprint.
   * Maintain reversible coordinate mappings in the intermediate model metadata.
