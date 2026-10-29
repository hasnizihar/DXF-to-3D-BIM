"""Automated tests for Universal DXF Preflight Analyzer."""

from pathlib import Path
import json
import pytest
import ezdxf

from dxf_to_3d_bim.preflight import PreflightAnalyzer, PreflightStatus, ScaleConfidence
from tests.create_fixtures import create_synthetic_room_dxf


def test_preflight_valid_dxf(tmp_path):
    dxf_file = tmp_path / "valid.dxf"
    create_synthetic_room_dxf(dxf_file)

    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(dxf_file)

    assert report.overall_status in (PreflightStatus.PASSED, PreflightStatus.WARNING)
    assert report.dxf_version == "AC1024"
    assert report.insunits_code == 4
    assert report.detected_units == "mm"
    assert report.unit_ambiguity is False
    assert report.scale_confidence == ScaleConfidence.HIGH
    assert report.candidate_counts["walls"] >= 8
    assert report.candidate_counts["doors"] >= 2
    assert report.candidate_counts["windows"] >= 1
    assert report.candidate_counts["closed_polylines"] == 1


def test_preflight_missing_file(tmp_path):
    missing_path = tmp_path / "does_not_exist.dxf"
    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(missing_path)

    assert report.overall_status == PreflightStatus.FAILED
    assert len(report.errors) == 1
    assert "inaccessible" in report.errors[0] or "not found" in report.errors[0]


def test_preflight_empty_file(tmp_path):
    empty_file = tmp_path / "empty.dxf"
    empty_file.write_bytes(b"")

    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(empty_file)

    assert report.overall_status == PreflightStatus.FAILED
    assert "empty (0 bytes)" in report.errors[0]


def test_preflight_corrupt_dxf(tmp_path):
    corrupt_file = tmp_path / "corrupt.dxf"
    corrupt_file.write_text("THIS IS NOT A VALID DXF FILE", encoding="utf-8")

    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(corrupt_file)

    assert report.overall_status == PreflightStatus.FAILED
    assert "Corrupt or invalid DXF file" in report.errors[0]


def test_preflight_empty_modelspace(tmp_path):
    empty_msp = tmp_path / "empty_msp.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.saveas(str(empty_msp))

    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(empty_msp)

    assert report.overall_status == PreflightStatus.FAILED
    assert any("Modelspace contains 0 entities" in err for err in report.errors)


def test_preflight_annotations_only_drawing(tmp_path):
    anno_file = tmp_path / "anno_only.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("A-ANNO-TEXT")
    msp = doc.modelspace()
    msp.add_text("Note: Site boundary only", dxfattribs={"layer": "A-ANNO-TEXT", "insert": (100, 100)})
    doc.saveas(str(anno_file))

    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(anno_file)

    assert report.overall_status == PreflightStatus.FAILED
    assert any("No architectural wall geometry recognized" in err for err in report.errors)


def test_preflight_missing_units_ambiguity(tmp_path):
    unspec_file = tmp_path / "unspecified_units.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0  # Unspecified
    doc.layers.add("A-WALL-EXTR")
    msp = doc.modelspace()
    # 8.0 x 6.0 meters in raw units
    msp.add_line((0, 0), (8.0, 0), dxfattribs={"layer": "A-WALL-EXTR"})
    msp.add_line((8.0, 0), (8.0, 6.0), dxfattribs={"layer": "A-WALL-EXTR"})
    doc.saveas(str(unspec_file))

    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(unspec_file)

    assert report.unit_ambiguity is True
    assert report.scale_confidence == ScaleConfidence.AMBIGUOUS
    assert report.suggested_unit == "m"
    assert report.scale_factor_to_mm == 1000.0


def test_preflight_explicit_non_mm_units(tmp_path):
    meters_file = tmp_path / "meters.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # Meters
    doc.layers.add("A-WALL-EXTR")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10.0, 0), dxfattribs={"layer": "A-WALL-EXTR"})
    msp.add_line((10.0, 0), (10.0, 5.0), dxfattribs={"layer": "A-WALL-EXTR"})
    doc.saveas(str(meters_file))

    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(meters_file)

    assert report.detected_units == "m"
    assert report.scale_factor_to_mm == 1000.0
    assert report.extents_mm["width"] == 10000.0
    assert report.extents_mm["depth"] == 5000.0
    assert report.scale_confidence == ScaleConfidence.HIGH


def test_preflight_unknown_layers(tmp_path):
    unk_file = tmp_path / "unknown_layers.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("A-WALL-EXTR")
    doc.layers.add("STRANGE_CUSTOM_LAYER_XYZ")
    msp = doc.modelspace()
    msp.add_line((0, 0), (5000, 0), dxfattribs={"layer": "A-WALL-EXTR"})
    msp.add_line((0, 0), (1000, 1000), dxfattribs={"layer": "STRANGE_CUSTOM_LAYER_XYZ"})
    doc.saveas(str(unk_file))

    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(unk_file)

    assert "STRANGE_CUSTOM_LAYER_XYZ" in report.unclassified_layers
    assert report.layer_classifications["STRANGE_CUSTOM_LAYER_XYZ"] == "unknown"


def test_preflight_degenerate_geometry(tmp_path):
    degen_file = tmp_path / "degen.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("A-WALL-EXTR")
    msp = doc.modelspace()
    # Normal wall line
    msp.add_line((0, 0), (5000, 0), dxfattribs={"layer": "A-WALL-EXTR"})
    # Duplicate line
    msp.add_line((0, 0), (5000, 0), dxfattribs={"layer": "A-WALL-EXTR"})
    # Zero-length line
    msp.add_line((100, 100), (100, 100), dxfattribs={"layer": "A-WALL-EXTR"})
    doc.saveas(str(degen_file))

    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(degen_file)

    assert report.degenerate_geometry_counts["zero_length"] == 1
    assert report.degenerate_geometry_counts["duplicates"] == 1


def test_preflight_json_and_markdown_reports(tmp_path):
    dxf_file = tmp_path / "room.dxf"
    create_synthetic_room_dxf(dxf_file)

    analyzer = PreflightAnalyzer()
    report = analyzer.analyze(dxf_file)

    # Test JSON serialization
    json_str = report.to_json()
    parsed_json = json.loads(json_str)
    assert parsed_json["file_name"] == "room.dxf"
    assert parsed_json["overall_status"] in ("PASSED", "WARNING")

    # Test Markdown output
    md_str = report.to_markdown()
    assert "# Universal DXF Preflight Report: room.dxf" in md_str
    assert "## 1. Units & Scale Evaluation" in md_str
    assert "## 3. Semantic Layer Analysis" in md_str
    assert "## 4. Candidate Architectural Features" in md_str

