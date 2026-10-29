"""Configuration management and validation for DXF-to-3D-BIM."""

import copy
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import jsonschema
from pydantic import BaseModel, Field, ValidationError

CONFIG_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "skills" / "dxf-to-3d-bim" / "schemas" / "project-config.schema.json"
REPO_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


class BimcraftConfig(BaseModel):
    cli_path: str = r"C:\Program Files\BIMCraft\bimcraft-cli.exe"
    gui_path: str = r"C:\Program Files\BIMCraft\bimcraft.exe"
    timeout_seconds: int = 60
    default_format: str = "IFC4"


class UnitsConfig(BaseModel):
    internal: str = "mm"
    source_unit: Optional[str] = None
    dxf_default_if_unspecified: str = "mm"


class LevelsConfig(BaseModel):
    default_storeys: int = 1
    ground_floor_elevation: float = 0.0
    floor_to_floor_height: float = 3000.0
    storey_heights: List[float] = Field(default_factory=list)
    repeat_ground_floor: bool = False
    storey_config_path: Optional[str] = None
    level_names: List[str] = Field(default_factory=lambda: ["Level 1", "Level 2"])

    def get_storey_elevations(self, storeys_count: Optional[int] = None) -> List[Tuple[str, float, float]]:
        """Returns list of (level_name, base_elevation, storey_height) for storeys and top roof datum."""
        count = storeys_count if storeys_count is not None else self.default_storeys
        count = max(1, count)
        result = []
        current_elev = self.ground_floor_elevation

        for i in range(count):
            name = self.level_names[i] if i < len(self.level_names) else f"Level {i+1}"
            height = self.storey_heights[i] if i < len(self.storey_heights) else self.floor_to_floor_height
            result.append((name, current_elev, height))
            current_elev += height

        # Add roof datum / top ceiling level
        top_name = self.level_names[count] if count < len(self.level_names) else f"Level {count+1}"
        result.append((top_name, current_elev, 0.0))
        return result


class WallsConfig(BaseModel):
    exterior_thickness: float = 200.0
    interior_thickness: float = 100.0
    height: float = 3000.0


class OpeningsConfig(BaseModel):
    door_width: float = 900.0
    door_height: float = 2100.0
    window_width: float = 1200.0
    window_height: float = 1200.0
    window_sill_height: float = 900.0


class SlabConfig(BaseModel):
    thickness: float = 150.0
    elevation: float = 0.0


class RoofConfig(BaseModel):
    enabled: bool = False
    roof_type: str = "none"  # "none", "gable", "hip", "flat", "shed"
    pitch_degrees: float = 30.0
    overhang: float = 300.0
    thickness: float = 200.0


class TolerancesConfig(BaseModel):
    endpoint_snap: float = 25.0
    collinear_distance: float = 5.0
    collinear_angle_deg: float = 1.0
    min_wall_thickness: float = 60.0
    max_wall_thickness: float = 450.0
    min_wall_length: float = 200.0
    opening_snap_to_wall: float = 150.0
    duplicate_line_threshold: float = 5.0
    polygon_closure_threshold: float = 30.0


class ProjectConfig(BaseModel):
    version: str = "1.0.0"
    bimcraft: BimcraftConfig = Field(default_factory=BimcraftConfig)
    units: UnitsConfig = Field(default_factory=UnitsConfig)
    levels: LevelsConfig = Field(default_factory=LevelsConfig)
    walls: WallsConfig = Field(default_factory=WallsConfig)
    openings: OpeningsConfig = Field(default_factory=OpeningsConfig)
    slab: SlabConfig = Field(default_factory=SlabConfig)
    roof: RoofConfig = Field(default_factory=RoofConfig)
    tolerances: TolerancesConfig = Field(default_factory=TolerancesConfig)
    layer_aliases: Optional[Dict[str, Any]] = None
    ignored_layers: List[str] = Field(default_factory=list)

    def compute_hash(self) -> str:
        """Deterministic SHA-256 hash of configuration content."""
        data = self.model_dump()
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def save(self, file_path: str | Path) -> Path:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))
        return path


class ConfigManager:
    """Manages loading, merging, and schema-validating project configurations."""

    @classmethod
    def load_defaults(cls) -> ProjectConfig:
        """Loads repository baseline defaults from config/ directory."""
        cfg_dict: Dict[str, Any] = {}
        defaults_path = REPO_CONFIG_DIR / "defaults.json"
        tolerances_path = REPO_CONFIG_DIR / "tolerances.json"
        aliases_path = REPO_CONFIG_DIR / "layer-aliases.json"

        if defaults_path.exists():
            with open(defaults_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                cfg_dict.update(d)

        # Merge openings structure if flat in defaults
        openings = cfg_dict.get("openings", {})
        if "door" in openings:
            cfg_dict["openings"] = {
                "door_width": openings["door"].get("width", 900.0),
                "door_height": openings["door"].get("height", 2100.0),
                "window_width": openings.get("window", {}).get("width", 1200.0),
                "window_height": openings.get("window", {}).get("height", 1200.0),
                "window_sill_height": openings.get("window", {}).get("sill_height", 900.0),
            }

        if tolerances_path.exists():
            with open(tolerances_path, "r", encoding="utf-8") as f:
                t = json.load(f)
                cfg_dict["tolerances"] = t.get("tolerances_mm", {})

        if aliases_path.exists():
            with open(aliases_path, "r", encoding="utf-8") as f:
                a = json.load(f)
                cfg_dict["layer_aliases"] = a

        # Remove JSON Schema meta fields if present
        cfg_dict.pop("$schema", None)

        return ProjectConfig.model_validate(cfg_dict)

    @classmethod
    def load_user_config(cls, config_path: str | Path) -> ProjectConfig:
        """Loads and schema-validates a user configuration file, overlaying onto defaults."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_dict = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Corrupt JSON configuration in {path}: {str(e)}")

        # Validate against JSON schema if present
        if CONFIG_SCHEMA_PATH.exists():
            with open(CONFIG_SCHEMA_PATH, "r", encoding="utf-8") as sf:
                schema = json.load(sf)
            try:
                jsonschema.validate(instance=raw_dict, schema=schema)
            except jsonschema.ValidationError as ve:
                raise ValueError(f"Configuration schema violation in {path}: {ve.message}")

        # Start from defaults and merge user dict
        defaults = cls.load_defaults().model_dump()
        cls._deep_merge(defaults, raw_dict)

        try:
            return ProjectConfig.model_validate(defaults)
        except ValidationError as ve:
            raise ValueError(f"Invalid configuration parameters in {path}: {ve}")

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]):
        for k, v in override.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                ConfigManager._deep_merge(base[k], v)
            else:
                base[k] = v

