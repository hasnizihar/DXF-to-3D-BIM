"""Mandatory approval gate enforcing persistent, version-bound human approval."""

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Tuple
import jsonschema

from dxf_to_3d_bim.intermediate_model import IntermediateBimModel

APPROVAL_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "skills" / "dxf-to-3d-bim" / "schemas" / "approval.schema.json"


def compute_model_hash(model_data: Dict[str, Any]) -> str:
    """Computes deterministic SHA-256 hash of geometric and architectural content."""
    canonical = copy.deepcopy(model_data)
    # Exclude metadata timestamps and approval block for hashing
    if "metadata" in canonical:
        canonical["metadata"].pop("updatedAt", None)
        canonical["metadata"].pop("createdAt", None)
    canonical.pop("approval", None)
    canonical.pop("status", None)

    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ApprovalGate:
    """Enforces that intermediate models cannot be sent to BIM generation without valid human approval."""

    @staticmethod
    def generate_proposal_summary(model: IntermediateBimModel) -> Dict[str, Any]:
        d = model.data
        walls = d.get("walls", [])
        openings = d.get("openings", [])
        floors = d.get("floors", [])
        assumptions = d.get("assumptions", [])

        ext_walls = [w for w in walls if w.get("classification") == "exterior"]
        int_walls = [w for w in walls if w.get("classification") == "interior"]
        doors = [op for op in openings if op.get("type") == "door"]
        windows = [op for op in openings if op.get("type") == "window"]

        # Approximate footprint
        min_x = min([w["start"][0] for w in walls] + [w["end"][0] for w in walls]) if walls else 0
        max_x = max([w["start"][0] for w in walls] + [w["end"][0] for w in walls]) if walls else 0
        min_y = min([w["start"][1] for w in walls] + [w["end"][1] for w in walls]) if walls else 0
        max_y = max([w["start"][1] for w in walls] + [w["end"][1] for w in walls]) if walls else 0

        width = round(max_x - min_x, 2)
        depth = round(max_y - min_y, 2)

        return {
            "projectName": d.get("metadata", {}).get("projectName", "Project"),
            "modelHash": compute_model_hash(d),
            "footprint": {
                "width_mm": width,
                "depth_mm": depth,
                "area_m2": round((width * depth) / 1_000_000.0, 2),
            },
            "counts": {
                "exterior_walls": len(ext_walls),
                "interior_walls": len(int_walls),
                "doors": len(doors),
                "windows": len(windows),
                "floors": len(floors),
            },
            "proposed_vertical_parameters": {
                "storeys": len(d.get("levels", [])),
                "wall_height_mm": walls[0].get("height", 3000.0) if walls else 3000.0,
                "slab_thickness_mm": floors[0].get("thickness", 150.0) if floors else 150.0,
                "window_sill_height_mm": windows[0].get("sillHeight", 900.0) if windows else 900.0,
            },
            "uncertainties": assumptions,
        }

    @staticmethod
    def approve(
        model: IntermediateBimModel,
        approved_by: str = "Authorized Reviewer",
        notes: str = "Approved for BIMCraft construction",
    ) -> Dict[str, Any]:
        """Applies approval to the model and updates status."""
        model_hash = compute_model_hash(model.data)
        now_iso = datetime.now(timezone.utc).isoformat()

        model.data["status"] = "approved"
        model.data["approval"] = {
            "isApproved": True,
            "approvedBy": approved_by,
            "approvedAt": now_iso,
            "modelHash": model_hash,
            "notes": notes,
        }
        model.data["metadata"]["updatedAt"] = now_iso

        # Validate against approval.schema.json
        summary = ApprovalGate.generate_proposal_summary(model)
        vert = summary["proposed_vertical_parameters"]

        approval_record = {
            "projectName": model.data.get("metadata", {}).get("projectName", "Project"),
            "modelHash": model_hash,
            "status": "approved",
            "approvedBy": approved_by,
            "timestamp": now_iso,
            "approvedParameters": {
                "storeyCount": vert["storeys"],
                "wallHeight": vert["wall_height_mm"],
                "slabThickness": vert["slab_thickness_mm"],
            },
            "notes": notes,
        }

        if APPROVAL_SCHEMA_PATH.exists():
            with open(APPROVAL_SCHEMA_PATH, "r", encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(instance=approval_record, schema=schema)

        return approval_record

    @staticmethod
    def verify_approval(model: IntermediateBimModel) -> Tuple[bool, str]:
        """Verifies that the model has valid, untampered approval."""
        approval = model.data.get("approval", {})
        if not approval.get("isApproved", False):
            return False, "Model has not been approved (approval.isApproved is False)."

        current_hash = compute_model_hash(model.data)
        recorded_hash = approval.get("modelHash", "")

        if current_hash != recorded_hash:
            return False, (
                f"Model content has changed since approval! Recorded hash: {recorded_hash[:8]}..., "
                f"Current hash: {current_hash[:8]}... Prior approval is invalidated."
            )

        if model.data.get("status") != "approved":
            return False, f"Model status is '{model.data.get('status')}', must be 'approved'."

        return True, "Approval is valid."

