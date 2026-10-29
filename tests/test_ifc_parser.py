"""Comprehensive tests for pure-Python ISO-10303-21 STEP/IFC parser."""

import pytest
from pathlib import Path
from dxf_to_3d_bim.ifc_parser import PureIfcParser, tokenize_step_args, split_step_statements

def test_step_tokenizer_escaped_strings_and_aggregates():
    # String containing commas, semicolons, and escaped apostrophe
    raw = "'Living Room, Zone 1; Owner''s Suite', 3000., $, (#10, #20), .ELEMENT."
    tokens = tokenize_step_args(raw)

    assert len(tokens) == 5
    assert tokens[0] == "Living Room, Zone 1; Owner's Suite"
    assert tokens[1] == 3000.0
    assert tokens[2] is None  # $ is None
    assert tokens[3] == (10, 20)  # Nested tuple
    assert tokens[4] == ".ELEMENT."

def test_split_step_statements_multiline():
    step_data = """
    #1=IFCCARTESIANPOINT((0.,0.,0.));
    #2=IFCDOOR('guid',$,'Single Door; 900x2100',
        $,$,#10,#20,'Mark 1',2100.,900.,.DOOR.,$,$);
    #3=IFCBUILDINGSTOREY('guid2',$,'Owner''s Floor',$,$,#30,$,$,.ELEMENT.,0.);
    """
    stmts = split_step_statements(step_data)
    assert len(stmts) == 3
    assert stmts[0].startswith("#1=IFCCARTESIANPOINT")
    assert "Single Door; 900x2100" in stmts[1]
    assert "Owner''s Floor" in stmts[2]

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
    assert inspection.counts["storey"] == 2

    # Verify physical voiding of host walls
    assert inspection.voids_verified is True
    assert inspection.fills_verified is True
    assert inspection.containment_verified is True

    # Check door dimensions
    door = inspection.openings["doors"][0]
    assert door["width"] == 900.0
    assert door["height"] == 2100.0
    assert door["host_wall_id"] is not None

    # Check window dimensions
    window = inspection.openings["windows"][0]
    assert window["width"] == 1200.0
    assert window["height"] == 1500.0
    assert window["host_wall_id"] is not None

def test_ifc_parser_handles_synthetic_malformed_input(tmp_path):
    bad_ifc = tmp_path / "bad.ifc"
    bad_ifc.write_text("""
    ISO-10303-21;
    HEADER;
    FILE_SCHEMA(('IFC4'));
    ENDSEC;
    DATA;
    #10=IFCWALL('w1_guid',$,'Test Wall',$,$,$,$,'Mark',.STANDARD.);
    #20=NOT_VALID_SYNTAX_WITHOUT_EQUALS;
    #10=IFCWALL('dup_guid',$,'Duplicate ID',$,$,$,$,$,.STANDARD.);
    ENDSEC;
    END-ISO-10303-21;
    """)

    parser = PureIfcParser(bad_ifc)
    inspection = parser.inspect()
    assert len(parser.warnings) >= 1
    assert inspection.counts["wall"] == 1  # Deduplicated
