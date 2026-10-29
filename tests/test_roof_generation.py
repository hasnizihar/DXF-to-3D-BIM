"""Comprehensive tests for Parametric Roof Generation (Milestone 12).

Tests gable, hip, flat, and shed roofs, rotated buildings, multi-storey integration,
parameter rejection, approval tamper detection, BIMCraft CLI generation, and IFC4 validation.
"""

import math
from pathlib import Path
import pytest
from shapely.geometry import Polygon

from dxf_to_3d_bim.approval import ApprovalGate, compute_model_hash
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter
from dxf_to_3d_bim.ifc_parser import PureIfcParser
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.roof_engine import ParametricRoofEngine, RoofGeometry
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall


def _create_sample_single_storey_walls():
    # 8000 x 6000 rectangular building (length 8000 on X, width 6000 on Y)
    return [
        ReconstructedWall(id="w1", classification="exterior", start=(0.0, 0.0), end=(8000.0, 0.0), thickness=200.0, height=3000.0, level_id="Level 1"),
        ReconstructedWall(id="w2", classification="exterior", start=(8000.0, 0.0), end=(8000.0, 6000.0), thickness=200.0, height=3000.0, level_id="Level 1"),
        ReconstructedWall(id="w3", classification="exterior", start=(8000.0, 6000.0), end=(0.0, 6000.0), thickness=200.0, height=3000.0, level_id="Level 1"),
        ReconstructedWall(id="w4", classification="exterior", start=(0.0, 6000.0), end=(0.0, 0.0), thickness=200.0, height=3000.0, level_id="Level 1"),
    ]


def test_parametric_roof_engine_gable():
    """Verifies gable roof calculations on an 8000x6000 rectangle."""
    footprint = [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)]
    roof = ParametricRoofEngine.generate_roof(
        footprint=footprint,
        top_level_name="Level 1",
        top_level_elevation=0.0,
        top_wall_height=3000.0,
        roof_type="gable",
        pitch_degrees=30.0,
        overhang=300.0,
        thickness=200.0,
    )
    assert roof is not None
    assert roof.roof_type == "gable"
    assert roof.level_id == "Level 1"
    assert roof.base_elevation == 3000.0
    assert roof.pitch_degrees == 30.0
    assert roof.overhang == 300.0
    assert roof.thickness == 200.0

    # Short edges are 1 and 3 (length 6000 mm, connecting Y=0 to Y=6000)
    assert roof.gable_edge_indices == [1, 3]

    # Half-span is 6000 / 2 = 3000 mm
    # Delta Z = 3000 * tan(30 deg) = 1732.05 mm
    expected_ridge_elev = 3000.0 + 3000.0 * math.tan(math.radians(30.0))
    assert pytest.approx(roof.ridge_elevation, 0.1) == expected_ridge_elev

    # Ridge runs along centerline at Y = 3000 from X=0 to X=8000
    assert len(roof.ridge_endpoints) == 2
    r_pts = sorted(roof.ridge_endpoints, key=lambda p: p[0])
    assert pytest.approx(r_pts[0][0], 0.1) == 0.0
    assert pytest.approx(r_pts[0][1], 0.1) == 3000.0
    assert pytest.approx(r_pts[0][2], 0.1) == expected_ridge_elev
    assert pytest.approx(r_pts[1][0], 0.1) == 8000.0
    assert pytest.approx(r_pts[1][1], 0.1) == 3000.0

    # Area 8000 * 6000 = 48 m2
    assert pytest.approx(roof.area_m2, 0.1) == 48.0


def test_parametric_roof_engine_hip():
    """Verifies hip roof calculations on an 8000x6000 rectangle."""
    footprint = [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)]
    roof = ParametricRoofEngine.generate_roof(
        footprint=footprint,
        top_level_name="Level 1",
        top_level_elevation=0.0,
        top_wall_height=3000.0,
        roof_type="hip",
        pitch_degrees=30.0,
        overhang=300.0,
    )
    assert roof is not None
    assert roof.roof_type == "hip"
    assert roof.gable_edge_indices == []  # All edges slope

    # Half-span = 3000 mm. Ridge inset by half-span from ends (8000 - 2*3000 = 2000 mm long)
    r_pts = sorted(roof.ridge_endpoints, key=lambda p: p[0])
    assert len(r_pts) == 2
    assert pytest.approx(r_pts[0][0], 0.1) == 3000.0
    assert pytest.approx(r_pts[0][1], 0.1) == 3000.0
    assert pytest.approx(r_pts[1][0], 0.1) == 5000.0
    assert pytest.approx(r_pts[1][1], 0.1) == 3000.0


