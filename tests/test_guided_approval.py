"""Automated tests for Guided Approval workflow and approval security."""

from pathlib import Path
import json
import pytest
import ezdxf
from unittest.mock import patch

from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.config import ConfigManager, ProjectConfig
from dxf_to_3d_bim.dxf_parser import DxfParser
from dxf_to_3d_bim.guided_approval import GuidedApprovalSession
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.preflight import PreflightAnalyzer
from dxf_to_3d_bim.room_detection import SpatialDetector
from dxf_to_3d_bim.wall_reconstruction import WallReconstructor
from tests.create_fixtures import create_synthetic_room_dxf


@pytest.fixture
def sample_model_and_preflight(tmp_path):
    dxf_file = tmp_path / "room.dxf"
    create_synthetic_room_dxf(dxf_file)

    analyzer = PreflightAnalyzer()
    preflight = analyzer.analyze(dxf_file)

    parser = DxfParser()
    parsed = parser.parse(dxf_file)
    classifier = LayerClassifier()
    wall_rec = WallReconstructor()
    walls = wall_rec.reconstruct(parsed.lines, classifier=classifier)

    spatial = SpatialDetector()
    slab = spatial.detect_slab(walls)
    floors = [slab] if slab else []

    model = IntermediateBimModel.create(
        project_name="TestApprovalRoom",
        source_dxf_path=str(dxf_file),
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=[],
        floors=floors,
        rooms=[],
    )
    return dxf_file, model, preflight


def test_approval_accepted_interactive_simulation(sample_model_and_preflight):
    dxf_file, model, preflight = sample_model_and_preflight
    session = GuidedApprovalSession(model, preflight, dxf_file)

    with patch("builtins.input", side_effect=["1"]):
        record = session.run_guided_session(interactive=True)

    assert record["status"] == "approved"
    assert model.data["status"] == "approved"
    assert "modelHash" in record
    assert record["dxfHash"] == session.dxf_hash
    assert record["approvalMethod"] == "interactive"

    is_valid, _ = ApprovalGate.verify_approval(model, expected_dxf_hash=session.dxf_hash)
    assert is_valid


def test_approval_edit_parameter_simulation(sample_model_and_preflight):
    dxf_file, model, preflight = sample_model_and_preflight
    session = GuidedApprovalSession(model, preflight, dxf_file)

    # Option 2 (edit wall height) -> enter 2800 -> Option 1 (accept)
    with patch("builtins.input", side_effect=["2", "2800", "1"]):
        record = session.run_guided_session(interactive=True)

    assert record["approvedParameters"]["wallHeight"] == 2800.0
    for w in model.data["walls"]:
        assert w["height"] == 2800.0


def test_approval_rejected_cancels_generation(sample_model_and_preflight):
    dxf_file, model, preflight = sample_model_and_preflight
    session = GuidedApprovalSession(model, preflight, dxf_file)

    with patch("builtins.input", side_effect=["5"]):
        with pytest.raises(PermissionError, match="rejected proposal"):
            session.run_guided_session(interactive=True)

    assert model.data["status"] == "awaiting_approval"


def test_input_dxf_changed_after_approval_invalidates(sample_model_and_preflight):
    dxf_file, model, preflight = sample_model_and_preflight
    session = GuidedApprovalSession(model, preflight, dxf_file)

    record = session.run_guided_session(interactive=False, auto_approve=True)
    assert model.data["status"] == "approved"

    # Simulate DXF modified after approval
    different_dxf_hash = "0000000000000000000000000000000000000000000000000000000000000000"
    is_valid, reason = ApprovalGate.verify_approval(model, expected_dxf_hash=different_dxf_hash)
    assert not is_valid
    assert "Source DXF file has been modified" in reason


def test_config_changed_after_approval_invalidates(sample_model_and_preflight):
    dxf_file, model, preflight = sample_model_and_preflight
    session = GuidedApprovalSession(model, preflight, dxf_file)

    record = session.run_guided_session(interactive=False, auto_approve=True)

    # Simulate config hash mismatch
    different_config_hash = "1111111111111111111111111111111111111111111111111111111111111111"
    is_valid, reason = ApprovalGate.verify_approval(model, expected_config_hash=different_config_hash)
    assert not is_valid
    assert "Configuration parameters have changed" in reason


def test_non_interactive_run_with_unit_ambiguity_fails_without_override(tmp_path):
    dxf_file = tmp_path / "ambiguous.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    doc.layers.add("A-WALL-EXTR")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "A-WALL-EXTR"})
    doc.saveas(str(dxf_file))

    analyzer = PreflightAnalyzer()
    preflight = analyzer.analyze(dxf_file)
    assert preflight.unit_ambiguity is True

    model = IntermediateBimModel.create(
        project_name="AmbiguousRoom",
        source_dxf_path=str(dxf_file),
        source_units="unspecified",
        scale_factor=1.0,
        walls=[],
        openings=[],
        floors=[],
        rooms=[],
    )

    # Session without source_unit in config
    cfg = ProjectConfig()
    cfg.units.source_unit = None
    session = GuidedApprovalSession(model, preflight, dxf_file, config=cfg)

    with pytest.raises(ValueError, match="Drawing units are unspecified"):
        session.run_guided_session(interactive=False)


def test_approved_config_successfully_reused(sample_model_and_preflight):
    dxf_file, model, preflight = sample_model_and_preflight
    cfg = ProjectConfig()
    cfg.walls.height = 3200.0
    cfg.slab.thickness = 180.0

    session = GuidedApprovalSession(model, preflight, dxf_file, config=cfg)
    record = session.run_guided_session(interactive=False, auto_approve=False)

    assert record["status"] == "approved"
    assert record["approvalMethod"] == "config_file"
    assert record["approvedParameters"]["wallHeight"] == 3200.0
    assert record["approvedParameters"]["slabThickness"] == 180.0
