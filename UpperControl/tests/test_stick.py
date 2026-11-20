import pytest

from mecanum.core.stick import (
    apply_deadzone,
    condition_stick,
    limit_to_unit_circle,
    screen_to_body,
)


class TestDeadzone:
    def test_inside_deadzone_is_zero(self):
        assert apply_deadzone(0.03, 0.08) == 0.0
        assert apply_deadzone(-0.03, 0.08) == 0.0

    def test_outside_deadzone_is_unchanged(self):
        # Deliberately not rescaled: rescaling would create a jump at the
        # deadzone edge, which is felt as a lurch on a floored PWM.
        assert apply_deadzone(0.5, 0.08) == 0.5

    def test_exactly_at_edge_counts_as_outside(self):
        assert apply_deadzone(0.08, 0.08) == 0.08


class TestUnitCircle:
    def test_inside_unchanged(self):
        assert limit_to_unit_circle(0.3, 0.4) == (0.3, 0.4)

    def test_diagonal_full_push_is_scaled(self):
        # Without this a corner push would command 1.414x a straight push
        # and would saturate the wheels on every diagonal.
        x, y = limit_to_unit_circle(1.0, 1.0)
        assert (x * x + y * y) ** 0.5 == pytest.approx(1.0)

    def test_direction_preserved(self):
        x, y = limit_to_unit_circle(3.0, 4.0)
        assert x / y == pytest.approx(0.75)


class TestScreenToBody:
    def test_up_on_screen_is_forward(self):
        # Screen y grows downward, forward grows toward the nose.
        _, forward = screen_to_body(0.0, -1.0)
        assert forward == 1.0

    def test_right_on_screen_is_right(self):
        right, _ = screen_to_body(1.0, 0.0)
        assert right == 1.0


class TestConditionStick:
    def test_centred_gives_zero(self):
        assert condition_stick(0.0, 0.0) == (0.0, 0.0)

    def test_within_deadzone_gives_zero(self):
        assert condition_stick(0.05, 0.05) == (0.0, 0.0)

    def test_push_up_gives_forward(self):
        forward, right = condition_stick(0.0, -1.0)
        assert forward == pytest.approx(1.0)
        assert right == 0.0

    def test_push_right(self):
        forward, right = condition_stick(1.0, 0.0)
        assert right == pytest.approx(1.0)
        assert forward == 0.0

    def test_diagonal_limited_to_unit_circle(self):
        forward, right = condition_stick(-1.0, -1.0)
        assert (forward**2 + right**2) ** 0.5 == pytest.approx(1.0)

    def test_forward_direction_matches_screen_up(self):
        # Pushing the pointer up must move the chassis toward its nose.
        forward, _ = condition_stick(0.0, -0.9)
        assert forward > 0
