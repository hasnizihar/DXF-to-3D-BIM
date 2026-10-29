"""Tests for error handling, recovery, and diagnostic reporting."""

import pytest
from pathlib import Path
from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter
from dxf_to_3d_bim.dxf_parser import DxfParser
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall

def test_missing_dxf_file():
    parser = DxfParser()
    with pytest.raises(FileNotFoundError) as exc_info:
        parser.inspect_file("nonexistent_drawing.dxf")
    assert "DXF file not found" in str(exc_info.value)

def test_missing_bimcraft_cli_path(tmp_path):
    adapter = BimcraftAdapter(cli_path=tmp_path / "fake_bimcraft.exe")
    assert not adapter.is_available()

    walls = [ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(5000, 0), thickness=200)]
    model = IntermediateBimModel.create("CLIErrorTest", "test.dxf", "mm", 1.0, walls, [], [], [])
    ApprovalGate.approve(model)

    with pytest.raises(FileNotFoundError) as exc_info:
        adapter.execute_build(model, output_dir=tmp_path)
    assert "BIMCraft CLI executable not found" in str(exc_info.value)

