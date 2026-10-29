"""Tests for validation logic and validation report generation."""

import pytest
from pathlib import Path
from dxf_to_3d_bim.bimcraft_adapter import BimcraftBuildResult
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall

def test_validator_detects_missing_files(tmp_path):
    validator = ModelValidator()
    walls = [ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(5000, 0), thickness=200)]
    model = IntermediateBimModel.create("ValTest", "t.dxf", "mm", 1.0, walls, [], [], [])

    dummy_result = BimcraftBuildResult(
        success=True,
        bimcraft_path=tmp_path / "nonexistent.bimcraft",
        ifc_path=tmp_path / "nonexistent.ifc",
        png_path=tmp_path / "nonexistent.png",
    )

    report = validator.validate(model, dummy_result)
    assert report["overallStatus"] == "FAILED"
    assert any("not found on disk" in c["details"] for c in report["checks"])

