"""Parametric 3D Roof Generation Engine for gable, hip, flat, and shed roofs."""

import math
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional
from shapely.geometry import Polygon, LineString, MultiLineString
from shapely.ops import unary_union, polygonize


@dataclass
class RoofGeometry:
    id: str
    roof_type: str
    level_id: str
    base_elevation: float
    pitch_degrees: float
    overhang: float
    thickness: float
    boundary: List[Tuple[float, float]]
    ridge_endpoints: List[Tuple[float, float, float]]
    ridge_elevation: float
    gable_edge_indices: List[int]
    area_m2: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "roofType": self.roof_type,
            "levelId": self.level_id,
            "baseElevation": round(self.base_elevation, 2),
            "pitchDegrees": round(self.pitch_degrees, 2),
            "overhang": round(self.overhang, 2),
            "thickness": round(self.thickness, 2),
            "boundary": [[round(p[0], 2), round(p[1], 2)] for p in self.boundary],
            "ridgeEndpoints": [[round(r[0], 2), round(r[1], 2), round(r[2], 2)] for r in self.ridge_endpoints],
            "ridgeElevation": round(self.ridge_elevation, 2),
            "gableEdgeIndices": list(self.gable_edge_indices),
            "areaM2": round(self.area_m2, 2),
            "provenance": "parametric_engine",
            "confidence": "high",
        }


