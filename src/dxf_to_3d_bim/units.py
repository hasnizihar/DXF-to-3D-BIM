"""Units and coordinate normalization module for DXF-to-3D-BIM."""

from typing import Tuple, List, Optional

UNIT_FACTORS_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    "ft": 304.8,
}

INSUNITS_MAP = {
    0: "unspecified",
    1: "in",
    2: "ft",
    4: "mm",
    5: "cm",
    6: "m",
}

class UnitConverter:
    def __init__(self, source_units: str = "mm"):
        self.source_units = source_units.lower().strip()
        if self.source_units not in UNIT_FACTORS_TO_MM:
            raise ValueError(f"Unsupported unit: '{source_units}'. Supported: {list(UNIT_FACTORS_TO_MM.keys())}")
        self.scale_factor = UNIT_FACTORS_TO_MM[self.source_units]

    @classmethod
    def from_insunits(cls, insunits_code: int, fallback: str = "mm") -> "UnitConverter":
        unit_name = INSUNITS_MAP.get(insunits_code, "unspecified")
        if unit_name == "unspecified":
            unit_name = fallback
        return cls(unit_name)

    def to_mm(self, value: float) -> float:
        return float(value) * self.scale_factor

    def point_to_mm(self, point: Tuple[float, float]) -> Tuple[float, float]:
        return (self.to_mm(point[0]), self.to_mm(point[1]))

    def polygon_to_mm(self, points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        return [self.point_to_mm(p) for p in points]

