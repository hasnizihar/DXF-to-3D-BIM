"""Tests for DXF layer classification."""

import pytest
from dxf_to_3d_bim.layer_classifier import LayerClassifier

def test_layer_classifier_standard():
    lc = LayerClassifier()

    assert lc.classify("A-WALL-EXTR") == "exterior_wall"
    assert lc.classify("A-WALL-INTR") == "interior_wall"
    assert lc.classify("A-DOOR") == "door"
    assert lc.classify("A-GLAZ") == "window"
    assert lc.classify("A-FLOR") == "slab"
    assert lc.classify("A-ANNO-TEXT") == "annotation_text"
    assert lc.classify("RANDOM_UNKNOWN_LAYER") == "unknown"

def test_layer_classifier_regex_fallbacks():
    lc = LayerClassifier()

    assert lc.classify("WALL_EXTERIOR_01") == "exterior_wall"
    assert lc.classify("INT_PARTITION_WALL") == "interior_wall"
    assert lc.classify("WINDOW_GLAZING") == "window"
    assert lc.classify("DOORS_FIRST_FLOOR") == "door"

