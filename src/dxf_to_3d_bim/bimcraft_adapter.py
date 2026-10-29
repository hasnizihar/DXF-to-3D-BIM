"""BIMCraft 0.9.0 adapter for executing verified CLI commands and rendering 2D/3D views."""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel


@dataclass
class BimcraftBuildResult:
    success: bool
    bimcraft_path: Optional[Path] = None
    ifc_path: Optional[Path] = None
    png_path: Optional[Path] = None
    view_3d_path: Optional[Path] = None
    elevation_south_path: Optional[Path] = None
    elevation_east_path: Optional[Path] = None
    section_path: Optional[Path] = None
    level_plan_paths: Dict[str, Path] = field(default_factory=dict)
    executed_commands: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)
    raw_output: str = ""
    error_message: Optional[str] = None


class BimcraftAdapter:
    """Adapter translating IntermediateBimModel into verified BIMCraft 0.9.0 operations."""

    def __init__(self, cli_path: Optional[str | Path] = None):
        if cli_path is None:
            config_file = Path(__file__).resolve().parent.parent.parent / "config" / "defaults.json"
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                cli_path = cfg.get("bimcraft", {}).get("cli_path", r"C:\Program Files\BIMCraft\bimcraft-cli.exe")
            else:
                cli_path = r"C:\Program Files\BIMCraft\bimcraft-cli.exe"

        self.cli_path = Path(cli_path)

    def is_available(self) -> bool:
        return self.cli_path.exists()

    def build_commands(
        self,
        model: IntermediateBimModel,
        views_config: Optional[Dict[str, Path]] = None,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Translates approved intermediate model into a sequenced list of BIMCraft commands."""
        cmds: List[Tuple[str, Dict[str, Any]]] = []
        d = model.data

        # 0. Level definitions & setup
        levels = d.get("levels", [])
        if levels:
            # Level 1 adjustments (id 100000 in empty project)
            lvl1 = levels[0]
            if float(lvl1.get("elevation", 0.0)) != 0.0:
                cmds.append(("modify", {"id": 100000, "elevation": float(lvl1["elevation"])}))
            if lvl1.get("name") and lvl1["name"] != "Level 1":
                cmds.append(("modify", {"id": 100000, "name": str(lvl1["name"])}))

            # Level 2 adjustments (id 100001 in empty project)
            if len(levels) > 1:
                lvl2 = levels[1]
                if float(lvl2.get("elevation", 3000.0)) != 3000.0:
                    cmds.append(("modify", {"id": 100001, "elevation": float(lvl2["elevation"])}))
                if lvl2.get("name") and lvl2["name"] != "Level 2":
                    cmds.append(("modify", {"id": 100001, "name": str(lvl2["name"])}))

            # Additional levels (Level 3+)
            for lvl in levels[2:]:
                cmds.append(("level", {
                    "name": str(lvl.get("name", f"Level_{lvl.get('id')}")),
                    "elevation": float(lvl.get("elevation", 0.0)),
                }))

        # 1. Walls
        for w in d.get("walls", []):
            wall_params = {
                "points": [w["start"], w["end"]],
                "level": w.get("levelId", "Level 1"),
                "height": float(w.get("height", 3000.0)),
                "location": "centre",
            }
            cmds.append(("wall", wall_params))

        # 2. Floors / Slabs
        for fl in d.get("floors", []):
            floor_params = {
                "boundary": fl["boundary"],
                "level": fl.get("levelId", "Level 1"),
            }
            cmds.append(("floor", floor_params))

        # 3. Doors (hosted)
        for op in d.get("openings", []):
            if op.get("type") == "door":
                door_params: Dict[str, Any] = {
                    "at": op["center"],
                    "level": op.get("levelId", "Level 1"),
                }
                cmds.append(("door", door_params))

        # 4. Windows (hosted)
        for op in d.get("openings", []):
            if op.get("type") == "window":
                win_params: Dict[str, Any] = {
                    "at": op["center"],
                    "level": op.get("levelId", "Level 1"),
                }
                if "sillHeight" in op:
                    win_params["sill"] = float(op["sillHeight"])
                cmds.append(("window", win_params))

        # 5. Roofs
        for rf in d.get("roofs", []):
            roof_type = rf.get("roofType", "none")
            if roof_type in ("none", None):
                continue
            roof_params: Dict[str, Any] = {
                "boundary": rf["boundary"],
                "level": rf.get("levelId", "Level 1"),
                "slope": float(rf.get("pitchDegrees", 30.0)),
            }
            if "offset" in rf:
                roof_params["offset"] = float(rf["offset"])
            elif "baseElevation" in rf:
                host_level_name = rf.get("levelId", "Level 1")
                host_level = next((l for l in levels if l.get("name") == host_level_name or l.get("id") == host_level_name), None)
                host_elev = float(host_level.get("elevation", 0.0)) if host_level else 0.0
                roof_params["offset"] = float(rf["baseElevation"]) - host_elev
            else:
                roof_params["offset"] = 3000.0

            if "overhang" in rf and rf["overhang"] is not None:
                roof_params["overhang"] = float(rf["overhang"])

            # Gable ends: pass edge indices if gable roof
            if roof_type == "gable":
                gable_indices = rf.get("gableEdgeIndices")
                if gable_indices:
                    roof_params["gables"] = list(gable_indices)
                else:
                    roof_params["gable"] = True

            cmds.append(("roof", roof_params))

        # 6. Visual Views & Renderings (if configured)
        if views_config:
            # Elevation views
            if "elevation_south" in views_config:
                cmds.append(("elevation", {"facing": "south", "name": "South Elevation"}))
                cmds.append(("render", {"view": "South Elevation", "path": str(views_config["elevation_south"])}))

            if "elevation_east" in views_config:
                cmds.append(("elevation", {"facing": "east", "name": "East Elevation"}))
                cmds.append(("render", {"view": "East Elevation", "path": str(views_config["elevation_east"])}))

            # Longitudinal section view through middle of building
            if "section" in views_config:
                walls = d.get("walls", [])
                if walls:
                    all_y = [w["start"][1] for w in walls] + [w["end"][1] for w in walls]
                    all_x = [w["start"][0] for w in walls] + [w["end"][0] for w in walls]
                    mid_y = (min(all_y) + max(all_y)) / 2.0
                    min_x, max_x = min(all_x), max(all_x)
                    cmds.append(("section", {"start": [min_x - 500, mid_y], "end": [max_x + 500, mid_y], "name": "Section A-A"}))
                    cmds.append(("render", {"view": "Section A-A", "path": str(views_config["section"])}))

            # 3D Axonometric / Isometric view
            if "view_3d" in views_config:
                cmds.append(("render", {
                    "view": "{3D}",
                    "azimuth": 315,
                    "elevation": 30,
                    "path": str(views_config["view_3d"]),
                }))

            # Upper floor level plans
            for k, p in views_config.items():
                if k.startswith("plan_"):
                    lvl_name = k[len("plan_"):]
                    cmds.append(("render", {"view": lvl_name, "path": str(p)}))

        return cmds

    def execute_build(
        self,
        model: IntermediateBimModel,
        output_dir: str | Path,
        base_name: Optional[str] = None,
        generate_3d_views: bool = True,
        models_dir: Optional[str | Path] = None,
        previews_dir: Optional[str | Path] = None,
    ) -> BimcraftBuildResult:
        # Enforce approval gate
        valid_approval, reason = ApprovalGate.verify_approval(model)
        if not valid_approval:
            raise PermissionError(f"Approval Gate Violation: {reason}")

        if not self.is_available():
            raise FileNotFoundError(f"BIMCraft CLI executable not found at: {self.cli_path}")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        m_dir = Path(models_dir) if models_dir else output_dir
        m_dir.mkdir(parents=True, exist_ok=True)

        p_dir = Path(previews_dir) if previews_dir else output_dir
        p_dir.mkdir(parents=True, exist_ok=True)

        if not base_name:
            base_name = model.data.get("metadata", {}).get("projectName", "bim_model")
            base_name = base_name.replace(" ", "_").lower()

        bimcraft_file = m_dir / f"{base_name}.bimcraft"
        ifc_file = m_dir / f"{base_name}.ifc"
        png_file = p_dir / f"{base_name}.png"

        views_config: Dict[str, Path] = {}
        level_plan_paths: Dict[str, Path] = {}
        if generate_3d_views:
            views_config["view_3d"] = p_dir / f"{base_name}_3d.png"
            views_config["elevation_south"] = p_dir / f"{base_name}_elev_south.png"
            views_config["elevation_east"] = p_dir / f"{base_name}_elev_east.png"
            views_config["section"] = p_dir / f"{base_name}_section_a.png"

            # Multi-level plan views: detect inhabited storeys
            levels = model.data.get("levels", [])
            walls = model.data.get("walls", [])
            floors = model.data.get("floors", [])
            for i, lvl in enumerate(levels):
                lname = lvl.get("name", "")
                lid = lvl.get("id", "")
                has_elements = any(w.get("levelId") in (lname, lid) for w in walls) or any(fl.get("levelId") in (lname, lid) for fl in floors)
                if has_elements:
                    if i == 0:
                        level_plan_paths[lname] = png_file
                    else:
                        slug = lname.lower().replace(" ", "_")
                        lvl_plan_path = p_dir / f"{base_name}_plan_{slug}.png"
                        views_config[f"plan_{lname}"] = lvl_plan_path
                        level_plan_paths[lname] = lvl_plan_path

        commands = self.build_commands(model, views_config=views_config if generate_3d_views else None)

        cli_args = [str(self.cli_path), "run"]
        for cmd_id, params in commands:
            cli_args.extend(["--cmd", f"{cmd_id} {json.dumps(params)}"])

        cli_args.extend(["--save", str(bimcraft_file)])
        cli_args.extend(["--save", str(ifc_file)])
        cli_args.extend(["--save", str(png_file)])

        proc = subprocess.run(
            cli_args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )

        if proc.returncode != 0:
            return BimcraftBuildResult(
                success=False,
                executed_commands=commands,
                raw_output=proc.stdout + "\n" + proc.stderr,
                error_message=f"BIMCraft CLI exited with code {proc.returncode}: {proc.stderr}",
            )

        # Update model status
        model.data["status"] = "built"

        return BimcraftBuildResult(
            success=True,
            bimcraft_path=bimcraft_file,
            ifc_path=ifc_file,
            png_path=png_file,
            view_3d_path=views_config.get("view_3d"),
            elevation_south_path=views_config.get("elevation_south"),
            elevation_east_path=views_config.get("elevation_east"),
            section_path=views_config.get("section"),
            level_plan_paths=level_plan_paths,
            executed_commands=commands,
            raw_output=proc.stdout,
        )

    def inspect_file(self, target_path: str | Path) -> Dict[str, Any]:
        """Runs 'bimcraft-cli info <target_path>' and parses returned JSON."""
        target_path = Path(target_path)
        if not target_path.exists():
            raise FileNotFoundError(f"Target model file not found: {target_path}")

        proc = subprocess.run(
            [str(self.cli_path), "info", str(target_path)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return json.loads(proc.stdout)
