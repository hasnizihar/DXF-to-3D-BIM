"""Milestone 11 comprehensive test suite: Configurable Multi-Storey Building Reconstruction."""

import json
from pathlib import Path
import pytest
import ezdxf

from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter
from dxf_to_3d_bim.cli import reconstruct_dxf_model
from dxf_to_3d_bim.config import ProjectConfig, LevelsConfig
from dxf_to_3d_bim.dxf_parser import DxfParser, LineSegment, ArcEntity
from dxf_to_3d_bim.ifc_parser import PureIfcParser
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.opening_detection import ReconstructedOpening
from dxf_to_3d_bim.reporting import ReviewSummaryGenerator
from dxf_to_3d_bim.room_detection import FloorSlab
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall


def _create_sample_single_storey_elements():
    """Returns baseline walls, door, window, and slab for a 6000 x 4000 mm room."""
    walls = [
        ReconstructedWall(id="wall_1", classification="exterior", start=(0.0, 0.0), end=(6000.0, 0.0), thickness=200.0, height=3000.0, level_id="Level 1"),
        ReconstructedWall(id="wall_2", classification="exterior", start=(6000.0, 0.0), end=(6000.0, 4000.0), thickness=200.0, height=3000.0, level_id="Level 1"),
        ReconstructedWall(id="wall_3", classification="exterior", start=(6000.0, 4000.0), end=(0.0, 4000.0), thickness=200.0, height=3000.0, level_id="Level 1"),
        ReconstructedWall(id="wall_4", classification="exterior", start=(0.0, 4000.0), end=(0.0, 0.0), thickness=200.0, height=3000.0, level_id="Level 1"),
    ]
    openings = [
        ReconstructedOpening(id="door_1", type="door", wall_id="wall_1", center=(2000.0, 0.0), width=900.0, height=2100.0, sill_height=0.0),
        ReconstructedOpening(id="win_1", type="window", wall_id="wall_3", center=(3000.0, 4000.0), width=1200.0, height=1200.0, sill_height=900.0),
    ]
    floors = [
        FloorSlab(id="floor_1", level_id="Level 1", thickness=150.0, elevation=0.0, boundary=[(0.0, 0.0), (6000.0, 0.0), (6000.0, 4000.0), (0.0, 4000.0)]),
    ]
    return walls, openings, floors


def test_multi_storey_single_storey_baseline_regression():
    """Verifies that storeys=1 produces backwards-compatible single-storey structure."""
    walls, openings, floors = _create_sample_single_storey_elements()
    model = IntermediateBimModel.create(
        project_name="SingleStoreyBaseline",
        source_dxf_path="dummy.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=openings,
        floors=floors,
        rooms=[],
        storeys_count=1,
    )
    d = model.data
    assert len(d["levels"]) == 2
    assert d["levels"][0]["name"] == "Level 1"
    assert d["levels"][0]["elevation"] == 0.0
    assert d["levels"][1]["name"] == "Level 2"
    assert d["levels"][1]["elevation"] == 3000.0

    summary = model.get_levels_summary()
    assert len(summary) == 2
    assert summary[0]["walls"] == 4
    assert summary[0]["openings"] == 2
    assert summary[0]["floors"] == 1
    assert summary[1]["walls"] == 0


