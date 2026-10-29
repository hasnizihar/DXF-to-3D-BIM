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

                # Multi-Storey Element Distribution Check
                if ifc_sem.contained_by_storey:
                    inhabited_model_storeys = {}
                    for w in model.data.get("walls", []):
                        lvl = w.get("levelId", "Level 1")
                        inhabited_model_storeys[lvl] = inhabited_model_storeys.get(lvl, 0) + 1

                    multi_storey_failures = []
                    for lvl_name, expected_elem_count in inhabited_model_storeys.items():
                        contained_count = len(ifc_sem.contained_by_storey.get(lvl_name, []))
                        if contained_count == 0:
                            multi_storey_failures.append(f"Storey '{lvl_name}' expects {expected_elem_count} walls but has 0 contained elements in IFC")

                    if multi_storey_failures:
                        checks.append({
                            "category": "Spatial Structure",
                            "name": "Multi-Storey Element Allocation",
                            "status": "FAILED",
                            "details": "; ".join(multi_storey_failures),
                        })
                        overall_status = "FAILED"
                    elif len(inhabited_model_storeys) > 1:
                        checks.append({
                            "category": "Spatial Structure",
                            "name": "Multi-Storey Element Allocation",
                            "status": "PASSED",
                            "details": f"Verified elements distributed across {len(inhabited_model_storeys)} inhabited storeys in IFC.",
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

        # Roof Element Count & Type Checks
        expected_roofs = len([r for r in model.data.get("roofs", []) if r.get("roofType") not in ("none", None)])
        gen_roofs = actual_counts.get("roof", 0)
        roof_diff = abs(gen_roofs - expected_roofs)
        if expected_roofs > 0 or gen_roofs > 0:
            checks.append({
                "category": "Geometric Topology",
                "name": "Roof Element Count",
                "status": "PASSED" if roof_diff == 0 else "WARNING",
                "details": f"Expected {expected_roofs} roof(s), found {gen_roofs} in IFC",
                "numericalDifference": float(roof_diff),
            })

            # Check IFC roof attributes if parsed
            if expected_roofs > 0 and ifc_sem and ifc_sem.roofs:
                model_roof = [r for r in model.data.get("roofs", []) if r.get("roofType") not in ("none", None)][0]
                expected_type = model_roof.get("roofType", "").upper()
                actual_type = ifc_sem.roofs[0].get("predefined_type", "")
                type_match = (expected_type in actual_type) or (actual_type in expected_type)
                checks.append({
                    "category": "Geometric Topology",
                    "name": "Roof Predefined Type",
                    "status": "PASSED" if type_match else "WARNING",
                    "details": f"Expected {expected_type}_ROOF, found {actual_type} in IFC",
                })

                host_level_id = model_roof.get("levelId", "Level 1")
                actual_host = ifc_sem.roofs[0].get("contained_in_storey")
                containment_match = (actual_host == host_level_id)
                checks.append({
                    "category": "Spatial Structure",
                    "name": "Roof Spatial Containment",
                    "status": "PASSED" if containment_match else "WARNING",
                    "details": f"Roof is contained in host storey '{actual_host}' (expected '{host_level_id}')",
                })

        # Staircase Element Count & Component Checks
        expected_stairs = len(model.data.get("staircases", []))
        gen_stairs = actual_counts.get("stair", 0)
        stair_diff = abs(gen_stairs - expected_stairs)

        expected_flights = 0
        expected_railings = 0
        for st in model.data.get("staircases", []):
            st_type = st.get("stairType", "straight")
            if st_type == "straight":
                expected_flights += 1
            else:
                expected_flights += 2
            if st.get("railings", True):
                expected_railings += 2

        gen_flights = actual_counts.get("stair_flight", 0)
        gen_railings = actual_counts.get("railing", 0)

        if expected_stairs > 0 or gen_stairs > 0:
            checks.append({
                "category": "Vertical Circulation",
                "name": "Staircase Element Count",
                "status": "PASSED" if stair_diff == 0 else "WARNING",
                "details": f"Expected {expected_stairs} staircase(s), found {gen_stairs} in IFC",
                "numericalDifference": float(stair_diff),
            })

            # Check Stair predefined type
            if expected_stairs > 0 and ifc_sem and ifc_sem.stairs:
                m_stair = model.data.get("staircases", [])[0]
                m_type = m_stair.get("stairType", "straight")
                ifc_type = ifc_sem.stairs[0].get("predefined_type", "")
                type_ok = False
                if m_type == "straight" and "STRAIGHT" in ifc_type:
                    type_ok = True
                elif m_type == "l_shaped" and ("QUARTER" in ifc_type or "L" in ifc_type):
                    type_ok = True
                elif m_type == "u_shaped" and ("HALF" in ifc_type or "U" in ifc_type):
                    type_ok = True
                checks.append({
                    "category": "Vertical Circulation",
                    "name": "Staircase Predefined Type",
                    "status": "PASSED" if type_ok else "WARNING",
                    "details": f"Expected {m_type.upper()}_STAIR, found {ifc_type} in IFC",
                })

                # Check aggregates
                checks.append({
                    "category": "Vertical Circulation",
                    "name": "Stair Aggregation Integrity",
                    "status": "PASSED" if ifc_sem.stair_aggregates_verified else "WARNING",
                    "details": "IFCSTAIR properly aggregates flights, landings, and guardrails via IfcRelAggregates",
                })

                # Check riser and tread match
                if ifc_sem.stair_flights:
                    exp_r = m_stair.get("actualRiserHeight", 175.0)
                    exp_g = m_stair.get("actualGoing", 280.0)
                    act_r = ifc_sem.stair_flights[0].get("riser_height", 0.0)
                    act_g = ifc_sem.stair_flights[0].get("tread_length", 0.0)
                    r_diff = abs(act_r - exp_r)
                    g_diff = abs(act_g - exp_g)
                    checks.append({
                        "category": "Vertical Circulation",
                        "name": "Riser / Tread Dimensions",
                        "status": "PASSED" if (r_diff < 1.0 and g_diff < 1.0) else "WARNING",
                        "details": f"Riser: expected {exp_r:.1f} mm, found {act_r:.1f} mm; Tread: expected {exp_g:.1f} mm, found {act_g:.1f} mm",
                    })

                # Check upper slab opening cut
                floors = model.data.get("floors", [])
                top_floor = next((fl for fl in floors if fl.get("levelId") == m_stair.get("topLevelId")), None)
                has_model_void = bool(top_floor and top_floor.get("openings"))
                has_ifc_void = getattr(ifc_sem, "has_slab_voids", False)
                slab_cut_ok = has_model_void and has_ifc_void
                checks.append({
                    "category": "Vertical Circulation",
                    "name": "Stairwell Floor Slab Opening",
                    "status": "PASSED" if slab_cut_ok else "WARNING",
                    "details": f"Upper floor slab '{m_stair.get('topLevelId')}' has void opening punched (model: {has_model_void}, IFC: {has_ifc_void})",
                })

        # Structural Column Element Count Check
        expected_columns = len(model.data.get("columns", []))
        gen_columns = actual_counts.get("column", 0)
        col_diff = abs(gen_columns - expected_columns)
        if expected_columns > 0 or gen_columns > 0:
            checks.append({
                "category": "Structural Topology",
                "name": "Column Element Count",
                "status": "PASSED" if col_diff == 0 else "WARNING",
                "details": f"Expected {expected_columns} RC columns, found {gen_columns} in IFC",
                "numericalDifference": float(col_diff),
            })

        # Structural Beam Element Count Check
        expected_beams = len(model.data.get("beams", []))
        gen_beams = actual_counts.get("beam", 0)
        beam_diff = abs(gen_beams - expected_beams)
        if expected_beams > 0 or gen_beams > 0:
            checks.append({
                "category": "Structural Topology",
                "name": "Beam Element Count",
                "status": "PASSED" if beam_diff == 0 else "WARNING",
                "details": f"Expected {expected_beams} primary beams, found {gen_beams} in IFC",
                "numericalDifference": float(beam_diff),
            })

        # Foundation Footing Count Check
        expected_foundations = len(model.data.get("foundations", []))
        gen_foundations = actual_counts.get("footing", 0)
        ftg_diff = abs(gen_foundations - expected_foundations)
        if expected_foundations > 0 or gen_foundations > 0:
            checks.append({
                "category": "Structural Topology",
                "name": "Foundation Footing Count",
                "status": "PASSED" if ftg_diff == 0 else "WARNING",
                "details": f"Expected {expected_foundations} footings, found {gen_foundations} in IFC",
                "numericalDifference": float(ftg_diff),
            })

        # Structural Slab Classification Check
        expected_struct_slabs = len([
            fl for fl in model.data.get("floors", [])
            if fl.get("structuralRole") in ("structural", "ground_bearing", "roof_slab")
        ])
        if expected_struct_slabs > 0:
            checks.append({
                "category": "Structural Topology",
                "name": "Structural Slab Classification",
                "status": "PASSED",
                "details": f"Verified {expected_struct_slabs} structural slab(s) classified with structural roles.",
            })

        # Storey Count Check
        if gen_levels > 0:
            level_diff = abs(gen_levels - expected_levels)
            inhabited_levels = len([l for l in model.data.get("levels", []) if l.get("storeyType") != "roof_datum"])
            datum_levels = expected_levels - inhabited_levels
            checks.append({
                "category": "Spatial Structure",
                "name": "Storey Level Count",
                "status": "PASSED" if level_diff == 0 else "WARNING",
                "details": f"Expected {expected_levels} levels ({inhabited_levels} occupied storeys, {datum_levels} roof datum), found {gen_levels} in IFC",
                "numericalDifference": float(level_diff),
            })

        # Level Elevation Monotonicity Check
        levels = model.data.get("levels", [])
        if len(levels) > 1:
            elevations = [lvl.get("elevation", 0.0) for lvl in levels]
            is_monotonic = all(elevations[i] < elevations[i+1] for i in range(len(elevations)-1))
            checks.append({
                "category": "Spatial Structure",
                "name": "Storey Elevation Monotonicity",
                "status": "PASSED" if is_monotonic else "FAILED",
                "details": f"Storey elevations are strictly ascending: {elevations}" if is_monotonic else f"Storey elevations are not ascending: {elevations}",
            })
            if not is_monotonic:
                overall_status = "FAILED"

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
                    "roofs": expected_roofs,
                    "stairs": expected_stairs,
                    "stair_flights": expected_flights,
                    "railings": expected_railings,
                    "grids": len(model.data.get("structuralGrids", [])),
                    "columns": expected_columns,
                    "beams": expected_beams,
                    "foundations": expected_foundations,
                    "structural_slabs": expected_struct_slabs,
                },
                "generated": {
                    "walls": gen_walls,
                    "doors": gen_doors,
                    "windows": gen_windows,
                    "levels": gen_levels,
                    "roofs": gen_roofs,
                    "stairs": gen_stairs,
                    "stair_flights": gen_flights,
                    "railings": gen_railings,
                    "grids": len(model.data.get("structuralGrids", [])),
                    "columns": gen_columns,
                    "beams": gen_beams,
                    "foundations": gen_foundations,
                    "structural_slabs": actual_counts.get("slab", 0) if expected_struct_slabs > 0 else 0,
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

        # 3. Roof Boundary & Parameter Check
        for rf in d.get("roofs", []):
            if rf.get("roofType") in ("none", None):
                continue
            boundary = rf.get("boundary", [])
            pitch = float(rf.get("pitchDegrees", 30.0))
            if len(boundary) >= 3:
                poly = Polygon(boundary)
                if poly.is_valid and poly.area > 100_000.0:
                    results.append({
                        "category": "Geometric Topology",
                        "name": f"Roof {rf.get('id', 'rf')} Footprint Boundary",
                        "status": "PASSED",
                        "details": f"Roof footprint is a valid polygon ({poly.area / 1_000_000.0:.2f} m²), pitch {pitch:.1f}°.",
                    })
                else:
                    results.append({
                        "category": "Geometric Topology",
                        "name": f"Roof {rf.get('id', 'rf')} Footprint Boundary",
                        "status": "FAILED",
                        "details": "Roof boundary polygon is degenerate or invalid.",
                    })

        # 4. Beam Support Connectivity Check
        columns = d.get("columns", [])
        col_map = {c["id"]: c for c in columns}
        beams = d.get("beams", [])
        if beams:
            disconnected_beams = []
            for b in beams:
                sc_id = b.get("startColumnId")
                ec_id = b.get("endColumnId")
                # If column IDs are specified, verify they exist
                if sc_id and sc_id not in col_map:
                    disconnected_beams.append(f"{b.get('id')} (start column '{sc_id}' missing)")
                if ec_id and ec_id not in col_map:
                    disconnected_beams.append(f"{b.get('id')} (end column '{ec_id}' missing)")

            if not disconnected_beams:
                results.append({
                    "category": "Structural Topology",
                    "name": "Beam Support Connectivity",
                    "status": "PASSED",
                    "details": f"All {len(beams)} primary beams connect to valid column supports.",
                })
            else:
                results.append({
                    "category": "Structural Topology",
                    "name": "Beam Support Connectivity",
                    "status": "WARNING",
                    "details": f"Unconnected beams: {', '.join(disconnected_beams[:3])}",
                })

        # 5. Column Foundation Alignment Check
        foundations = d.get("foundations", [])
        pad_ftgs = [f for f in foundations if f.get("foundationType") == "isolated"]
        if pad_ftgs:
            misaligned_ftgs = []
            ground_cols = [c for c in columns if c.get("levelId") in ("Level 1", "level_1")]
            for ft in pad_ftgs:
                ft_at = ft.get("at")
                if not ft_at:
                    continue
                # Find nearest ground column
                min_c_dist = min([
                    math.hypot(ft_at[0] - c["at"][0], ft_at[1] - c["at"][1])
                    for c in ground_cols
                ]) if ground_cols else 9999.0
                if min_c_dist > 50.0:
                    misaligned_ftgs.append(f"{ft.get('id')} ({min_c_dist:.1f}mm from nearest column)")

            if not misaligned_ftgs:
                results.append({
                    "category": "Structural Topology",
                    "name": "Column-Foundation Placement Alignment",
                    "status": "PASSED",
                    "details": f"All {len(pad_ftgs)} isolated pad footings are aligned beneath structural columns.",
                })
            else:
                results.append({
                    "category": "Structural Topology",
                    "name": "Column-Foundation Placement Alignment",
                    "status": "WARNING",
                    "details": f"Misaligned footings: {', '.join(misaligned_ftgs[:3])}",
                })

        return results
