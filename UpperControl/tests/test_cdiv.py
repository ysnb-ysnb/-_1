import math

import pytest

from mecanum.core.cdiv import clamp, trunc_div


class TestTruncDiv:
    def test_positive(self):
        assert trunc_div(45, 100) == 0
        assert trunc_div(150, 100) == 1
        assert trunc_div(399, 100) == 3

    def test_negative_truncates_toward_zero(self):
        # This is the whole reason the helper exists: C truncates toward
        # zero while Python's // floors, giving -1 and -2 here.
        assert trunc_div(-45, 100) == 0
        assert trunc_div(-150, 100) == -1
        assert trunc_div(-399, 100) == -3

    def test_matches_python_floor_for_exact_division(self):
        assert trunc_div(200, 100) == 2
        assert trunc_div(-200, 100) == -2

    def test_zero_denominator_raises(self):
        with pytest.raises(ZeroDivisionError):
            trunc_div(1, 0)

    @pytest.mark.parametrize("value", range(-400, 401, 7))
    def test_agrees_with_int_truncation(self, value):
        assert trunc_div(value, 100) == int(value / 100)


class TestClamp:
    def test_within_range(self):
        assert clamp(5, -100, 100) == 5

    def test_bounds(self):
        assert clamp(-200, -100, 100) == -100
        assert clamp(200, -100, 100) == 100
