"""Universal DXF Preflight Analyzer module for validating and analyzing arbitrary CAD drawings."""

import json
import math
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import ezdxf
from ezdxf.document import Drawing

from dxf_to_3d_bim.layer_classifier import LayerClassifier
from dxf_to_3d_bim.units import INSUNITS_MAP, UNIT_FACTORS_TO_MM, UnitConverter


class PreflightStatus(str, Enum):
    PASSED = "PASSED"
    WARNING = "WARNING"
    FAILED = "FAILED"


class ScaleConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass
class PreflightReport:
    file_path: str
    file_name: str
    file_size_bytes: int
    overall_status: PreflightStatus
    dxf_version: str
    insunits_code: int
    detected_units: str
    unit_ambiguity: bool
    suggested_unit: Optional[str]
    scale_confidence: ScaleConfidence
    scale_factor_to_mm: float
    raw_extents: Dict[str, float]
    extents_mm: Dict[str, float]
    total_modelspace_entities: int
    total_paperspace_entities: int
    entity_counts_by_type: Dict[str, int]
    layer_classifications: Dict[str, str]
    unclassified_layers: List[str]
    candidate_counts: Dict[str, int]  # walls, doors, windows, slabs, annotations, closed_polylines
    external_references: List[Dict[str, str]]
    degenerate_geometry_counts: Dict[str, int]  # zero_length, duplicates
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    recommended_next_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["overall_status"] = self.overall_status.value
        data["scale_confidence"] = self.scale_confidence.value
        return data

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        status_badge = {
            PreflightStatus.PASSED: "🟢 **PASSED**",
            PreflightStatus.WARNING: "🟡 **WARNING (Action Required)**",
            PreflightStatus.FAILED: "🔴 **FAILED (Blocked)**",
        }.get(self.overall_status, str(self.overall_status))

        lines = [
            f"# Universal DXF Preflight Report: {self.file_name}",
            f"**File Path:** `{self.file_path}`  ",
            f"**File Size:** {self.file_size_bytes} bytes  ",
            f"**Overall Status:** {status_badge}  ",
            f"**DXF Version:** `{self.dxf_version}`  ",
            "",
            "---",
            "## 1. Units & Scale Evaluation",
            f"* **INSUNITS Header Code:** `{self.insunits_code}` (`{INSUNITS_MAP.get(self.insunits_code, 'unspecified')}`)",
            f"* **Detected / Applied Unit:** `{self.detected_units}` (Scale to mm: `{self.scale_factor_to_mm}x`)",
            f"* **Unit Ambiguity:** `{'YES - Confirmation Required' if self.unit_ambiguity else 'NO - Confirmed'}`",
            f"* **Scale Confidence:** `{self.scale_confidence.value}`",
        ]

        if self.suggested_unit:
            lines.append(f"* **Heuristic Suggested Unit:** `{self.suggested_unit}`")

        raw_w = self.raw_extents.get("width", 0.0)
        raw_d = self.raw_extents.get("depth", 0.0)
        mm_w = self.extents_mm.get("width", 0.0)
        mm_d = self.extents_mm.get("depth", 0.0)

        lines.extend([
            f"* **Raw CAD Extents:** {raw_w:.2f} x {raw_d:.2f} (raw drawing units)",
            f"* **Projected Footprint (mm):** {mm_w:.1f} x {mm_d:.1f} mm ({round((mm_w * mm_d) / 1_000_000.0, 2)} m²)",
            "",
            "---",
            "## 2. Drawing Entity & Space Breakdown",
            f"* **Modelspace Entities:** {self.total_modelspace_entities}",
            f"* **Paperspace Entities (Ignored):** {self.total_paperspace_entities}",
            "",
            "| Entity Type | Count | Status |",
            "| :--- | :--- | :--- |",
        ])

        supported_types = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "TEXT", "MTEXT", "INSERT"}
        for etype, count in sorted(self.entity_counts_by_type.items()):
            supp = "Supported" if etype in supported_types else "Ignored / Unsupported"
            lines.append(f"| `{etype}` | {count} | {supp} |")

        lines.extend([
            "",
            "---",
            "## 3. Semantic Layer Analysis",
            "| Layer Name | Classified Semantic Role |",
            "| :--- | :--- |",
        ])
        for layer, cat in sorted(self.layer_classifications.items()):
            badge = f"`{cat}`" if cat != "unknown" else "⚠️ `unknown`"
            lines.append(f"| `{layer}` | {badge} |")

        if self.unclassified_layers:
            lines.extend([
                "",
                f"> [!WARNING] Unclassified Layers Detected",
                f"> The following layers could not be matched to standard AIA or alias patterns: `{', '.join(self.unclassified_layers)}`. Geometry on these layers will be ignored unless mapped.",
            ])

        lines.extend([
            "",
            "---",
            "## 4. Candidate Architectural Features",
            f"* **Candidate Wall Linework:** {self.candidate_counts.get('walls', 0)} segments",
            f"* **Candidate Hosted Openings:** {self.candidate_counts.get('doors', 0)} doors, {self.candidate_counts.get('windows', 0)} windows",
            f"* **Candidate Slab / Boundary Elements:** {self.candidate_counts.get('slabs', 0)} lines, {self.candidate_counts.get('closed_polylines', 0)} closed polylines",
            f"* **Candidate Text Annotations:** {self.candidate_counts.get('annotations', 0)} text labels",
            "",
            "---",
            "## 5. Geometry Integrity & Quality Checks",
            f"* **Zero-length Segments (< 0.1):** {self.degenerate_geometry_counts.get('zero_length', 0)}",
            f"* **Duplicate / Overlapping Lines:** {self.degenerate_geometry_counts.get('duplicates', 0)}",
            f"* **External References (XREFs):** {len(self.external_references)}",
        ])

        if self.external_references:
            for xref in self.external_references:
                lines.append(f"  - ⚠️ XREF: `{xref.get('name')}` -> `{xref.get('path')}`")

        if self.errors:
            lines.extend(["", "---", "## 6. Critical Errors (Generation Blocked)"])
            for err in self.errors:
                lines.append(f"- 🔴 {err}")

        if self.warnings:
            lines.extend(["", "---", "## 7. Warnings & Items for User Review"])
            for w in self.warnings:
                lines.append(f"- ⚠️ {w}")

        if self.recommended_next_steps:
            lines.extend(["", "---", "## 8. Recommended Next Steps"])
            for step in self.recommended_next_steps:
                lines.append(f"1. {step}")

        return "\n".join(lines)