def test_multi_storey_repeated_ground_floor(tmp_path):
    """Verifies two-storey building reconstruction with repeated ground floor footprint."""
    walls, openings, floors = _create_sample_single_storey_elements()
    model = IntermediateBimModel.create(
        project_name="TwoStoreyRepeated",
        source_dxf_path="dummy.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=openings,
        floors=floors,
        rooms=[],
        storeys_count=2,
        storey_heights=[3000.0, 3000.0],
        repeat_ground_floor=True,
    )
    d = model.data

    # 3 levels: Level 1 (0), Level 2 (3000), Level 3 (6000 datum)
    assert len(d["levels"]) == 3
    assert d["levels"][0]["name"] == "Level 1" and d["levels"][0]["elevation"] == 0.0
    assert d["levels"][1]["name"] == "Level 2" and d["levels"][1]["elevation"] == 3000.0
    assert d["levels"][2]["name"] == "Level 3" and d["levels"][2]["elevation"] == 6000.0

    # Walls: 4 ground + 4 upper = 8
    assert len(d["walls"]) == 8
    lvl1_walls = [w for w in d["walls"] if w["levelId"] == "Level 1"]
    lvl2_walls = [w for w in d["walls"] if w["levelId"] == "Level 2"]
    assert len(lvl1_walls) == 4
    assert len(lvl2_walls) == 4
    for w in lvl2_walls:
        assert w["baseElevation"] == 3000.0
        assert w["height"] == 3000.0
        assert "_L2" in w["id"]

    # Openings: 2 ground + 2 upper = 4
    assert len(d["openings"]) == 4
    lvl2_openings = [op for op in d["openings"] if op["levelId"] == "Level 2"]
    assert len(lvl2_openings) == 2
    assert any(op["type"] == "door" and "_L2" in op["id"] and "_L2" in op["wallId"] for op in lvl2_openings)

    # Slabs: 1 ground + 1 upper = 2
    assert len(d["floors"]) == 2
    lvl2_floors = [fl for fl in d["floors"] if fl["levelId"] == "Level 2"]
    assert len(lvl2_floors) == 1
    assert lvl2_floors[0]["elevation"] == 3000.0

    # Test BIMCraft command translation
    adapter = BimcraftAdapter()
    cmds = adapter.build_commands(model)
    # Check that Level 3 is created via level command
    level_cmds = [p for cid, p in cmds if cid == "level"]
    assert any(p.get("name") == "Level 3" and p.get("elevation") == 6000.0 for p in level_cmds)

    # Check wall commands target Level 1 and Level 2
    wall_levels = {p.get("level") for cid, p in cmds if cid == "wall"}
    assert "Level 1" in wall_levels and "Level 2" in wall_levels


def test_multi_storey_unequal_storey_heights():
    """Verifies multi-storey reconstruction with unequal storey heights and ground elevation."""
    walls, openings, floors = _create_sample_single_storey_elements()
    model = IntermediateBimModel.create(
        project_name="UnequalHeights",
        source_dxf_path="dummy.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=openings,
        floors=floors,
        rooms=[],
        storeys_count=2,
        storey_heights=[3500.0, 2800.0],
        ground_elevation=500.0,
        repeat_ground_floor=True,
    )
    d = model.data

    assert d["levels"][0]["elevation"] == 500.0 and d["levels"][0]["height"] == 3500.0
    assert d["levels"][1]["elevation"] == 4000.0 and d["levels"][1]["height"] == 2800.0
    assert d["levels"][2]["elevation"] == 6800.0  # 500 + 3500 + 2800

    lvl2_walls = [w for w in d["walls"] if w["levelId"] == "Level 2"]
    for w in lvl2_walls:
        assert w["baseElevation"] == 4000.0
        assert w["height"] == 2800.0

    adapter = BimcraftAdapter()
    cmds = adapter.build_commands(model)
    # Verify modify command adjusts Level 1 to 500 and Level 2 to 4000
    modifies = [p for cid, p in cmds if cid == "modify"]
    assert any(p.get("id") == 100000 and p.get("elevation") == 500.0 for p in modifies)
    assert any(p.get("id") == 100001 and p.get("elevation") == 4000.0 for p in modifies)


