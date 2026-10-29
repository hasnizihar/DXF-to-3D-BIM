"""Utility to generate synthetic architectural DXF test fixtures."""

from pathlib import Path
import ezdxf

def create_synthetic_room_dxf(output_path: str | Path) -> Path:
    """Creates a synthetic single-storey room DXF with 4 exterior walls, 1 door, 1 window, 1 slab, 1 text."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # Millimeters

    # Setup standard layers
    doc.layers.add("A-WALL-EXTR", color=1)
    doc.layers.add("A-DOOR", color=2)
    doc.layers.add("A-GLAZ", color=3)
    doc.layers.add("A-FLOR", color=4)
    doc.layers.add("A-ANNO-TEXT", color=7)

    msp = doc.modelspace()

    # Outer wall face: 6000 x 4000 mm
    outer_pts = [(0, 0), (6000, 0), (6000, 4000), (0, 4000)]
    for i in range(len(outer_pts)):
        p1 = outer_pts[i]
        p2 = outer_pts[(i + 1) % len(outer_pts)]
        msp.add_line(p1, p2, dxfattribs={"layer": "A-WALL-EXTR"})

    # Inner wall face: 200 mm thickness -> 5600 x 3600 mm inside
    inner_pts = [(200, 200), (5800, 200), (5800, 3800), (200, 3800)]
    for i in range(len(inner_pts)):
        p1 = inner_pts[i]
        p2 = inner_pts[(i + 1) % len(inner_pts)]
        msp.add_line(p1, p2, dxfattribs={"layer": "A-WALL-EXTR"})

    # Door opening lines / leaf on A-DOOR at bottom wall: center at x=3000, width=900 mm
    msp.add_line((2550, 100), (3450, 100), dxfattribs={"layer": "A-DOOR"})
    msp.add_arc((2550, 100), radius=900, start_angle=0, end_angle=90, dxfattribs={"layer": "A-DOOR"})

    # Window opening on right wall: center at y=2000, width=1200 mm (from 1400 to 2600)
    msp.add_line((5900, 1400), (5900, 2600), dxfattribs={"layer": "A-GLAZ"})

    # Floor slab boundary on A-FLOR
    msp.add_lwpolyline([(0, 0), (6000, 0), (6000, 4000), (0, 4000)], close=True, dxfattribs={"layer": "A-FLOR"})

    # Room text label
    msp.add_text("Living Room", dxfattribs={"layer": "A-ANNO-TEXT", "insert": (3000, 2000), "height": 200})

    doc.saveas(str(output_path))
    return output_path

if __name__ == "__main__":
    out = Path(__file__).parent / "fixtures" / "simple_room.dxf"
    create_synthetic_room_dxf(out)
    print(f"Created synthetic fixture at: {out}")

