"""DXF Parser module for extracting 2D architectural entities and metadata."""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import ezdxf
from ezdxf.document import Drawing
from ezdxf.math import Vec3

from dxf_to_3d_bim.units import UnitConverter


@dataclass
class Point2D:
    x: float
    y: float

    def as_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


@dataclass
class LineSegment:
    id: str
    layer: str
    start: Tuple[float, float]
    end: Tuple[float, float]
    length: float
    source_type: str = "LINE"


@dataclass
class ArcEntity:
    id: str
    layer: str
    center: Tuple[float, float]
    radius: float
    start_angle_deg: float
    end_angle_deg: float
    source_type: str = "ARC"


@dataclass
class TextEntity:
    id: str
    layer: str
    text: str
    position: Tuple[float, float]
    source_type: str = "TEXT"


@dataclass
class DxfInspectionReport:
    file_path: str
    dxf_version: str
    insunits_code: int
    detected_units: str
    scale_factor_to_mm: float
    bounding_box: Dict[str, float]
    layers: List[str]
    layer_entity_counts: Dict[str, Dict[str, int]]
    total_entities: int
    warnings: List[str] = field(default_factory=list)


@dataclass
class ParsedDxfData:
    report: DxfInspectionReport
    lines: List[LineSegment] = field(default_factory=list)
    arcs: List[ArcEntity] = field(default_factory=list)
    texts: List[TextEntity] = field(default_factory=list)


