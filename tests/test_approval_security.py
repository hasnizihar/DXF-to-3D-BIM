"""Comprehensive tests for approval security, hash tamper protection, and gate enforcement."""

import pytest
from dxf_to_3d_bim.approval import ApprovalGate, compute_model_hash
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall

def test_tamper_detection_on_wall_coordinates():
    walls = [ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(5000, 0), thickness=200)]
    model = IntermediateBimModel.create("SecureProject", "test.dxf", "mm", 1.0, walls, [], [], [])

    # Step 1: Human approves
    ApprovalGate.approve(model, approved_by="Project Architect", notes="Approved initial design")
    valid, msg = ApprovalGate.verify_approval(model)
    assert valid is True

    # Step 2: Modification to wall start coordinate
    model.data["walls"][0]["start"][0] = 50.0  # shifted by 50mm

    # Step 3: Approval gate must detect tamper and reject
    valid, msg = ApprovalGate.verify_approval(model)
    assert valid is False
    assert "changed since approval" in msg

def test_tamper_detection_on_opening_dimensions():
    walls = [ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(5000, 0), thickness=200)]
    model = IntermediateBimModel.create("SecureProject", "test.dxf", "mm", 1.0, walls, [], [], [])
    ApprovalGate.approve(model)

    # Add unauthorized opening after approval
    model.data["openings"].append({
        "id": "unapproved_door",
        "type": "door",
        "wallId": "w1",
        "center": [2500, 0],
        "width": 1000,
        "height": 2100,
        "confidence": "low",
    })

    valid, msg = ApprovalGate.verify_approval(model)
    assert valid is False
    assert "changed since approval" in msg

def test_stale_or_replaced_approval_hash():
    walls = [ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(5000, 0), thickness=200)]
    model = IntermediateBimModel.create("SecureProject", "test.dxf", "mm", 1.0, walls, [], [], [])
    ApprovalGate.approve(model)

    # Attacker replaces modelHash with arbitrary fake hash
    model.data["approval"]["modelHash"] = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    valid, msg = ApprovalGate.verify_approval(model)
    assert valid is False
    assert "changed since approval" in msg

def test_adapter_refuses_unapproved_or_tampered_model(tmp_path):
    adapter = BimcraftAdapter()
    walls = [ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(5000, 0), thickness=200)]
    model = IntermediateBimModel.create("TamperedBuild", "test.dxf", "mm", 1.0, walls, [], [], [])

    # Attempt build when unapproved
    with pytest.raises(PermissionError) as exc_info:
        adapter.execute_build(model, output_dir=tmp_path)
    assert "not been approved" in str(exc_info.value)

    # Approve then tamper
    ApprovalGate.approve(model)
    model.data["walls"][0]["thickness"] = 350.0

    with pytest.raises(PermissionError) as exc_info:
        adapter.execute_build(model, output_dir=tmp_path)
    assert "changed since approval" in str(exc_info.value)
