"""BIMCraft 0.9.0 adapter for executing verified CLI commands."""

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

    def build_commands(self, model: IntermediateBimModel) -> List[Tuple[str, Dict[str, Any]]]:
        """Translates approved intermediate model into a sequenced list of BIMCraft commands."""
        cmds: List[Tuple[str, Dict[str, Any]]] = []
        d = model.data

        # 1. Levels (BIMCraft defaults to Level 1 (0) and Level 2 (3000), but we configure if custom)
        # 2. Walls
        for w in d.get("walls", []):
            wall_params = {
                "points": [w["start"], w["end"]],
                "level": w.get("levelId", "Level 1"),
                "height": float(w.get("height", 3000.0)),
                "location": "centre",
            }
            cmds.append(("wall", wall_params))

        # 3. Floors / Slabs
        for fl in d.get("floors", []):
            floor_params = {
                "boundary": fl["boundary"],
                "level": fl.get("levelId", "Level 1"),
            }
            cmds.append(("floor", floor_params))

        # 4. Doors (hosted)
        for op in d.get("openings", []):
            if op.get("type") == "door":
                door_params: Dict[str, Any] = {
                    "at": op["center"],
                }
                cmds.append(("door", door_params))

        # 5. Windows (hosted)
        for op in d.get("openings", []):
            if op.get("type") == "window":
                win_params: Dict[str, Any] = {
                    "at": op["center"],
                }
                if "sillHeight" in op:
                    win_params["sill"] = float(op["sillHeight"])
                cmds.append(("window", win_params))

        return cmds

    def execute_build(
        self,
        model: IntermediateBimModel,
        output_dir: str | Path,
        base_name: Optional[str] = None,
    ) -> BimcraftBuildResult:
        # Enforce approval gate
        valid_approval, reason = ApprovalGate.verify_approval(model)
        if not valid_approval:
            raise PermissionError(f"Approval Gate Violation: {reason}")

        if not self.is_available():
            raise FileNotFoundError(f"BIMCraft CLI executable not found at: {self.cli_path}")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not base_name:
            base_name = model.data.get("metadata", {}).get("projectName", "bim_model")
            base_name = base_name.replace(" ", "_").lower()

        bimcraft_file = output_dir / f"{base_name}.bimcraft"
        ifc_file = output_dir / f"{base_name}.ifc"
        png_file = output_dir / f"{base_name}.png"

        commands = self.build_commands(model)

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

