"""Run manifest module for recording traceable BIM run artifacts and hashes."""

import hashlib
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional


def file_sha256(path: str | Path) -> str:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return "NOT_FOUND"
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class ArtifactInfo:
    relative_path: str
    absolute_path: str
    sha256: str
    size_bytes: int


@dataclass
class RunManifest:
    manifest_version: str = "1.0.0"
    project_name: str = "BIMProject"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    run_status: str = "SUCCESS"  # SUCCESS, WARNING, FAILED
    source_dxf: Dict[str, Any] = field(default_factory=dict)
    toolchain: Dict[str, str] = field(default_factory=dict)
    approved_parameters: Dict[str, Any] = field(default_factory=dict)
    element_summary: Dict[str, int] = field(default_factory=dict)
    validation_summary: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "analysis": {},
        "models": {},
        "previews": {},
        "reports": {},
    })
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_artifact(self, category: str, name: str, file_path: str | Path, base_dir: Optional[Path] = None):
        p = Path(file_path)
        if not p.exists():
            return
        rel = str(p.relative_to(base_dir)) if base_dir and p.is_relative_to(base_dir) else p.name
        self.artifacts[category][name] = {
            "relative_path": rel,
            "absolute_path": str(p.resolve()),
            "sha256": file_sha256(p),
            "size_bytes": p.stat().st_size,
        }

    def save(self, output_path: str | Path) -> Path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        return out