def test_mode_a_dxf_layers_different_footprints(tmp_path):
    """Verifies Mode A (distinct DXF layers) reconstructs different upper-floor footprints."""
    dxf_file = tmp_path / "mode_a_building.dxf"
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Level 1: 8000 x 6000 mm footprint
    doc.layers.add("L1-WALL-EXTR")
    msp.add_line((0, 0), (8000, 0), dxfattribs={"layer": "L1-WALL-EXTR"})
    msp.add_line((8000, 0), (8000, 6000), dxfattribs={"layer": "L1-WALL-EXTR"})
    msp.add_line((8000, 6000), (0, 6000), dxfattribs={"layer": "L1-WALL-EXTR"})
    msp.add_line((0, 6000), (0, 0), dxfattribs={"layer": "L1-WALL-EXTR"})

    # Level 2: Stepped 5000 x 4000 mm footprint
    doc.layers.add("L2-WALL-EXTR")
    msp.add_line((0, 0), (5000, 0), dxfattribs={"layer": "L2-WALL-EXTR"})
    msp.add_line((5000, 0), (5000, 4000), dxfattribs={"layer": "L2-WALL-EXTR"})
    msp.add_line((5000, 4000), (0, 4000), dxfattribs={"layer": "L2-WALL-EXTR"})
    msp.add_line((0, 4000), (0, 0), dxfattribs={"layer": "L2-WALL-EXTR"})

    doc.saveas(dxf_file)

    parser = DxfParser()
    parsed = parser.parse(dxf_file)
    classifier = LayerClassifier()

    model = reconstruct_dxf_model(
        dxf_path=dxf_file,
        parsed=parsed,
        classifier=classifier,
        active_unit="mm",
        scale_factor_to_mm=1.0,
        storeys=2,
        storey_height=3000.0,
        repeat_ground_floor=False,
    )

    d = model.data
    lvl1_walls = [w for w in d["walls"] if w["levelId"] == "Level 1"]
    lvl2_walls = [w for w in d["walls"] if w["levelId"] == "Level 2"]

    assert len(lvl1_walls) == 4
    assert len(lvl2_walls) == 4

    # Verify Level 1 max extent is 8000
    l1_max_x = max(max(w["start"][0], w["end"][0]) for w in lvl1_walls)
    assert pytest.approx(l1_max_x, 1.0) == 8000.0

    # Verify Level 2 max extent is 5000
    l2_max_x = max(max(w["start"][0], w["end"][0]) for w in lvl2_walls)
    assert pytest.approx(l2_max_x, 1.0) == 5000.0


def test_multi_storey_rotated_geometry():
    """Verifies that 45-degree rotated multi-storey geometry is correctly replicated and stacked."""
    walls = [
        ReconstructedWall(id="wall_1", classification="exterior", start=(0.0, 0.0), end=(2828.43, 2828.43), thickness=200.0, height=3000.0, level_id="Level 1"),
        ReconstructedWall(id="wall_2", classification="exterior", start=(2828.43, 2828.43), end=(0.0, 5656.85), thickness=200.0, height=3000.0, level_id="Level 1"),
    ]
    model = IntermediateBimModel.create(
        project_name="RotatedMultiStorey",
        source_dxf_path="dummy.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=[],
        floors=[],
        rooms=[],
        storeys_count=2,
        repeat_ground_floor=True,
    )
    d = model.data
    lvl2_walls = [w for w in d["walls"] if w["levelId"] == "Level 2"]
    assert len(lvl2_walls) == 2
    assert pytest.approx(lvl2_walls[0]["start"][0], 0.1) == 0.0
    assert pytest.approx(lvl2_walls[0]["end"][0], 0.1) == 2828.43
    assert lvl2_walls[0]["baseElevation"] == 3000.0


