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
            # Center of the opening is offset from the hinge by radius / 2
            center_x = arc.center[0]
            center_y = arc.center[1]

            host_wall, proj_pt, offset, dist = self._find_host_wall((center_x, center_y), walls)
            if host_wall and dist <= self.host_snap_tolerance:
                op = ReconstructedOpening(
                    id=f"door_{counter}",
                    type="door",
                    wall_id=host_wall.id,
                    center=(round(proj_pt[0], 2), round(proj_pt[1], 2)),
                    width=round(width, 2) if width > 200 else self.default_door_width,
                    height=self.default_door_height,
                    offset_along_wall=round(offset, 2),
                    swing="single",
                    confidence="high",
                    source_entities=[arc.id],
                )
                openings.append(op)
                processed_door_locations.append(proj_pt)
                counter += 1
            else:
                unhosted.append({"type": "door", "source": arc.id, "position": [center_x, center_y]})

        # 2. Process Door Lines (if not already captured by arc)
        door_lines = [l for l in lines if classifier.classify(l.layer) == "door"]
        for line in door_lines:
            mid = ((line.start[0] + line.end[0]) / 2.0, (line.start[1] + line.end[1]) / 2.0)
            # Avoid duplicate if near processed arc door
            if any(distance_point_to_point(mid, p) < 500 for p in processed_door_locations):
                continue

            host_wall, proj_pt, offset, dist = self._find_host_wall(mid, walls)
            if host_wall and dist <= self.host_snap_tolerance:
                width = line.length if line.length > 200 else self.default_door_width
                op = ReconstructedOpening(
                    id=f"door_{counter}",
                    type="door",
                    wall_id=host_wall.id,
                    center=(round(proj_pt[0], 2), round(proj_pt[1], 2)),
                    width=round(width, 2),
                    height=self.default_door_height,
                    offset_along_wall=round(offset, 2),
                    confidence="medium",
                    source_entities=[line.id],
                )
                openings.append(op)
                processed_door_locations.append(proj_pt)
                counter += 1

        # 3. Process Windows
        window_lines = [l for l in lines if classifier.classify(l.layer) == "window"]
        processed_window_locations: List[Tuple[float, float]] = []

        for line in window_lines:
            mid = ((line.start[0] + line.end[0]) / 2.0, (line.start[1] + line.end[1]) / 2.0)
            if any(distance_point_to_point(mid, p) < 400 for p in processed_window_locations):
                continue

            host_wall, proj_pt, offset, dist = self._find_host_wall(mid, walls)
            if host_wall and dist <= self.host_snap_tolerance:
                width = line.length if line.length > 200 else self.default_window_width
                op = ReconstructedOpening(
                    id=f"window_{counter}",
                    type="window",
                    wall_id=host_wall.id,
                    center=(round(proj_pt[0], 2), round(proj_pt[1], 2)),
                    width=round(width, 2),
                    height=self.default_window_height,
                    sill_height=self.default_window_sill_height,
                    offset_along_wall=round(offset, 2),
                    confidence="high",
                    source_entities=[line.id],
                )
                openings.append(op)
                processed_window_locations.append(proj_pt)
                counter += 1
            else:
                unhosted.append({"type": "window", "source": line.id, "position": [mid[0], mid[1]]})

        return openings, unhosted

    def _find_host_wall(
        self,
        pt: Tuple[float, float],
        walls: List[ReconstructedWall],
    ) -> Tuple[Optional[ReconstructedWall], Tuple[float, float], float, float]:
        best_wall = None
        best_proj = pt
        best_offset = 0.0
        best_dist = float("inf")

        for w in walls:
            proj, dist, offset = project_point_onto_segment(pt, w.start, w.end)
            if dist < best_dist:
                best_dist = dist
                best_wall = w
                best_proj = proj
                best_offset = offset

        return best_wall, best_proj, best_offset, best_dist

