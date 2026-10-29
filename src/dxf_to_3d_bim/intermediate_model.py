"""Intermediate BIM model module conforming to bim-model.schema.json."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import jsonschema


SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "skills" / "dxf-to-3d-bim" / "schemas" / "bim-model.schema.json"


class IntermediateBimModel:
    """Represents the engine-independent, semantically structured 3D BIM model."""

    def __init__(self, data: Dict[str, Any]):
        self.data = data

    @classmethod
    def create(
        cls,
        project_name: str,
        source_dxf_path: str,
        source_units: str,
        scale_factor: float,
        walls: List[Any],
        openings: List[Any],
        floors: List[Any],
        rooms: List[Any],
        assumptions: Optional[List[Dict[str, Any]]] = None,
        source_json_path: Optional[str] = None,
        storeys_count: int = 1,
        storey_heights: Optional[List[float]] = None,
        ground_elevation: float = 0.0,
        repeat_ground_floor: bool = False,
        storey_config: Optional[Dict[str, Any]] = None,
        levels_override: Optional[List[Dict[str, Any]]] = None,
    ) -> "IntermediateBimModel":
        now_iso = datetime.now(timezone.utc).isoformat()

        # Build walls dicts
        wall_dicts = []
        for w in walls:
            item = {
                "id": w.id,
                "classification": w.classification,
                "start": [w.start[0], w.start[1]],
                "end": [w.end[0], w.end[1]],
                "thickness": w.thickness,
                "height": getattr(w, "height", 3000.0),
                "levelId": getattr(w, "level_id", "Level 1"),
                "confidence": getattr(w, "confidence", "high"),
                "sourceEntities": getattr(w, "source_entities", []),
            }
            if hasattr(w, "base_elevation") and w.base_elevation is not None:
                item["baseElevation"] = float(w.base_elevation)
            wall_dicts.append(item)

        # Build openings dicts
        opening_dicts = []
        for op in openings:
            item_op: Dict[str, Any] = {
                "id": op.id,
                "type": op.type,
                "wallId": op.wall_id,
                "center": [op.center[0], op.center[1]],
                "width": op.width,
                "height": op.height,
                "levelId": getattr(op, "level_id", getattr(op, "levelId", "Level 1")),
                "confidence": getattr(op, "confidence", "high"),
            }
            if op.sill_height is not None:
                item_op["sillHeight"] = op.sill_height
            if getattr(op, "swing", None):
                item_op["swing"] = op.swing
            opening_dicts.append(item_op)

        # Build floor dicts
        floor_dicts = []
        for fl in floors:
            floor_dicts.append({
                "id": fl.id,
                "levelId": fl.level_id,
                "thickness": fl.thickness,
                "elevation": fl.elevation,
                "boundary": [[p[0], p[1]] for p in fl.boundary],
            })

        # Build room dicts
        room_dicts = []
        for rm in rooms:
            room_dicts.append({
                "id": rm.id,
                "name": rm.name,
                "levelId": rm.level_id,
                "approximateArea": rm.approximate_area,
                "labelPosition": [rm.label_position[0], rm.label_position[1]],
            })

        # Configure levels and multi-storey replication
        if levels_override:
            levels = levels_override
        elif storey_config and "storeys" in storey_config:
            levels = []
            curr_elev = ground_elevation
            cfg_storeys = storey_config["storeys"]
            for st in cfg_storeys:
                st_idx = st.get("index", len(levels) + 1)
                st_name = st.get("name", f"Level {st_idx}")
                st_height = float(st.get("height", 3000.0))
                st_elev = float(st.get("elevation", curr_elev))
                levels.append({
                    "id": f"level_{st_idx}",
                    "name": st_name,
                    "elevation": st_elev,
                    "height": st_height,
                    "index": st_idx,
                    "storeyType": "ground" if st_idx == 1 else "upper",
                    "provenance": "user_configured_custom",
                })
                curr_elev = st_elev + st_height
            # Top datum
            top_idx = len(levels) + 1
            levels.append({
                "id": f"level_{top_idx}",
                "name": f"Level {top_idx}",
                "elevation": curr_elev,
                "height": 0.0,
                "index": top_idx,
                "storeyType": "roof_datum",
                "provenance": "default",
            })
        elif storeys_count > 1:
            levels = []
            curr_elev = ground_elevation
            heights = storey_heights or [3000.0] * storeys_count
            while len(heights) < storeys_count:
                heights.append(3000.0)

            for i in range(storeys_count):
                st_idx = i + 1
                st_name = f"Level {st_idx}"
                st_height = float(heights[i])
                levels.append({
                    "id": f"level_{st_idx}",
                    "name": st_name,
                    "elevation": curr_elev,
                    "height": st_height,
                    "index": st_idx,
                    "storeyType": "ground" if st_idx == 1 else "upper",
                    "provenance": "user_configured_repeated" if repeat_ground_floor else "default",
                })
                curr_elev += st_height

            # Top datum
            top_idx = storeys_count + 1
            levels.append({
                "id": f"level_{top_idx}",
                "name": f"Level {top_idx}",
                "elevation": curr_elev,
                "height": 0.0,
                "index": top_idx,
                "storeyType": "roof_datum",
                "provenance": "default",
            })
        else:
            # Baseline single-storey default (backward compatible)
            h0 = wall_dicts[0].get("height", 3000.0) if wall_dicts else 3000.0
            levels = [
                {"id": "level_1", "name": "Level 1", "elevation": ground_elevation, "height": h0},
                {"id": "level_2", "name": "Level 2", "elevation": ground_elevation + h0, "height": h0},
            ]

        # Multi-storey replication of ground floor geometry if requested
        if (repeat_ground_floor or (storey_config and any(s.get("repeat_footprint") for s in storey_config.get("storeys", [])))) and (storeys_count > 1 or (storey_config and len(storey_config.get("storeys", [])) > 1)):
            target_storeys = storeys_count if storeys_count > 1 else len(storey_config["storeys"])
            # Isolate ground floor elements
            base_walls = [w for w in wall_dicts if w.get("levelId") in ("Level 1", "level_1")]
            base_openings = [op for op in opening_dicts if op.get("levelId") in ("Level 1", "level_1") or not op.get("levelId")]
            base_floors = [fl for fl in floor_dicts if fl.get("levelId") in ("Level 1", "level_1")]

            # Ensure ground elements have explicit baseElevation 0.0
            for w in base_walls:
                if "baseElevation" not in w:
                    w["baseElevation"] = ground_elevation

            for i in range(2, target_storeys + 1):
                level_meta = next((l for l in levels if l.get("name") == f"Level {i}"), None)
                storey_elev = level_meta["elevation"] if level_meta else (ground_elevation + (i - 1) * 3000.0)
                storey_height = level_meta["height"] if level_meta else 3000.0

                # Replicate walls
                for w in base_walls:
                    rep_w_id = f"{w['id']}_L{i}"
                    wall_dicts.append({
                        "id": rep_w_id,
                        "classification": w["classification"],
                        "start": list(w["start"]),
                        "end": list(w["end"]),
                        "thickness": w["thickness"],
                        "height": storey_height,
                        "levelId": f"Level {i}",
                        "baseElevation": storey_elev,
                        "confidence": w.get("confidence", "high"),
                        "sourceEntities": [f"{s}_L{i}" for s in w.get("sourceEntities", [])],
                    })

                # Replicate openings
                for op in base_openings:
                    rep_op = {
                        "id": f"{op['id']}_L{i}",
                        "type": op["type"],
                        "wallId": f"{op['wallId']}_L{i}",
                        "center": list(op["center"]),
                        "width": op["width"],
                        "height": op["height"],
                        "levelId": f"Level {i}",
                        "confidence": op.get("confidence", "high"),
                    }
                    if "sillHeight" in op:
                        rep_op["sillHeight"] = op["sillHeight"]
                    if "swing" in op:
                        rep_op["swing"] = op["swing"]
                    opening_dicts.append(rep_op)

                # Replicate floor slab for upper level
                for fl in base_floors:
                    floor_dicts.append({
                        "id": f"{fl['id']}_L{i}",
                        "levelId": f"Level {i}",
                        "thickness": fl.get("thickness", 150.0),
                        "elevation": storey_elev,
                        "boundary": [list(pt) for pt in fl.get("boundary", [])],
                    })

        model_dict: Dict[str, Any] = {
            "schemaVersion": "1.0.0",
            "metadata": {
                "projectName": project_name,
                "sourceDxfPath": str(source_dxf_path),
                "createdAt": now_iso,
                "updatedAt": now_iso,
            },
            "status": "awaiting_approval",
            "units": {
                "sourceUnits": source_units,
                "normalizedUnits": "mm",
                "scaleFactor": scale_factor,
                "originOffset": [0.0, 0.0],
            },
            "levels": levels,
            "walls": wall_dicts,
            "openings": opening_dicts,
            "floors": floor_dicts,
            "rooms": room_dicts,
            "roofs": [],
            "assumptions": assumptions or [],
            "approval": {
                "isApproved": False,
                "notes": "Pending human review of 3D vertical parameters",
            },
        }

        if source_json_path:
            model_dict["metadata"]["sourceJsonPath"] = str(source_json_path)

        return cls(model_dict)

    @classmethod
    def from_sketch_to_cad_json(cls, json_path: str | Path) -> "IntermediateBimModel":
        """Adapts upstream Sketch-to-CAD floor-plan-model.json into IntermediateBimModel."""
        json_path = Path(json_path)
        with open(json_path, "r", encoding="utf-8") as f:
            upstream = json.load(f)

        now_iso = datetime.now(timezone.utc).isoformat()
        units = upstream.get("units", "mm")
        scale = 1000.0 if units == "m" else (25.4 if units == "in" else (304.8 if units == "ft" else 1.0))

        walls = []
        for w in upstream.get("walls", []):
            walls.append({
                "id": w["id"],
                "classification": w.get("type", "exterior"),
                "start": [round(w["start"][0] * scale, 2), round(w["start"][1] * scale, 2)],
                "end": [round(w["end"][0] * scale, 2), round(w["end"][1] * scale, 2)],
                "thickness": round(w.get("thickness", 200) * scale, 2),
                "height": 3000.0,
                "levelId": "Level 1",
                "confidence": "high",
                "sourceEntities": [w.get("layer", "A-WALL")],
            })

        openings = []
        for op in upstream.get("openings", []):
            item: Dict[str, Any] = {
                "id": op["id"],
                "type": "door" if op.get("type") == "door" else "window",
                "wallId": op.get("wallId", "wall_1"),
                "center": [round(op["center"][0] * scale, 2), round(op["center"][1] * scale, 2)],
                "width": round(op.get("width", 900) * scale, 2),
                "height": 2100.0 if op.get("type") == "door" else 1200.0,
                "confidence": "high",
            }
            if op.get("type") == "window":
                item["sillHeight"] = round(op.get("sillHeight", 900) * scale, 2)
            openings.append(item)

        # Outer envelope to floor slab
        env = upstream.get("envelope", {})
        width_mm = round(env.get("width", 6000) * scale, 2)
        depth_mm = round(env.get("depth", 4000) * scale, 2)
        floors = [{
            "id": "floor_1",
            "levelId": "Level 1",
            "thickness": 150.0,
            "elevation": 0.0,
            "boundary": [[0.0, 0.0], [width_mm, 0.0], [width_mm, depth_mm], [0.0, depth_mm]],
        }]

        rooms = []
        for rm in upstream.get("rooms", []):
            rooms.append({
                "id": rm["id"],
                "name": rm.get("name", "Room"),
                "levelId": "Level 1",
                "approximateArea": rm.get("approximateArea", 0.0),
                "labelPosition": [
                    round(rm.get("labelPosition", [0, 0])[0] * scale, 2),
                    round(rm.get("labelPosition", [0, 0])[1] * scale, 2),
                ],
            })

        model_dict: Dict[str, Any] = {
            "schemaVersion": "1.0.0",
            "metadata": {
                "projectName": upstream.get("metadata", {}).get("projectName", "SketchToCadImport"),
                "sourceJsonPath": str(json_path),
                "createdAt": now_iso,
                "updatedAt": now_iso,
            },
            "status": "awaiting_approval",
            "units": {
                "sourceUnits": units,
                "normalizedUnits": "mm",
                "scaleFactor": scale,
                "originOffset": [0.0, 0.0],
            },
            "levels": [
                {"id": "level_1", "name": "Level 1", "elevation": 0.0, "height": 3000.0},
                {"id": "level_2", "name": "Level 2", "elevation": 3000.0, "height": 3000.0},
            ],
            "walls": walls,
            "openings": openings,
            "floors": floors,
            "rooms": rooms,
            "roofs": [],
            "assumptions": upstream.get("uncertainties", []),
            "approval": {
                "isApproved": False,
                "notes": "Imported from Sketch-to-CAD model. Awaiting 3D approval.",
            },
        }

        return cls(model_dict)

    def validate_schema(self) -> None:
        """Validates internal dictionary against bim-model.schema.json."""
        if not SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = json.load(f)

        jsonschema.validate(instance=self.data, schema=schema)

    def save(self, output_path: str | Path) -> Path:
        self.validate_schema()
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        return out_path

    @classmethod
    def load(cls, file_path: str | Path) -> "IntermediateBimModel":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        instance = cls(data)
        instance.validate_schema()
        return instance

    def get_levels_summary(self) -> List[Dict[str, Any]]:
        """Returns structured breakdown of levels with counts of walls, openings, and slabs."""
        summary = []
        walls = self.data.get("walls", [])
        openings = self.data.get("openings", [])
        floors = self.data.get("floors", [])

        for lvl in self.data.get("levels", []):
            lname = lvl.get("name")
            lid = lvl.get("id")
            lvl_walls = [w for w in walls if w.get("levelId") in (lname, lid)]
            lvl_ops = [op for op in openings if op.get("levelId") in (lname, lid)]
            lvl_fls = [fl for fl in floors if fl.get("levelId") in (lname, lid)]
            summary.append({
                "id": lid,
                "name": lname,
                "elevation": lvl.get("elevation", 0.0),
                "height": lvl.get("height", 0.0),
                "storeyType": lvl.get("storeyType", "standard"),
                "walls": len(lvl_walls),
                "openings": len(lvl_ops),
                "floors": len(lvl_fls),
            })
        return summary

