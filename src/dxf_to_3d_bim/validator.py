"""Independent model validator conforming to validation-report.schema.json with deep IFC and geometric checks."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import jsonschema
from shapely.geometry import Polygon, Point, LineString

from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter, BimcraftBuildResult
from dxf_to_3d_bim.ifc_parser import PureIfcParser
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

        # 1. Deliverables existence and non-zero size checks
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
        if build_result.bimcraft_path and build_result.bimcraft_path.exists():
            try:
                self.adapter.inspect_file(build_result.bimcraft_path)
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

        # 3. Deep Independent IFC4 Parsing & Relationship Verification
        actual_counts: Dict[str, int] = {}
        if build_result.ifc_path and build_result.ifc_path.exists():
            try:
                ifc_parser = PureIfcParser(build_result.ifc_path)
                ifc_sem = ifc_parser.inspect()
                actual_counts = ifc_sem.counts

                checks.append({
                    "category": "IFC Verification",
                    "name": "Parse IFC Model",
                    "status": "PASSED",
                    "details": f"IFC4 parsed successfully (schema: {ifc_sem.schema})",
                })

                # Opening Void & Wall Penetration Check
                if ifc_sem.voids_verified and ifc_sem.fills_verified:
                    checks.append({
                        "category": "Geometric Topology",
                        "name": "Wall Voiding and Opening Penetration",
                        "status": "PASSED",
                        "details": "All doors and windows are verified to create IfcOpeningElement voids that cut their host IfcWalls via IfcRelVoidsElement and IfcRelFillsElement.",
                    })
                else:
                    checks.append({
                        "category": "Geometric Topology",
                        "name": "Wall Voiding and Opening Penetration",
                        "status": "FAILED",
                        "details": "One or more openings do not properly void their host walls in IFC.",
                    })
                    overall_status = "FAILED"

                # Spatial Storey Containment Check
                if ifc_sem.containment_verified:
                    checks.append({
                        "category": "Spatial Structure",
                        "name": "Storey Containment",
                        "status": "PASSED",
                        "details": "All architectural elements are formally assigned to building storeys via IfcRelContainedInSpatialStructure.",
                    })
                else:
                    checks.append({
                        "category": "Spatial Structure",
                        "name": "Storey Containment",
                        "status": "WARNING",
                        "details": "Some elements lack formal IfcRelContainedInSpatialStructure association.",
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

        gen_walls = actual_counts.get("wall", 0)
        gen_doors = actual_counts.get("door", 0)
        gen_windows = actual_counts.get("window", 0)
        gen_levels = actual_counts.get("storey", 0)

        wall_diff = abs(gen_walls - expected_walls)
        checks.append({
            "category": "Geometric Topology",
            "name": "Wall Element Count",
            "status": "PASSED" if wall_diff == 0 else "WARNING",
            "details": f"Expected {expected_walls} walls, found {gen_walls} in IFC",
            "numericalDifference": float(wall_diff),
        })

        door_diff = abs(gen_doors - expected_doors)
        checks.append({
            "category": "Geometric Topology",
            "name": "Door Opening Count",
            "status": "PASSED" if door_diff == 0 else "WARNING",
            "details": f"Expected {expected_doors} doors, found {gen_doors} in IFC",
            "numericalDifference": float(door_diff),
        })

        win_diff = abs(gen_windows - expected_windows)
        checks.append({
            "category": "Geometric Topology",
            "name": "Window Opening Count",
            "status": "PASSED" if win_diff == 0 else "WARNING",
            "details": f"Expected {expected_windows} windows, found {gen_windows} in IFC",
            "numericalDifference": float(win_diff),
        })

        # 5. Deep Geometric Integrity Checks
        geom_checks = self._validate_model_geometry(model)
        checks.extend(geom_checks)

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

    def _validate_model_geometry(self, model: IntermediateBimModel) -> List[Dict[str, Any]]:
        """Validates opening placements, wall lengths, and slab boundaries."""
        results: List[Dict[str, Any]] = []
        d = model.data
        wall_map = {w["id"]: w for w in d.get("walls", [])}

        # 1. Opening Placement & Wall Overhang Check
        misaligned_openings = []
        overhanging_openings = []

        for op in d.get("openings", []):
            op_id = op.get("id", "op")
            wall_id = op.get("wallId")
            host_wall = wall_map.get(wall_id)

            if not host_wall:
                misaligned_openings.append(f"{op_id} (missing host wall '{wall_id}')")
                continue

            # Line of host wall
            p1 = host_wall["start"]
            p2 = host_wall["end"]
            line = LineString([p1, p2])
            center_pt = Point(op["center"])
            dist = line.distance(center_pt)

            if dist > 50.0:  # mm
                misaligned_openings.append(f"{op_id} (distance {dist:.1f}mm from wall '{wall_id}')")

            # Check overhang: width cannot exceed wall length
            wall_len = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            width = op.get("width", 900.0)
            if width > wall_len + 50.0:
                overhanging_openings.append(f"{op_id} (width {width}mm exceeds wall length {wall_len:.1f}mm)")

        if not misaligned_openings:
            results.append({
                "category": "Geometric Topology",
                "name": "Opening Host Alignment",
                "status": "PASSED",
                "details": f"All {len(d.get('openings', []))} openings align within tolerance to their host walls.",
            })
        else:
            results.append({
                "category": "Geometric Topology",
                "name": "Opening Host Alignment",
                "status": "WARNING",
                "details": f"Misaligned openings: {', '.join(misaligned_openings[:3])}",
            })

        if not overhanging_openings:
            results.append({
                "category": "Geometric Topology",
                "name": "Opening Boundary Containment",
                "status": "PASSED",
                "details": "All opening widths fit cleanly within their host wall lengths.",
            })
        else:
            results.append({
                "category": "Geometric Topology",
                "name": "Opening Boundary Containment",
                "status": "WARNING",
                "details": f"Overhanging openings: {', '.join(overhanging_openings[:3])}",
            })

        # 2. Floor Slab Boundary Closure & Area Check
        for fl in d.get("floors", []):
            boundary = fl.get("boundary", [])
            if len(boundary) >= 3:
                poly = Polygon(boundary)
                if poly.is_valid and poly.area > 100_000.0:  # > 0.1 m2
                    results.append({
                        "category": "Geometric Topology",
                        "name": f"Floor Slab {fl.get('id', 'fl')} Boundary",
                        "status": "PASSED",
                        "details": f"Slab boundary is a closed, valid polygon with area {poly.area / 1_000_000.0:.2f} m².",
                    })
                else:
                    results.append({
                        "category": "Geometric Topology",
                        "name": f"Floor Slab {fl.get('id', 'fl')} Boundary",
                        "status": "FAILED",
                        "details": "Slab boundary polygon is self-intersecting or invalid.",
                    })

        return results
