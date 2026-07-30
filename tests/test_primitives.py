"""Unit tests for the shared calculation primitives.

Testing the building blocks in isolation -- especially the ceiling rounding,
which is the single most error-prone rule in the whole document -- guards
against silent regressions in the pieces every tariff depends on.
"""

import pytest

from port_tariff.calculation.primitives import (
    apply_minimum,
    blocks_per_100t,
    metres_ceiling,
)


class TestBlocksPer100t:
    def test_exact_multiple(self):
        assert blocks_per_100t(51300) == 513

    def test_part_thereof_rounds_up(self):
        assert blocks_per_100t(51301) == 514
        assert blocks_per_100t(1) == 1
        assert blocks_per_100t(100) == 1
        assert blocks_per_100t(101) == 2

    def test_zero(self):
        assert blocks_per_100t(0) == 0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            blocks_per_100t(-1)


class TestMetresCeiling:
    def test_rounds_up(self):
        assert metres_ceiling(229.2) == 230
        assert metres_ceiling(30.0) == 30
        assert metres_ceiling(30.01) == 31

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            metres_ceiling(-5)


class TestApplyMinimum:
    def test_below_minimum_floored(self):
        assert apply_minimum(100.0, 235.52) == 235.52

    def test_above_minimum_unchanged(self):
        assert apply_minimum(500.0, 235.52) == 500.0

    def test_no_minimum(self):
        assert apply_minimum(100.0, None) == 100.0
