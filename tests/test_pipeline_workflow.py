"""Automated integration tests for the universal one-command DXF-to-3D-BIM pipeline."""

from pathlib import Path
import json
import pytest
from typer.testing import CliRunner
import ezdxf

from dxf_to_3d_bim.cli import app
from dxf_to_3d_bim.manifest import file_sha256
from tests.create_fixtures import create_synthetic_room_dxf

runner = CliRunner()


def test_pipeline_successful_end_to_end_run(tmp_path):
    dxf_file = tmp_path / "room.dxf"
    create_synthetic_room_dxf(dxf_file)
    out_dir = tmp_path / "deliverables"

    result = runner.invoke(app, ["run", str(dxf_file), "--out", str(out_dir), "--auto-approve", "--non-interactive"])
    assert result.exit_code == 0, f"CLI output: {result.output}"

    # Verify directory structure
    assert (out_dir / "analysis").is_dir()
    assert (out_dir / "models").is_dir()
    assert (out_dir / "previews").is_dir()
    assert (out_dir / "reports").is_dir()

    # Verify manifest
    manifest_file = out_dir / "manifest.json"
    assert manifest_file.exists()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["run_status"] == "SUCCESS"
    assert manifest_data["project_name"] == "room"

    # Verify models
    assert (out_dir / "models" / "room.bimcraft").exists()
    assert (out_dir / "models" / "room.ifc").exists()

    # Verify previews
    assert (out_dir / "previews" / "room.png").exists()
    assert (out_dir / "previews" / "room_3d.png").exists()

    # Verify reports
    assert (out_dir / "reports" / "validation-report.json").exists()
    assert (out_dir / "reports" / "review_summary.md").exists()


def test_pipeline_missing_file_fails(tmp_path):
    missing_dxf = tmp_path / "missing.dxf"
    out_dir = tmp_path / "output_missing"

    result = runner.invoke(app, ["run", str(missing_dxf), "--out", str(out_dir), "--auto-approve", "--non-interactive"])
    assert result.exit_code == 1
    assert "File not found" in result.output


def test_pipeline_corrupt_dxf_fails(tmp_path):
    corrupt_dxf = tmp_path / "bad.dxf"
    corrupt_dxf.write_text("INVALID DXF CONTENT", encoding="utf-8")
    out_dir = tmp_path / "output_bad"

    result = runner.invoke(app, ["run", str(corrupt_dxf), "--out", str(out_dir), "--auto-approve", "--non-interactive"])
    assert result.exit_code == 1
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_status"] == "FAILED"


def test_pipeline_approval_rejected_fails(tmp_path):
    dxf_file = tmp_path / "room.dxf"
    create_synthetic_room_dxf(dxf_file)
    out_dir = tmp_path / "output_rejected"

    # In interactive mode, user enters '5' to cancel
    result = runner.invoke(app, ["run", str(dxf_file), "--out", str(out_dir)], input="5\n")
    assert result.exit_code == 2
    assert (out_dir / "manifest.json").exists()
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_status"] == "REJECTED"


def test_pipeline_non_interactive_ambiguity_without_unit_fails(tmp_path):
    dxf_file = tmp_path / "ambig.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    doc.layers.add("A-WALL-EXTR")
    msp = doc.modelspace()
    msp.add_line((0, 0), (8.0, 0), dxfattribs={"layer": "A-WALL-EXTR"})
    msp.add_line((8.0, 0), (8.0, 6.0), dxfattribs={"layer": "A-WALL-EXTR"})
    doc.saveas(str(dxf_file))
    out_dir = tmp_path / "output_ambig"

    result = runner.invoke(app, ["run", str(dxf_file), "--out", str(out_dir), "--non-interactive"])
    assert result.exit_code == 1
    assert "Drawing units" in result.output
    assert "unspecified" in result.output


def test_pipeline_non_interactive_ambiguity_with_unit_override_succeeds(tmp_path):
    dxf_file = tmp_path / "ambig_override.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    doc.layers.add("A-WALL-EXTR")
    msp = doc.modelspace()
    # 4 walls of a small room in meters
    msp.add_line((0, 0), (6.0, 0), dxfattribs={"layer": "A-WALL-EXTR"})
    msp.add_line((6.0, 0), (6.0, 4.0), dxfattribs={"layer": "A-WALL-EXTR"})
    msp.add_line((6.0, 4.0), (0, 4.0), dxfattribs={"layer": "A-WALL-EXTR"})
    msp.add_line((0, 4.0), (0, 0), dxfattribs={"layer": "A-WALL-EXTR"})
    doc.saveas(str(dxf_file))
    out_dir = tmp_path / "output_ambig_resolved"

    result = runner.invoke(app, [
        "run", str(dxf_file),
        "--out", str(out_dir),
        "--unit", "m",
        "--auto-approve",
        "--non-interactive"
    ])
    assert result.exit_code == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_status"] in ("SUCCESS", "WARNING")


def test_pipeline_views_disabled_flag(tmp_path):
    dxf_file = tmp_path / "room_noviews.dxf"
    create_synthetic_room_dxf(dxf_file)
    out_dir = tmp_path / "output_noviews"

    result = runner.invoke(app, [
        "run", str(dxf_file),
        "--out", str(out_dir),
        "--no-views",
        "--auto-approve",
        "--non-interactive"
    ])
    assert result.exit_code == 0
    assert not (out_dir / "previews" / "room_noviews_3d.png").exists()


def test_pipeline_manifest_integrity(tmp_path):
    dxf_file = tmp_path / "room_manifest.dxf"
    create_synthetic_room_dxf(dxf_file)
    out_dir = tmp_path / "output_manifest"

    result = runner.invoke(app, [
        "run", str(dxf_file),
        "--out", str(out_dir),
        "--auto-approve",
        "--non-interactive"
    ])
    assert result.exit_code == 0
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Verify that recorded artifact hashes match actual disk files
    for cat, artifacts in manifest["artifacts"].items():
        for name, info in artifacts.items():
            abs_p = Path(info["absolute_path"])
            assert abs_p.exists()
            assert file_sha256(abs_p) == info["sha256"]
            assert abs_p.stat().st_size == info["size_bytes"]
