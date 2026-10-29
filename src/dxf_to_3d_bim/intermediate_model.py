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
    ) -> "IntermediateBimModel":
        now_iso = datetime.now(timezone.utc).isoformat()

        # Build walls dicts
        wall_dicts = []
        for w in walls:
            wall_dicts.append({
                "id": w.id,
                "classification": w.classification,
                "start": [w.start[0], w.start[1]],
                "end": [w.end[0], w.end[1]],
                "thickness": w.thickness,
                "height": getattr(w, "height", 3000.0),
                "levelId": getattr(w, "level_id", "Level 1"),
                "confidence": getattr(w, "confidence", "high"),
                "sourceEntities": getattr(w, "source_entities", []),
            })

        # Build openings dicts
        opening_dicts = []
        for op in openings:
            item: Dict[str, Any] = {
                "id": op.id,
                "type": op.type,
                "wallId": op.wall_id,
                "center": [op.center[0], op.center[1]],
                "width": op.width,
                "height": op.height,
                "confidence": getattr(op, "confidence", "high"),
            }
            if op.sill_height is not None:
                item["sillHeight"] = op.sill_height
            if getattr(op, "swing", None):
                item["swing"] = op.swing
            opening_dicts.append(item)

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

        levels = [
            {"id": "level_1", "name": "Level 1", "elevation": 0.0, "height": 3000.0},
            {"id": "level_2", "name": "Level 2", "elevation": 3000.0, "height": 3000.0},
        ]

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

