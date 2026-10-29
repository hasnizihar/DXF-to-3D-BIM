"""Independent model validator conforming to validation-report.schema.json."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import jsonschema

from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter, BimcraftBuildResult
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel

VALIDATION_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "skills"
    / "dxf-to-3d-bim"
    / "schemas"
    / "validation-report.schema.json"
)


class ModelValidator:
    """Independently verifies generated BIMCraft project and IFC models against intermediate specifications."""

    def __init__(self, adapter: Optional[BimcraftAdapter] = None):
        self.adapter = adapter or BimcraftAdapter()

    def validate(
        self,
        model: IntermediateBimModel,
        build_result: BimcraftBuildResult,
    ) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        checks: List[Dict[str, Any]] = []
        overall_status = "PASSED"

        # 1. Deliverables existence and size checks
        for label, file_path in [
            ("Native BIMCraft Project", build_result.bimcraft_path),
            ("IFC4 Export", build_result.ifc_path),
            ("Plan Preview PNG", build_result.png_path),
        ]:
            if file_path and file_path.exists():
                size = file_path.stat().st_size
                if size > 0:
                    checks.append({
                        "category": "Export Deliverables",
                        "name": f"{label} File Verification",
                        "status": "PASSED",
                        "details": f"File exists at {file_path.name} with size {size} bytes",
                    })
                else:
                    checks.append({
                        "category": "Export Deliverables",
                        "name": f"{label} File Verification",
                        "status": "FAILED",
                        "details": f"File {file_path.name} exists but has 0 bytes",
                    })
                    overall_status = "FAILED"
            else:
                checks.append({
                    "category": "Export Deliverables",
                    "name": f"{label} File Verification",
                    "status": "FAILED",
                    "details": f"File {label} was not found on disk",
                })
                overall_status = "FAILED"

        # 2. Inspect native .bimcraft project reopenability
        bimcraft_info = {}
        if build_result.bimcraft_path and build_result.bimcraft_path.exists():
            try:
                bimcraft_info = self.adapter.inspect_file(build_result.bimcraft_path)
                checks.append({
                    "category": "Native Project Inspection",
                    "name": "Reopen Native Project",
                    "status": "PASSED",
                    "details": "Successfully reopened and inspected .bimcraft project structure",
                })
            except Exception as e:
                checks.append({
                    "category": "Native Project Inspection",
                    "name": "Reopen Native Project",
                    "status": "FAILED",
                    "details": f"Failed to reopen native project: {e}",
                })
                overall_status = "FAILED"

        # 3. Inspect IFC structure and counts
        ifc_info = {}
        if build_result.ifc_path and build_result.ifc_path.exists():
            try:
                ifc_info = self.adapter.inspect_file(build_result.ifc_path)
                checks.append({
                    "category": "IFC Verification",
                    "name": "Parse IFC Model",
                    "status": "PASSED",
                    "details": f"IFC4 parsed successfully. Units: {ifc_info.get('units', 'unknown')}",
                })
            except Exception as e:
                checks.append({
                    "category": "IFC Verification",
                    "name": "Parse IFC Model",
                    "status": "FAILED",
                    "details": f"Failed to parse IFC file: {e}",
                })
                overall_status = "FAILED"

        # 4. Element count comparison
        expected_walls = len(model.data.get("walls", []))
        expected_doors = len([op for op in model.data.get("openings", []) if op.get("type") == "door"])
        expected_windows = len([op for op in model.data.get("openings", []) if op.get("type") == "window"])
        expected_levels = len(model.data.get("levels", []))

        actual_counts = ifc_info.get("counts", {})
        gen_walls = actual_counts.get("wall", 0)
        gen_doors = actual_counts.get("door", 0)
        gen_windows = actual_counts.get("window", 0)
        gen_levels = actual_counts.get("level", 0)

        # Walls check
        wall_diff = abs(gen_walls - expected_walls)
        checks.append({
            "category": "Geometric Topology",
            "name": "Wall Element Count",
            "status": "PASSED" if wall_diff == 0 else "WARNING",
            "details": f"Expected {expected_walls} walls, found {gen_walls} in IFC",
            "numericalDifference": float(wall_diff),
        })

        # Doors check
        door_diff = abs(gen_doors - expected_doors)
        checks.append({
            "category": "Geometric Topology",
            "name": "Door Opening Count",
            "status": "PASSED" if door_diff == 0 else "WARNING",
            "details": f"Expected {expected_doors} doors, found {gen_doors} in IFC",
            "numericalDifference": float(door_diff),
        })

        # Windows check
        win_diff = abs(gen_windows - expected_windows)
        checks.append({
            "category": "Geometric Topology",
            "name": "Window Opening Count",
            "status": "PASSED" if win_diff == 0 else "WARNING",
            "details": f"Expected {expected_windows} windows, found {gen_windows} in IFC",
            "numericalDifference": float(win_diff),
        })

        if any(c["status"] == "FAILED" for c in checks):
            overall_status = "FAILED"
        elif any(c["status"] == "WARNING" for c in checks):
            overall_status = "WARNING"

        report: Dict[str, Any] = {
            "timestamp": now_iso,
            "projectName": model.data.get("metadata", {}).get("projectName", "BimProject"),
            "overallStatus": overall_status,
            "checks": checks,
            "elementSummary": {
                "expected": {
                    "walls": expected_walls,
                    "doors": expected_doors,
                    "windows": expected_windows,
                    "levels": expected_levels,
                },
                "generated": {
                    "walls": gen_walls,
                    "doors": gen_doors,
                    "windows": gen_windows,
                    "levels": gen_levels,
                },
            },
            "deliverables": {
                "bimcraftPath": str(build_result.bimcraft_path) if build_result.bimcraft_path else "",
                "ifcPath": str(build_result.ifc_path) if build_result.ifc_path else "",
                "previewPngPath": str(build_result.png_path) if build_result.png_path else "",
            },
        }

        # Validate against schema
        if VALIDATION_SCHEMA_PATH.exists():
            with open(VALIDATION_SCHEMA_PATH, "r", encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(instance=report, schema=schema)

        return report
