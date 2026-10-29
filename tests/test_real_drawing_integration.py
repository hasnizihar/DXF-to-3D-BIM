"""Integration tests against real drawings and genuine upstream Sketch-to-CAD models."""

from pathlib import Path
import pytest
from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter
from dxf_to_3d_bim.dxf_parser import DxfParser
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.opening_detection import OpeningDetector
from dxf_to_3d_bim.room_detection import SpatialDetector
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.wall_reconstruction import WallReconstructor

UPSTREAM_JSON_PATH = Path(r"D:\Agent Skills\sketch-to-cad-main\floor-plan-model.json")
REAL_DXF_PATH = Path(r"D:\Agent Skills\DXF to 3D-BIM\residential-floor-plan.dxf")


@pytest.mark.skipif(not UPSTREAM_JSON_PATH.exists(), reason="Upstream Sketch-to-CAD JSON fixture not found")
def test_genuine_sketch_to_cad_upstream_workflow(tmp_path):
    """Verifies end-to-end BIMCraft model generation from genuine Sketch-to-CAD JSON model."""
    model = IntermediateBimModel.from_sketch_to_cad_json(UPSTREAM_JSON_PATH)
    model.validate_schema()

    assert len(model.data["walls"]) == 12
    assert len(model.data["openings"]) == 16
    assert len(model.data["floors"]) == 1

    # Enforce approval gate
    ApprovalGate.approve(model, approved_by="Integration Reviewer", notes="Approved genuine Sketch-to-CAD model")
    is_valid, _ = ApprovalGate.verify_approval(model)
    assert is_valid

    # Execute build via BIMCraft
    adapter = BimcraftAdapter()
    build_res = adapter.execute_build(model, output_dir=tmp_path, base_name="sketch_to_cad_bim")
    assert build_res.success
    assert build_res.bimcraft_path.exists()
    assert build_res.ifc_path.exists()
    assert build_res.png_path.exists()

    # Deep validation
    validator = ModelValidator(adapter)
    report = validator.validate(model, build_res)

    assert report["overallStatus"] == "PASSED"
    assert report["elementSummary"]["generated"]["walls"] == 12
    assert report["elementSummary"]["generated"]["doors"] == 8
    assert report["elementSummary"]["generated"]["windows"] == 8


@pytest.mark.skipif(not REAL_DXF_PATH.exists(), reason="Real DXF floor plan not found")
def test_direct_dxf_inspection_and_reconstruction():
    """Verifies inspection and geometric reconstruction directly on residential-floor-plan.dxf."""
    parser = DxfParser()
    report = parser.inspect_file(REAL_DXF_PATH)

    assert report.insunits_code == 4  # mm
    assert report.detected_units == "mm"
    assert report.bounding_box["width"] == 8000.0
    assert report.bounding_box["depth"] == 8700.0
    assert report.total_entities >= 140

    parsed = parser.parse(REAL_DXF_PATH)
    classifier = LayerClassifier()
    wall_rec = WallReconstructor()
    walls = wall_rec.reconstruct(parsed.lines, classifier=classifier)

    # Reconstructed walls must detect exterior boundary
    assert len(walls) >= 14
    ext_walls = [w for w in walls if w.classification == "exterior"]
    assert len(ext_walls) >= 4

    detector = OpeningDetector()
    openings, unhosted = detector.detect_openings(parsed.lines, parsed.arcs, walls, classifier=classifier)
    assert len(openings) >= 10

