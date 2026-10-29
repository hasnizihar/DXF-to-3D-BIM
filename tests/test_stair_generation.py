"""Test suite for Parametric Staircase Generation & Vertical Circulation (Milestone 13)."""

import math
from pathlib import Path
import pytest

from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter
from dxf_to_3d_bim.ifc_parser import PureIfcParser
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.approval import ApprovalGate, compute_model_hash
from dxf_to_3d_bim.stair_engine import ParametricStairEngine, StairGeometry
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall
from dxf_to_3d_bim.room_detection import FloorSlab


def test_parametric_stair_engine_straight():
    """Verifies straight-flight stair calculation for standard 3000 mm storey rise."""
    stair = ParametricStairEngine.generate_stair(
        stair_id="stair_test_1",
        stair_type="straight",
        level_id="Level 1",
        top_level_id="Level 2",
        base_elevation=0.0,
        top_elevation=3000.0,
        start_point=(1000.0, 2000.0),
        direction_angle_deg=0.0,
        width=1000.0,
        target_riser=175.0,
        target_going=280.0,
        railings=True,
    )

    assert stair.id == "stair_test_1"
    assert stair.stair_type == "straight"
    assert stair.total_rise == 3000.0
    # 3000 / 175 = 17.14 -> 17 risers
    assert stair.riser_count == 17
    assert math.isclose(stair.actual_riser_height, 3000.0 / 17, rel_tol=1e-3)
    assert stair.tread_count == 16
    assert stair.actual_going == 280.0
    # 16 treads * 280 mm = 4480 mm
    assert math.isclose(stair.total_run, 4480.0, rel_tol=1e-3)
    assert math.isclose(stair.end[0], 1000.0 + 4480.0, rel_tol=1e-2)
    assert math.isclose(stair.end[1], 2000.0, rel_tol=1e-2)
    assert len(stair.landings) == 0
    assert stair.railings is True
    assert stair.headroom_clearance >= 2000.0
    assert stair.stairwell_area_m2 > 4.0  # Approx 4.5 m2
    assert len(stair.stairwell_boundary) >= 4


def test_parametric_stair_engine_l_shaped():
    """Verifies L-shaped quarter-turn stair with mid-height landing."""
    stair = ParametricStairEngine.generate_stair(
        stair_id="stair_l_1",
        stair_type="l_shaped",
        level_id="Level 1",
        top_level_id="Level 2",
        base_elevation=0.0,
        top_elevation=3000.0,
        start_point=(1000.0, 1000.0),
        direction_angle_deg=0.0,
        width=1000.0,
        target_riser=175.0,
        target_going=280.0,
        turn_direction="left",
    )

    assert stair.stair_type == "l_shaped"
    assert len(stair.landings) == 1
    landing = stair.landings[0]
    assert landing["atRiser"] == 8
    assert landing["turnDegrees"] == 90.0
    assert math.isclose(landing["elevation"], 8 * (3000.0 / 17), rel_tol=1e-3)
    assert landing["dimensions"] == [1000.0, 1000.0]
    assert stair.stairwell_area_m2 > 3.0


def test_parametric_stair_engine_u_shaped():
    """Verifies U-shaped half-turn dog-legged stair with intermediate landing."""
    stair = ParametricStairEngine.generate_stair(
        stair_id="stair_u_1",
        stair_type="u_shaped",
        level_id="Level 1",
        top_level_id="Level 2",
        base_elevation=0.0,
        top_elevation=3000.0,
        start_point=(2000.0, 2000.0),
        direction_angle_deg=0.0,
        width=1000.0,
        target_riser=175.0,
        target_going=280.0,
    )

    assert stair.stair_type == "u_shaped"
    assert len(stair.landings) == 1
    landing = stair.landings[0]
    assert landing["atRiser"] == 8
    assert landing["turnDegrees"] == 180.0
    assert landing["dimensions"][1] == 1000.0  # depth
    assert landing["dimensions"][0] >= 2000.0  # width >= 2*W
    assert stair.stairwell_area_m2 > 4.0


def test_rotated_stair_orientation():
    """Verifies stair calculation along a 45-degree diagonal trajectory."""
    stair = ParametricStairEngine.generate_stair(
        stair_id="stair_rot",
        stair_type="straight",
        level_id="Level 1",
        top_level_id="Level 2",
        base_elevation=0.0,
        top_elevation=3000.0,
        start_point=(1000.0, 1000.0),
        direction_angle_deg=45.0,
        width=900.0,
    )

    total_run = stair.total_run
    exp_dx = total_run * math.cos(math.radians(45.0))
    exp_dy = total_run * math.sin(math.radians(45.0))

    assert math.isclose(stair.end[0], 1000.0 + exp_dx, rel_tol=1e-2)
    assert math.isclose(stair.end[1], 1000.0 + exp_dy, rel_tol=1e-2)
    assert len(stair.stairwell_boundary) >= 4


