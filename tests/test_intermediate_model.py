"""Tests for intermediate model creation, validation, and Sketch-to-CAD import."""

import json
import pytest
from pathlib import Path
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel
from dxf_to_3d_bim.wall_reconstruction import ReconstructedWall
from dxf_to_3d_bim.opening_detection import ReconstructedOpening
from dxf_to_3d_bim.room_detection import FloorSlab, RoomZone

def test_intermediate_model_validates():
    walls = [
        ReconstructedWall(id="wall_1", classification="exterior", start=(0, 0), end=(5000, 0), thickness=200),
        ReconstructedWall(id="wall_2", classification="exterior", start=(5000, 0), end=(5000, 3000), thickness=200),
    ]
    openings = [
        ReconstructedOpening(id="door_1", type="door", wall_id="wall_1", center=(2500, 0), width=900, height=2100)
    ]
    floors = [
        FloorSlab(id="floor_1", level_id="Level 1", thickness=150, elevation=0, boundary=[(0, 0), (5000, 0), (5000, 3000), (0, 3000)])
    ]
    rooms = [
        RoomZone(id="room_1", name="Entry", level_id="Level 1", approximate_area=15.0, label_position=(2500, 1500))
    ]

    model = IntermediateBimModel.create(
        project_name="TestProject",
        source_dxf_path="test.dxf",
        source_units="mm",
        scale_factor=1.0,
        walls=walls,
        openings=openings,
        floors=floors,
        rooms=rooms,
    )

    # Must validate schema without exception
    model.validate_schema()
    assert model.data["status"] == "awaiting_approval"
    assert model.data["approval"]["isApproved"] is False

def test_sketch_to_cad_json_import(tmp_path):
    upstream_data = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "metadata": {"projectName": "ImportedHouse", "version": "1.0", "createdAt": "2026-10-30"},
        "status": "approved",
        "units": "m",
        "envelope": {"width": 6.0, "depth": 4.0, "origin": [0.0, 0.0], "widthSource": "explicit", "depthSource": "explicit"},
        "walls": [
            {"id": "w1", "type": "exterior", "start": [0, 0], "end": [6, 0], "thickness": 0.2, "layer": "A-WALL-EXTR", "source": "explicit"}
        ],
        "openings": [
            {"id": "d1", "type": "door", "wallId": "w1", "center": [3, 0], "width": 0.9, "source": "explicit"}
        ],
        "rooms": [
            {"id": "r1", "name": "Studio", "approximateArea": 24.0, "labelPosition": [3, 2]}
        ],
        "dimensions": [],
        "uncertainties": []
    }

    json_file = tmp_path / "floor-plan-model.json"
    with open(json_file, "w") as f:
        json.dump(upstream_data, f)

    model = IntermediateBimModel.from_sketch_to_cad_json(json_file)
    model.validate_schema()

    # Units scaled from m to mm
    assert model.data["units"]["scaleFactor"] == 1000.0
    assert model.data["walls"][0]["end"] == [6000.0, 0.0]
    assert model.data["walls"][0]["thickness"] == 200.0
    assert model.data["openings"][0]["center"] == [3000.0, 0.0]
    assert model.data["openings"][0]["width"] == 900.0
