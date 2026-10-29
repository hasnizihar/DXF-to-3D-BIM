"""Layer classification module for matching DXF layers to architectural categories."""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any


class LayerClassifier:
    """Classifies DXF layers using exact aliases and regex patterns."""

    def __init__(self, config_path: Optional[str | Path] = None):
        if config_path is None:
            # Default to repo config/layer-aliases.json
            config_path = Path(__file__).resolve().parent.parent.parent / "config" / "layer-aliases.json"
        
        config_path = Path(config_path)
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
        else:
            self.config = {"categories": {}}

        self.categories: Dict[str, Dict[str, Any]] = self.config.get("categories", {})

    @staticmethod
    def extract_level(layer_name: str) -> Optional[int]:
        """Extracts 1-based storey index from layer name if present (Mode A).
        
        Matches patterns like:
        - L1-WALL, L2_WALL, L03-DOOR
        - LEVEL-1-WALL, LEVEL_2_DOOR
        - STOREY-1-WALL, STOREY_2_WALL
        - FL01-WALL, FL02_WALL, FLOOR_1_WALL
        - WALL-L1, WALL_LEVEL_2, A-WALL-L2
        """
        clean = layer_name.strip().upper()
        # Prefix patterns: L1-, LEVEL_1-, FL01-, STOREY-1-
        m_pref = re.search(r"^(?:L|LEVEL[_-]?|STOREY[_-]?|FL(?:OOR)?[_-]?)0*([1-9]\d*)[_-]", clean)
        if m_pref:
            return int(m_pref.group(1))
        # Suffix patterns: -L1, _LEVEL_2, -FL02, -STOREY-1
        m_suff = re.search(r"[_-](?:L|LEVEL[_-]?|STOREY[_-]?|FL(?:OOR)?[_-]?)0*([1-9]\d*)$", clean)
        if m_suff:
            return int(m_suff.group(1))
        # Middle patterns: e.g. A-L1-WALL or A-LEVEL1-WALL
        m_mid = re.search(r"[_-](?:L|LEVEL[_-]?|STOREY[_-]?|FL(?:OOR)?[_-]?)0*([1-9]\d*)[_-]", clean)
        if m_mid:
            return int(m_mid.group(1))
        return None

    @staticmethod
    def strip_level_qualifier(layer_name: str) -> str:
        """Removes storey prefix/suffix to allow standard architectural classification."""
        clean = layer_name.strip()
        # Remove prefix
        s = re.sub(r"^(?:L|LEVEL[_-]?|STOREY[_-]?|FL(?:OOR)?[_-]?)[0-9]+[_-]", "", clean, flags=re.IGNORECASE)
        # Remove suffix
        s = re.sub(r"[_-](?:L|LEVEL[_-]?|STOREY[_-]?|FL(?:OOR)?[_-]?)[0-9]+$", "", s, flags=re.IGNORECASE)
        # Remove middle
        s = re.sub(r"[_-](?:L|LEVEL[_-]?|STOREY[_-]?|FL(?:OOR)?[_-]?)[0-9]+[_-]", "-", s, flags=re.IGNORECASE)
        return s.strip()

    def classify(self, layer_name: str) -> str:
        """Returns the semantic category or 'unknown'."""
        clean_name = layer_name.strip()
        upper_name = clean_name.upper()

        # 1. Exact match check (case-insensitive)
        for category, rules in self.categories.items():
            exacts = rules.get("exact", [])
            if any(upper_name == e.upper() for e in exacts):
                return category

        # 2. Regex pattern match
        for category, rules in self.categories.items():
            patterns = rules.get("patterns", [])
            for pat in patterns:
                if re.match(pat, clean_name, re.IGNORECASE):
                    return category

        # 3. Fallback: try after stripping storey qualifier (e.g., L2-WALL-EXTR -> WALL-EXTR)
        stripped = self.strip_level_qualifier(clean_name)
        if stripped != clean_name:
            stripped_upper = stripped.upper()
            for category, rules in self.categories.items():
                exacts = rules.get("exact", [])
                if any(stripped_upper == e.upper() for e in exacts):
                    return category
            for category, rules in self.categories.items():
                patterns = rules.get("patterns", [])
                for pat in patterns:
                    if re.match(pat, stripped, re.IGNORECASE):
                        return category

        return "unknown"

    def is_wall_layer(self, layer_name: str) -> bool:
        category = self.classify(layer_name)
        return category in ("exterior_wall", "interior_wall", "generic_wall")

    def is_opening_layer(self, layer_name: str) -> bool:
        category = self.classify(layer_name)
        return category in ("door", "window")

    def is_slab_layer(self, layer_name: str) -> bool:
        return self.classify(layer_name) == "slab"

    def is_stair_layer(self, layer_name: str) -> bool:
        return self.classify(layer_name) == "stair"

    def is_column_layer(self, layer_name: str) -> bool:
        return self.classify(layer_name) == "column"

    def is_beam_layer(self, layer_name: str) -> bool:
        return self.classify(layer_name) == "beam"

    def is_grid_layer(self, layer_name: str) -> bool:
        return self.classify(layer_name) == "grid"

    def is_foundation_layer(self, layer_name: str) -> bool:
        return self.classify(layer_name) == "foundation"