def test_stair_slab_opening_punching():
    """Verifies that upper floor slab gets stairwell void opening punched while ground slab is untouched."""
    floors = [
        {
            "id": "floor_1",
            "levelId": "Level 1",
            "thickness": 150.0,
            "elevation": 0.0,
            "boundary": [[0.0, 0.0], [8000.0, 0.0], [8000.0, 8000.0], [0.0, 8000.0]],
        },
        {
            "id": "floor_1_L2",
            "levelId": "Level 2",
            "thickness": 150.0,
            "elevation": 3000.0,
            "boundary": [[0.0, 0.0], [8000.0, 0.0], [8000.0, 8000.0], [0.0, 8000.0]],
        },
    ]

    stair = ParametricStairEngine.generate_stair(
        stair_id="stair_1",
        stair_type="straight",
        level_id="Level 1",
        top_level_id="Level 2",
        base_elevation=0.0,
        top_elevation=3000.0,
        start_point=(1500.0, 1500.0),
    )

    updated_floors = ParametricStairEngine.punch_stairwell_opening_into_floors(floors, [stair])

    fl_g = next(f for f in updated_floors if f["levelId"] == "Level 1")
    fl_u = next(f for f in updated_floors if f["levelId"] == "Level 2")

    # Ground floor has no stairwell opening
    assert len(fl_g.get("openings", [])) == 0
    # Level 2 floor slab has exactly 1 void opening
    assert len(fl_u.get("openings", [])) == 1
    assert len(fl_u["openings"][0]) >= 4


def test_stair_invalid_parameters_rejection():
    """Verifies that unphysical or code-violating stair configurations are safely rejected."""
    # Negative / inverted elevations
    with pytest.raises(ValueError, match="strictly greater"):
        ParametricStairEngine.generate_stair(base_elevation=3000.0, top_elevation=1000.0)

    # Insufficient rise (< 500 mm)
    with pytest.raises(ValueError, match="below minimum required"):
        ParametricStairEngine.generate_stair(base_elevation=0.0, top_elevation=300.0)

    # Stair width < 500 mm
    with pytest.raises(ValueError, match="below minimum permitted"):
        ParametricStairEngine.generate_stair(width=400.0)

    # Unsupported stair type
    with pytest.raises(ValueError, match="Unsupported stair type"):
        ParametricStairEngine.generate_stair(stair_type="spiral")

    # Coincident start and end
    with pytest.raises(ValueError, match="cannot be coincident"):
        ParametricStairEngine.generate_stair(start_point=(1000.0, 1000.0), end_point=(1000.0, 1000.0))


def test_stair_approval_tamper_detection():
    """Verifies that altering stair parameters in approved intermediate model invalidates SHA-256 seal."""
    model = IntermediateBimModel.create(
        project_name="StairTamperTest",
        source_dxf_path="test.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=[
            ReconstructedWall(
                id="w1",
                classification="exterior",
                start=(0.0, 0.0),
                end=(6000.0, 0.0),
                thickness=200.0,
                height=3000.0,
                level_id="Level 1",
            ),
        ],
        openings=[],
        floors=[
            FloorSlab(
                id="fl1",
                level_id="Level 1",
                thickness=150.0,
                elevation=0.0,
                boundary=[(0.0, 0.0), (6000.0, 0.0), (6000.0, 6000.0), (0.0, 6000.0)],
            )
        ],
        rooms=[],
        storeys_count=2,
        repeat_ground_floor=True,
        staircases=[
            ParametricStairEngine.generate_stair(
                stair_id="stair_1",
                stair_type="straight",
                level_id="Level 1",
                top_level_id="Level 2",
                base_elevation=0.0,
                top_elevation=3000.0,
                start_point=(1000.0, 1000.0),
                width=1000.0,
            ).to_dict()
        ],
    )

    # Approve
    ApprovalGate.approve(model, approved_by="Architect Reviewer", approval_method="test")
    valid, _ = ApprovalGate.verify_approval(model)
    assert valid is True

    # Tamper with stair width
    model.data["staircases"][0]["width"] = 1400.0
    valid_after_tamper, msg = ApprovalGate.verify_approval(model)
    assert valid_after_tamper is False
    assert "changed since approval" in msg


