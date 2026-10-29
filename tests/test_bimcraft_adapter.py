"""Tests for BIMCraft adapter command building and execution."""

import pytest
from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall
from dxf_to_3d_bim.opening_detection import ReconstructedOpening
from dxf_to_3d_bim.room_detection import FloorSlab

def test_build_commands_translation():
    adapter = BimcraftAdapter()
    walls = [
        ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(6000, 0), thickness=200, height=3200)
    ]
    openings = [
        ReconstructedOpening(id="d1", type="door", wall_id="w1", center=(3000, 0), width=900, height=2100),
        ReconstructedOpening(id="w1_op", type="window", wall_id="w1", center=(1500, 0), width=1200, height=1200, sill_height=950),
    ]
    floors = [
        FloorSlab(id="fl1", level_id="Level 1", thickness=150, elevation=0, boundary=[(0, 0), (6000, 0), (6000, 4000), (0, 4000)])
    ]
    model = IntermediateBimModel.create("BimcraftTest", "test.dxf", "mm", 1.0, walls, openings, floors, [])

    cmds = adapter.build_commands(model)

    cmd_ids = [c[0] for c in cmds]
    assert "wall" in cmd_ids
    assert "floor" in cmd_ids
    assert "door" in cmd_ids
    assert "window" in cmd_ids

    # Check wall params
    wall_cmd = next(c for c in cmds if c[0] == "wall")
    assert wall_cmd[1]["points"] == [[0, 0], [6000, 0]]
    assert wall_cmd[1]["height"] == 3200.0

    # Check window sill
    win_cmd = next(c for c in cmds if c[0] == "window")
    assert win_cmd[1]["sill"] == 950.0

def test_approval_enforced_before_build(tmp_path):
    adapter = BimcraftAdapter()
    walls = [ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(6000, 0), thickness=200)]
    model = IntermediateBimModel.create("UnapprovedTest", "test.dxf", "mm", 1.0, walls, [], [], [])

    # Must raise PermissionError if model is unapproved
    with pytest.raises(PermissionError):
        adapter.execute_build(model, output_dir=tmp_path)
