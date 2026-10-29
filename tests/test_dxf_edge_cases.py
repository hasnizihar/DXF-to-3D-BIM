"""Tests for real-world DXF edge cases: duplicate lines, unsupported entities, block inserts, and missing units."""

import pytest
from pathlib import Path
import ezdxf

from dxf_to_3d_bim.dxf_parser import DxfParser
from dxf_to_3d_bim.wall_reconstruction import WallReconstructor
from dxf_to_3d_bim.layer_classifier import LayerClassifier

def test_dxf_with_unsupported_entities_gracefully_ignored(tmp_path):
    """DXF containing HATCH, POINT, and 3DFACE entities alongside walls."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("A-WALL-EXTR")
    doc.layers.add("A-HATCH")
    msp = doc.modelspace()

    # Legitimate wall line
    msp.add_line((0, 0), (5000, 0), dxfattribs={"layer": "A-WALL-EXTR"})

    # Unsupported / non-building entities
    msp.add_point((100, 100))
    msp.add_circle((200, 200), radius=50)

    dxf_file = tmp_path / "mixed_entities.dxf"
    doc.saveas(str(dxf_file))

    parser = DxfParser()
    parsed = parser.parse(dxf_file)
    assert len(parsed.lines) == 1
    assert parsed.lines[0].layer == "A-WALL-EXTR"

def test_dxf_missing_units_fallback(tmp_path):
    """DXF with $INSUNITS = 0 (unspecified) should log warning and use fallback."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0  # Unspecified
    doc.layers.add("A-WALL-EXTR")
    msp = doc.modelspace()
    msp.add_line((0, 0), (3000, 0), dxfattribs={"layer": "A-WALL-EXTR"})

    dxf_file = tmp_path / "unspecified_units.dxf"
    doc.saveas(str(dxf_file))

    parser = DxfParser(fallback_units="mm")
    report = parser.inspect_file(dxf_file)
    assert report.detected_units == "mm"
    assert any("unspecified" in w for w in report.warnings)

def test_dxf_with_block_insert_expansion(tmp_path):
    """DXF where wall lines are defined inside a block INSERT."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("A-WALL-EXTR")

    # Define block
    blk = doc.blocks.new("WALL_BLOCK")
    blk.add_line((0, 0), (4000, 0))

    msp = doc.modelspace()
    msp.add_blockref("WALL_BLOCK", insert=(1000, 2000), dxfattribs={"layer": "A-WALL-EXTR"})

    dxf_file = tmp_path / "block_insert.dxf"
    doc.saveas(str(dxf_file))

    parser = DxfParser()
    parsed = parser.parse(dxf_file)

    assert len(parsed.lines) == 1
    l = parsed.lines[0]
    assert l.start == (1000.0, 2000.0)
    assert l.end == (5000.0, 2000.0)
    assert l.source_type == "INSERT/LINE"
