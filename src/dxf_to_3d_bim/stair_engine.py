"""Parametric 3D Staircase Generation Engine for straight, L-shaped, and U-shaped stairs."""

import math
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional
from shapely.geometry import Polygon, LineString, box
from shapely.ops import unary_union


@dataclass
class StairGeometry:
    id: str
    stair_type: str  # "straight", "l_shaped", "u_shaped"
    level_id: str
    top_level_id: str
    base_elevation: float
    top_elevation: float
    total_rise: float
    start: Tuple[float, float]
    end: Tuple[float, float]
    width: float
    riser_count: int
    actual_riser_height: float
    tread_count: int
    actual_going: float
    total_run: float
    climb_angle_deg: float
    landings: List[Dict[str, Any]]
    railings: bool
    headroom_clearance: float
    stairwell_boundary: List[Tuple[float, float]]
    stairwell_area_m2: float
    provenance: str = "user_configured"
    confidence: str = "high"
    approval_status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "stairType": self.stair_type,
            "levelId": self.level_id,
            "topLevelId": self.top_level_id,
            "baseElevation": round(self.base_elevation, 2),
            "topElevation": round(self.top_elevation, 2),
            "totalRise": round(self.total_rise, 2),
            "start": [round(self.start[0], 2), round(self.start[1], 2)],
            "end": [round(self.end[0], 2), round(self.end[1], 2)],
            "climbAngleDeg": round(self.climb_angle_deg, 2),
            "width": round(self.width, 2),
            "riserCount": int(self.riser_count),
            "actualRiserHeight": round(self.actual_riser_height, 2),
            "treadCount": int(self.tread_count),
            "actualGoing": round(self.actual_going, 2),
            "totalRun": round(self.total_run, 2),
            "landings": self.landings,
            "railings": bool(self.railings),
            "headroomClearance": round(self.headroom_clearance, 2),
            "stairwellBoundary": [[round(p[0], 2), round(p[1], 2)] for p in self.stairwell_boundary],
            "stairwellAreaM2": round(self.stairwell_area_m2, 2),
            "provenance": self.provenance,
            "confidence": self.confidence,
            "approvalStatus": self.approval_status,
        }


