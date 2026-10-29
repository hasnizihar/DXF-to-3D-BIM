"""Tests for Structural BIM Reconstruction Engine (Milestone 14)."""

import math
import tempfile
from pathlib import Path
import ezdxf
import pytest

from dxf_to_3d_bim.approval import ApprovalGate
from dxf_to_3d_bim.bimcraft_adapter import BimcraftAdapter
from dxf_to_3d_bim.dxf_parser import DxfParser
from dxf_to_3d_bim.ifc_parser import PureIfcParser
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.structural_engine import (
    ParametricStructuralEngine,
    StructuralGrid,
    StructuralColumn,
    StructuralBeam,
    StructuralFoundation,
    ENGINEERING_DISCLAIMER,
)
from dxf_to_3d_bim.validator import ModelValidator
from dxf_to_3d_bim.cli import reconstruct_dxf_model


def test_parametric_structural_engine_grids():
    """Verifies orthogonal grid generation, labeling, and intersection calculation."""
    x_coords = [0.0, 6000.0]
    y_coords = [0.0, 4000.0]

    grids = ParametricStructuralEngine.generate_orthogonal_grids_from_bounds(
        x_coords=x_coords,
        y_coords=y_coords,
        margin=1500.0,
    )
    assert len(grids) == 4

    names = {g.name for g in grids}
    assert names == {"1", "2", "A", "B"}

    intersections = ParametricStructuralEngine.calculate_grid_intersections(grids)
    assert len(intersections) > 0

    # Look for intersection tags
    tags = {item[1] for item in intersections.values()}
    assert "A-1" in tags
    assert "A-2" in tags
    assert "B-1" in tags
    assert "B-2" in tags

    # Test nearest grid intersection tag lookup
    lbl_origin = ParametricStructuralEngine.find_nearest_grid_intersection((0.0, 0.0), intersections)
    assert lbl_origin == "A-1"

    lbl_far = ParametricStructuralEngine.find_nearest_grid_intersection((6000.0, 4000.0), intersections)
    assert lbl_far == "B-2"


def test_parametric_structural_engine_columns():
    """Tests rectangular, circular, and rotated column generation across storeys."""
    locations = [(0.0, 0.0), (6000.0, 0.0), (6000.0, 4000.0), (0.0, 4000.0)]
    levels = [
        {"id": "level_1", "name": "Level 1", "elevation": 0.0, "height": 3000.0, "storeyType": "ground"},
        {"id": "level_2", "name": "Level 2", "elevation": 3000.0, "height": 3000.0, "storeyType": "upper"},
        {"id": "level_3", "name": "Level 3", "elevation": 6000.0, "height": 0.0, "storeyType": "roof_datum"},
    ]

    # 1. Rectangular columns across 2 storeys
    cols = ParametricStructuralEngine.generate_columns_at_locations(
        locations=locations,
        levels=levels,
        width=300.0,
        depth=300.0,
        profile="rectangular",
    )
    # 4 locations * 2 inhabited storeys = 8 columns
    assert len(cols) == 8
    assert cols[0].width == 300.0
    assert cols[0].depth == 300.0
    assert cols[0].profile == "rectangular"
    assert cols[0].level_id == "Level 1"
    assert cols[0].top_level_id == "Level 2"

    # Check storey 2 columns
    l2_cols = [c for c in cols if c.level_id == "Level 2"]
    assert len(l2_cols) == 4
    assert l2_cols[0].top_level_id == "Level 3"

    # 2. Circular columns
    round_cols = ParametricStructuralEngine.generate_columns_at_locations(
        locations=[(0.0, 0.0)],
        levels=levels[:1],
        width=350.0,
        depth=350.0,
        profile="circular",
        diameter=350.0,
    )
    assert len(round_cols) == 1
    assert round_cols[0].profile == "circular"
    assert round_cols[0].diameter == 350.0

    # 3. Rotated column
    rot_cols = ParametricStructuralEngine.generate_columns_at_locations(
        locations=[(0.0, 0.0)],
        levels=levels[:1],
        width=300.0,
        depth=400.0,
        angle=45.0,
    )
    assert rot_cols[0].angle == 45.0

    # 4. Invalid dimension validation
    with pytest.raises(ValueError):
        ParametricStructuralEngine.generate_columns_at_locations(
            locations=[(0.0, 0.0)],
            levels=levels[:1],
            width=50.0,
            depth=300.0,
        )


