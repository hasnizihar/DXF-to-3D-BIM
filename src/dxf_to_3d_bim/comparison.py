"""Source-DXF versus Reconstructed-BIM geometric comparison and visual overlay generation."""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from dxf_to_3d_bim.dxf_parser import DxfParser, ParsedDxfData
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel


@dataclass
class DeviationMetric:
    metric_name: str
    source_value: float
    reconstructed_value: float
    deviation_abs: float
    deviation_pct: float
    tolerance: float
    status: str  # "PASSED" or "FAILED"


@dataclass
class ComparisonReport:
    dxf_path: str
    project_name: str
    footprint_deviation: Dict[str, DeviationMetric]
    wall_counts: Dict[str, Any]
    opening_counts: Dict[str, Any]
    slab_deviation: Optional[DeviationMetric]
    overall_status: str
    overlay_image_path: Optional[str] = None
    findings: List[str] = field(default_factory=list)


class SourceToBimComparator:
    """Compares original 2D DXF linework against reconstructed BIM model geometry."""

    def __init__(
        self,
        length_tolerance_mm: float = 50.0,
        area_tolerance_pct: float = 2.0,
    ):
        self.length_tolerance_mm = length_tolerance_mm
        self.area_tolerance_pct = area_tolerance_pct

    def compare(
        self,
        dxf_path: str | Path,
        model: IntermediateBimModel,
        output_image_path: Optional[str | Path] = None,
    ) -> ComparisonReport:
        dxf_path = Path(dxf_path)
        parser = DxfParser()
        parsed = parser.parse(dxf_path)

        dxf_bbox = parsed.report.bounding_box
        dxf_w = dxf_bbox["width"]
        dxf_d = dxf_bbox["depth"]
        dxf_area = round((dxf_w * dxf_d) / 1_000_000.0, 2)

        # BIM extents
        walls = model.data.get("walls", [])
        all_x = [w["start"][0] for w in walls] + [w["end"][0] for w in walls]
        all_y = [w["start"][1] for w in walls] + [w["end"][1] for w in walls]

        bim_w = round(max(all_x) - min(all_x), 2) if all_x else 0.0
        bim_d = round(max(all_y) - min(all_y), 2) if all_y else 0.0
        bim_area = round((bim_w * bim_d) / 1_000_000.0, 2)

        # Deviations
        dev_w = abs(bim_w - dxf_w)
        pct_w = round((dev_w / dxf_w * 100.0), 2) if dxf_w else 0.0
        w_status = "PASSED" if dev_w <= self.length_tolerance_mm else "FAILED"

        dev_d = abs(bim_d - dxf_d)
        pct_d = round((dev_d / dxf_d * 100.0), 2) if dxf_d else 0.0
        d_status = "PASSED" if dev_d <= self.length_tolerance_mm else "FAILED"

        dev_area = abs(bim_area - dxf_area)
        pct_area = round((dev_area / dxf_area * 100.0), 2) if dxf_area else 0.0
        area_status = "PASSED" if pct_area <= self.area_tolerance_pct else "FAILED"

        footprint_metrics = {
            "width": DeviationMetric("Width", dxf_w, bim_w, dev_w, pct_w, self.length_tolerance_mm, w_status),
            "depth": DeviationMetric("Depth", dxf_d, bim_d, dev_d, pct_d, self.length_tolerance_mm, d_status),
            "area": DeviationMetric("Area (m2)", dxf_area, bim_area, dev_area, pct_area, self.area_tolerance_pct, area_status),
        }

        # Counts
        dxf_wall_lines = [l for l in parsed.lines if "WALL" in l.layer.upper()]
        bim_walls_count = len(walls)
        wall_counts = {
            "dxf_raw_wall_lines": len(dxf_wall_lines),
            "bim_reconstructed_walls": bim_walls_count,
        }

        dxf_door_lines = [l for l in parsed.lines if "DOOR" in l.layer.upper()] + [a for a in parsed.arcs if "DOOR" in a.layer.upper()]
        dxf_window_lines = [l for l in parsed.lines if "GLAZ" in l.layer.upper() or "WIND" in l.layer.upper()]
        bim_doors = len([op for op in model.data.get("openings", []) if op.get("type") == "door"])
        bim_windows = len([op for op in model.data.get("openings", []) if op.get("type") == "window"])

        opening_counts = {
            "doors": {"dxf_features": len(dxf_door_lines), "bim_hosted": bim_doors},
            "windows": {"dxf_features": len(dxf_window_lines), "bim_hosted": bim_windows},
        }

        overall_status = "PASSED"
        if any(m.status == "FAILED" for m in footprint_metrics.values()):
            overall_status = "FAILED"

        findings = []
        if dev_w > 0:
            findings.append(f"Footprint width deviation: {dev_w:.1f} mm ({pct_w}%).")
        if dev_d > 0:
            findings.append(f"Footprint depth deviation: {dev_d:.1f} mm ({pct_d}%).")
        if not findings:
            findings.append("Exact 1:1 footprint alignment with zero measurable deviation.")

        # Visual overlay generation
        overlay_path = None
        if output_image_path:
            overlay_path = self.generate_overlay(parsed, model, output_image_path)

        return ComparisonReport(
            dxf_path=str(dxf_path),
            project_name=model.data.get("metadata", {}).get("projectName", "BimProject"),
            footprint_deviation=footprint_metrics,
            wall_counts=wall_counts,
            opening_counts=opening_counts,
            slab_deviation=None,
            overall_status=overall_status,
            overlay_image_path=str(overlay_path) if overlay_path else None,
            findings=findings,
        )

    def generate_overlay(
        self,
        parsed_dxf: ParsedDxfData,
        model: IntermediateBimModel,
        output_path: str | Path,
        img_size: Tuple[int, int] = (1600, 1200),
    ) -> Path:
        """Draws source DXF lines in light gray and reconstructed BIM elements in bold colors."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        w_img, h_img = img_size
        margin = 100

        # Compute bounding extents of both DXF and BIM
        walls = model.data.get("walls", [])
        pts = []
        for l in parsed_dxf.lines:
            pts.extend([l.start, l.end])
        for w in walls:
            pts.extend([w["start"], w["end"]])

        if not pts:
            pts = [(0, 0), (1000, 1000)]

        min_x = min(p[0] for p in pts)
        max_x = max(p[0] for p in pts)
        min_y = min(p[1] for p in pts)
        max_y = max(p[1] for p in pts)

        span_x = max(max_x - min_x, 100.0)
        span_y = max(max_y - min_y, 100.0)

        scale_x = (w_img - 2 * margin) / span_x
        scale_y = (h_img - 2 * margin) / span_y
        scale = min(scale_x, scale_y)

        def to_img(pt: Tuple[float, float]) -> Tuple[int, int]:
            # Invert Y so positive Y is upwards
            ix = int(margin + (pt[0] - min_x) * scale)
            iy = int(h_img - margin - (pt[1] - min_y) * scale)
            return (ix, iy)

        img = Image.new("RGB", (w_img, h_img), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # 1. Draw Source DXF Lines (gray)
        for line in parsed_dxf.lines:
            p1 = to_img(line.start)
            p2 = to_img(line.end)
            color = (180, 180, 190)
            if "WALL" in line.layer.upper():
                color = (140, 140, 150)
            draw.line([p1, p2], fill=color, width=2)

        # 2. Draw Reconstructed BIM Walls (solid blue)
        for w in walls:
            p1 = to_img((w["start"][0], w["start"][1]))
            p2 = to_img((w["end"][0], w["end"][1]))
            color = (20, 60, 180) if w.get("classification") == "exterior" else (70, 130, 220)
            draw.line([p1, p2], fill=color, width=4)

        # 3. Draw Doors (green dots / bars) and Windows (orange bars)
        for op in model.data.get("openings", []):
            cp = to_img((op["center"][0], op["center"][1]))
            r = 7
            if op.get("type") == "door":
                draw.ellipse([cp[0] - r, cp[1] - r, cp[0] + r, cp[1] + r], fill=(30, 160, 40), outline=(10, 100, 20))
            else:
                draw.rectangle([cp[0] - r, cp[1] - r, cp[0] + r, cp[1] + r], fill=(240, 140, 20), outline=(180, 80, 10))

        # Legend
        draw.rectangle([30, 30, 450, 170], fill=(245, 245, 248), outline=(200, 200, 210))
        draw.text((45, 40), "Source DXF vs Reconstructed BIM Overlay", fill=(20, 20, 30))
        draw.line([(45, 75), (95, 75)], fill=(140, 140, 150), width=2)
        draw.text((105, 68), "Source DXF Linework", fill=(80, 80, 90))

        draw.line([(45, 105), (95, 105)], fill=(20, 60, 180), width=4)
        draw.text((105, 98), "Reconstructed BIM Walls", fill=(20, 60, 180))

        draw.ellipse([(60, 130), (74, 144)], fill=(30, 160, 40))
        draw.text((85, 127), "Doors", fill=(30, 160, 40))

        draw.rectangle([(160, 130), (174, 144)], fill=(240, 140, 20))
        draw.text((185, 127), "Windows", fill=(240, 140, 20))

        img.save(str(output_path), format="PNG")
        return output_path
