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
        t5.add_column("Property", style="cyan")
        t5.add_column("Value", style="green")
        t5.add_row("Supported Storeys", f"{vert['storeys']} Storey")
        t5.add_row("Base Level (Level 1)", "0.0 mm (Ground)")
        t5.add_row("Ceiling Level (Level 2)", f"{vert['wall_height_mm']} mm")
        self.console.print(t5)

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

            try:
                choice = input("\nEnter option (1-5) [1]: ").strip()
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
            else:
                self.console.print("[red]Unrecognized option. Enter 1-5.[/red]")