def test_dxf_layer_stair_detection():
    """Verifies layer classification and candidate detection from 2D DXF stair linework."""
    classifier = LayerClassifier()
    assert classifier.is_stair_layer("A-FLOR-STRS") is True
    assert classifier.is_stair_layer("STAIR") is True
    assert classifier.is_stair_layer("S-STAIR") is True
    assert classifier.is_stair_layer("A-WALL-EXTR") is False

    # Synthetic stair lines
    class DummyLine:
        def __init__(self, start, end, layer="A-FLOR-STRS"):
            self.start = start
            self.end = end
            self.layer = layer

    lines = [
        DummyLine((1000.0, 1000.0), (1000.0, 2000.0)),
        DummyLine((1280.0, 1000.0), (1280.0, 2000.0)),
        DummyLine((1560.0, 1000.0), (1560.0, 2000.0)),
        DummyLine((1840.0, 1000.0), (1840.0, 2000.0)),
    ]

    detected = ParametricStairEngine.detect_stairs_from_lines(
        stair_lines=lines,
        level_id="Level 1",
        top_level_id="Level 2",
        base_elevation=0.0,
        top_elevation=3000.0,
    )

    assert detected is not None
    assert detected.provenance == "dxf_detected"
    assert detected.width >= 800.0


def test_live_bimcraft_and_ifc_stair_generation(tmp_path):
    """Executes full live BIMCraft CLI generation for 2-storey building with staircase.

    Verifies native BIMCraft commands, IFC4 IFCSTAIR, IFCSTAIRFLIGHT, IfcRelAggregates,
    stairwell void in upper slab (IFCARBITRARYPROFILEDEFWITHVOIDS), and ModelValidator pass.
    """
    adapter = BimcraftAdapter()
    if not adapter.is_available():
        pytest.skip("BIMCraft CLI not available in test environment.")

    walls = [
        ReconstructedWall(id="w1", classification="exterior", start=(0.0, 0.0), end=(8000.0, 0.0), thickness=200.0, height=3000.0, level_id="Level 1"),
        ReconstructedWall(id="w2", classification="exterior", start=(8000.0, 0.0), end=(8000.0, 6000.0), thickness=200.0, height=3000.0, level_id="Level 1"),
        ReconstructedWall(id="w3", classification="exterior", start=(8000.0, 6000.0), end=(0.0, 6000.0), thickness=200.0, height=3000.0, level_id="Level 1"),
        ReconstructedWall(id="w4", classification="exterior", start=(0.0, 6000.0), end=(0.0, 0.0), thickness=200.0, height=3000.0, level_id="Level 1"),
    ]
    slab = FloorSlab(
        id="floor_1",
        level_id="Level 1",
        thickness=150.0,
        elevation=0.0,
        boundary=[(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)],
    )

    stair_geom = ParametricStairEngine.generate_stair(
        stair_id="stair_live_1",
        stair_type="straight",
        level_id="Level 1",
        top_level_id="Level 2",
        base_elevation=0.0,
        top_elevation=3000.0,
        start_point=(1500.0, 2000.0),
        width=1000.0,
        target_riser=176.5,
        target_going=280.0,
        railings=True,
    )

    model = IntermediateBimModel.create(
        project_name="LiveStairTest",
        source_dxf_path="test_stair.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=[],
        floors=[slab],
        rooms=[],
        storeys_count=2,
        repeat_ground_floor=True,
        staircases=[stair_geom.to_dict()],
    )

    ApprovalGate.approve(model, approved_by="Lead Engineer", approval_method="automated_test")

    out_dir = tmp_path / "deliverables"
    out_dir.mkdir(parents=True, exist_ok=True)

    build_res = adapter.execute_build(
        model=model,
        output_dir=out_dir,
        base_name="livestairtest",
        generate_3d_views=True,
    )

    assert build_res.success is True, f"BIMCraft CLI execution failed: {build_res.error_message}"
    assert build_res.ifc_path.exists()
    assert build_res.bimcraft_path.exists()

    # Deep IFC Verification with PureIfcParser
    parser = PureIfcParser(build_res.ifc_path)
    sem = parser.inspect()

    assert sem.counts["stair"] == 1
    assert sem.counts["stair_flight"] >= 1
    assert sem.counts["railing"] >= 2
    assert sem.stair_aggregates_verified is True
    assert sem.has_slab_voids is True

    # Validate with ModelValidator
    validator = ModelValidator(adapter)
    report = validator.validate(model, build_res)

    assert report["overallStatus"] == "PASSED"
    assert report["elementSummary"]["generated"]["stairs"] == 1
    assert report["elementSummary"]["generated"]["stair_flights"] >= 1
    assert report["elementSummary"]["generated"]["railings"] >= 2
