"""Wall reconstruction module for converting 2D CAD linework into normalized BIM walls."""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
from shapely.geometry import LineString, MultiLineString
from shapely.ops import linemerge

from dxf_to_3d_bim.dxf_parser import LineSegment
from dxf_to_3d_bim.geometry import (
    distance_point_to_point,
    are_lines_parallel,
    project_point_onto_segment,
    snap_point,
)
from dxf_to_3d_bim.layer_classifier import LayerClassifier


@dataclass
class ReconstructedWall:
    id: str
    classification: str  # "exterior" or "interior"
    start: Tuple[float, float]
    end: Tuple[float, float]
    thickness: float
    height: float = 3000.0
    level_id: str = "Level 1"
    confidence: str = "high"
    source_entities: List[str] = field(default_factory=list)

    @property
    def length(self) -> float:
        return distance_point_to_point(self.start, self.end)

    @property
    def midpoint(self) -> Tuple[float, float]:
        return ((self.start[0] + self.end[0]) / 2.0, (self.start[1] + self.end[1]) / 2.0)


class WallReconstructor:
    """Reconstructs architectural wall centerlines and properties from 2D CAD lines."""

    def __init__(
        self,
        min_thickness: float = 60.0,
        max_thickness: float = 450.0,
        default_exterior_thickness: float = 200.0,
        default_interior_thickness: float = 100.0,
        default_height: float = 3000.0,
        endpoint_snap_tolerance: float = 50.0,
        min_wall_length: float = 100.0,
    ):
        self.min_thickness = min_thickness
        self.max_thickness = max_thickness
        self.default_exterior_thickness = default_exterior_thickness
        self.default_interior_thickness = default_interior_thickness
        self.default_height = default_height
        self.endpoint_snap_tolerance = endpoint_snap_tolerance
        self.min_wall_length = min_wall_length

    def reconstruct(
        self,
        lines: List[LineSegment],
        classifier: Optional[LayerClassifier] = None,
    ) -> List[ReconstructedWall]:
        if classifier is None:
            classifier = LayerClassifier()

        wall_lines = [l for l in lines if classifier.is_wall_layer(l.layer)]
        if not wall_lines:
            return []

        # Group by classification
        exterior_lines = [
            l for l in wall_lines if classifier.classify(l.layer) in ("exterior_wall", "generic_wall")
        ]
        interior_lines = [
            l for l in wall_lines if classifier.classify(l.layer) == "interior_wall"
        ]

        reconstructed: List[ReconstructedWall] = []
        wall_counter = 1

        # Process exterior walls
        ext_walls = self._reconstruct_group(exterior_lines, "exterior", self.default_exterior_thickness)
        for w in ext_walls:
            w.id = f"wall_{wall_counter}"
            wall_counter += 1
            reconstructed.append(w)

        # Process interior walls
        int_walls = self._reconstruct_group(interior_lines, "interior", self.default_interior_thickness)
        for w in int_walls:
            w.id = f"wall_{wall_counter}"
            wall_counter += 1
            reconstructed.append(w)

        # Snap junctions across all walls
        reconstructed = self._snap_wall_network(reconstructed)

        # Merge collinear segments separated by door/window opening breaks
        reconstructed = self._merge_collinear_walls(reconstructed)

        # Filter out degenerate or too-short wall segments (e.g. collapsed jamb lines)
        reconstructed = [w for w in reconstructed if w.length >= self.min_wall_length]

        # Re-index wall IDs cleanly
        for idx, w in enumerate(reconstructed, start=1):
            w.id = f"wall_{idx}"

        return reconstructed

    def _dist_point_to_infinite_line(self, pt: Tuple[float, float], s: Tuple[float, float], e: Tuple[float, float]) -> float:
        x0, y0 = pt
        x1, y1 = s
        x2, y2 = e
        dx, dy = x2 - x1, y2 - y1
        l = math.hypot(dx, dy)
        if l == 0:
            return distance_point_to_point(pt, s)
        return abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / l

    def _merge_collinear_walls(self, walls: List[ReconstructedWall], max_gap: float = 2200.0) -> List[ReconstructedWall]:
        """Merges collinear wall segments interrupted by door or window gaps."""
        filtered = [x for x in walls if x.length > 250.0]
        merged = list(filtered)
        changed = True
        while changed:
            changed = False
            n = len(merged)
            for i in range(n):
                if changed:
                    break
                for j in range(i + 1, n):
                    w1, w2 = merged[i], merged[j]
                    if w1.classification != w2.classification:
                        continue
                    if not are_lines_parallel(w1.start, w1.end, w2.start, w2.end):
                        continue
                    dist = self._dist_point_to_infinite_line(w2.start, w1.start, w1.end)
                    if dist > 35.0:
                        continue
                    d1 = distance_point_to_point(w1.end, w2.start)
                    d2 = distance_point_to_point(w1.start, w2.end)
                    d3 = distance_point_to_point(w1.start, w2.start)
                    d4 = distance_point_to_point(w1.end, w2.end)
                    if min(d1, d2, d3, d4) <= max_gap:
                        vx, vy = w1.end[0] - w1.start[0], w1.end[1] - w1.start[1]
                        vl = math.hypot(vx, vy)
                        if vl == 0:
                            continue
                        ux, uy = vx / vl, vy / vl
                        all_pts = [w1.start, w1.end, w2.start, w2.end]
                        projs = [(pt[0] * ux + pt[1] * uy, pt) for pt in all_pts]
                        projs.sort(key=lambda x: x[0])
                        w1.start = projs[0][1]
                        w1.end = projs[-1][1]
                        merged.pop(j)
                        changed = True
                        break
        return merged

    def _reconstruct_group(
        self,
        lines: List[LineSegment],
        classification: str,
        default_thickness: float,
    ) -> List[ReconstructedWall]:
        if not lines:
            return []

        # Try pairing parallel lines (double-line detection)
        paired_walls, consumed_indices = self._pair_parallel_lines(lines, classification)

        # Remaining unpaired lines treated as single-line centerlines
        for idx, line in enumerate(lines):
            if idx not in consumed_indices:
                paired_walls.append(
                    ReconstructedWall(
                        id="",
                        classification=classification,
                        start=line.start,
                        end=line.end,
                        thickness=default_thickness,
                        height=self.default_height,
                        confidence="medium",
                        source_entities=[line.id],
                    )
                )

        return paired_walls

    def _pair_parallel_lines(
        self,
        lines: List[LineSegment],
        classification: str,
    ) -> Tuple[List[ReconstructedWall], set]:
        paired: List[ReconstructedWall] = []
        consumed = set()

        n = len(lines)
        for i in range(n):
            if i in consumed:
                continue
            l1 = lines[i]

            best_pair_idx = None
            best_dist = float("inf")

            for j in range(i + 1, n):
                if j in consumed:
                    continue
                l2 = lines[j]

                # Check parallel
                if not are_lines_parallel(l1.start, l1.end, l2.start, l2.end):
                    continue

                # Measure distance between lines
                mid1 = ((l1.start[0] + l1.end[0]) / 2.0, (l1.start[1] + l1.end[1]) / 2.0)
                _, dist, _ = project_point_onto_segment(mid1, l2.start, l2.end)

                if self.min_thickness <= dist <= self.max_thickness:
                    if dist < best_dist:
                        best_dist = dist
                        best_pair_idx = j

            if best_pair_idx is not None:
                l2 = lines[best_pair_idx]
                consumed.add(i)
                consumed.add(best_pair_idx)

                # Compute centerline by averaging endpoints
                # Ensure same direction
                d_same = distance_point_to_point(l1.start, l2.start)
                d_cross = distance_point_to_point(l1.start, l2.end)
                if d_cross < d_same:
                    p2_start, p2_end = l2.end, l2.start
                else:
                    p2_start, p2_end = l2.start, l2.end

                c_start = ((l1.start[0] + p2_start[0]) / 2.0, (l1.start[1] + p2_start[1]) / 2.0)
                c_end = ((l1.end[0] + p2_end[0]) / 2.0, (l1.end[1] + p2_end[1]) / 2.0)

                paired.append(
                    ReconstructedWall(
                        id="",
                        classification=classification,
                        start=(round(c_start[0], 2), round(c_start[1], 2)),
                        end=(round(c_end[0], 2), round(c_end[1], 2)),
                        thickness=round(best_dist, 2),
                        height=self.default_height,
                        confidence="high",
                        source_entities=[l1.id, l2.id],
                    )
                )

        return paired, consumed

    def _snap_wall_network(self, walls: List[ReconstructedWall]) -> List[ReconstructedWall]:
        """Snaps endpoints of nearby walls to form clean corners and junctions."""
        if len(walls) < 2:
            return walls

        nodes: List[Tuple[float, float]] = []
        for w in walls:
            nodes.append(w.start)
            nodes.append(w.end)

        # Cluster nodes within snap tolerance
        clustered_nodes: List[Tuple[float, float]] = []
        for pt in nodes:
            found = False
            for c in clustered_nodes:
                if distance_point_to_point(pt, c) <= self.endpoint_snap_tolerance:
                    found = True
                    break
            if not found:
                clustered_nodes.append(pt)

        # Snap walls to clustered nodes
        for w in walls:
            w.start = snap_point(w.start, clustered_nodes, self.endpoint_snap_tolerance)
            w.end = snap_point(w.end, clustered_nodes, self.endpoint_snap_tolerance)

        return walls

