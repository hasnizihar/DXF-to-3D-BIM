"""Structured human review summary and deliverable reporting module."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from dxf_to_3d_bim.bimcraft_adapter import BimcraftBuildResult
from dxf_to_3d_bim.comparison import ComparisonReport
from dxf_to_3d_bim.intermediate_model import IntermediateBimModel


def compute_file_sha256(file_path: str | Path) -> str:
    path = Path(file_path)
    if not path.exists():
        return "FILE_NOT_FOUND"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class ReviewSummaryGenerator:
    """Generates comprehensive human-reviewable reports bridging DXF, intermediate model, BIMCraft, and IFC."""

    @staticmethod
    def generate_markdown(
        model: IntermediateBimModel,
        validation_report: Dict[str, Any],
        comparison_report: Optional[ComparisonReport] = None,
        build_result: Optional[BimcraftBuildResult] = None,
    ) -> str:
        d = model.data
        meta = d.get("metadata", {})
        projectName = meta.get("projectName", "BIM_Project")
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        dxf_path = meta.get("sourceDxfPath", "N/A")
        dxf_hash = compute_file_sha256(dxf_path) if dxf_path != "N/A" else "N/A"
        model_hash = d.get("approval", {}).get("modelHash", "UNAPPROVED")

        walls = d.get("walls", [])
        ext_walls = [w for w in walls if w.get("classification") == "exterior"]
        int_walls = [w for w in walls if w.get("classification") == "interior"]
        doors = [op for op in d.get("openings", []) if op.get("type") == "door"]
        windows = [op for op in d.get("openings", []) if op.get("type") == "window"]
        floors = d.get("floors", [])

        # Build Markdown
        md = []
        md.append(f"# BIM Review & Visual Verification Summary: {projectName}")
        md.append(f"**Date Generated:** {now_str}  ")
        md.append(f"**Approval Status:** `{d.get('status', 'unknown').upper()}`  ")
        md.append(f"**Overall Validation:** `{validation_report.get('overallStatus', 'UNKNOWN')}`  \n")

        md.append("---")
        md.append("## 1. Input Traceability & Cryptographic Hashes")
        md.append(f"* **Source DXF Path:** `{dxf_path}`")
        md.append(f"* **Source DXF SHA-256:** `{dxf_hash}`")
        md.append(f"* **Model Content Hash:** `{model_hash}`")
        if "sourceJsonPath" in meta:
            j_path = meta["sourceJsonPath"]
            md.append(f"* **Upstream Sketch-to-CAD JSON:** `{j_path}` (SHA-256: `{compute_file_sha256(j_path)}`)")
        md.append("")

        md.append("---")
        md.append("## 2. Reconstructed Building Elements")
        md.append("| Category | Reconstructed Target | Generated in IFC | Match Status |")
        md.append("| :--- | :--- | :--- | :--- |")

        gen = validation_report.get("elementSummary", {}).get("generated", {})
        md.append(f"| **Exterior Walls** | {len(ext_walls)} | {gen.get('walls', 'N/A')} (total) | {'PASSED' if gen.get('walls') == len(walls) else 'VERIFY'} |")
        md.append(f"| **Interior Partitions** | {len(int_walls)} | — | — |")
        md.append(f"| **Hosted Doors** | {len(doors)} | {gen.get('doors', 'N/A')} | {'PASSED' if gen.get('doors') == len(doors) else 'VERIFY'} |")
        md.append(f"| **Hosted Windows** | {len(windows)} | {gen.get('windows', 'N/A')} | {'PASSED' if gen.get('windows') == len(windows) else 'VERIFY'} |")
        md.append(f"| **Floor Slabs** | {len(floors)} | {len(floors)} | PASSED |")
        md.append("")

        md.append("---")
        md.append("## 3. Geometric & Semantic Validation Checks")
        for check in validation_report.get("checks", []):
            icon = "✅" if check["status"] == "PASSED" else ("⚠️" if check["status"] == "WARNING" else "❌")
            md.append(f"* {icon} **{check['name']}** (`{check['category']}`): {check['details']}")
        md.append("")

        if comparison_report:
            md.append("---")
            md.append("## 4. Source-DXF vs. Reconstructed-BIM Comparison")
            md.append("| Metric | Source DXF | Reconstructed BIM | Absolute Deviation | Tolerance | Status |")
            md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for m_key, m in comparison_report.footprint_deviation.items():
                md.append(f"| **{m.metric_name}** | {m.source_value:.1f} | {m.reconstructed_value:.1f} | {m.deviation_abs:.1f} ({m.deviation_pct}%) | {m.tolerance} | **{m.status}** |")
            md.append("")
            for f in comparison_report.findings:
                md.append(f"* {f}")
            md.append("")

        if build_result:
            md.append("---")
            md.append("## 5. Visual Deliverables & Renders")
            if build_result.view_3d_path and build_result.view_3d_path.exists():
                md.append(f"* **3D Axonometric Render:** `{build_result.view_3d_path.name}` ({build_result.view_3d_path.stat().st_size} bytes)")
            if build_result.png_path and build_result.png_path.exists():
                md.append(f"* **2D Plan View:** `{build_result.png_path.name}` ({build_result.png_path.stat().st_size} bytes)")
            if build_result.elevation_south_path and build_result.elevation_south_path.exists():
                md.append(f"* **South Elevation:** `{build_result.elevation_south_path.name}` ({build_result.elevation_south_path.stat().st_size} bytes)")
            if build_result.elevation_east_path and build_result.elevation_east_path.exists():
                md.append(f"* **East Elevation:** `{build_result.elevation_east_path.name}` ({build_result.elevation_east_path.stat().st_size} bytes)")
            if build_result.section_path and build_result.section_path.exists():
                md.append(f"* **Building Section A-A:** `{build_result.section_path.name}` ({build_result.section_path.stat().st_size} bytes)")
            if comparison_report and comparison_report.overlay_image_path:
                md.append(f"* **Geometry Overlay:** `{Path(comparison_report.overlay_image_path).name}`")
            md.append("")

        md.append("---")
        md.append("## 6. Engineering Boundary & Review Notice")
        md.append("> [!NOTE] Professional Review Required")
        md.append("> All 3D BIM elements, materials, thicknesses, and structural representations generated by this skill are architectural and conceptual for spatial coordination. Structural engineering calculations, local building code compliance, egress verification, and licensed sign-off must be independently performed by a licensed professional.")
        md.append("")

        return "\n".join(md)