class DxfParser:
    """Parses DXF files into normalized millimeter coordinates and structured entities."""

    def __init__(self, fallback_units: str = "mm"):
        self.fallback_units = fallback_units

    def inspect_file(self, dxf_path: str | Path) -> DxfInspectionReport:
        dxf_path = Path(dxf_path)
        if not dxf_path.exists():
            raise FileNotFoundError(f"DXF file not found: {dxf_path}")

        doc = ezdxf.readfile(str(dxf_path))
        header = doc.header
        insunits = header.get("$INSUNITS", 0)
        converter = UnitConverter.from_insunits(insunits, fallback=self.fallback_units)

        msp = doc.modelspace()
        layers = [layer.dxf.name for layer in doc.layers]
        layer_counts: Dict[str, Dict[str, int]] = {}
        total = 0

        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        for entity in msp:
            if entity.dxf.paperspace:
                continue
            etype = entity.dxftype()
            layer = entity.dxf.layer
            total += 1

            if layer not in layer_counts:
                layer_counts[layer] = {}
            layer_counts[layer][etype] = layer_counts[layer].get(etype, 0) + 1

            # Rough bbox collection
            if etype == "LINE":
                for pt in [entity.dxf.start, entity.dxf.end]:
                    x_mm = converter.to_mm(pt.x)
                    y_mm = converter.to_mm(pt.y)
                    min_x, min_y = min(min_x, x_mm), min(min_y, y_mm)
                    max_x, max_y = max(max_x, x_mm), max(max_y, y_mm)
            elif etype in ("LWPOLYLINE", "POLYLINE"):
                for pt in entity.get_points("xy"):
                    x_mm = converter.to_mm(pt[0])
                    y_mm = converter.to_mm(pt[1])
                    min_x, min_y = min(min_x, x_mm), min(min_y, y_mm)
                    max_x, max_y = max(max_x, x_mm), max(max_y, y_mm)

        if min_x == float("inf"):
            min_x, min_y, max_x, max_y = 0.0, 0.0, 0.0, 0.0

        warnings = []
        if insunits == 0:
            warnings.append(f"$INSUNITS is 0 (unspecified). Fallback to '{self.fallback_units}' was used.")

        return DxfInspectionReport(
            file_path=str(dxf_path),
            dxf_version=doc.dxfversion,
            insunits_code=insunits,
            detected_units=converter.source_units,
            scale_factor_to_mm=converter.scale_factor,
            bounding_box={
                "min_x": round(min_x, 2),
                "min_y": round(min_y, 2),
                "max_x": round(max_x, 2),
                "max_y": round(max_y, 2),
                "width": round(max_x - min_x, 2),
                "depth": round(max_y - min_y, 2),
            },
            layers=layers,
            layer_entity_counts=layer_counts,
            total_entities=total,
            warnings=warnings,
        )

    def parse(self, dxf_path: str | Path, unit_override: Optional[str] = None) -> ParsedDxfData:
        report = self.inspect_file(dxf_path)
        unit = unit_override or report.detected_units
        converter = UnitConverter(unit)

        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        lines: List[LineSegment] = []
        arcs: List[ArcEntity] = []
        texts: List[TextEntity] = []

        counter = 0

        for entity in msp:
            if entity.dxf.paperspace:
                continue
            etype = entity.dxftype()
            layer = entity.dxf.layer
            handle = entity.dxf.handle or f"ent_{counter}"
            counter += 1

            if etype == "LINE":
                p1 = converter.point_to_mm((entity.dxf.start.x, entity.dxf.start.y))
                p2 = converter.point_to_mm((entity.dxf.end.x, entity.dxf.end.y))
                length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                lines.append(LineSegment(id=handle, layer=layer, start=p1, end=p2, length=round(length, 2)))

            elif etype in ("LWPOLYLINE", "POLYLINE"):
                pts = [converter.point_to_mm((p[0], p[1])) for p in entity.get_points("xy")]
                is_closed = entity.is_closed
                for i in range(len(pts) - 1):
                    p1, p2 = pts[i], pts[i + 1]
                    seg_len = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                    if seg_len > 0.1:
                        lines.append(
                            LineSegment(
                                id=f"{handle}_seg_{i}",
                                layer=layer,
                                start=p1,
                                end=p2,
                                length=round(seg_len, 2),
                                source_type=etype,
                            )
                        )
                if is_closed and len(pts) > 2:
                    p1, p2 = pts[-1], pts[0]
                    seg_len = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                    if seg_len > 0.1:
                        lines.append(
                            LineSegment(
                                id=f"{handle}_seg_close",
                                layer=layer,
                                start=p1,
                                end=p2,
                                length=round(seg_len, 2),
                                source_type=etype,
                            )
                        )

            elif etype == "ARC":
                c = converter.point_to_mm((entity.dxf.center.x, entity.dxf.center.y))
                r = converter.to_mm(entity.dxf.radius)
                arcs.append(
                    ArcEntity(
                        id=handle,
                        layer=layer,
                        center=c,
                        radius=round(r, 2),
                        start_angle_deg=round(entity.dxf.start_angle, 2),
                        end_angle_deg=round(entity.dxf.end_angle, 2),
                    )
                )

            elif etype in ("TEXT", "MTEXT"):
                txt = entity.dxf.text if etype == "TEXT" else entity.text
                pos = converter.point_to_mm((entity.dxf.insert.x, entity.dxf.insert.y))
                texts.append(TextEntity(id=handle, layer=layer, text=txt.strip(), position=pos, source_type=etype))

            elif etype == "INSERT":
                # Expand block references
                block = doc.blocks.get(entity.dxf.name)
                if block:
                    ins_pt = converter.point_to_mm((entity.dxf.insert.x, entity.dxf.insert.y))
                    for b_ent in block:
                        if b_ent.dxftype() == "LINE":
                            p1 = (
                                ins_pt[0] + converter.to_mm(b_ent.dxf.start.x),
                                ins_pt[1] + converter.to_mm(b_ent.dxf.start.y),
                            )
                            p2 = (
                                ins_pt[0] + converter.to_mm(b_ent.dxf.end.x),
                                ins_pt[1] + converter.to_mm(b_ent.dxf.end.y),
                            )
                            length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                            lines.append(
                                LineSegment(
                                    id=f"{handle}_{b_ent.dxf.handle}",
                                    layer=layer,
                                    start=p1,
                                    end=p2,
                                    length=round(length, 2),
                                    source_type="INSERT/LINE",
                                )
                            )

        return ParsedDxfData(report=report, lines=lines, arcs=arcs, texts=texts)