class ParametricRoofEngine:
    """Computes exact 3D parametric roof geometry, bearing elevations, ridge orientations, and gable profiles."""

    SUPPORTED_ROOF_TYPES = {"none", "gable", "hip", "flat", "shed"}

    @classmethod
    def generate_roof(
        cls,
        footprint: List[Tuple[float, float]] | List[List[float]],
        top_level_name: str = "Level 1",
        top_level_elevation: float = 0.0,
        top_wall_height: float = 3000.0,
        roof_type: str = "gable",
        pitch_degrees: float = 30.0,
        overhang: float = 300.0,
        thickness: float = 200.0,
        roof_id: str = "roof_1",
    ) -> Optional[RoofGeometry]:
        """Calculates parametric roof geometry and returns RoofGeometry instance."""
        r_type = (roof_type or "none").strip().lower()
        if r_type not in cls.SUPPORTED_ROOF_TYPES:
            raise ValueError(
                f"Unsupported roof type: '{roof_type}'. Supported types: {sorted(cls.SUPPORTED_ROOF_TYPES)}"
            )

        if r_type == "none":
            return None

        # Validate numerical parameters
        if pitch_degrees < 0.0 or pitch_degrees >= 89.9:
            raise ValueError(f"Roof pitch must be in range [0, 89.9) degrees (got {pitch_degrees})")
        if overhang < 0.0:
            raise ValueError(f"Roof overhang cannot be negative (got {overhang})")
        if thickness < 0.0:
            raise ValueError(f"Roof thickness cannot be negative (got {thickness})")
        if top_wall_height < 0.0:
            raise ValueError(f"Top wall height cannot be negative (got {top_wall_height})")

        # Clean and validate footprint polygon
        raw_pts = [(float(p[0]), float(p[1])) for p in footprint]
        if len(raw_pts) < 3:
            raise ValueError(f"Roof footprint requires at least 3 vertices (got {len(raw_pts)})")

        # Strip duplicate closing vertex if present
        if math.isclose(raw_pts[0][0], raw_pts[-1][0], abs_tol=1e-3) and math.isclose(
            raw_pts[0][1], raw_pts[-1][1], abs_tol=1e-3
        ):
            clean_pts = raw_pts[:-1]
        else:
            clean_pts = raw_pts

        if len(clean_pts) < 3:
            raise ValueError("Roof footprint degenerate after removing duplicate closing vertex.")

        poly = Polygon(clean_pts)
        if not poly.is_valid:
            # Try buffer(0) repair
            repaired = poly.buffer(0)
            if isinstance(repaired, Polygon) and repaired.is_valid and repaired.area > 0:
                poly = repaired
                clean_pts = [(round(p[0], 2), round(p[1], 2)) for p in poly.exterior.coords[:-1]]
            else:
                raise ValueError("Roof footprint polygon is self-intersecting or invalid.")

        if poly.area <= 100.0:
            raise ValueError(f"Roof footprint area is too small ({poly.area} mm²).")

        # Bearing elevation is at top of host level walls
        bearing_elev = top_level_elevation + top_wall_height
        area_m2 = poly.area / 1_000_000.0

        n = len(clean_pts)
        gable_edge_indices: List[int] = []
        ridge_endpoints: List[Tuple[float, float, float]] = []
        ridge_elevation = bearing_elev

        if r_type == "flat":
            pitch_degrees = 0.0
            ridge_elevation = bearing_elev
            gable_edge_indices = []

        elif r_type in ("gable", "hip"):
            if n != 4:
                if r_type == "gable":
                    raise ValueError(
                        f"Gable roof currently requires a 4-sided rectangular footprint (found {n} vertices). "
                        f"For complex polygons, use hip roof or simplify footprint."
                    )
                else:
                    # Generic polygon hip roof
                    gable_edge_indices = []
                    # Approximate ridge or apex at centroid
                    c = poly.centroid
                    # Approximate half-span by radius of maximum inscribed circle or sqrt(area)/4
                    approx_half_span = math.sqrt(poly.area) / 4.0
                    delta_z = approx_half_span * math.tan(math.radians(pitch_degrees))
                    ridge_elevation = bearing_elev + delta_z
                    ridge_endpoints = [(c.x, c.y, ridge_elevation), (c.x, c.y, ridge_elevation)]
            else:
                # 4-sided polygon: can be axis-aligned or rotated
                # Calculate edge lengths
                edge_lens = []
                for i in range(4):
                    p_curr = clean_pts[i]
                    p_next = clean_pts[(i + 1) % 4]
                    dist = math.hypot(p_next[0] - p_curr[0], p_next[1] - p_curr[1])
                    edge_lens.append(dist)

                len_pair_a = (edge_lens[0] + edge_lens[2]) / 2.0
                len_pair_b = (edge_lens[1] + edge_lens[3]) / 2.0

                if len_pair_a <= len_pair_b:
                    # Edges 0 and 2 are shorter -> gable ends
                    short_indices = [0, 2]
                    span = len_pair_a
                    m_start = (
                        (clean_pts[0][0] + clean_pts[1][0]) / 2.0,
                        (clean_pts[0][1] + clean_pts[1][1]) / 2.0,
                    )
                    m_end = (
                        (clean_pts[2][0] + clean_pts[3][0]) / 2.0,
                        (clean_pts[2][1] + clean_pts[3][1]) / 2.0,
                    )
                else:
                    # Edges 1 and 3 are shorter -> gable ends
                    short_indices = [1, 3]
                    span = len_pair_b
                    m_start = (
                        (clean_pts[1][0] + clean_pts[2][0]) / 2.0,
                        (clean_pts[1][1] + clean_pts[2][1]) / 2.0,
                    )
                    m_end = (
                        (clean_pts[3][0] + clean_pts[0][0]) / 2.0,
                        (clean_pts[3][1] + clean_pts[0][1]) / 2.0,
                    )

                half_span = span / 2.0
                delta_z = half_span * math.tan(math.radians(pitch_degrees))
                ridge_elevation = bearing_elev + delta_z

                if r_type == "gable":
                    gable_edge_indices = short_indices
                    ridge_endpoints = [
                        (m_start[0], m_start[1], ridge_elevation),
                        (m_end[0], m_end[1], ridge_elevation),
                    ]
                elif r_type == "hip":
                    gable_edge_indices = []
                    # Ridge is inset along centerline by half_span from both ends
                    ridge_len_total = math.hypot(m_end[0] - m_start[0], m_end[1] - m_start[1])
                    if ridge_len_total > (2.0 * half_span):
                        ux = (m_end[0] - m_start[0]) / ridge_len_total
                        uy = (m_end[1] - m_start[1]) / ridge_len_total
                        r1 = (m_start[0] + half_span * ux, m_start[1] + half_span * uy, ridge_elevation)
                        r2 = (m_end[0] - half_span * ux, m_end[1] - half_span * uy, ridge_elevation)
                        ridge_endpoints = [r1, r2]
                    else:
                        # Square building: hip terminates at central apex
                        apex_x = (m_start[0] + m_end[0]) / 2.0
                        apex_y = (m_start[1] + m_end[1]) / 2.0
                        ridge_endpoints = [
                            (apex_x, apex_y, ridge_elevation),
                            (apex_x, apex_y, ridge_elevation),
                        ]

        elif r_type == "shed":
            # Shed roof: slopes in one direction
            gable_edge_indices = []
            if n == 4:
                # Top edge is highest, opposite is at bearing elevation
                ridge_elevation = bearing_elev + math.hypot(
                    clean_pts[1][0] - clean_pts[0][0], clean_pts[1][1] - clean_pts[0][1]
                ) * math.tan(math.radians(pitch_degrees))
                ridge_endpoints = [
                    (clean_pts[2][0], clean_pts[2][1], ridge_elevation),
                    (clean_pts[3][0], clean_pts[3][1], ridge_elevation),
                ]

        return RoofGeometry(
            id=roof_id,
            roof_type=r_type,
            level_id=top_level_name,
            base_elevation=bearing_elev,
            pitch_degrees=pitch_degrees,
            overhang=overhang,
            thickness=thickness,
            boundary=clean_pts,
            ridge_endpoints=ridge_endpoints,
            ridge_elevation=ridge_elevation,
            gable_edge_indices=gable_edge_indices,
            area_m2=area_m2,
        )

    @classmethod
    def derive_roof_footprint_from_model(
        cls,
        model_data: Dict[str, Any],
        target_level_name: str,
    ) -> List[Tuple[float, float]]:
        """Derives clean 2D footprint boundary for the roof from existing model elements (slabs or exterior walls)."""
        floors = model_data.get("floors", [])
        walls = model_data.get("walls", [])

        # 1. Prefer floor slab on target level
        target_slabs = [fl for fl in floors if fl.get("levelId") == target_level_name]
        if target_slabs and "boundary" in target_slabs[0] and len(target_slabs[0]["boundary"]) >= 3:
            return [(p[0], p[1]) for p in target_slabs[0]["boundary"]]

        # 2. Check any floor slab (e.g. ground slab in repeated storey building)
        if floors and "boundary" in floors[0] and len(floors[0]["boundary"]) >= 3:
            return [(p[0], p[1]) for p in floors[0]["boundary"]]

        # 3. Derive from exterior walls on target level
        target_walls = [
            w for w in walls
            if w.get("levelId") == target_level_name and w.get("classification") == "exterior"
        ]
        if not target_walls:
            # Fall back to all exterior walls or all walls
            target_walls = [w for w in walls if w.get("classification") == "exterior"]
        if not target_walls:
            target_walls = walls

        if not target_walls:
            raise ValueError("Cannot derive roof footprint: model has no walls or floor slabs.")

        # Try to order wall segments into a closed polygon
        lines = [LineString([w["start"], w["end"]]) for w in target_walls]
        merged = unary_union(lines)
        polys = list(polygonize(merged))
        if polys:
            # Choose largest polygon
            largest = max(polys, key=lambda p: p.area)
            coords = list(largest.exterior.coords)
            return [(round(p[0], 2), round(p[1], 2)) for p in coords[:-1]]

        # Fallback to convex hull or oriented bounding box of wall points
        all_pts = []
        for w in target_walls:
            all_pts.append(w["start"])
            all_pts.append(w["end"])

        ls = MultiLineString([LineString([w["start"], w["end"]]) for w in target_walls])
        hull = ls.convex_hull
        if isinstance(hull, Polygon) and hull.is_valid:
            return [(round(p[0], 2), round(p[1], 2)) for p in hull.exterior.coords[:-1]]

        # Minimum bounding box fallback
        min_x = min(p[0] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_y = max(p[1] for p in all_pts)
        return [
            (round(min_x, 2), round(min_y, 2)),
            (round(max_x, 2), round(min_y, 2)),
            (round(max_x, 2), round(max_y, 2)),
            (round(min_x, 2), round(max_y, 2)),
        ]