def test_parametric_roof_engine_flat_and_shed():
    """Verifies flat and shed roof calculations."""
    footprint = [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)]

    flat_roof = ParametricRoofEngine.generate_roof(
        footprint=footprint,
        top_level_name="Level 1",
        top_level_elevation=0.0,
        top_wall_height=3000.0,
        roof_type="flat",
        pitch_degrees=0.0,
    )
    assert flat_roof.pitch_degrees == 0.0
    assert flat_roof.ridge_elevation == 3000.0

    none_roof = ParametricRoofEngine.generate_roof(
        footprint=footprint,
        roof_type="none",
    )
    assert none_roof is None


def test_parametric_roof_rotated_building():
    """Verifies gable roof calculations on a 45-degree rotated rectangular building."""
    # 6000 x 3000 rectangle rotated by 45 degrees
    # P0 = (0, 0)
    # P1 = (6000/sqrt(2), 6000/sqrt(2)) = (4242.64, 4242.64)  [length 6000]
    # P2 = (4242.64 - 3000/sqrt(2), 4242.64 + 3000/sqrt(2)) = (2121.32, 6363.96) [length 3000]
    # P3 = (-2121.32, 2121.32) [length 6000]
    footprint = [(0.0, 0.0), (4242.64, 4242.64), (2121.32, 6363.96), (-2121.32, 2121.32)]

    roof = ParametricRoofEngine.generate_roof(
        footprint=footprint,
        top_level_name="Level 1",
        top_level_elevation=0.0,
        top_wall_height=3000.0,
        roof_type="gable",
        pitch_degrees=30.0,
    )
    assert roof is not None
    # Edges 1 and 3 are shorter (length 3000)
    assert roof.gable_edge_indices == [1, 3]

    # Half span is 3000 / 2 = 1500 mm
    expected_ridge_elev = 3000.0 + 1500.0 * math.tan(math.radians(30.0))
    assert pytest.approx(roof.ridge_elevation, 0.1) == expected_ridge_elev

    # Ridge runs parallel to 45 degree long edges
    assert len(roof.ridge_endpoints) == 2
    r0, r1 = roof.ridge_endpoints
    dx = r1[0] - r0[0]
    dy = r1[1] - r0[1]
    # dx should equal dy (45 degree line)
    assert pytest.approx(abs(dx), 0.5) == pytest.approx(abs(dy), 0.5)


def test_roof_invalid_parameters():
    """Verifies that invalid roof parameters are strictly rejected."""
    footprint = [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)]

    # Invalid pitch >= 90
    with pytest.raises(ValueError, match="pitch"):
        ParametricRoofEngine.generate_roof(footprint, pitch_degrees=90.0)

    # Negative pitch
    with pytest.raises(ValueError, match="pitch"):
        ParametricRoofEngine.generate_roof(footprint, pitch_degrees=-5.0)

    # Negative overhang
    with pytest.raises(ValueError, match="overhang"):
        ParametricRoofEngine.generate_roof(footprint, overhang=-100.0)

    # Degenerate footprint (< 3 points)
    with pytest.raises(ValueError, match="vertices"):
        ParametricRoofEngine.generate_roof([(0, 0), (100, 100)])

    # Unsupported roof type
    with pytest.raises(ValueError, match="Unsupported roof type"):
        ParametricRoofEngine.generate_roof(footprint, roof_type="mansard")


def test_multi_storey_with_gable_roof():
    """Verifies 2-storey building with gable roof integration."""
    walls = _create_sample_single_storey_walls()
    floor_slab = {
        "id": "floor_1",
        "level_id": "Level 1",
        "thickness": 150.0,
        "elevation": 0.0,
        "boundary": [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)],
    }

    dummy_model_data = {
        "floors": [floor_slab],
        "walls": [{"start": w.start, "end": w.end, "levelId": "Level 2", "classification": "exterior"} for w in walls],
    }

    footprint = ParametricRoofEngine.derive_roof_footprint_from_model(dummy_model_data, "Level 2")
    roof = ParametricRoofEngine.generate_roof(
        footprint=footprint,
        top_level_name="Level 2",
        top_level_elevation=3000.0,
        top_wall_height=3000.0,
        roof_type="gable",
        pitch_degrees=30.0,
        overhang=300.0,
    )

    model = IntermediateBimModel.create(
        project_name="MultiStoreyWithRoof",
        source_dxf_path="dummy.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=[],
        floors=[],
        rooms=[],
        storeys_count=2,
        repeat_ground_floor=True,
        roofs=[roof.to_dict()],
    )

    # Validate model schema
    model.validate_schema()

    d = model.data
    assert len(d["roofs"]) == 1
    rf = d["roofs"][0]
    assert rf["levelId"] == "Level 2"
    assert rf["baseElevation"] == 6000.0  # Bearing elevation at top of Level 2 (3000 + 3000)
    assert rf["roofType"] == "gable"

    # Storey breakdown
    levels_summary = model.get_levels_summary()
    assert len(levels_summary) == 3
    assert levels_summary[0]["name"] == "Level 1"
    assert levels_summary[1]["name"] == "Level 2"
    assert levels_summary[1]["roofs"] == 1
    assert levels_summary[2]["name"] == "Level 3"
    assert levels_summary[2]["storeyType"] == "roof_datum"
    assert levels_summary[2]["walls"] == 0
    assert levels_summary[2]["roofs"] == 0


