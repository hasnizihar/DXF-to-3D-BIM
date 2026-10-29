"""Tests for wall geometry reconstruction and centerline pairing."""

import pytest
from dxf_to_3d_bim.dxf_parser import LineSegment
from dxf_to_3d_bim.wall_reconstruction import WallReconstructor

def test_pair_parallel_lines():
    rec = WallReconstructor()
    # 2 parallel horizontal lines 200mm apart
    l1 = LineSegment(id="line_1", layer="A-WALL-EXTR", start=(0, 0), end=(5000, 0), length=5000.0)
    l2 = LineSegment(id="line_2", layer="A-WALL-EXTR", start=(0, 200), end=(5000, 200), length=5000.0)

    walls = rec.reconstruct([l1, l2])
    assert len(walls) == 1
    w = walls[0]
    assert w.classification == "exterior"
    assert w.thickness == 200.0
    assert pytest.approx(w.start[1], 0.1) == 100.0  # Centerline y = 100
    assert pytest.approx(w.end[1], 0.1) == 100.0
    assert "line_1" in w.source_entities
    assert "line_2" in w.source_entities

def test_single_line_wall():
    rec = WallReconstructor()
    l = LineSegment(id="line_single", layer="A-WALL-INTR", start=(1000, 0), end=(1000, 3000), length=3000.0)
    walls = rec.reconstruct([l])
    assert len(walls) == 1
    assert walls[0].classification == "interior"
    assert walls[0].thickness == 100.0  # Default interior thickness
