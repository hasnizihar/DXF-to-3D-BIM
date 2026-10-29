"""Tests for DXF parsing and metadata extraction."""

from pathlib import Path
import pytest
from dxf_to_3d_bim.dxf_parser import DxfParser
from tests.create_fixtures import create_synthetic_room_dxf

@pytest.fixture
def sample_dxf(tmp_path) -> Path:
    dxf_file = tmp_path / "test_room.dxf"
    return create_synthetic_room_dxf(dxf_file)

def test_inspect_file(sample_dxf):
    parser = DxfParser()
    report = parser.inspect_file(sample_dxf)

    assert report.insunits_code == 4
    assert report.detected_units == "mm"
    assert report.scale_factor_to_mm == 1.0
    assert report.bounding_box["width"] == 6000.0
    assert report.bounding_box["depth"] == 4000.0
    assert "A-WALL-EXTR" in report.layers
    assert "A-DOOR" in report.layers
    assert "A-GLAZ" in report.layers
    assert report.total_entities >= 10

def test_parse_entities(sample_dxf):
    parser = DxfParser()
    data = parser.parse(sample_dxf)

    assert len(data.lines) > 0
    assert len(data.arcs) >= 1
    assert len(data.texts) >= 1
    assert data.texts[0].text == "Living Room"
