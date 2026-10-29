"""Comprehensive command-line interface for DXF-to-3D-BIM."""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter, BimcraftBuildResult
from dxf_to_3d_bim.comparison import SourceToBimComparator
from dxf_to_3d_bim.dxf_parser import DxfParser
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.opening_detection import OpeningDetector
from dxf_to_3d_bim.reporting import ReviewSummaryGenerator
from dxf_to_3d_bim.room_detection import SpatialDetector
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.wall_reconstruction import WallReconstructor

app = typer.Typer(help="DXF-to-3D-BIM: Autonomous conversion of 2D DXF floor plans into 3D BIM models.")
console = Console()


@app.command()
def inspect(dxf_path: str):
    """Inspects a 2D DXF file and displays units, bounding box, and layer tallies."""
    parser = DxfParser()
    try:
        report = parser.inspect_file(dxf_path)
    except Exception as e:
        console.print(f"[bold red]Error inspecting file:[/bold red] {e}")
        raise typer.Exit(1)

    table = Table(title=f"DXF Inspection: {Path(dxf_path).name}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("DXF Version", report.dxf_version)
    table.add_row("Detected Units", f"{report.detected_units} (INSUNITS={report.insunits_code})")
    table.add_row("Scale to mm", str(report.scale_factor_to_mm))
    table.add_row("Extents (mm)", f"{report.bounding_box['width']} x {report.bounding_box['depth']}")
    table.add_row("Total Entities", str(report.total_entities))
    table.add_row("Layers Found", ", ".join(report.layers))

    console.print(table)
    if report.warnings:
        for w in report.warnings:
            console.print(f"[yellow]Warning: {w}[/yellow]")


@app.command()
def prepare(
    dxf_path: str,
    json_path: Optional[str] = typer.Option(None, "--json", "-j", help="Upstream Sketch-to-CAD JSON file"),
    output_path: str = typer.Option("intermediate-model.json", "--out", "-o", help="Output intermediate model path"),
):
    """Parses DXF, reconstructs geometry, and creates an intermediate model awaiting approval."""
    if json_path and Path(json_path).exists():
        console.print(f"[cyan]Integrating upstream Sketch-to-CAD model:[/cyan] {json_path}")
        model = IntermediateBimModel.from_sketch_to_cad_json(json_path)
    else:
        parser = DxfParser()
        parsed = parser.parse(dxf_path)

        classifier = LayerClassifier()
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

        project_name = Path(dxf_path).stem
        model = IntermediateBimModel.create(
            project_name=project_name,
            source_dxf_path=dxf_path,
            source_units=parsed.report.detected_units,
            scale_factor=parsed.report.scale_factor_to_mm,
            walls=walls,
            openings=openings,
            floors=floors,
            rooms=rooms,
            assumptions=assumptions,
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
    dxf_path: str,
    out_dir: str = typer.Option("output", "--out", "-o", help="Deliverables output directory"),
    auto_approve: bool = typer.Option(False, "--auto-approve", help="Simulate human approval for automated testing"),
):
    """Runs complete end-to-end pipeline from DXF to validated BIMCraft project, IFC, & 3D renders."""
    console.print(f"[bold cyan]=== Starting DXF-to-3D-BIM Pipeline ===[/bold cyan]")
    model_file = Path(out_dir) / "intermediate-model.json"

    # 1. Prepare
    prepare(dxf_path=dxf_path, json_path=None, output_path=str(model_file))

    # 2. Approval
    if auto_approve:
        console.print("[yellow]Auto-approving model for automated pipeline execution...[/yellow]")
        approve(model_path=str(model_file), approved_by="Automated Test Runner", notes="Auto-approved test run")
    else:
        console.print("[bold red]Approval required! Run 'approve' on the model before build.[/bold red]")
        raise typer.Exit(0)

    # 3. Build & Validate
    build(model_path=str(model_file), out_dir=out_dir, views=True)
    console.print(f"[bold green]=== Pipeline Complete! ===[/bold green]")


def main():
    app()


if __name__ == "__main__":
    main()