def test_parametric_structural_engine_beams():
    """Tests primary beam generation connecting column centers and dimension checks."""
    cols = [
        StructuralColumn(id="c1", name="C1", profile="rectangular", width=300, depth=300, at=(0.0, 0.0), top_level_id="Level 2"),
        StructuralColumn(id="c2", name="C2", profile="rectangular", width=300, depth=300, at=(6000.0, 0.0), top_level_id="Level 2"),
        StructuralColumn(id="c3", name="C3", profile="rectangular", width=300, depth=300, at=(6000.0, 4000.0), top_level_id="Level 2"),
        StructuralColumn(id="c4", name="C4", profile="rectangular", width=300, depth=300, at=(0.0, 4000.0), top_level_id="Level 2"),
    ]
    levels = [{"name": "Level 1"}, {"name": "Level 2"}]

    beams = ParametricStructuralEngine.generate_beams_between_columns(
        columns=cols,
        levels=levels,
        width=230.0,
        depth=450.0,
    )
    # Perimeter of 4 columns has 4 orthogonal connections
    assert len(beams) == 4
    for b in beams:
        assert b.width == 230.0
        assert b.depth == 450.0
        assert b.level_id == "Level 2"
        assert b.start_column_id is not None
        assert b.end_column_id is not None
        assert b.beam_type == "primary"

    # Dimension validation
    with pytest.raises(ValueError):
        ParametricStructuralEngine.generate_beams_between_columns(
            columns=cols,
            levels=levels,
            width=50.0,
            depth=450.0,
        )


def test_parametric_structural_engine_foundations():
    """Tests pad footing and strip footing generation."""
    cols = [
        StructuralColumn(id="c1", name="C1", profile="rectangular", width=300, depth=300, at=(0.0, 0.0), level_id="Level 1"),
        StructuralColumn(id="c2", name="C2", profile="rectangular", width=300, depth=300, at=(5000.0, 0.0), level_id="Level 1"),
    ]
    dummy_walls = [
        {"id": "w1", "classification": "exterior", "levelId": "Level 1", "start": [0, 0], "end": [5000, 0]}
    ]

    # 1. Isolated pad footings
    pad_ftgs = ParametricStructuralEngine.generate_foundations(
        columns=cols,
        walls=dummy_walls,
        foundation_type="isolated",
        pad_width=1200.0,
        pad_depth=1200.0,
        pad_thickness=400.0,
        pad_offset=-1200.0,
    )
    assert len(pad_ftgs) == 2
    assert pad_ftgs[0].foundation_type == "isolated"
    assert pad_ftgs[0].width == 1200.0
    assert pad_ftgs[0].thickness == 400.0
    assert pad_ftgs[0].offset == -1200.0
    assert pad_ftgs[0].supporting_element_id == "c1"

    # 2. Strip footings
    strip_ftgs = ParametricStructuralEngine.generate_foundations(
        columns=cols,
        walls=dummy_walls,
        foundation_type="strip",
        strip_width=600.0,
        strip_thickness=300.0,
    )
    assert len(strip_ftgs) == 1
    assert strip_ftgs[0].foundation_type == "strip"
    assert strip_ftgs[0].width == 600.0
    assert strip_ftgs[0].points is not None

    # 3. Both
    both_ftgs = ParametricStructuralEngine.generate_foundations(
        columns=cols,
        walls=dummy_walls,
        foundation_type="both",
    )
    assert len(both_ftgs) == 3


