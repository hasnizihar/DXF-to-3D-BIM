"""Room and floor slab detection module."""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
from shapely.geometry import Polygon, MultiLineString, Point
from shapely.ops import polygonize, unary_union

from dxf_to_3d_bim.dxf_parser import TextEntity, LineSegment
from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall


@dataclass
class FloorSlab:
    id: str
    level_id: str
    thickness: float
    elevation: float
    boundary: List[Tuple[float, float]]


@dataclass
class RoomZone:
    id: str
    name: str
    level_id: str
    approximate_area: float
    label_position: Tuple[float, float]
    boundary: Optional[List[Tuple[float, float]]] = None


class SpatialDetector:
    """Detects floor slab boundaries and room zones from reconstructed walls and DXF texts."""

    def __init__(self, default_slab_thickness: float = 150.0):
        self.default_slab_thickness = default_slab_thickness

    def detect_slab(
        self,
        walls: List[ReconstructedWall],
        slab_lines: Optional[List[LineSegment]] = None,
    ) -> Optional[FloorSlab]:
        # If explicit slab lines provided, try forming polygon
        if slab_lines and len(slab_lines) >= 3:
            pts = []
            for l in slab_lines:
                pts.append(l.start)
            # Ensure closed
            if pts[0] != pts[-1]:
                pts.append(pts[0])
            poly = Polygon(pts)
            if poly.is_valid and poly.area > 1000.0:
                coords = [(round(p[0], 2), round(p[1], 2)) for p in poly.exterior.coords]
                return FloorSlab(
                    id="floor_1",
                    level_id="Level 1",
                    thickness=self.default_slab_thickness,
                    elevation=0.0,
                    boundary=coords[:-1],  # omit duplicate closing pt in schema array
                )

        # Fallback to outer perimeter from walls
        ext_walls = [w for w in walls if w.classification == "exterior"]
        target_walls = ext_walls if ext_walls else walls

        if not target_walls:
            return None

        # Build minimum bounding rectangle or convex hull from wall endpoints
        all_pts = []
        for w in target_walls:
            all_pts.append(w.start)
            all_pts.append(w.end)

        min_x = min(p[0] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_y = max(p[1] for p in all_pts)

        boundary = [
            (round(min_x, 2), round(min_y, 2)),
            (round(max_x, 2), round(min_y, 2)),
            (round(max_x, 2), round(max_y, 2)),
            (round(min_x, 2), round(max_y, 2)),
        ]

        return FloorSlab(
            id="floor_1",
            level_id="Level 1",
            thickness=self.default_slab_thickness,
            elevation=0.0,
            boundary=boundary,
        )

    def detect_rooms(
        self,
        texts: List[TextEntity],
        slab: Optional[FloorSlab] = None,
        classifier: Optional[LayerClassifier] = None,
    ) -> List[RoomZone]:
        if classifier is None:
            classifier = LayerClassifier()

        room_texts = [t for t in texts if classifier.classify(t.layer) == "annotation_text" or t.text]
        rooms: List[RoomZone] = []

        total_area = 0.0
        if slab and len(slab.boundary) >= 3:
            poly = Polygon(slab.boundary)
            total_area = round(poly.area / 1_000_000.0, 2)  # mm2 to m2

        counter = 1
        for t in room_texts:
            # Filter out numeric dimensions
            if t.text.replace(".", "").isdigit():
                continue
            rooms.append(
                RoomZone(
                    id=f"room_{counter}",
                    name=t.text,
                    level_id="Level 1",
                    approximate_area=total_area if len(room_texts) == 1 else round(total_area / len(room_texts), 2),
                    label_position=(round(t.position[0], 2), round(t.position[1], 2)),
                )
            )
            counter += 1

        return rooms

