"""Guided Approval workflow module for presenting, adjusting, and locking BIM parameters."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.config import ProjectConfig
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.preflight import PreflightReport
from dxf_to_3d_bim.reporting import compute_file_sha256


class GuidedApprovalSession:
    """Manages guided human or non-interactive approval of intermediate BIM model parameters."""

    def __init__(
        self,
        model: IntermediateBimModel,
        preflight: PreflightReport,
        dxf_path: str | Path,
        config: Optional[ProjectConfig] = None,
        console: Optional[Console] = None,
    ):
        self.model = model
        self.preflight = preflight
        self.dxf_path = Path(dxf_path)
        self.config = config or ProjectConfig()
        self.console = console or Console()
        self.dxf_hash = compute_file_sha256(self.dxf_path)
        self.config_hash = self.config.compute_hash()

    def display_proposal(self):
        """Displays the proposed BIM interpretation across 7 logical architectural sections."""
        summary = ApprovalGate.generate_proposal_summary(self.model)
        vert = summary["proposed_vertical_parameters"]
        footprint = summary["footprint"]
        counts = summary["counts"]

        self.console.print("\n[bold cyan]====================================================================[/bold cyan]")
        self.console.print("[bold cyan]       DXF-to-3D-BIM: Guided Architectural Proposal Review         [/bold cyan]")
        self.console.print("[bold cyan]====================================================================[/bold cyan]\n")

        # Section 1: Units and Scale
        t1 = Table(title="Section 1: Units and Scale")
        t1.add_column("Property", style="cyan")
        t1.add_column("Value", style="green")
        t1.add_row("Source Units", f"{self.preflight.detected_units} (INSUNITS={self.preflight.insunits_code})")
        t1.add_row("Scale Factor to mm", f"{self.preflight.scale_factor_to_mm}x")
        t1.add_row("Raw Extents", f"{self.preflight.raw_extents.get('width', 0):.2f} x {self.preflight.raw_extents.get('depth', 0):.2f}")
        t1.add_row("Normalized Extents (mm)", f"{footprint['width_mm']} x {footprint['depth_mm']} mm ({footprint['area_m2']} m²)")
        t1.add_row("Scale Confidence", str(self.preflight.scale_confidence.value))
        self.console.print(t1)

        # Section 2: Walls
        t2 = Table(title="Section 2: Wall Interpretation & Parameters")
        t2.add_column("Classification", style="cyan")
        t2.add_column("Count", style="white")
        t2.add_column("Thickness (mm)", style="green")
        t2.add_column("Height (mm)", style="green")
        t2.add_row("Exterior Walls", str(counts["exterior_walls"]), str(self.config.walls.exterior_thickness), str(vert["wall_height_mm"]))
        t2.add_row("Interior Partitions", str(counts["interior_walls"]), str(self.config.walls.interior_thickness), str(vert["wall_height_mm"]))
        self.console.print(t2)

        # Section 3: Openings
        t3 = Table(title="Section 3: Hosted Openings")
        t3.add_column("Type", style="cyan")
        t3.add_column("Count", style="white")
        t3.add_column("Default Width (mm)", style="green")
        t3.add_column("Default Height (mm)", style="green")
        t3.add_column("Sill Elevation (mm)", style="green")
        t3.add_row("Doors", str(counts["doors"]), str(self.config.openings.door_width), str(self.config.openings.door_height), "0.0")
        t3.add_row("Windows", str(counts["windows"]), str(self.config.openings.window_width), str(self.config.openings.window_height), str(vert.get("window_sill_height_mm", 900.0)))
        self.console.print(t3)

        # Section 4: Slab & Footprint
        t4 = Table(title="Section 4: Floor Slab & Footprint")
        t4.add_column("Property", style="cyan")
        t4.add_column("Value", style="green")
        t4.add_row("Detected Floor Slabs", str(counts["floors"]))
        t4.add_row("Slab Thickness (mm)", str(vert["slab_thickness_mm"]))
        t4.add_row("Ground Slab Elevation (mm)", str(self.config.slab.elevation))
        self.console.print(t4)

        # Section 5: Storeys & Elevation
        t5 = Table(title="Section 5: Storeys & Datums")
        t5.add_column("Level / Storey", style="cyan")
        t5.add_column("Base Elevation (mm)", style="green")
        t5.add_column("Height (mm)", style="green")
        t5.add_column("Walls / Slabs / Roofs", style="white")

        breakdown = vert.get("levels_breakdown", [])
        if breakdown:
            for b in breakdown:
                elem_desc = f"{b['walls']} walls, {b['floors']} slabs"
                if b.get("roofs", 0) > 0:
                    elem_desc += f", {b['roofs']} roof"
                t5.add_row(
                    f"{b['name']} ({b.get('storeyType', 'standard')})",
                    f"{b['elevation']:.1f}",
                    f"{b['height']:.1f}",
                    elem_desc,
                )
        else:
            t5.add_row("Level 1 (Ground)", "0.0", f"{vert['wall_height_mm']:.1f}", "Ground Floor")
            t5.add_row("Level 2 (Ceiling/Roof Datum)", f"{vert['wall_height_mm']:.1f}", "0.0", "Roof Datum")
        self.console.print(t5)

        # Section 5b: Parametric Roof (if configured)
        roofs = self.model.data.get("roofs", [])
        if roofs and roofs[0].get("roofType") not in ("none", None):
            rf = roofs[0]
            t_roof = Table(title="Section 5b: Parametric Roof Specification")
            t_roof.add_column("Parameter", style="cyan")
            t_roof.add_column("Approved Value", style="green")
            t_roof.add_row("Roof Type", rf.get("roofType", "none").upper())
            t_roof.add_row("Host Spatial Storey", rf.get("levelId", "Level 1"))
            t_roof.add_row("Bearing Elevation", f"{rf.get('baseElevation', 0.0):.1f} mm")
            t_roof.add_row("Slope / Pitch", f"{rf.get('pitchDegrees', 30.0):.1f}°")
            t_roof.add_row("Eave Overhang", f"{rf.get('overhang', 300.0):.1f} mm")
            t_roof.add_row("Ridge Elevation", f"{rf.get('ridgeElevation', 0.0):.1f} mm")
            t_roof.add_row("Roof Plan Area", f"{rf.get('areaM2', 0.0):.2f} m²")
            self.console.print(t_roof)

        # Section 5c: Staircase & Vertical Circulation (if configured)
        staircases = self.model.data.get("staircases", [])
        if staircases:
            st = staircases[0]
            t_stair = Table(title="Section 5c: Staircase & Vertical Circulation Specification")
            t_stair.add_column("Parameter", style="cyan")
            t_stair.add_column("Approved Value", style="green")
            t_stair.add_row("Stair Type", st.get("stairType", "straight").upper())
            t_stair.add_row("Levels Connected", f"{st.get('levelId')} -> {st.get('topLevelId')}")
            t_stair.add_row("Total Rise", f"{st.get('totalRise', 0.0):.1f} mm")
            t_stair.add_row(
                "Risers / Treads",
                f"{st.get('riserCount')} risers @ {st.get('actualRiserHeight', 0.0):.1f} mm / "
                f"{st.get('treadCount')} treads @ {st.get('actualGoing', 0.0):.1f} mm"
            )
            t_stair.add_row("Flight Width", f"{st.get('width', 1000.0):.1f} mm")
            t_stair.add_row("Total Horizontal Run", f"{st.get('totalRun', 0.0):.1f} mm")
            t_stair.add_row("Headroom Clearance", f"{st.get('headroomClearance', 2000.0):.1f} mm")
            t_stair.add_row(
                "Upper Slab Opening",
                f"{st.get('stairwellAreaM2', 0.0):.2f} m² void cut in {st.get('topLevelId')}"
            )
            landings = st.get("landings", [])
            if landings:
                l_desc = f"{len(landings)} landing(s) (turn: {landings[0].get('turnDegrees', 0)}° at riser {landings[0].get('atRiser')})"
                t_stair.add_row("Intermediate Landings", l_desc)
            self.console.print(t_stair)

        # Section 6: Warnings & Uncertainties
        t6 = Table(title="Section 6: Uncertain Geometry & Preflight Warnings")
        t6.add_column("Item", style="yellow")
        if self.preflight.warnings:
            for w in self.preflight.warnings:
                t6.add_row(w)
        else:
            t6.add_row("None - clean geometry and layer mapping.")
        if self.preflight.unclassified_layers:
            t6.add_row(f"Ignored unclassified layers: {', '.join(self.preflight.unclassified_layers)}")
        self.console.print(t6)

        # Section 7: Deliverables
        t7 = Table(title="Section 7: Target Deliverables & Formats")
        t7.add_column("Deliverable", style="cyan")
        t7.add_column("Format / View", style="green")
        t7.add_row("Native Project", ".bimcraft (BIMCraft 0.9.0 project format)")
        t7.add_row("Open Standard Model", ".ifc (IFC4 Coordination View)")
        t7.add_row("2D Plan View", ".png (Orthographic plan preview)")
        t7.add_row("3D Axonometric Render", "_3d.png (Isometric isometric perspective)")
        t7.add_row("Elevations & Cross-Section", "_elev_south.png, _elev_east.png, _section_a.png")
        t7.add_row("Visual Comparison", "_comparison_overlay.png (CAD linework vs BIM overlay)")
        t7.add_row("Run Manifest", "manifest.json (SHA-256 artifacts & toolchain audit)")
        self.console.print(t7)

    def update_wall_height(self, new_height_mm: float):
        for w in self.model.data.get("walls", []):
            w["height"] = float(new_height_mm)
        for lvl in self.model.data.get("levels", []):
            if lvl.get("id") == "level_2":
                lvl["elevation"] = float(new_height_mm)

    def update_slab_thickness(self, new_thickness_mm: float):
        for fl in self.model.data.get("floors", []):
            fl["thickness"] = float(new_thickness_mm)

    def update_window_sill_height(self, new_sill_mm: float):
        for op in self.model.data.get("openings", []):
            if op.get("type") == "window":
                op["sillHeight"] = float(new_sill_mm)

    def update_roof_parameters(
        self,
        pitch_degrees: Optional[float] = None,
        overhang: Optional[float] = None,
    ):
        roofs = self.model.data.get("roofs", [])
        if not roofs:
            return
        rf = roofs[0]
        if pitch_degrees is not None:
            rf["pitchDegrees"] = float(pitch_degrees)
        if overhang is not None:
            rf["overhang"] = float(overhang)

        from dxf_to_3d_bim.roof_engine import ParametricRoofEngine
        recomputed = ParametricRoofEngine.generate_roof(
            footprint=rf["boundary"],
            top_level_name=rf["levelId"],
            top_level_elevation=rf.get("baseElevation", 3000.0) - 3000.0,
            top_wall_height=3000.0,
            roof_type=rf["roofType"],
            pitch_degrees=rf["pitchDegrees"],
            overhang=rf["overhang"],
            thickness=rf.get("thickness", 200.0),
            roof_id=rf.get("id", "roof_1"),
        )
        if recomputed:
            rf["ridgeEndpoints"] = [[round(r[0], 2), round(r[1], 2), round(r[2], 2)] for r in recomputed.ridge_endpoints]
            rf["ridgeElevation"] = round(recomputed.ridge_elevation, 2)
            rf["gableEdgeIndices"] = recomputed.gable_edge_indices
            rf["areaM2"] = round(recomputed.area_m2, 2)

    def update_stair_parameters(
        self,
        width: Optional[float] = None,
        target_riser: Optional[float] = None,
        target_going: Optional[float] = None,
    ):
        staircases = self.model.data.get("staircases", [])
        if not staircases:
            return
        st = staircases[0]
        w = width if width is not None else st.get("width", 1000.0)
        from dxf_to_3d_bim.stair_engine import ParametricStairEngine
        recomputed = ParametricStairEngine.generate_stair(
            stair_id=st.get("id", "stair_1"),
            stair_type=st.get("stairType", "straight"),
            level_id=st.get("levelId", "Level 1"),
            top_level_id=st.get("topLevelId", "Level 2"),
            base_elevation=st.get("baseElevation", 0.0),
            top_elevation=st.get("topElevation", 3000.0),
            start_point=tuple(st.get("start", [1000.0, 1000.0])),
            end_point=None,
            direction_angle_deg=st.get("climbAngleDeg", 0.0),
            width=w,
            target_riser=target_riser if target_riser is not None else st.get("actualRiserHeight", 175.0),
            target_going=target_going if target_going is not None else st.get("actualGoing", 280.0),
            railings=st.get("railings", True),
            provenance="user_configured",
        )
        staircases[0] = recomputed.to_dict()
        # Re-punch floor openings
        self.model.data["floors"] = ParametricStairEngine.punch_stairwell_opening_into_floors(
            self.model.data.get("floors", []), staircases
        )

    def run_guided_session(
        self,
        interactive: bool = True,
        auto_approve: bool = False,
        approved_by: str = "Authorized Reviewer",
        notes: str = "Approved for BIMCraft construction",
    ) -> Dict[str, Any]:
        """Executes guided approval session, either interactively or non-interactively."""
        # 1. Non-interactive path
        if not interactive:
            if self.preflight.unit_ambiguity and not self.config.units.source_unit:
                raise ValueError(
                    f"Non-interactive run blocked: Drawing units are unspecified (INSUNITS=0) and no explicit "
                    f"'source_unit' was provided in config. Provide --config with 'units.source_unit' or use --unit."
                )

            # Apply any configuration overrides
            if self.config.walls.height != 3000.0:
                self.update_wall_height(self.config.walls.height)
            if self.config.slab.thickness != 150.0:
                self.update_slab_thickness(self.config.slab.thickness)
            if self.config.openings.window_sill_height != 900.0:
                self.update_window_sill_height(self.config.openings.window_sill_height)

            method = "config_file" if self.config else "non_interactive"
            if auto_approve:
                method = "cli_auto_approve"

            approval_record = ApprovalGate.approve(
                self.model,
                approved_by=approved_by,
                notes=notes,
                dxf_hash=self.dxf_hash,
                config_hash=self.config_hash,
                approval_method=method,
            )
            return approval_record

        # 2. Interactive path
        self.display_proposal()

        while True:
            self.console.print("\n[bold yellow]Guided Approval Options:[/bold yellow]")
            self.console.print("  [1] [bold green]Accept and Approve all parameters[/bold green]")
            self.console.print("  [2] Edit Wall Height (current: {} mm)".format(
                self.model.data.get("walls", [{}])[0].get("height", 3000.0) if self.model.data.get("walls") else 3000.0
            ))
            self.console.print("  [3] Edit Floor Slab Thickness (current: {} mm)".format(
                self.model.data.get("floors", [{}])[0].get("thickness", 150.0) if self.model.data.get("floors") else 150.0
            ))
            self.console.print("  [4] Edit Window Sill Height")
            self.console.print("  [5] Reject / Cancel Generation")
            has_roof = bool(self.model.data.get("roofs") and self.model.data["roofs"][0].get("roofType") not in ("none", None))
            if has_roof:
                rf = self.model.data["roofs"][0]
                self.console.print(f"  [6] Edit Roof Parameters (Pitch: {rf.get('pitchDegrees', 30.0)}°, Overhang: {rf.get('overhang', 300.0)} mm)")

            try:
                prompt_text = "\nEnter option (1-6) [1]: " if has_roof else "\nEnter option (1-5) [1]: "
                choice = input(prompt_text).strip()
            except (EOFError, KeyboardInterrupt):
                raise PermissionError("Approval aborted by user.")

            if choice in ("", "1"):
                approval_record = ApprovalGate.approve(
                    self.model,
                    approved_by=approved_by,
                    notes=notes,
                    dxf_hash=self.dxf_hash,
                    config_hash=self.config_hash,
                    approval_method="interactive",
                )
                self.console.print("[bold green][OK] Proposed parameters approved and locked![/bold green]")
                return approval_record

            elif choice == "2":
                val = input("Enter new wall height in mm (e.g. 2800): ").strip()
                try:
                    h = float(val)
                    if h < 1000 or h > 10000:
                        self.console.print("[red]Wall height must be between 1000 and 10000 mm.[/red]")
                    else:
                        self.update_wall_height(h)
                        self.console.print(f"[green]Wall height updated to {h} mm.[/green]")
                except ValueError:
                    self.console.print("[red]Invalid numerical value.[/red]")

            elif choice == "3":
                val = input("Enter new slab thickness in mm (e.g. 200): ").strip()
                try:
                    th = float(val)
                    if th < 50 or th > 1000:
                        self.console.print("[red]Slab thickness must be between 50 and 1000 mm.[/red]")
                    else:
                        self.update_slab_thickness(th)
                        self.console.print(f"[green]Slab thickness updated to {th} mm.[/green]")
                except ValueError:
                    self.console.print("[red]Invalid numerical value.[/red]")

            elif choice == "4":
                val = input("Enter new window sill height in mm (e.g. 800): ").strip()
                try:
                    sill = float(val)
                    if sill < 0 or sill > 3000:
                        self.console.print("[red]Sill height must be between 0 and 3000 mm.[/red]")
                    else:
                        self.update_window_sill_height(sill)
                        self.console.print(f"[green]Window sill height updated to {sill} mm.[/green]")
                except ValueError:
                    self.console.print("[red]Invalid numerical value.[/red]")

            elif choice == "5":
                raise PermissionError("Generation cancelled: User rejected proposal parameters.")
            elif choice == "6" and has_roof:
                p_val = input("Enter new roof pitch in degrees (e.g. 35.0) [leave blank to keep]: ").strip()
                o_val = input("Enter new roof overhang in mm (e.g. 400.0) [leave blank to keep]: ").strip()
                try:
                    p = float(p_val) if p_val else None
                    o = float(o_val) if o_val else None
                    self.update_roof_parameters(pitch_degrees=p, overhang=o)
                    self.console.print("[green]Roof parameters updated.[/green]")
                except ValueError:
                    self.console.print("[red]Invalid numerical value.[/red]")
            else:
                max_opt = "1-6" if has_roof else "1-5"
                self.console.print(f"[red]Unrecognized option. Enter {max_opt}.[/red]")
