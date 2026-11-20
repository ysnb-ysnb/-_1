"""Joystick conditioning: deadzone and unit-circle limiting."""

from __future__ import annotations

import math

DEFAULT_DEADZONE = 0.08


def apply_deadzone(value: float, deadzone: float = DEFAULT_DEADZONE) -> float:
    """Return 0 inside the deadzone, otherwise the value unchanged.

    The output is deliberately not rescaled to fill the range 0..1. Doing
    so would turn the deadzone edge into a discontinuity, which on a
    chassis with a PWM floor of 15% is felt as a sudden lurch.
    """
    return 0.0 if abs(value) < deadzone else value


def limit_to_unit_circle(x: float, y: float) -> tuple[float, float]:
    """Scale (x, y) down so its length never exceeds 1.

    Without this a diagonal push would command sqrt(2) times the
    magnitude of a straight push, so diagonals would always saturate the
    four wheels and run at reduced speed after normalisation.
    """
    radius = math.hypot(x, y)
    if radius <= 1.0:
        return x, y
    return x / radius, y / radius


def screen_to_body(x: float, y: float) -> tuple[float, float]:
    """Convert screen axes to body axes.

    Screen Y grows downward, body ``forward`` grows toward the nose.
    """
    return x, -y


def condition_stick(
    x: float,
    y: float,
    deadzone: float = DEFAULT_DEADZONE,
) -> tuple[float, float]:
    """Full stick pipeline for the translation axes.

    Returns body-frame (forward, right) in -1..1, limited to the unit
    circle. No scaling to the command range happens here; that is the
    shaper's job because it also owns the speed limit and the PWM floor.
    """
    right, forward = screen_to_body(x, y)
    right = apply_deadzone(right, deadzone)
    forward = apply_deadzone(forward, deadzone)
    right, forward = limit_to_unit_circle(right, forward)
    return forward, right
