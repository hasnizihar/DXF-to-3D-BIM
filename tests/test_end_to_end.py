"""Mandatory End-to-End Acceptance Test: Synthetic DXF to 3D BIM with BIMCraft 0.9.0."""

import pytest
from pathlib import Path
from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter
from dxf_to_3d_bim.dxf_parser import DxfParser
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.opening_detection import OpeningDetector
from dxf_to_3d_bim.room_detection import SpatialDetector
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.wall_reconstruction import WallReconstructor
from tests.create_fixtures import create_synthetic_room_dxf


def test_end_to_end_acceptance_workflow(tmp_path):
    """
    Mandatory Acceptance Test:
    1. Parse synthetic DXF with 4 walls, 1 door, 1 window, 1 slab.
    2. Reconstruct walls, openings, floor slab, and room zones.
    3. Generate intermediate model conforming to bim-model.schema.json.
    4. Enforce approval gate (validate lock with SHA-256 hash).
    5. Construct native .bimcraft model, export IFC4, and render PNG preview using BIMCraft 0.9.0.
    6. Reopen native project and parse IFC to verify semantic element counts.
    7. Generate validation report conforming to validation-report.schema.json with PASSED status.
    """
    dxf_file = tmp_path / "synthetic_house.dxf"
    create_synthetic_room_dxf(dxf_file)
    assert dxf_file.exists()

    # 1. Parse DXF
    parser = DxfParser()
    parsed = parser.parse(dxf_file)
    assert parsed.report.detected_units == "mm"
    assert parsed.report.total_entities >= 10

    # 2. Reconstruct Geometry
    classifier = LayerClassifier()
    wall_rec = WallReconstructor()
    walls = wall_rec.reconstruct(parsed.lines, classifier=classifier)
    assert len(walls) == 4
    for w in walls:
        assert w.classification == "exterior"
        assert w.thickness == 200.0

    # Detect openings
    detector = OpeningDetector()
    openings, unhosted = detector.detect_openings(parsed.lines, parsed.arcs, walls, classifier=classifier)
    doors = [op for op in openings if op.type == "door"]
    windows = [op for op in openings if op.type == "window"]
    assert len(doors) == 1
    assert len(windows) == 1
    assert len(unhosted) == 0

    # Detect slab and room
    spatial = SpatialDetector()
    slab_lines = [l for l in parsed.lines if classifier.is_slab_layer(l.layer)]
    slab = spatial.detect_slab(walls, slab_lines=slab_lines)
    assert slab is not None
    assert len(slab.boundary) >= 4

    rooms = spatial.detect_rooms(parsed.texts, slab=slab, classifier=classifier)
    assert len(rooms) >= 1
    assert rooms[0].name == "Living Room"

    # 3. Create Intermediate Model
    model = IntermediateBimModel.create(
        project_name="SyntheticHouseAcceptance",
        source_dxf_path=str(dxf_file),
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=openings,
        floors=[slab],
        rooms=rooms,
    )
    model.validate_schema()
    assert model.data["status"] == "awaiting_approval"

    # 4. Mandatory Approval Gate
    summary = ApprovalGate.generate_proposal_summary(model)
    assert summary["counts"]["exterior_walls"] == 4
    assert summary["counts"]["doors"] == 1
    assert summary["counts"]["windows"] == 1

    # Simulate approval
    approval_record = ApprovalGate.approve(model, approved_by="Acceptance Tester", notes="Approved")
    assert model.data["status"] == "approved"
    is_valid, _ = ApprovalGate.verify_approval(model)
    assert is_valid

    # 5. BIMCraft Construction
    adapter = BimcraftAdapter()
    assert adapter.is_available()

    output_dir = tmp_path / "bim_output"
    build_result = adapter.execute_build(model, output_dir=output_dir, base_name="synthetic_house")
    assert build_result.success
    assert build_result.bimcraft_path.exists()
    assert build_result.ifc_path.exists()
    assert build_result.png_path.exists()

    # 6 & 7. Independent Validation
    validator = ModelValidator(adapter)
    val_report = validator.validate(model, build_result)

    assert val_report["overallStatus"] == "PASSED"
    assert val_report["elementSummary"]["generated"]["walls"] == 4
    assert val_report["elementSummary"]["generated"]["doors"] == 1
    assert val_report["elementSummary"]["generated"]["windows"] == 1
    assert val_report["elementSummary"]["generated"]["levels"] >= 2