def test_multi_storey_invalid_parameters():
    """Verifies robust error handling for invalid multi-storey parameters."""
    walls, openings, floors = _create_sample_single_storey_elements()
    dummy_parsed = type("Parsed", (), {"lines": [], "arcs": [], "texts": []})()
    classifier = LayerClassifier()

    # Storeys < 1
    with pytest.raises(ValueError, match="Storey count must be >= 1"):
        reconstruct_dxf_model(
            dxf_path="dummy.dxf",
            parsed=dummy_parsed,
            classifier=classifier,
            active_unit="mm",
            scale_factor_to_mm=1.0,
            storeys=0,
        )

    # Storey height < 1000 mm
    with pytest.raises(ValueError, match="Storey height must be >= 1000 mm"):
        reconstruct_dxf_model(
            dxf_path="dummy.dxf",
            parsed=dummy_parsed,
            classifier=classifier,
            active_unit="mm",
            scale_factor_to_mm=1.0,
            storeys=2,
            storey_height=800.0,
        )

    # Storeys > 1 without repeat flag in non-interactive mode
    with pytest.raises(ValueError, match="Multi-storey reconstruction requested"):
        reconstruct_dxf_model(
            dxf_path="dummy.dxf",
            parsed=dummy_parsed,
            classifier=classifier,
            active_unit="mm",
            scale_factor_to_mm=1.0,
            storeys=2,
            repeat_ground_floor=False,
            interactive_prompt=False,
        )


def test_multi_storey_approval_tamper_detection():
    """Verifies that tampering with multi-storey level definitions invalidates approval."""
    walls, openings, floors = _create_sample_single_storey_elements()
    model = IntermediateBimModel.create(
        project_name="ApprovalSecurityMultiStorey",
        source_dxf_path="dummy.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=openings,
        floors=floors,
        rooms=[],
        storeys_count=2,
        repeat_ground_floor=True,
    )
    # Approve model
    ApprovalGate.approve(model, approved_by="Architect")
    valid, reason = ApprovalGate.verify_approval(model)
    assert valid, f"Expected valid approval, got: {reason}"

    # Tamper 1: change Level 2 elevation from 3000 to 3500
    model.data["levels"][1]["elevation"] = 3500.0
    valid_tampered, reason = ApprovalGate.verify_approval(model)
    assert not valid_tampered
    assert "changed" in reason.lower() or "invalidated" in reason.lower()


def test_multi_storey_end_to_end_bimcraft_and_ifc(tmp_path):
    """Executes full BIMCraft 0.9.0 build, IFC export, and deep validation on a 2-storey model."""
    adapter = BimcraftAdapter()
    if not adapter.is_available():
        pytest.skip("BIMCraft CLI 0.9.0 not installed.")

    walls, openings, floors = _create_sample_single_storey_elements()
    model = IntermediateBimModel.create(
        project_name="TwoStoreyE2E",
        source_dxf_path="dummy.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=openings,
        floors=floors,
        rooms=[],
        storeys_count=2,
        repeat_ground_floor=True,
    )
    ApprovalGate.approve(model, approved_by="Lead Engineer", notes="2-Storey acceptance test")

    out_dir = tmp_path / "e2e_multistorey"
    build_res = adapter.execute_build(model, output_dir=out_dir, generate_3d_views=True)

    assert build_res.success
    assert build_res.bimcraft_path.exists()
    assert build_res.ifc_path.exists()
    assert build_res.view_3d_path.exists()
    assert build_res.section_path.exists()
    assert "Level 2" in build_res.level_plan_paths
    assert build_res.level_plan_paths["Level 2"].exists()

    # Deep IFC parsing
    ifc_parser = PureIfcParser(build_res.ifc_path)
    insp = ifc_parser.inspect()

    assert insp.counts["storey"] >= 2
    assert insp.counts["wall"] == 8
    assert insp.counts["door"] == 2
    assert insp.counts["window"] == 2
    assert insp.counts["slab"] == 2

    # Spatial containment check: elements must be contained in both Level 1 and Level 2
    assert "Level 1" in insp.contained_by_storey
    assert "Level 2" in insp.contained_by_storey
    assert len(insp.contained_by_storey["Level 1"]) >= 4
    assert len(insp.contained_by_storey["Level 2"]) >= 4

    # Validation check
    validator = ModelValidator(adapter)
    val_report = validator.validate(model, build_res)
    assert val_report["overallStatus"] == "PASSED"

    # Human review summary generation
    summary_md = ReviewSummaryGenerator.generate_markdown(model, val_report, build_result=build_res)
    assert "Storey & Level Spatial Structure" in summary_md
    assert "Level 2" in summary_md
