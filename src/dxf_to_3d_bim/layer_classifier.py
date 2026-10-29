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

        return "unknown"

    def is_wall_layer(self, layer_name: str) -> bool:
        category = self.classify(layer_name)
        return category in ("exterior_wall", "interior_wall", "generic_wall")

    def is_opening_layer(self, layer_name: str) -> bool:
        category = self.classify(layer_name)
        return category in ("door", "window")

    def is_slab_layer(self, layer_name: str) -> bool:
        return self.classify(layer_name) == "slab"
