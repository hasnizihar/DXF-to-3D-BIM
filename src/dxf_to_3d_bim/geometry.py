"""Geometric helper functions using Shapely and math for CAD/BIM reconstruction."""

import math
from typing import Tuple, List, Optional
from shapely.geometry import Point, LineString, Polygon


def distance_point_to_point(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


def segment_angle_deg(start: Tuple[float, float], end: Tuple[float, float]) -> float:
    """Returns angle in degrees [0, 360)."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    deg = math.degrees(math.atan2(dy, dx))
    return deg % 360.0


def are_lines_parallel(
    s1: Tuple[float, float], e1: Tuple[float, float],
    s2: Tuple[float, float], e2: Tuple[float, float],
    angle_tolerance_deg: float = 2.0
) -> bool:
    a1 = segment_angle_deg(s1, e1) % 180.0
    a2 = segment_angle_deg(s2, e2) % 180.0
    diff = abs(a1 - a2)
    return diff <= angle_tolerance_deg or abs(diff - 180.0) <= angle_tolerance_deg


def project_point_onto_segment(
    pt: Tuple[float, float], start: Tuple[float, float], end: Tuple[float, float]
) -> Tuple[Tuple[float, float], float, float]:
    """Projects point onto segment. Returns (projected_point, distance, offset_from_start)."""
    line = LineString([start, end])
    point = Point(pt)
    dist = line.distance(point)
    offset = line.project(point)
    proj_pt = line.interpolate(offset)
    return ((proj_pt.x, proj_pt.y), dist, offset)


def snap_point(pt: Tuple[float, float], reference_points: List[Tuple[float, float]], tolerance: float = 25.0) -> Tuple[float, float]:
    for ref in reference_points:
        if distance_point_to_point(pt, ref) <= tolerance:
            return ref
    return pt