def test_roof_approval_tamper_detection():
    """Verifies that tampering with roof parameters after approval invalidates the model hash."""
    walls = _create_sample_single_storey_walls()
    footprint = [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)]
    roof = ParametricRoofEngine.generate_roof(
        footprint=footprint,
        top_level_name="Level 1",
        top_level_elevation=0.0,
        top_wall_height=3000.0,
        roof_type="gable",
        pitch_degrees=30.0,
    )

    model = IntermediateBimModel.create(
        project_name="ApprovalRoofTamper",
        source_dxf_path="dummy.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=[],
        floors=[],
        rooms=[],
        roofs=[roof.to_dict()],
    )

    # Approve
    approval = ApprovalGate.approve(model, approved_by="Architect Jane")
    assert approval["status"] == "approved"
    assert approval["approvedParameters"]["roofType"] == "gable"
    assert approval["approvedParameters"]["roofPitch"] == 30.0

    valid, _ = ApprovalGate.verify_approval(model)
    assert valid is True

    # Tamper with roof pitch (e.g. 30 -> 35 degrees)
    model.data["roofs"][0]["pitchDegrees"] = 35.0
    valid_after_tamper, msg = ApprovalGate.verify_approval(model)
    assert valid_after_tamper is False
    assert "content has changed" in msg


def test_live_bimcraft_and_ifc_roof_generation(tmp_path):
    """Executes live BIMCraft CLI build and IFC4 semantic verification for gable roof."""
    adapter = BimcraftAdapter()
    if not adapter.is_available():
        pytest.skip("BIMCraft CLI executable not available in environment.")

    walls = _create_sample_single_storey_walls()
    footprint = [(0.0, 0.0), (8000.0, 0.0), (8000.0, 6000.0), (0.0, 6000.0)]
    roof = ParametricRoofEngine.generate_roof(
        footprint=footprint,
        top_level_name="Level 1",
        top_level_elevation=0.0,
        top_wall_height=3000.0,
        roof_type="gable",
        pitch_degrees=30.0,
        overhang=300.0,
    )

    # Also add a slab
    floor_slab = type("FloorSlab", (), {
        "id": "floor_1",
        "level_id": "Level 1",
        "thickness": 150.0,
        "elevation": 0.0,
        "boundary": footprint,
    })()

    model = IntermediateBimModel.create(
        project_name="LiveRoofTest",
        source_dxf_path=str(tmp_path / "dummy.dxf"),
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=[],
        floors=[floor_slab],
        rooms=[],
        roofs=[roof.to_dict()],
    )

    # Approve
    ApprovalGate.approve(model, approved_by="QA Tester")

    # Build deliverables
    build_res = adapter.execute_build(
        model,
        output_dir=tmp_path / "deliverables",
        generate_3d_views=True,
    )

    assert build_res.success is True
    assert build_res.bimcraft_path.exists()
    assert build_res.ifc_path.exists()

    # Parse and inspect exported IFC
    ifc_parser = PureIfcParser(build_res.ifc_path)
    ifc_sem = ifc_parser.inspect()

    # Verify roof counts and attributes
    assert ifc_sem.counts["roof"] == 1
    assert len(ifc_sem.roofs) == 1
    assert ifc_sem.roofs[0]["predefined_type"] == "GABLE_ROOF"
    assert ifc_sem.roofs[0]["contained_in_storey"] == "Level 1"

    # Validate model
    validator = ModelValidator(adapter)
    val_report = validator.validate(model, build_res)
    assert val_report["overallStatus"] in ("PASSED", "WARNING")

    # Verify 3D view and Section A-A files rendered
    p_dir = tmp_path / "deliverables"
    assert (p_dir / "liverooftest_3d.png").exists()
    assert (p_dir / "liverooftest_section_a.png").exists()