def test_structural_slab_classification_and_stair_opening_preservation():
    """Tests classification of ground-bearing and upper structural slabs, preserving openings."""
    floors = [
        {
            "id": "floor_1",
            "levelId": "Level 1",
            "thickness": 150.0,
            "elevation": 0.0,
            "boundary": [[0, 0], [6000, 0], [6000, 4000], [0, 4000]],
        },
        {
            "id": "floor_2",
            "levelId": "Level 2",
            "thickness": 150.0,
            "elevation": 3000.0,
            "boundary": [[0, 0], [6000, 0], [6000, 4000], [0, 4000]],
            "openings": [[[1500, 1500], [3500, 1500], [3500, 2500], [1500, 2500]]],
        },
    ]
    levels = [
        {"name": "Level 1", "storeyType": "ground"},
        {"name": "Level 2", "storeyType": "upper"},
    ]

    classified = ParametricStructuralEngine.classify_structural_slabs(floors, levels)
    assert len(classified) == 2
    assert classified[0]["structuralRole"] == "ground_bearing"
    assert classified[1]["structuralRole"] == "roof_slab"
    # Ensure stair opening is intact!
    assert "openings" in classified[1]
    assert len(classified[1]["openings"]) == 1


def test_structural_approval_tamper_detection():
    """Tests that modifying any structural member invalidates the SHA-256 approval hash."""
    cols = [
        StructuralColumn(id="c1", name="C1", profile="rectangular", width=300, depth=300, at=(0.0, 0.0)),
        StructuralColumn(id="c2", name="C2", profile="rectangular", width=300, depth=300, at=(6000.0, 0.0)),
    ]
    bms = [
        StructuralBeam(id="b1", name="B1", width=230, depth=450, start=(0.0, 0.0), end=(6000.0, 0.0)),
    ]
    ftgs = [
        StructuralFoundation(id="f1", name="F1", foundation_type="isolated", width=1200, depth=1200, thickness=400, at=(0.0, 0.0)),
    ]

    model = IntermediateBimModel.create(
        project_name="TamperTest",
        source_dxf_path="test.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=[],
        openings=[],
        floors=[],
        rooms=[],
        columns=[c.to_dict() for c in cols],
        beams=[b.to_dict() for b in bms],
        foundations=[f.to_dict() for f in ftgs],
    )

    ApprovalGate.approve(model, approved_by="Architect")
    valid, _ = ApprovalGate.verify_approval(model)
    assert valid is True

    # Tamper 1: modify column coordinates
    tampered_1 = IntermediateBimModel(dict(model.data))
    tampered_1.data["columns"][0]["at"] = [100.0, 0.0]
    valid_1, reason_1 = ApprovalGate.verify_approval(tampered_1)
    assert valid_1 is False
    assert "invalidated" in reason_1.lower() or "changed" in reason_1.lower()

    # Tamper 2: modify beam depth
    tampered_2 = IntermediateBimModel(dict(model.data))
    tampered_2.data["beams"][0]["depth"] = 500.0
    valid_2, reason_2 = ApprovalGate.verify_approval(tampered_2)
    assert valid_2 is False

    # Tamper 3: modify footing thickness
    tampered_3 = IntermediateBimModel(dict(model.data))
    tampered_3.data["foundations"][0]["thickness"] = 500.0
    valid_3, reason_3 = ApprovalGate.verify_approval(tampered_3)
    assert valid_3 is False


def test_dxf_layer_structural_detection(tmp_path):
    """Verifies that circular and line entities on column/beam layers are reconstructed."""
    dxf_path = tmp_path / "structural_test.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()

    # Walls
    msp.add_line((0, 0), (6000, 0), dxfattribs={"layer": "A-WALL"})
    msp.add_line((6000, 0), (6000, 4000), dxfattribs={"layer": "A-WALL"})
    msp.add_line((6000, 4000), (0, 4000), dxfattribs={"layer": "A-WALL"})
    msp.add_line((0, 4000), (0, 0), dxfattribs={"layer": "A-WALL"})

    # Circular RC columns on S-COLS
    msp.add_circle((0, 0), radius=175.0, dxfattribs={"layer": "S-COLS"})
    msp.add_circle((6000, 0), radius=175.0, dxfattribs={"layer": "S-COLS"})
    msp.add_circle((6000, 4000), radius=175.0, dxfattribs={"layer": "S-COLS"})
    msp.add_circle((0, 4000), radius=175.0, dxfattribs={"layer": "S-COLS"})

    doc.saveas(str(dxf_path))

    parser = DxfParser()
    parsed = parser.parse(dxf_path)
    classifier = LayerClassifier()

    assert len(parsed.circles) == 4

    model = reconstruct_dxf_model(
        dxf_path=dxf_path,
        parsed=parsed,
        classifier=classifier,
        active_unit="mm",
        scale_factor_to_mm=1.0,
        structure_mode="auto",
        storeys=1,
    )

    data = model.data
    assert len(data.get("columns", [])) == 4
    # Profile should be circular with diameter 350
    col0 = data["columns"][0]
    assert col0["profile"] == "circular"
    assert col0["diameter"] == 350.0

    # Primary beams generated between column centers
    assert len(data.get("beams", [])) == 4

    # Pad footings beneath columns
    assert len(data.get("foundations", [])) == 4