class ParametricStairEngine:
    """Calculates code-compliant riser/tread geometry, intermediate landings, 

    3D circulation paths, and upper-slab stairwell openings for building models.
    """

    SUPPORTED_STAIR_TYPES = {"straight", "l_shaped", "u_shaped"}

    @classmethod
    def calculate_risers_and_treads(
        cls,
        total_rise: float,
        target_riser: float = 175.0,
        target_going: float = 280.0,
        max_riser: float = 190.0,
        min_going: float = 250.0,
    ) -> Tuple[int, float, int, float]:
        """Calculates exact integer riser count, reconciled riser height, tread count, and going.

        Returns (riser_count, actual_riser_height, tread_count, actual_going).
        """
        if total_rise < 500.0:
            raise ValueError(f"Total rise {total_rise} mm is below minimum required 500 mm.")
        if target_riser <= 0 or target_going <= 0:
            raise ValueError("Target riser and going must be positive.")
        if target_going < 150.0:
            raise ValueError(f"Target going {target_going} mm is dangerously below code minimum 150 mm.")

        # Estimate risers
        num_risers = max(2, int(round(total_rise / target_riser)))
        actual_riser = total_rise / num_risers

        # If riser exceeds max_riser, try increasing riser count
        if actual_riser > max_riser:
            num_risers = int(math.ceil(total_rise / max_riser))
            actual_riser = total_rise / num_risers

        if actual_riser > 250.0:
            raise ValueError(f"Actual riser height {actual_riser:.1f} mm exceeds absolute safe limit 250 mm.")
        if actual_riser < 100.0:
            raise ValueError(f"Actual riser height {actual_riser:.1f} mm is below absolute minimum 100 mm.")

        num_treads = num_risers - 1
        actual_going = max(min_going, target_going)

        return num_risers, round(actual_riser, 4), num_treads, round(actual_going, 4)

    @classmethod
    def generate_stair(
        cls,
        stair_id: str = "stair_1",
        stair_type: str = "straight",
        level_id: str = "Level 1",
        top_level_id: str = "Level 2",
        base_elevation: float = 0.0,
        top_elevation: float = 3000.0,
        start_point: Tuple[float, float] = (1000.0, 1000.0),
        end_point: Optional[Tuple[float, float]] = None,
        direction_angle_deg: float = 0.0,
        width: float = 1000.0,
        target_riser: float = 175.0,
        target_going: float = 280.0,
        max_riser: float = 190.0,
        min_going: float = 250.0,
        railings: bool = True,
        turn_direction: str = "left",  # "left" (+90) or "right" (-90) for L-shaped
        stairwell_margin: float = 50.0,
        provenance: str = "user_configured",
    ) -> StairGeometry:
        stair_type = stair_type.strip().lower()
        if stair_type not in cls.SUPPORTED_STAIR_TYPES:
            raise ValueError(f"Unsupported stair type '{stair_type}'. Supported: {sorted(cls.SUPPORTED_STAIR_TYPES)}")

        if width < 500.0:
            raise ValueError(f"Stair width {width} mm is below minimum permitted 500 mm.")

        total_rise = top_elevation - base_elevation
        if total_rise <= 0:
            raise ValueError(f"Top elevation ({top_elevation}) must be strictly greater than base elevation ({base_elevation}).")

        n_risers, actual_riser, n_treads, actual_going = cls.calculate_risers_and_treads(
            total_rise=total_rise,
            target_riser=target_riser,
            target_going=target_going,
            max_riser=max_riser,
            min_going=min_going,
        )

        p0 = (float(start_point[0]), float(start_point[1]))

        # Calculate unit direction vector
        if end_point is not None:
            dx = float(end_point[0]) - p0[0]
            dy = float(end_point[1]) - p0[1]
            dist = math.hypot(dx, dy)
            if dist < 1e-3:
                raise ValueError("Start and end points cannot be coincident.")
            ux, uy = dx / dist, dy / dist
        else:
            rad = math.radians(direction_angle_deg)
            ux, uy = math.cos(rad), math.sin(rad)

        # Perpendicular normal vector (left-hand side)
        nx, ny = -uy, ux

        landings: List[Dict[str, Any]] = []

        if stair_type == "straight":
            total_run = n_treads * actual_going
            # Calculated end point is at the top riser
            p1 = (p0[0] + total_run * ux, p0[1] + total_run * uy)
            climb_angle = math.degrees(math.atan2(total_rise, total_run)) if total_run > 0 else 90.0

            # Stairwell opening polygon covers stair flight + small margin
            # Bounding box along the flight corridor
            hw = width / 2.0 + stairwell_margin
            # Start margin along length
            p_start_left = (p0[0] - stairwell_margin * ux + hw * nx, p0[1] - stairwell_margin * uy + hw * ny)
            p_start_right = (p0[0] - stairwell_margin * ux - hw * nx, p0[1] - stairwell_margin * uy - hw * ny)
            p_end_right = (p1[0] + stairwell_margin * ux - hw * nx, p1[1] + stairwell_margin * uy - hw * ny)
            p_end_left = (p1[0] + stairwell_margin * ux + hw * nx, p1[1] + stairwell_margin * uy + hw * ny)

            stairwell_poly = Polygon([p_start_left, p_start_right, p_end_right, p_end_left])
            stairwell_boundary = [p_start_left, p_start_right, p_end_right, p_end_left]

        elif stair_type == "l_shaped":
            # Quarter landing at mid-rise
            n1_risers = max(1, n_risers // 2)
            n2_risers = n_risers - n1_risers
            n1_treads = n1_risers - 1
            n2_treads = n2_risers - 1

            turn_deg = 90.0 if turn_direction.lower() in ("left", "+90", "ccw") else -90.0
            turn_sign = 1.0 if turn_deg > 0 else -1.0

            run1 = n1_treads * actual_going
            landing_elev = base_elevation + n1_risers * actual_riser
            landings = [{
                "atRiser": n1_risers,
                "turnDegrees": turn_deg,
                "elevation": round(landing_elev, 2),
                "dimensions": [round(width, 2), round(width, 2)],
            }]

            # Flight 2 runs perpendicular
            vx, vy = -uy * turn_sign, ux * turn_sign
            run2 = n2_treads * actual_going
            total_run = run1 + width + run2
            climb_angle = math.degrees(math.atan2(total_rise, total_run)) if total_run > 0 else 45.0

            # Intermediate landing center: p0 + (run1 + width/2) * u
            # Flight 2 top end point: landing center + (width/2) * u + (run2) * v
            landing_center = (p0[0] + (run1 + width / 2.0) * ux, p0[1] + (run1 + width / 2.0) * uy)
            p1 = (landing_center[0] + run2 * vx, landing_center[1] + run2 * vy)

            # Construct L-shaped stairwell boundary using union of two flight boxes
            box1 = LineString([
                (p0[0] - stairwell_margin * ux, p0[1] - stairwell_margin * uy),
                (p0[0] + (run1 + width + stairwell_margin) * ux, p0[1] + (run1 + width + stairwell_margin) * uy)
            ]).buffer(width / 2.0 + stairwell_margin, cap_style=3)

            box2 = LineString([
                (landing_center[0], landing_center[1]),
                (p1[0] + stairwell_margin * vx, p1[1] + stairwell_margin * vy)
            ]).buffer(width / 2.0 + stairwell_margin, cap_style=3)

            stairwell_poly = unary_union([box1, box2])
            if hasattr(stairwell_poly, "exterior"):
                coords = list(stairwell_poly.exterior.coords)[:-1]
            else:
                coords = list(stairwell_poly.envelope.exterior.coords)[:-1]
            stairwell_boundary = [(float(c[0]), float(c[1])) for c in coords]

        elif stair_type == "u_shaped":
            # Half landing at mid-rise (dog-leg)
            n1_risers = max(1, n_risers // 2)
            n2_risers = n_risers - n1_risers
            n1_treads = n1_risers - 1
            n2_treads = n2_risers - 1

            well_gap = 100.0  # gap between parallel flights
            landing_depth = width
            landing_width = 2 * width + well_gap
            landing_elev = base_elevation + n1_risers * actual_riser

            landings = [{
                "atRiser": n1_risers,
                "turnDegrees": 180.0,
                "elevation": round(landing_elev, 2),
                "dimensions": [round(landing_width, 2), round(landing_depth, 2)],
            }]

            run1 = n1_treads * actual_going
            run2 = n2_treads * actual_going
            total_run = max(run1, run2) + landing_depth
            climb_angle = math.degrees(math.atan2(total_rise, run1 + landing_depth + run2)) if (run1 + run2) > 0 else 45.0

            # Flight 1 goes p0 -> landing
            # Flight 2 returns parallel in opposite direction: -ux, -uy, shifted by (width + well_gap) in normal direction nx, ny
            lateral_shift = width + well_gap
            p1 = (p0[0] + (run1 - run2) * ux + lateral_shift * nx, p0[1] + (run1 - run2) * uy + lateral_shift * ny)

            # Construct U-shaped bounding stairwell box
            box_flight1 = LineString([
                (p0[0] - stairwell_margin * ux, p0[1] - stairwell_margin * uy),
                (p0[0] + (run1 + landing_depth + stairwell_margin) * ux, p0[1] + (run1 + landing_depth + stairwell_margin) * uy)
            ]).buffer(width / 2.0 + stairwell_margin, cap_style=3)

            box_flight2 = LineString([
                (p0[0] + lateral_shift * nx - stairwell_margin * ux, p0[1] + lateral_shift * ny - stairwell_margin * uy),
                (p0[0] + lateral_shift * nx + (run1 + landing_depth + stairwell_margin) * ux, p0[1] + lateral_shift * ny + (run1 + landing_depth + stairwell_margin) * uy)
            ]).buffer(width / 2.0 + stairwell_margin, cap_style=3)

            stairwell_poly = unary_union([box_flight1, box_flight2])
            if hasattr(stairwell_poly, "exterior"):
                coords = list(stairwell_poly.exterior.coords)[:-1]
            else:
                coords = list(stairwell_poly.envelope.exterior.coords)[:-1]
            stairwell_boundary = [(float(c[0]), float(c[1])) for c in coords]

        # Calculate exact area of stairwell void
        stairwell_area_m2 = stairwell_poly.area / 1_000_000.0

        # Calculate nominal headroom clearance: vertical distance under upper floor slab
        # Assuming typical 200 mm floor slab thickness
        floor_slab_thickness = 200.0
        headroom_clearance = max(2000.0, total_rise - floor_slab_thickness)

        return StairGeometry(
            id=stair_id,
            stair_type=stair_type,
            level_id=level_id,
            top_level_id=top_level_id,
            base_elevation=base_elevation,
            top_elevation=top_elevation,
            total_rise=total_rise,
            start=p0,
            end=p1,
            width=width,
            riser_count=n_risers,
            actual_riser_height=actual_riser,
            tread_count=n_treads,
            actual_going=actual_going,
            total_run=round(total_run, 2),
            climb_angle_deg=round(climb_angle, 2),
            landings=landings,
            railings=railings,
            headroom_clearance=round(headroom_clearance, 2),
            stairwell_boundary=stairwell_boundary,
            stairwell_area_m2=round(stairwell_area_m2, 2),
            provenance=provenance,
            confidence="high",
            approval_status="pending",
        )

    @classmethod
    def punch_stairwell_opening_into_floors(
        cls,
        floors: List[Dict[str, Any]],
        staircases: List[Dict[str, Any]] | List[StairGeometry],
    ) -> List[Dict[str, Any]]:
        """Punches stairwell openings into floor slabs of destination (upper) levels.

        Returns updated floor list with 'openings' list populated.
        """
        stair_list = [s.to_dict() if isinstance(s, StairGeometry) else s for s in staircases]
        if not stair_list:
            return floors

        updated_floors = []
        for fl in floors:
            fl_copy = dict(fl)
            fl_level = fl_copy.get("levelId")
            existing_openings = list(fl_copy.get("openings", []))

            for st in stair_list:
                top_lvl = st.get("topLevelId")
                # If this floor matches the destination upper level of the staircase
                if fl_level in (top_lvl, f"level_{top_lvl.replace('Level ', '')}" if "Level " in top_lvl else top_lvl):
                    stairwell = st.get("stairwellBoundary")
                    if stairwell and len(stairwell) >= 3:
                        # Add polygon to openings if not already present
                        poly_pts = [[round(p[0], 2), round(p[1], 2)] for p in stairwell]
                        if poly_pts not in existing_openings:
                            existing_openings.append(poly_pts)

            fl_copy["openings"] = existing_openings
            updated_floors.append(fl_copy)

        return updated_floors

    @classmethod
    def detect_stairs_from_lines(
        cls,
        stair_lines: List[Any],
        level_id: str = "Level 1",
        top_level_id: str = "Level 2",
        base_elevation: float = 0.0,
        top_elevation: float = 3000.0,
    ) -> Optional[StairGeometry]:
        """Detects staircase candidate geometry from 2D DXF linework on stair layers."""
        if not stair_lines or len(stair_lines) < 2:
            return None

        # Collect all points
        all_pts = []
        for l in stair_lines:
            all_pts.append((l.start[0], l.start[1]))
            all_pts.append((l.end[0], l.end[1]))

        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        dx = max_x - min_x
        dy = max_y - min_y

        if dx < 600 and dy < 600:
            return None

        # Determine dominant direction: if dx > dy, runs along X; else runs along Y
        if dx >= dy:
            width = min(dy, 1200.0)
            mid_y = (min_y + max_y) / 2.0
            start_pt = (min_x, mid_y)
            end_pt = (max_x, mid_y)
            angle = 0.0
        else:
            width = min(dx, 1200.0)
            mid_x = (min_x + max_x) / 2.0
            start_pt = (mid_x, min_y)
            end_pt = (mid_x, max_y)
            angle = 90.0

        return cls.generate_stair(
            stair_id="stair_dxf_1",
            stair_type="straight",
            level_id=level_id,
            top_level_id=top_level_id,
            base_elevation=base_elevation,
            top_elevation=top_elevation,
            start_point=start_pt,
            end_point=end_pt,
            direction_angle_deg=angle,
            width=max(800.0, width),
            provenance="dxf_detected",
        )