class PreflightAnalyzer:
    """Rigorous preflight analyzer inspecting arbitrary DXF drawings before BIM generation."""

    def __init__(self, classifier: Optional[LayerClassifier] = None):
        self.classifier = classifier or LayerClassifier()

    def analyze(self, file_path: str | Path, unit_override: Optional[str] = None) -> PreflightReport:
        path = Path(file_path)
        file_name = path.name

        # 1. Inaccessible / Missing File
        if not path.exists():
            return PreflightReport(
                file_path=str(path),
                file_name=file_name,
                file_size_bytes=0,
                overall_status=PreflightStatus.FAILED,
                dxf_version="UNKNOWN",
                insunits_code=0,
                detected_units="unspecified",
                unit_ambiguity=True,
                suggested_unit=None,
                scale_confidence=ScaleConfidence.LOW,
                scale_factor_to_mm=1.0,
                raw_extents={"width": 0.0, "depth": 0.0},
                extents_mm={"width": 0.0, "depth": 0.0},
                total_modelspace_entities=0,
                total_paperspace_entities=0,
                entity_counts_by_type={},
                layer_classifications={},
                unclassified_layers=[],
                candidate_counts={},
                external_references=[],
                degenerate_geometry_counts={},
                warnings=[],
                errors=[f"DXF file does not exist or is inaccessible: {path}"],
                recommended_next_steps=["Verify the file path and ensure read permissions."],
            )

        file_size = path.stat().st_size
        if file_size == 0:
            return PreflightReport(
                file_path=str(path),
                file_name=file_name,
                file_size_bytes=0,
                overall_status=PreflightStatus.FAILED,
                dxf_version="UNKNOWN",
                insunits_code=0,
                detected_units="unspecified",
                unit_ambiguity=True,
                suggested_unit=None,
                scale_confidence=ScaleConfidence.LOW,
                scale_factor_to_mm=1.0,
                raw_extents={"width": 0.0, "depth": 0.0},
                extents_mm={"width": 0.0, "depth": 0.0},
                total_modelspace_entities=0,
                total_paperspace_entities=0,
                entity_counts_by_type={},
                layer_classifications={},
                unclassified_layers=[],
                candidate_counts={},
                external_references=[],
                degenerate_geometry_counts={},
                warnings=[],
                errors=["The DXF file is empty (0 bytes)."],
                recommended_next_steps=["Export the CAD drawing properly before converting to BIM."],
            )

        # 2. Corrupt or unreadable DXF
        try:
            doc = ezdxf.readfile(str(path))
        except Exception as e:
            return PreflightReport(
                file_path=str(path),
                file_name=file_name,
                file_size_bytes=file_size,
                overall_status=PreflightStatus.FAILED,
                dxf_version="UNKNOWN",
                insunits_code=0,
                detected_units="unspecified",
                unit_ambiguity=True,
                suggested_unit=None,
                scale_confidence=ScaleConfidence.LOW,
                scale_factor_to_mm=1.0,
                raw_extents={"width": 0.0, "depth": 0.0},
                extents_mm={"width": 0.0, "depth": 0.0},
                total_modelspace_entities=0,
                total_paperspace_entities=0,
                entity_counts_by_type={},
                layer_classifications={},
                unclassified_layers=[],
                candidate_counts={},
                external_references=[],
                degenerate_geometry_counts={},
                warnings=[],
                errors=[f"Corrupt or invalid DXF file: {str(e)}"],
                recommended_next_steps=["Open and re-save the file in AutoCAD, LibreCAD, or DXF recovery utility."],
            )

        warnings: List[str] = []
        errors: List[str] = []
        next_steps: List[str] = []

        dxf_version = doc.dxfversion
        header = doc.header
        insunits = header.get("$INSUNITS", 0)

        # 3. Modelspace vs Paperspace
        msp = doc.modelspace()
        total_msp = 0
        total_psp = 0
        entity_types: Dict[str, int] = {}
        layer_names = [layer.dxf.name for layer in doc.layers]

        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        degenerate_zero = 0
        line_signatures = set()
        duplicate_lines = 0
        closed_polylines = 0

        for entity in msp:
            if entity.dxf.paperspace:
                total_psp += 1
                continue

            total_msp += 1
            etype = entity.dxftype()
            entity_types[etype] = entity_types.get(etype, 0) + 1

            if etype == "LINE":
                s = (entity.dxf.start.x, entity.dxf.start.y)
                e = (entity.dxf.end.x, entity.dxf.end.y)
                length = math.hypot(e[0] - s[0], e[1] - s[1])
                if length < 0.1:
                    degenerate_zero += 1
                else:
                    sig = (round(min(s[0], e[0]), 3), round(min(s[1], e[1]), 3),
                           round(max(s[0], e[0]), 3), round(max(s[1], e[1]), 3))
                    if sig in line_signatures:
                        duplicate_lines += 1
                    else:
                        line_signatures.add(sig)

                min_x, min_y = min(min_x, s[0], e[0]), min(min_y, s[1], e[1])
                max_x, max_y = max(max_x, s[0], e[0]), max(max_y, s[1], e[1])

            elif etype in ("LWPOLYLINE", "POLYLINE"):
                pts = list(entity.get_points("xy"))
                if getattr(entity, "is_closed", False):
                    closed_polylines += 1
                for pt in pts:
                    min_x, min_y = min(min_x, pt[0]), min(min_y, pt[1])
                    max_x, max_y = max(max_x, pt[0]), max(max_y, pt[1])

            elif etype == "ARC":
                c = entity.dxf.center
                r = entity.dxf.radius
                min_x, min_y = min(min_x, c.x - r), min(min_y, c.y - r)
                max_x, max_y = max(max_x, c.x + r), max(max_y, c.y + r)

            elif etype in ("TEXT", "MTEXT"):
                p = entity.dxf.insert
                min_x, min_y = min(min_x, p.x), min(min_y, p.y)
                max_x, max_y = max(max_x, p.x), max(max_y, p.y)

        # Count paperspace layout entities
        for layout in doc.layouts:
            if layout.name != "Model":
                total_psp += len(layout)

        if total_msp == 0:
            errors.append("Modelspace contains 0 entities. All drawing data may be stored in layout/paperspace sheets.")
            next_steps.append("Export drawing from CAD with geometry placed in Modelspace.")

        if min_x == float("inf"):
            min_x, min_y, max_x, max_y = 0.0, 0.0, 0.0, 0.0

        raw_width = round(max(0.0, max_x - min_x), 2)
        raw_depth = round(max(0.0, max_y - min_y), 2)

        # 4. Check External References (XREFs)
        xrefs = []
        for block in doc.blocks:
            if getattr(block, "is_xref", False):
                xrefs.append({
                    "name": block.name,
                    "path": getattr(block, "dxf", {}).get("xref_path", "unknown"),
                })
        if xrefs:
            warnings.append(f"{len(xrefs)} External Reference(s) (XREFs) detected. Unbound external linework is not converted.")

        # 5. Unit Detection & Scale Confidence
        unit_ambiguity = False
        suggested_unit: Optional[str] = None
        applied_unit: str = "mm"
        scale_factor: float = 1.0

        if unit_override:
            applied_unit = unit_override.lower().strip()
            if applied_unit not in UNIT_FACTORS_TO_MM:
                errors.append(f"Invalid unit override: '{unit_override}'. Supported: {list(UNIT_FACTORS_TO_MM.keys())}")
            else:
                scale_factor = UNIT_FACTORS_TO_MM[applied_unit]
        elif insunits == 0:
            unit_ambiguity = True
            # Heuristic scale detection based on raw bounding box
            max_raw_dim = max(raw_width, raw_depth)
            if 1.0 <= max_raw_dim <= 150.0:
                suggested_unit = "m"
                applied_unit = "m"
                scale_factor = 1000.0
                warnings.append(f"$INSUNITS is unspecified (0). Raw extents ({max_raw_dim:.1f}) strongly suggest Meters ('m').")
            elif 15.0 <= max_raw_dim <= 500.0:
                suggested_unit = "ft"
                applied_unit = "ft"
                scale_factor = 304.8
                warnings.append(f"$INSUNITS is unspecified (0). Raw extents ({max_raw_dim:.1f}) suggest Feet ('ft').")
            elif 500.0 <= max_raw_dim <= 200000.0:
                suggested_unit = "mm"
                applied_unit = "mm"
                scale_factor = 1.0
                warnings.append(f"$INSUNITS is unspecified (0). Raw extents ({max_raw_dim:.1f}) suggest Millimeters ('mm').")
            else:
                suggested_unit = "mm"
                applied_unit = "mm"
                scale_factor = 1.0
                warnings.append("$INSUNITS is unspecified (0) and raw dimensions are unusual. Explicit unit confirmation required.")
        else:
            ins_name = INSUNITS_MAP.get(insunits, "unspecified")
            if ins_name in UNIT_FACTORS_TO_MM:
                applied_unit = ins_name
                scale_factor = UNIT_FACTORS_TO_MM[applied_unit]
            else:
                unit_ambiguity = True
                warnings.append(f"Unrecognized INSUNITS code {insunits}. Explicit confirmation required.")

        mm_width = round(raw_width * scale_factor, 2)
        mm_depth = round(raw_depth * scale_factor, 2)

        # Evaluate Scale Confidence
        max_mm_dim = max(mm_width, mm_depth)
        if unit_ambiguity:
            scale_confidence = ScaleConfidence.AMBIGUOUS
        elif 1500.0 <= max_mm_dim <= 200000.0:
            scale_confidence = ScaleConfidence.HIGH
        elif max_mm_dim > 0:
            scale_confidence = ScaleConfidence.MEDIUM
            warnings.append(f"Projected footprint ({mm_width:.1f} x {mm_depth:.1f} mm) is atypical for a residential building.")
        else:
            scale_confidence = ScaleConfidence.LOW

        # 6. Layer Classification & Architectural Semantics
        layer_classifications: Dict[str, str] = {}
        unclassified_layers: List[str] = []
        candidate_counts: Dict[str, int] = {
            "walls": 0,
            "doors": 0,
            "windows": 0,
            "slabs": 0,
            "annotations": 0,
            "closed_polylines": closed_polylines,
        }

        for layer in layer_names:
            cat = self.classifier.classify(layer)
            layer_classifications[layer] = cat
            if cat == "unknown" and layer not in ("0", "Defpoints"):
                unclassified_layers.append(layer)

        for entity in msp:
            if entity.dxf.paperspace:
                continue
            etype = entity.dxftype()
            layer = entity.dxf.layer
            cat = layer_classifications.get(layer, "unknown")

            if cat in ("exterior_wall", "interior_wall", "generic_wall"):
                if etype in ("LINE", "LWPOLYLINE", "POLYLINE"):
                    candidate_counts["walls"] += 1
            elif cat == "door":
                candidate_counts["doors"] += 1
            elif cat == "window":
                candidate_counts["windows"] += 1
            elif cat == "slab":
                candidate_counts["slabs"] += 1
            elif cat in ("annotation_text", "annotation_dim") or etype in ("TEXT", "MTEXT"):
                candidate_counts["annotations"] += 1

        # Check for drawing with 0 walls
        if candidate_counts["walls"] == 0 and total_msp > 0:
            errors.append("No architectural wall geometry recognized on wall layers. The drawing contains only annotations, dimensions, or unclassified linework.")
            next_steps.append("Check layer naming in config/layer-aliases.json or assign CAD linework to recognized wall layers.")

        # Check for unsupported entities
        unsupported_count = sum(c for t, c in entity_types.items() if t not in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "TEXT", "MTEXT", "INSERT"))
        if unsupported_count > 0:
            warnings.append(f"{unsupported_count} unsupported entity/entities (e.g. SPLINE, HATCH, DIMENSION) will be ignored during BIM reconstruction.")

        if degenerate_zero > 0:
            warnings.append(f"{degenerate_zero} zero-length line segment(s) detected and filtered.")
        if duplicate_lines > 0:
            warnings.append(f"{duplicate_lines} duplicate/overlapping line segment(s) detected.")

        # Overall Status Determination
        if errors:
            overall_status = PreflightStatus.FAILED
        elif warnings or unit_ambiguity:
            overall_status = PreflightStatus.WARNING
        else:
            overall_status = PreflightStatus.PASSED

        if not errors:
            if unit_ambiguity:
                next_steps.append(f"Confirm or override drawing unit (heuristic suggests '{suggested_unit}').")
            next_steps.append("Proceed to guided human approval of vertical elevations, storey counts, and wall thicknesses.")

        return PreflightReport(
            file_path=str(path),
            file_name=file_name,
            file_size_bytes=file_size,
            overall_status=overall_status,
            dxf_version=dxf_version,
            insunits_code=insunits,
            detected_units=applied_unit,
            unit_ambiguity=unit_ambiguity,
            suggested_unit=suggested_unit,
            scale_confidence=scale_confidence,
            scale_factor_to_mm=scale_factor,
            raw_extents={
                "min_x": round(min_x, 2),
                "min_y": round(min_y, 2),
                "max_x": round(max_x, 2),
                "max_y": round(max_y, 2),
                "width": raw_width,
                "depth": raw_depth,
            },
            extents_mm={
                "width": mm_width,
                "depth": mm_depth,
            },
            total_modelspace_entities=total_msp,
            total_paperspace_entities=total_psp,
            entity_counts_by_type=entity_types,
            layer_classifications=layer_classifications,
            unclassified_layers=unclassified_layers,
            candidate_counts=candidate_counts,
            external_references=xrefs,
            degenerate_geometry_counts={
                "zero_length": degenerate_zero,
                "duplicates": duplicate_lines,
            },
            warnings=warnings,
            errors=errors,
            recommended_next_steps=next_steps,
        )

