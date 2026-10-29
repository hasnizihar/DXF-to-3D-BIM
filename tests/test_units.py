"""Unit tests for unit conversion and normalization."""

import pytest
from dxf_to_3d_bim.units import UnitConverter, UNIT_FACTORS_TO_MM

def test_unit_conversion_mm():
    c = UnitConverter("mm")
    assert c.scale_factor == 1.0
    assert c.to_mm(500) == 500.0
    assert c.point_to_mm((100, 200)) == (100.0, 200.0)

def test_unit_conversion_m():
    c = UnitConverter("m")
    assert c.scale_factor == 1000.0
    assert c.to_mm(3.5) == 3500.0
    assert c.point_to_mm((1.2, 2.5)) == (1200.0, 2500.0)

def test_unit_conversion_in_ft():
    c_in = UnitConverter("in")
    assert pytest.approx(c_in.to_mm(10), 0.001) == 254.0

    c_ft = UnitConverter("ft")
    assert pytest.approx(c_ft.to_mm(1), 0.001) == 304.8

def test_insunits_mapping():
    c_m = UnitConverter.from_insunits(6)
    assert c_m.source_units == "m"
    assert c_m.to_mm(2) == 2000.0

    c_fallback = UnitConverter.from_insunits(0, fallback="mm")
    assert c_fallback.source_units == "mm"
    assert c_fallback.to_mm(10) == 10.0

def test_invalid_unit():
    with pytest.raises(ValueError):
        UnitConverter("lightyears")

