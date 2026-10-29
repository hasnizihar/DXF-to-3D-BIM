"""Tests for opening detection and host wall projection."""

import pytest
from dxf_to_3d_bim.dxf_parser import LineSegment, ArcEntity
from dxf_to_3d_bim.opening_detection import OpeningDetector
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall

def test_door_arc_hosting():
    detector = OpeningDetector()
    wall = ReconstructedWall(
        id="wall_1",
        classification="exterior",
        start=(0.0, 0.0),
        end=(6000.0, 0.0),
        thickness=200.0,
    )

    arc = ArcEntity(
        id="arc_door",
        layer="A-DOOR",
        center=(2500.0, 0.0),
        radius=900.0,
        start_angle_deg=0.0,
        end_angle_deg=90.0,
    )

    openings, unhosted = detector.detect_openings([], [arc], [wall])
    assert len(openings) == 1
    assert len(unhosted) == 0
    op = openings[0]
    assert op.type == "door"
    assert op.wall_id == "wall_1"
    assert op.width == 900.0
    assert op.height == 2100.0

def test_window_line_hosting():
    detector = OpeningDetector()
    wall = ReconstructedWall(
        id="wall_2",
        classification="exterior",
        start=(6000.0, 0.0),
        end=(6000.0, 4000.0),
        thickness=200.0,
    )

    win_line = LineSegment(
        id="win_line",
        layer="A-GLAZ",
        start=(6000.0, 1400.0),
        end=(6000.0, 2600.0),
        length=1200.0,
    )

    openings, unhosted = detector.detect_openings([win_line], [], [wall])
    assert len(openings) == 1
    op = openings[0]
    assert op.type == "window"
    assert op.wall_id == "wall_2"
    assert op.width == 1200.0
    assert op.sill_height == 900.0
