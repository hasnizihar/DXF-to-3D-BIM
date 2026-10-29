"""Comprehensive command-line interface for DXF-to-3D-BIM."""

import json
import sys
from pathlib import Path
from typing import Optional, Any, Dict, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter, BimcraftBuildResult
from dxf_to_3d_bim.comparison import SourceToBimComparator
from dxf_to_3d_bim.config import ConfigManager, ProjectConfig
from dxf_to_3d_bim.dxf_parser import DxfParser
from dxf_to_3d_bim.guided_approval import GuidedApprovalSession
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.manifest import RunManifest, file_sha256
from dxf_to_3d_bim.opening_detection import OpeningDetector
from dxf_to_3d_bim.preflight import PreflightAnalyzer, PreflightStatus, ScaleConfidence
from dxf_to_3d_bim.reporting import ReviewSummaryGenerator, compute_file_sha256
from dxf_to_3d_bim.room_detection import SpatialDetector
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.wall_reconstruction import WallReconstructor

app = typer.Typer(help="DXF-to-3D-BIM: Autonomous conversion of 2D DXF floor plans into 3D BIM models.")
console = Console(legacy_windows=False)


@app.command()
def inspect(
    dxf_path: str = typer.Argument(..., help="Path to DXF drawing file to inspect"),
    out_json: Optional[str] = typer.Option(None, "--out-json", "-j", help="Path to save machine-readable preflight JSON"),
    out_md: Optional[str] = typer.Option(None, "--out-md", "-m", help="Path to save readable Markdown preflight report"),
    unit: Optional[str] = typer.Option(None, "--unit", "-u", help="Explicit unit override (mm, m, ft, in)"),
):
    """Executes universal preflight analysis on a DXF file before BIM generation."""
    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(dxf_path, unit_override=unit)

    # 1. Display Header & Status
    status_color = "green" if report.overall_status == PreflightStatus.PASSED else (
        "yellow" if report.overall_status == PreflightStatus.WARNING else "red"
    )
    console.print(f"\n[bold {status_color}]Preflight Status: {report.overall_status.value}[/bold {status_color}]")

    # 2. Key Properties Table
    table = Table(title=f"DXF Preflight Summary: {report.file_name}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("DXF Version", report.dxf_version)
    table.add_row("Detected Units", f"{report.detected_units} (INSUNITS={report.insunits_code})")
    table.add_row("Scale Confidence", report.scale_confidence.value)
    table.add_row("Scale Factor to mm", f"{report.scale_factor_to_mm}x")
    table.add_row("Raw Extents", f"{report.raw_extents.get('width', 0):.2f} x {report.raw_extents.get('depth', 0):.2f}")
    table.add_row("Projected Footprint (mm)", f"{report.extents_mm.get('width', 0):.1f} x {report.extents_mm.get('depth', 0):.1f}")
    table.add_row("Modelspace Entities", str(report.total_modelspace_entities))
    table.add_row("Paperspace Entities (Ignored)", str(report.total_paperspace_entities))
    table.add_row("Candidate Walls", str(report.candidate_counts.get("walls", 0)))
    table.add_row("Candidate Openings", f"{report.candidate_counts.get('doors', 0)} doors, {report.candidate_counts.get('windows', 0)} windows")
    console.print(table)

    # 3. Layer Classification Table
    layer_table = Table(title="Layer Semantic Classifications")
    layer_table.add_column("Layer Name", style="cyan")
    layer_table.add_column("Classification", style="white")
    for lname, cat in sorted(report.layer_classifications.items()):
        c_style = "green" if cat != "unknown" else "yellow"
        layer_table.add_row(lname, f"[{c_style}]{cat}[/{c_style}]")
    console.print(layer_table)

    # 4. Warnings and Errors
    if report.warnings:
        for w in report.warnings:
            console.print(f"[yellow][!] Warning: {w}[/yellow]")
    if report.errors:
        for err in report.errors:
            console.print(f"[bold red][X] Error: {err}[/bold red]")

    # 5. Output files if requested
    if out_json:
        p_json = Path(out_json)
        p_json.parent.mkdir(parents=True, exist_ok=True)
        p_json.write_text(report.to_json(), encoding="utf-8")
        console.print(f"[green]Machine-readable JSON preflight report written to: {out_json}[/green]")

    if out_md:
        p_md = Path(out_md)
        p_md.parent.mkdir(parents=True, exist_ok=True)
        p_md.write_text(report.to_markdown(), encoding="utf-8")
        console.print(f"[green]Markdown preflight report written to: {out_md}[/green]")

    if report.overall_status == PreflightStatus.FAILED:
        raise typer.Exit(1)


def reconstruct_dxf_model(
    dxf_path: Path | str,
    parsed: Any,
    classifier: LayerClassifier,
    active_unit: str,
    scale_factor_to_mm: float,
    storeys: int = 1,
    storey_height: float = 3000.0,
    ground_elevation: float = 0.0,
    repeat_ground_floor: bool = False,
    storey_config_path: Optional[str] = None,
    interactive_prompt: bool = True,
) -> IntermediateBimModel:
    """Reconstructs IntermediateBimModel from DXF supporting Mode A (layers) and Mode B (configured/repeated)."""
    if storeys < 1:
        raise ValueError(f"Storey count must be >= 1 (got {storeys})")
    if storey_height < 1000:
        raise ValueError(f"Storey height must be >= 1000 mm (got {storey_height})")

    loaded_storey_config = None
    if storey_config_path:
        sc_file = Path(storey_config_path)
        if not sc_file.exists():
            raise FileNotFoundError(f"Storey config file not found: {storey_config_path}")
        with open(sc_file, "r", encoding="utf-8") as f:
            loaded_storey_config = json.load(f)

    # Check for Mode A: distinct storey layers
    storey_indices = set()
    for l in parsed.lines:
        lvl = classifier.extract_level(l.layer)
        if lvl is not None:
            storey_indices.add(lvl)

    is_mode_a = len(storey_indices) > 1

    if is_mode_a:
        console.print(f"[cyan]Mode A detected: Multi-storey DXF layers found for storeys: {sorted(storey_indices)}[/cyan]")
        sorted_storeys = sorted(storey_indices)
        all_walls = []
        all_openings = []
        all_floors = []
        all_rooms = []
        all_assumptions = []

        curr_elev = ground_elevation
        for st_idx in sorted_storeys:
            st_lines = [l for l in parsed.lines if classifier.extract_level(l.layer) == st_idx]
            st_arcs = [a for a in parsed.arcs if classifier.extract_level(a.layer) == st_idx]
            st_texts = [t for t in parsed.texts if classifier.extract_level(t.layer) == st_idx]

            wall_rec = WallReconstructor()
            st_walls = wall_rec.reconstruct(st_lines, classifier=classifier)
            for w in st_walls:
                w.id = f"{w.id}_L{st_idx}"
                w.level_id = f"Level {st_idx}"
                w.height = storey_height
                setattr(w, "base_elevation", curr_elev)
            all_walls.extend(st_walls)

            detector = OpeningDetector()
            st_openings, st_unhosted = detector.detect_openings(st_lines, st_arcs, st_walls, classifier=classifier)
            for op in st_openings:
                op.id = f"{op.id}_L{st_idx}"
                setattr(op, "level_id", f"Level {st_idx}")
            all_openings.extend(st_openings)

            spatial = SpatialDetector()
            st_slab_lines = [l for l in st_lines if classifier.is_slab_layer(l.layer)]
            st_slab = spatial.detect_slab(st_walls, slab_lines=st_slab_lines)
            if st_slab:
                st_slab.id = f"{st_slab.id}_L{st_idx}"
                st_slab.level_id = f"Level {st_idx}"
                st_slab.elevation = curr_elev
                all_floors.append(st_slab)

            st_rooms = spatial.detect_rooms(st_texts, slab=st_slab, classifier=classifier)
            for rm in st_rooms:
                rm.id = f"{rm.id}_L{st_idx}"
                rm.level_id = f"Level {st_idx}"
            all_rooms.extend(st_rooms)

            curr_elev += storey_height

        storeys_effective = max(len(sorted_storeys), storeys)
        return IntermediateBimModel.create(
            project_name=Path(dxf_path).stem,
            source_dxf_path=str(Path(dxf_path).resolve()),
            source_units=active_unit,
            scale_factor=scale_factor_to_mm,
            walls=all_walls,
            openings=all_openings,
            floors=all_floors,
            rooms=all_rooms,
            assumptions=all_assumptions,
            storeys_count=storeys_effective,
            storey_heights=[storey_height] * storeys_effective,
            ground_elevation=ground_elevation,
            repeat_ground_floor=False,
            storey_config=loaded_storey_config,
        )

    # Mode B: single-level linework
    if storeys > 1 and not repeat_ground_floor and not loaded_storey_config:
        if not interactive_prompt:
            raise ValueError(
                f"Multi-storey reconstruction requested ({storeys} storeys) but DXF contains single-storey linework, "
                f"and neither --repeat-ground-floor nor --storey-config was specified."
            )
        else:
            console.print(f"[yellow]DXF linework is single-storey, but {storeys} storeys were requested.[/yellow]")
            try:
                rep_choice = input(f"Replicate ground floor footprint across all {storeys} storeys? [Y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                raise PermissionError("Generation aborted by user.")
            if rep_choice not in ("", "y", "yes"):
                raise PermissionError("Multi-storey generation aborted: unapproved ground floor replication.")
            repeat_ground_floor = True

    wall_rec = WallReconstructor()
    walls = wall_rec.reconstruct(parsed.lines, classifier=classifier)

    detector = OpeningDetector()
    openings, unhosted = detector.detect_openings(parsed.lines, parsed.arcs, walls, classifier=classifier)

    spatial = SpatialDetector()
    slab_lines = [l for l in parsed.lines if classifier.is_slab_layer(l.layer)]
    slab = spatial.detect_slab(walls, slab_lines=slab_lines)
    floors = [slab] if slab else []
    rooms = spatial.detect_rooms(parsed.texts, slab=slab, classifier=classifier)

    assumptions = []
    for u in unhosted:
        assumptions.append({
            "id": f"unhosted_{u['type']}_{u['source']}",
            "target": u["type"],
            "description": f"Unhosted {u['type']} detected near position {u['position']}",
            "assumedValue": None,
            "status": "unresolved",
        })

    return IntermediateBimModel.create(
        project_name=Path(dxf_path).stem,
        source_dxf_path=str(Path(dxf_path).resolve()),
        source_units=active_unit,
        scale_factor=scale_factor_to_mm,
        walls=walls,
        openings=openings,
        floors=floors,
        rooms=rooms,
        assumptions=assumptions,
        storeys_count=storeys,
        storey_heights=[storey_height] * storeys,
        ground_elevation=ground_elevation,
        repeat_ground_floor=repeat_ground_floor,
        storey_config=loaded_storey_config,
    )


@app.command()
def prepare(
    dxf_path: str,
    json_path: Optional[str] = typer.Option(None, "--json", "-j", help="Upstream Sketch-to-CAD JSON file"),
    output_path: str = typer.Option("intermediate-model.json", "--out", "-o", help="Output intermediate model path"),
    storeys: int = typer.Option(1, "--storeys", "-s", help="Number of storeys to reconstruct (>= 1)"),
    storey_height: float = typer.Option(3000.0, "--storey-height", help="Floor-to-floor height in mm (default 3000.0)"),
    ground_elevation: float = typer.Option(0.0, "--ground-elevation", help="Ground floor elevation in mm (default 0.0)"),
    repeat_ground_floor: bool = typer.Option(False, "--repeat-ground-floor", help="Replicate ground floor footprint across upper storeys"),
    storey_config: Optional[str] = typer.Option(None, "--storey-config", help="Path to JSON file with custom storey definitions"),
):
    """Parses DXF, reconstructs geometry, and creates an intermediate model awaiting approval."""
    if json_path and Path(json_path).exists():
        console.print(f"[cyan]Integrating upstream Sketch-to-CAD model:[/cyan] {json_path}")
        model = IntermediateBimModel.from_sketch_to_cad_json(json_path)
    else:
        parser = DxfParser()
        parsed = parser.parse(dxf_path)
        classifier = LayerClassifier()

        model = reconstruct_dxf_model(
            dxf_path=dxf_path,
            parsed=parsed,
            classifier=classifier,
            active_unit=parsed.report.detected_units,
            scale_factor_to_mm=parsed.report.scale_factor_to_mm,
            storeys=storeys,
            storey_height=storey_height,
            ground_elevation=ground_elevation,
            repeat_ground_floor=repeat_ground_floor,
            storey_config_path=storey_config,
            interactive_prompt=True,
        )

    saved_path = model.save(output_path)
    console.print(f"[bold green]Intermediate model generated at:[/bold green] {saved_path}")

    summary = ApprovalGate.generate_proposal_summary(model)
    console.print(f"[cyan]Model Footprint:[/cyan] {summary['footprint']['width_mm']} x {summary['footprint']['depth_mm']} mm ({summary['footprint']['area_m2']} m²)")
    console.print(f"[cyan]Walls:[/cyan] {summary['counts']['exterior_walls']} exterior, {summary['counts']['interior_walls']} interior")
    console.print(f"[cyan]Openings:[/cyan] {summary['counts']['doors']} doors, {summary['counts']['windows']} windows")
    console.print(f"[yellow]Status: awaiting_approval (Run 'approve {saved_path}' to approve)[/yellow]")


@app.command()
def approve(
    model_path: str,
    approved_by: str = typer.Option("User", "--by", help="Approver name"),
    notes: str = typer.Option("Approved for BIMCraft construction", "--notes", help="Approval notes"),
):
    """Enforces human approval gate and locks model version with SHA-256 hash."""
    model = IntermediateBimModel.load(model_path)
    ApprovalGate.approve(model, approved_by=approved_by, notes=notes)
    model.save(model_path)
    console.print(f"[bold green]Model successfully approved and locked:[/bold green] {model_path}")
    console.print(f"Model SHA-256: [cyan]{model.data['approval']['modelHash']}[/cyan]")


@app.command()
def build(
    model_path: str,
    out_dir: str = typer.Option("output", "--out", "-o", help="Deliverables output directory"),
    views: bool = typer.Option(True, "--views/--no-views", help="Generate 3D, elevation, and section views"),
):
    """Builds native .bimcraft project, IFC4 export, and 2D/3D views using BIMCraft CLI."""
    model = IntermediateBimModel.load(model_path)
    adapter = BimcraftAdapter()

    console.print("[cyan]Executing BIMCraft 0.9.0 build & rendering...[/cyan]")
    res = adapter.execute_build(model, output_dir=out_dir, generate_3d_views=views)

    if not res.success:
        console.print(f"[bold red]BIMCraft execution failed:[/bold red] {res.error_message}")
        raise typer.Exit(1)

    console.print(f"[bold green]Native project created:[/bold green] {res.bimcraft_path}")
    console.print(f"[bold green]IFC4 exported:[/bold green] {res.ifc_path}")
    console.print(f"[bold green]Plan preview rendered:[/bold green] {res.png_path}")
    if res.view_3d_path and res.view_3d_path.exists():
        console.print(f"[bold green]3D Axonometric view rendered:[/bold green] {res.view_3d_path}")
    if res.elevation_south_path and res.elevation_south_path.exists():
        console.print(f"[bold green]South Elevation rendered:[/bold green] {res.elevation_south_path}")
    if res.section_path and res.section_path.exists():
        console.print(f"[bold green]Building Section rendered:[/bold green] {res.section_path}")

    # Validate
    validator = ModelValidator(adapter)
    report = validator.validate(model, res)
    report_file = Path(out_dir) / "validation-report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    console.print(f"[bold green]Validation report written:[/bold green] {report_file}")
    console.print(f"Overall status: [bold]{report['overallStatus']}[/bold]")

    # Geometry Comparison & Overlay
    dxf_source = model.data.get("metadata", {}).get("sourceDxfPath")
    comp_report = None
    if dxf_source and Path(dxf_source).exists():
        overlay_file = Path(out_dir) / f"{Path(dxf_source).stem}_comparison_overlay.png"
        comparator = SourceToBimComparator()
        comp_report = comparator.compare(dxf_source, model, output_image_path=overlay_file)
        console.print(f"[bold green]Comparison overlay generated:[/bold green] {overlay_file}")

    # Generate Markdown Review Summary
    summary_md = ReviewSummaryGenerator.generate_markdown(model, report, comp_report, res)
    summary_file = Path(out_dir) / "review_summary.md"
    summary_file.write_text(summary_md, encoding="utf-8")
    console.print(f"[bold green]Human review summary generated:[/bold green] {summary_file}")


@app.command()
def compare(
    dxf_path: str,
    model_path: str,
    overlay_path: str = typer.Option("comparison_overlay.png", "--overlay", "-o", help="Output comparison overlay image"),
):
    """Compares source DXF geometry against reconstructed intermediate BIM model."""
    model = IntermediateBimModel.load(model_path)
    comparator = SourceToBimComparator()
    report = comparator.compare(dxf_path, model, output_image_path=overlay_path)

    table = Table(title=f"Source DXF vs Reconstructed BIM Comparison: {report.project_name}")
    table.add_column("Metric", style="cyan")
    table.add_column("DXF Source", style="white")
    table.add_column("BIM Model", style="white")
    table.add_column("Deviation", style="yellow")
    table.add_column("Status", style="green")

    for k, m in report.footprint_deviation.items():
        table.add_row(m.metric_name, f"{m.source_value:.1f}", f"{m.reconstructed_value:.1f}", f"{m.deviation_abs:.1f} ({m.deviation_pct}%)", m.status)

    console.print(table)
    console.print(f"Overall comparison status: [bold]{report.overall_status}[/bold]")
    if report.overlay_image_path:
        console.print(f"Visual overlay saved to: [green]{report.overlay_image_path}[/green]")


@app.command()
def run(
    dxf_path: str = typer.Argument(..., help="Path to input architectural DXF floor plan"),
    out_dir: str = typer.Option("output", "--out", "-o", help="Structured deliverables output directory"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to project configuration JSON"),
    unit: Optional[str] = typer.Option(None, "--unit", "-u", help="Explicit unit override (mm, m, ft, in)"),
    storeys: int = typer.Option(1, "--storeys", "-s", help="Number of storeys to reconstruct (>= 1)"),
    storey_height: float = typer.Option(3000.0, "--storey-height", help="Floor-to-floor height in mm (default 3000.0)"),
    ground_elevation: float = typer.Option(0.0, "--ground-elevation", help="Ground floor elevation in mm (default 0.0)"),
    repeat_ground_floor: bool = typer.Option(False, "--repeat-ground-floor", help="Replicate ground floor footprint across upper storeys"),
    storey_config: Optional[str] = typer.Option(None, "--storey-config", help="Path to JSON file with custom storey definitions"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Run without terminal prompts (requires config or auto-approve)"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Simulate human approval for automated headless testing"),
    views: bool = typer.Option(True, "--views/--no-views", help="Generate 3D isometric, elevation, and section views"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing output directory files without warning"),
):
    """Runs complete guided end-to-end pipeline from arbitrary DXF to validated BIMCraft project, IFC, & 3D renders."""
    console.print(f"\n[bold cyan]=== DXF-to-3D-BIM Universal Pipeline ===[/bold cyan]")
    input_path = Path(dxf_path)
    if not input_path.exists() or not input_path.is_file():
        console.print(f"[bold red]Input file error:[/bold red] File not found: {dxf_path}")
        raise typer.Exit(1)

    out_base = Path(out_dir).resolve()

    # Create structured subdirectories
    analysis_dir = out_base / "analysis"
    models_dir = out_base / "models"
    previews_dir = out_base / "previews"
    reports_dir = out_base / "reports"

    for d in [analysis_dir, models_dir, previews_dir, reports_dir]:
        d.mkdir(parents=True, exist_ok=True)

    manifest = RunManifest(
        project_name=input_path.stem,
        source_dxf={
            "path": str(input_path.resolve()),
            "sha256": compute_file_sha256(input_path),
            "size_bytes": input_path.stat().st_size,
        },
        toolchain={
            "python": sys.version.split()[0],
            "bimcraft_cli": "0.9.0",
            "platform": sys.platform,
        },
    )

    # 1. Preflight Analysis Stage
    console.print("[cyan]Running Preflight Analysis...[/cyan]")
    analyzer = PreflightAnalyzer()
    preflight = analyzer.analyze(input_path, unit_override=unit)

    # Save preflight outputs
    preflight_json = analysis_dir / "preflight_report.json"
    preflight_md = analysis_dir / "preflight_report.md"
    preflight_json.write_text(preflight.to_json(), encoding="utf-8")
    preflight_md.write_text(preflight.to_markdown(), encoding="utf-8")
    manifest.add_artifact("analysis", "preflight_json", preflight_json, base_dir=out_base)
    manifest.add_artifact("analysis", "preflight_md", preflight_md, base_dir=out_base)

    if preflight.overall_status == PreflightStatus.FAILED:
        console.print(f"[bold red]Preflight Analysis FAILED:[/bold red]")
        for err in preflight.errors:
            console.print(f"  [bold red][X] {err}[/bold red]")
        manifest.run_status = "FAILED"
        manifest.errors = preflight.errors
        manifest.save(out_base / "manifest.json")
        raise typer.Exit(1)

    if preflight.warnings:
        console.print("[yellow]Preflight Warnings Detected:[/yellow]")
        for w in preflight.warnings:
            console.print(f"  [yellow][!] {w}[/yellow]")
        manifest.warnings.extend(preflight.warnings)

    # 2. Configuration Stage
    if config:
        console.print(f"[cyan]Loading configuration overrides from:[/cyan] {config}")
        try:
            cfg = ConfigManager.load_user_config(config)
        except Exception as e:
            console.print(f"[bold red]Configuration error:[/bold red] {e}")
            manifest.run_status = "FAILED"
            manifest.errors.append(str(e))
            manifest.save(out_base / "manifest.json")
            raise typer.Exit(1)
    else:
        cfg = ConfigManager.load_defaults()

    if unit:
        cfg.units.source_unit = unit

    # 3. Geometric Reconstruction Stage
    console.print("[cyan]Reconstructing Architectural Geometry...[/cyan]")
    active_unit = cfg.units.source_unit or preflight.detected_units
    parser = DxfParser(fallback_units=active_unit)
    parsed = parser.parse(input_path, unit_override=active_unit)
    classifier = LayerClassifier()

    # Determine effective storey parameters
    eff_storey_height = storey_height
    if cfg.levels.floor_to_floor_height != 3000.0 and storey_height == 3000.0:
        eff_storey_height = cfg.levels.floor_to_floor_height

    eff_storeys = storeys
    if cfg.levels.default_storeys > 1 and storeys == 1:
        eff_storeys = cfg.levels.default_storeys

    eff_repeat = repeat_ground_floor or cfg.levels.repeat_ground_floor
    eff_config_path = storey_config or cfg.levels.storey_config_path

    try:
        model = reconstruct_dxf_model(
            dxf_path=input_path,
            parsed=parsed,
            classifier=classifier,
            active_unit=active_unit,
            scale_factor_to_mm=preflight.scale_factor_to_mm,
            storeys=eff_storeys,
            storey_height=eff_storey_height,
            ground_elevation=ground_elevation,
            repeat_ground_floor=eff_repeat,
            storey_config_path=eff_config_path,
            interactive_prompt=not non_interactive and not auto_approve,
        )
    except Exception as e:
        console.print(f"[bold red]Reconstruction error:[/bold red] {e}")
        manifest.run_status = "FAILED"
        manifest.errors.append(str(e))
        manifest.save(out_base / "manifest.json")
        raise typer.Exit(1)
    inter_model_path = analysis_dir / "intermediate-model.json"
    model.save(inter_model_path)
    manifest.add_artifact("analysis", "intermediate_model", inter_model_path, base_dir=out_base)

    # 4. Guided Approval Stage
    approval_session = GuidedApprovalSession(
        model=model,
        preflight=preflight,
        dxf_path=input_path,
        config=cfg,
        console=console,
    )

    try:
        approval_record = approval_session.run_guided_session(
            interactive=not non_interactive and not auto_approve,
            auto_approve=auto_approve,
            approved_by="CLI User" if not auto_approve else "Automated Runner",
            notes="Approved via DXF-to-3D-BIM guided workflow",
        )
    except PermissionError as pe:
        console.print(f"[bold red]Approval Gate:[/bold red] {pe}")
        manifest.run_status = "REJECTED"
        manifest.errors.append(str(pe))
        manifest.save(out_base / "manifest.json")
        raise typer.Exit(2)
    except ValueError as ve:
        console.print(f"[bold red]Configuration/Unit Requirement Error:[/bold red] {ve}")
        manifest.run_status = "FAILED"
        manifest.errors.append(str(ve))
        manifest.save(out_base / "manifest.json")
        raise typer.Exit(1)

    approval_record_file = analysis_dir / "approval_record.json"
    with open(approval_record_file, "w", encoding="utf-8") as f:
        json.dump(approval_record, f, indent=2)
    manifest.add_artifact("analysis", "approval_record", approval_record_file, base_dir=out_base)
    manifest.approved_parameters = approval_record.get("approvedParameters", {})

    # Re-save approved model state with updated hash and refresh manifest artifact
    model.save(inter_model_path)
    manifest.add_artifact("analysis", "intermediate_model", inter_model_path, base_dir=out_base)

    # 5. BIMCraft Semantic Construction & Renders
    console.print("\n[cyan]Executing BIMCraft 0.9.0 semantic construction and rendering...[/cyan]")
    adapter = BimcraftAdapter()
    build_res = adapter.execute_build(
        model=model,
        output_dir=out_base,
        base_name=input_path.stem,
        generate_3d_views=views,
        models_dir=models_dir,
        previews_dir=previews_dir,
    )

    if not build_res.success:
        console.print(f"[bold red]BIMCraft execution failed:[/bold red] {build_res.error_message}")
        manifest.run_status = "FAILED"
        manifest.errors.append(build_res.error_message or "BIMCraft failed")
        manifest.save(out_base / "manifest.json")
        raise typer.Exit(1)

    if build_res.bimcraft_path:
        manifest.add_artifact("models", "bimcraft", build_res.bimcraft_path, base_dir=out_base)
    if build_res.ifc_path:
        manifest.add_artifact("models", "ifc4", build_res.ifc_path, base_dir=out_base)
    if build_res.png_path:
        manifest.add_artifact("previews", "plan_preview", build_res.png_path, base_dir=out_base)
    if build_res.view_3d_path:
        manifest.add_artifact("previews", "view_3d", build_res.view_3d_path, base_dir=out_base)
    if build_res.elevation_south_path:
        manifest.add_artifact("previews", "elevation_south", build_res.elevation_south_path, base_dir=out_base)
    if build_res.elevation_east_path:
        manifest.add_artifact("previews", "elevation_east", build_res.elevation_east_path, base_dir=out_base)
    if build_res.section_path:
        manifest.add_artifact("previews", "section_a", build_res.section_path, base_dir=out_base)
    if build_res.level_plan_paths:
        for lvl_name, lpath in build_res.level_plan_paths.items():
            if lpath.exists() and lpath != build_res.png_path:
                slug = lvl_name.lower().replace(" ", "_")
                manifest.add_artifact("previews", f"plan_{slug}", lpath, base_dir=out_base)

    # 6. Deep Validation Stage
    console.print("[cyan]Performing Independent IFC & Topological Validation...[/cyan]")
    validator = ModelValidator(adapter)
    val_report = validator.validate(model, build_res)
    val_file = reports_dir / "validation-report.json"
    with open(val_file, "w", encoding="utf-8") as f:
        json.dump(val_report, f, indent=2)
    manifest.add_artifact("reports", "validation_report", val_file, base_dir=out_base)

    passed_checks = len([c for c in val_report.get("checks", []) if c.get("status") == "PASSED"])
    failed_checks = len([c for c in val_report.get("checks", []) if c.get("status") == "FAILED"])
    warning_checks = len([c for c in val_report.get("checks", []) if c.get("status") == "WARNING"])

    manifest.validation_summary = {
        "status": val_report.get("overallStatus", "UNKNOWN"),
        "total_checks": len(val_report.get("checks", [])),
        "passed": passed_checks,
        "failed": failed_checks,
        "warnings": warning_checks,
    }
    manifest.element_summary = val_report.get("elementSummary", {}).get("generated", {})

    # 7. Geometric Comparison & Overlay Stage
    comp_report = None
    if input_path.exists():
        console.print("[cyan]Generating Source DXF vs. BIM Geometric Overlay...[/cyan]")
        overlay_file = previews_dir / f"{input_path.stem}_comparison_overlay.png"
        comparator = SourceToBimComparator()
        comp_report = comparator.compare(str(input_path), model, output_image_path=overlay_file)
        manifest.add_artifact("previews", "comparison_overlay", overlay_file, base_dir=out_base)

    # 8. Human Review Summary Stage
    summary_md = ReviewSummaryGenerator.generate_markdown(model, val_report, comp_report, build_res)
    review_file = reports_dir / "review_summary.md"
    review_file.write_text(summary_md, encoding="utf-8")
    manifest.add_artifact("reports", "review_summary", review_file, base_dir=out_base)

    # 9. Save Manifest
    manifest.run_status = "SUCCESS" if val_report.get("overallStatus") == "PASSED" else "WARNING"
    manifest.save(out_base / "manifest.json")

    # 10. Display Completion Summary
    console.print("\n[bold green]====================================================================[/bold green]")
    console.print("[bold green]       DXF-to-3D-BIM Pipeline Run Successfully Completed!           [/bold green]")
    console.print("[bold green]====================================================================[/bold green]\n")

    summary_table = Table(title=f"Generated Deliverables Package: {out_base.name}")
    summary_table.add_column("Category", style="cyan")
    summary_table.add_column("Artifact", style="white")
    summary_table.add_column("Relative Path", style="green")

    summary_table.add_row("Manifest", "Run Manifest JSON", "manifest.json")
    summary_table.add_row("Models", "Native BIMCraft Project", f"models/{build_res.bimcraft_path.name}")
    summary_table.add_row("Models", "Standard IFC4 Export", f"models/{build_res.ifc_path.name}")
    summary_table.add_row("Previews", "2D Plan Preview", f"previews/{build_res.png_path.name}")
    if build_res.view_3d_path:
        summary_table.add_row("Previews", "3D Axonometric Render", f"previews/{build_res.view_3d_path.name}")
    if build_res.level_plan_paths:
        for lvl_name, lpath in build_res.level_plan_paths.items():
            if lpath.exists() and lpath != build_res.png_path:
                summary_table.add_row("Previews", f"{lvl_name} Plan Preview", f"previews/{lpath.name}")
    if comp_report and comp_report.overlay_image_path:
        summary_table.add_row("Previews", "CAD/BIM Comparison Overlay", f"previews/{overlay_file.name}")
    summary_table.add_row("Reports", "Independent Validation Report", "reports/validation-report.json")
    summary_table.add_row("Reports", "Human Review Summary Markdown", "reports/review_summary.md")
    console.print(summary_table)

    console.print(f"[bold]Validation Status:[/bold] [{('green' if manifest.run_status == 'SUCCESS' else 'yellow')}]{manifest.run_status}[/]")
    console.print(f"[bold]Output Root:[/bold] [cyan]{out_base}[/cyan]\n")


def main():
    app()


if __name__ == "__main__":
    main()
