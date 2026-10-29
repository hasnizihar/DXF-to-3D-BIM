"""Tests for Milestone 9: visual verification, 3D rendering, and geometry comparison."""

import pytest
from pathlib import Path
from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter
from dxf_to_3d_bim.comparison import SourceToBimComparator
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.reporting import ReviewSummaryGenerator
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall
from tests.create_fixtures import create_synthetic_room_dxf

def test_source_to_bim_comparison_and_overlay(tmp_path):
    dxf_file = tmp_path / "comp_room.dxf"
    create_synthetic_room_dxf(dxf_file)

    # 4 walls: 6000 x 4000
    walls = [
        ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(6000, 0), thickness=200),
        ReconstructedWall(id="w2", classification="exterior", start=(6000, 0), end=(6000, 4000), thickness=200),
        ReconstructedWall(id="w3", classification="exterior", start=(6000, 4000), end=(0, 4000), thickness=200),
        ReconstructedWall(id="w4", classification="exterior", start=(0, 4000), end=(0, 0), thickness=200),
    ]
    model = IntermediateBimModel.create("CompTest", str(dxf_file), "mm", 1.0, walls, [], [], [])

    comparator = SourceToBimComparator()
    overlay_img = tmp_path / "overlay.png"
    report = comparator.compare(dxf_file, model, output_image_path=overlay_img)

    assert report.overall_status == "PASSED"
    assert report.footprint_deviation["width"].status == "PASSED"
    assert report.footprint_deviation["depth"].status == "PASSED"
    assert overlay_img.exists()
    assert overlay_img.stat().st_size > 1000

def test_3d_views_and_elevations_generation(tmp_path):
    adapter = BimcraftAdapter()
    assert adapter.is_available()

    walls = [
        ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(6000, 0), thickness=200),
        ReconstructedWall(id="w2", classification="exterior", start=(6000, 0), end=(6000, 4000), thickness=200),
        ReconstructedWall(id="w3", classification="exterior", start=(6000, 4000), end=(0, 4000), thickness=200),
        ReconstructedWall(id="w4", classification="exterior", start=(0, 4000), end=(0, 0), thickness=200),
    ]
    model = IntermediateBimModel.create("ViewsTest", "v.dxf", "mm", 1.0, walls, [], [], [])
    ApprovalGate.approve(model)

    res = adapter.execute_build(model, output_dir=tmp_path, base_name="views_test", generate_3d_views=True)

    assert res.success
    assert res.view_3d_path.exists()
    assert res.view_3d_path.stat().st_size > 5000
    assert res.elevation_south_path.exists()
    assert res.elevation_south_path.stat().st_size > 5000
    assert res.section_path.exists()
    assert res.section_path.stat().st_size > 5000

    # Test Review Summary Generator
    validator = ModelValidator(adapter)
    val_report = validator.validate(model, res)
    md = ReviewSummaryGenerator.generate_markdown(model, val_report, build_result=res)
    assert "# BIM Review & Visual Verification Summary" in md
    assert "3D Axonometric Render:" in md

