"""Tests for pure-Python independent IFC/STEP parser."""

import pytest
from pathlib import Path
from dxf_to_3d_bim.ifc_parser import PureIfcParser

def test_ifc_parser_on_sample_fixture():
    sample_ifc = Path("skills/dxf-to-3d-bim/examples/simple-house/simple_room.ifc")
    assert sample_ifc.exists()

    parser = PureIfcParser(sample_ifc)
    inspection = parser.inspect()

    assert inspection.schema == "IFC4"
    assert inspection.counts["wall"] == 4
    assert inspection.counts["door"] == 1
    assert inspection.counts["window"] == 1
    assert inspection.counts["slab"] == 1
    assert inspection.counts["opening_element"] == 2

    # Verify physical voiding of host walls
    assert inspection.voids_verified is True
    assert inspection.fills_verified is True
    assert inspection.containment_verified is True

    # Check door dimensions
    door = inspection.openings["doors"][0]
    assert door["width"] == 900.0
    assert door["height"] == 2100.0
    assert door["host_wall"] is not None

    # Check window dimensions
    window = inspection.openings["windows"][0]
    assert window["width"] == 1200.0
    assert window["height"] == 1500.0
    assert window["host_wall"] is not None
