"""Tests for the mandatory human approval gate and hash verification."""

import pytest
from dxf_to_3d_bim.approval import ApprovalGate, compute_model_hash
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall

def test_approval_flow():
    walls = [ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(4000, 0), thickness=200)]
    model = IntermediateBimModel.create("TestApprove", "t.dxf", "mm", 1.0, walls, [], [], [])

    # Initially not approved
    valid, reason = ApprovalGate.verify_approval(model)
    assert not valid
    assert "not been approved" in reason

    # Approve
    record = ApprovalGate.approve(model, approved_by="Architect", notes="Looks great")
    assert model.data["status"] == "approved"
    assert model.data["approval"]["isApproved"] is True
    assert record["approvedParameters"]["wallHeight"] == 3000.0

    valid, _ = ApprovalGate.verify_approval(model)
    assert valid

def test_tamper_invalidates_approval():
    walls = [ReconstructedWall(id="w1", classification="exterior", start=(0, 0), end=(4000, 0), thickness=200)]
    model = IntermediateBimModel.create("TestTamper", "t.dxf", "mm", 1.0, walls, [], [], [])
    ApprovalGate.approve(model)

    # Modify wall geometry after approval
    model.data["walls"][0]["end"] = [8000.0, 0.0]

    # Verification must fail because hash changed
    valid, reason = ApprovalGate.verify_approval(model)
    assert not valid
    assert "changed since approval" in reason