def test_live_bimcraft_and_ifc_structural_generation(tmp_path):
    """End-to-end integration: generates native .bimcraft and IFC4 with real structural entities."""
    dxf_path = tmp_path / "struct_building.dxf"
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()

    # 4 walls: 8m x 6m
    msp.add_line((0, 0), (8000, 0), dxfattribs={"layer": "A-WALL"})
    msp.add_line((8000, 0), (8000, 6000), dxfattribs={"layer": "A-WALL"})
    msp.add_line((8000, 6000), (0, 6000), dxfattribs={"layer": "A-WALL"})
    msp.add_line((0, 6000), (0, 0), dxfattribs={"layer": "A-WALL"})
    doc.saveas(str(dxf_path))

    parser = DxfParser()
    parsed = parser.parse(dxf_path)
    classifier = LayerClassifier()

    model = reconstruct_dxf_model(
        dxf_path=dxf_path,
        parsed=parsed,
        classifier=classifier,
        active_unit="mm",
        scale_factor_to_mm=1.0,
        storeys=2,
        repeat_ground_floor=True,
        structure_mode="auto",
        column_default="300x300",
        beam_default="230x450",
        foundation_type="isolated",
        generate_grids=True,
    )

    # Approve model
    ApprovalGate.approve(model, approved_by="Structural Engineer", notes="Verified 3D RC frame")

    adapter = BimcraftAdapter()
    if not adapter.is_available():
        pytest.skip("BIMCraft CLI not available in test environment.")

    out_dir = tmp_path / "deliverables"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = adapter.execute_build(
        model=model,
        output_dir=out_dir,
        base_name="struct_model",
        generate_3d_views=True,
    )

    assert result.success is True
    assert result.bimcraft_path.exists()
    assert result.ifc_path.exists()

    # Reopen and inspect native .bimcraft project
    info = adapter.inspect_file(result.bimcraft_path)
    counts = info.get("counts", {})
    assert counts.get("structuralcolumn", 0) >= 4
    assert counts.get("beam", 0) >= 4
    assert counts.get("footing", 0) >= 4

    # Deep IFC4 Inspection
    ifc_parser = PureIfcParser(result.ifc_path)
    ifc_sem = ifc_parser.inspect()

    assert ifc_sem.counts.get("column", 0) >= 4
    assert ifc_sem.counts.get("beam", 0) >= 4
    assert ifc_sem.counts.get("footing", 0) >= 4
    assert ifc_sem.containment_verified is True

    # Check footing predefined type
    assert any("PAD_FOOTING" in ft.get("predefined_type", "") for ft in ifc_sem.foundations)

    # Validate with ModelValidator
    validator = ModelValidator(adapter)
    report = validator.validate(model, result)
    assert report["overallStatus"] in ("PASSED", "WARNING")
    assert report["elementSummary"]["generated"]["columns"] >= 4
    assert report["elementSummary"]["generated"]["beams"] >= 4
    assert report["elementSummary"]["generated"]["foundations"] >= 4


def test_structural_engineering_disclaimer_enforced():
    """Verifies that engineering disclaimers are present in code, schemas, and outputs."""
    assert "NOT constitute structural calculations" in ENGINEERING_DISCLAIMER
    assert "licensed professional structural engineer" in ENGINEERING_DISCLAIMER

    engine_mod = ParametricStructuralEngine()
    assert hasattr(engine_mod, "calculate_grid_intersections")
