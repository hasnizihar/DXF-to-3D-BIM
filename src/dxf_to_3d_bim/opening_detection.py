"""Opening detection module for identifying doors and windows and hosting them onto walls."""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

from dxf_to_3d_bim.dxf_parser import LineSegment, ArcEntity
from dxf_to_3d_bim.geometry import (
    distance_point_to_point,
    project_point_onto_segment,
)
from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall


@dataclass
class ReconstructedOpening:
    id: str
    type: str  # "door" or "window"
    wall_id: str
    center: Tuple[float, float]
    width: float
    height: float
    sill_height: Optional[float] = None
    offset_along_wall: float = 0.0
    swing: Optional[str] = None
    confidence: str = "high"
    source_entities: List[str] = field(default_factory=list)


class OpeningDetector:
    """Detects doors and windows and projects them onto host wall centerlines."""

    def __init__(
        self,
        default_door_width: float = 900.0,
        default_door_height: float = 2100.0,
        default_window_width: float = 1200.0,
        default_window_height: float = 1200.0,
        default_window_sill_height: float = 900.0,
        host_snap_tolerance: float = 350.0,
    ):
        self.default_door_width = default_door_width
        self.default_door_height = default_door_height
        self.default_window_width = default_window_width
        self.default_window_height = default_window_height
        self.default_window_sill_height = default_window_sill_height
        self.host_snap_tolerance = host_snap_tolerance

    def detect_openings(
        self,
        lines: List[LineSegment],
        arcs: List[ArcEntity],
        walls: List[ReconstructedWall],
        classifier: Optional[LayerClassifier] = None,
    ) -> Tuple[List[ReconstructedOpening], List[Dict[str, Any]]]:
        if classifier is None:
            classifier = LayerClassifier()

        openings: List[ReconstructedOpening] = []
        unhosted: List[Dict[str, Any]] = []
        counter = 1

        # 1. Process Door Arcs (swings)
        door_arcs = [a for a in arcs if classifier.classify(a.layer) == "door"]
        processed_door_locations: List[Tuple[float, float]] = []

        for arc in door_arcs:
            width = arc.radius
            eff_width = round(width, 2) if width > 200 else self.default_door_width
            half_w = max(460.0, eff_width / 2.0)
            req_len = 2.0 * half_w

            center_x = arc.center[0]
            center_y = arc.center[1]

            host_wall, proj_pt, offset, dist = self._find_host_wall((center_x, center_y), walls, required_length=req_len)
            if host_wall and dist <= self.host_snap_tolerance:
                # Clamp center to fit strictly inside wall segment
                clamped_offset = max(half_w, min(host_wall.length - half_w, offset))
                t = clamped_offset / host_wall.length if host_wall.length > 0 else 0.0
                cx = host_wall.start[0] + t * (host_wall.end[0] - host_wall.start[0])
                cy = host_wall.start[1] + t * (host_wall.end[1] - host_wall.start[1])

                op = ReconstructedOpening(
                    id=f"door_{counter}",
                    type="door",
                    wall_id=host_wall.id,
                    center=(round(cx, 2), round(cy, 2)),
                    width=eff_width,
                    height=self.default_door_height,
                    offset_along_wall=round(clamped_offset, 2),
                    swing="single",
                    confidence="high",
                    source_entities=[arc.id],
                )
                openings.append(op)
                processed_door_locations.append((cx, cy))
                counter += 1
            else:
                unhosted.append({"type": "door", "source": arc.id, "position": [center_x, center_y]})

        # 2. Process Door Lines (if not already captured by arc)
        door_lines = [l for l in lines if classifier.classify(l.layer) == "door"]
        for line in door_lines:
            mid = ((line.start[0] + line.end[0]) / 2.0, (line.start[1] + line.end[1]) / 2.0)
            if any(distance_point_to_point(mid, p) < 500 for p in processed_door_locations):
                continue

            eff_width = line.length if line.length > 200 else self.default_door_width
            half_w = max(460.0, eff_width / 2.0)
            req_len = 2.0 * half_w

            host_wall, proj_pt, offset, dist = self._find_host_wall(mid, walls, required_length=req_len)
            if host_wall and dist <= self.host_snap_tolerance:
                clamped_offset = max(half_w, min(host_wall.length - half_w, offset))
                t = clamped_offset / host_wall.length if host_wall.length > 0 else 0.0
                cx = host_wall.start[0] + t * (host_wall.end[0] - host_wall.start[0])
                cy = host_wall.start[1] + t * (host_wall.end[1] - host_wall.start[1])

                op = ReconstructedOpening(
                    id=f"door_{counter}",
                    type="door",
                    wall_id=host_wall.id,
                    center=(round(cx, 2), round(cy, 2)),
                    width=round(eff_width, 2),
                    height=self.default_door_height,
                    offset_along_wall=round(clamped_offset, 2),
                    confidence="medium",
                    source_entities=[line.id],
                )
                openings.append(op)
                processed_door_locations.append((cx, cy))
                counter += 1

        # 3. Process Windows
        window_lines = [l for l in lines if classifier.classify(l.layer) == "window"]
        processed_window_locations: List[Tuple[float, float]] = []

        for line in window_lines:
            mid = ((line.start[0] + line.end[0]) / 2.0, (line.start[1] + line.end[1]) / 2.0)
            if any(distance_point_to_point(mid, p) < 400 for p in processed_window_locations):
                continue

            eff_width = line.length if line.length > 200 else self.default_window_width
            half_w = max(610.0, eff_width / 2.0)
            req_len = 2.0 * half_w

            host_wall, proj_pt, offset, dist = self._find_host_wall(mid, walls, required_length=req_len)
            if host_wall and dist <= self.host_snap_tolerance:
                clamped_offset = max(half_w, min(host_wall.length - half_w, offset))
                t = clamped_offset / host_wall.length if host_wall.length > 0 else 0.0
                cx = host_wall.start[0] + t * (host_wall.end[0] - host_wall.start[0])
                cy = host_wall.start[1] + t * (host_wall.end[1] - host_wall.start[1])

                op = ReconstructedOpening(
                    id=f"window_{counter}",
                    type="window",
                    wall_id=host_wall.id,
                    center=(round(cx, 2), round(cy, 2)),
                    width=round(eff_width, 2),
                    height=self.default_window_height,
                    sill_height=self.default_window_sill_height,
                    offset_along_wall=round(clamped_offset, 2),
                    confidence="high",
                    source_entities=[line.id],
                )
                openings.append(op)
                processed_window_locations.append((cx, cy))
                counter += 1
            else:
                unhosted.append({"type": "window", "source": line.id, "position": [mid[0], mid[1]]})

        # 4. Deduplicate overlapping openings on the same host wall
        clean_openings = self._deduplicate_overlapping_openings(openings, walls)

        return clean_openings, unhosted

    def _deduplicate_overlapping_openings(
        self,
        openings: List[ReconstructedOpening],
        walls: List[ReconstructedWall],
    ) -> List[ReconstructedOpening]:
        """Ensures openings hosted on the same wall do not collide or overlap in 3D BIM."""
        by_wall: Dict[str, List[ReconstructedOpening]] = {}
        for op in openings:
            by_wall.setdefault(op.wall_id, []).append(op)

        wall_dict = {w.id: w for w in walls}
        deduped: List[ReconstructedOpening] = []

        for wid, wall_ops in by_wall.items():
            hw = wall_dict.get(wid)
            if not hw:
                continue
            wall_ops.sort(key=lambda x: x.offset_along_wall)
            kept: List[ReconstructedOpening] = []
            for op in wall_ops:
                min_half = 460.0 if op.type == "door" else 610.0
                half_w = max(min_half, op.width / 2.0)
                if kept:
                    prev = kept[-1]
                    prev_half = max(460.0 if prev.type == "door" else 610.0, prev.width / 2.0)
                    if op.offset_along_wall - prev.offset_along_wall < (half_w + prev_half + 50.0):
                        continue  # Overlaps with previous opening on same wall
                kept.append(op)
            deduped.extend(kept)

        return deduped

    def _find_host_wall(
        self,
        pt: Tuple[float, float],
        walls: List[ReconstructedWall],
        required_length: float = 0.0,
    ) -> Tuple[Optional[ReconstructedWall], Tuple[float, float], float, float]:
        best_wall = None
        best_proj = pt
        best_offset = 0.0
        best_dist = float("inf")

        for w in walls:
            if w.length < required_length:
                continue
            proj, dist, offset = project_point_onto_segment(pt, w.start, w.end)
            if dist < best_dist:
                best_dist = dist
                best_wall = w
                best_proj = proj
                best_offset = offset

        return best_wall, best_proj, best_offset, best_dist

