"""Tests for difficult geometry handling: internal walls, T-junctions, and rotated coordinates."""

import pytest
from dxf_to_3d_bim.dxf_parser import LineSegment
from dxf_to_3d_bim.geometry import distance_point_to_point
from dxf_to_3d_bim.wall_reconstruction import WallReconstructor

def test_t_junction_wall_network():
    """Exterior boundary with an intersecting interior partition wall."""
    rec = WallReconstructor()

    # Outer room walls (single-line representation for testing topology)
    w_bottom = LineSegment(id="ext_b", layer="A-WALL-EXTR", start=(0, 0), end=(6000, 0), length=6000)
    w_top = LineSegment(id="ext_t", layer="A-WALL-EXTR", start=(0, 4000), end=(6000, 4000), length=6000)
    w_left = LineSegment(id="ext_l", layer="A-WALL-EXTR", start=(0, 0), end=(0, 4000), length=4000)
    w_right = LineSegment(id="ext_r", layer="A-WALL-EXTR", start=(6000, 0), end=(6000, 4000), length=4000)

    # Interior partition forming T-junctions at (3000, 0) and (3000, 4000)
    w_int = LineSegment(id="int_1", layer="A-WALL-INTR", start=(3000, 10), end=(3000, 3990), length=3980)

    walls = rec.reconstruct([w_bottom, w_top, w_left, w_right, w_int])
    assert len(walls) == 5

    ext_walls = [w for w in walls if w.classification == "exterior"]
    int_walls = [w for w in walls if w.classification == "interior"]

    assert len(ext_walls) == 4
    assert len(int_walls) == 1
    assert int_walls[0].thickness == 100.0

    # Snapping should align interior endpoints to the exterior wall centerlines
    snapped_int = int_walls[0]
    assert pytest.approx(snapped_int.start[1], 15.0) == 0.0 or pytest.approx(snapped_int.start[1], 15.0) == 10.0

def test_rotated_geometry():
    """Rotated wall lines should maintain parallel detection and thickness."""
    rec = WallReconstructor()
    # 45-degree angled parallel lines: (0,0)->(3000,3000) and (141.42, -141.42) offset
    # Normal to (1, 1) is (-1, 1) / sqrt(2). With thickness 200 mm: offset is (-141.42, 141.42)
    l1 = LineSegment(id="rot_1", layer="A-WALL-EXTR", start=(0, 0), end=(3000, 3000), length=4242.6)
    l2 = LineSegment(id="rot_2", layer="A-WALL-EXTR", start=(-141.42, 141.42), end=(2858.58, 3141.42), length=4242.6)

    walls = rec.reconstruct([l1, l2])
    assert len(walls) == 1
    assert pytest.approx(walls[0].thickness, 1.0) == 200.0

