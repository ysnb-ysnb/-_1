"""Command shaping: speed limits, PWM floor and smoothing.

Pure arithmetic only. This module deliberately does not know about the
wire protocol, so it can be unit tested without touching serial code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .vector import DriveVector

# Must match the firmware's PWM_MIN_RUN and PWM_MAX_VALUE.
PWM_MIN_RUN = 60
PWM_MAX_VALUE = 399

# Smallest wheel value the firmware does not raise to PWM_MIN_RUN.
# Derived rather than hard-coded so it tracks the firmware constants:
# ceil(60 * 100 / 399) == 16.
FLOOR_WHEEL = math.ceil(PWM_MIN_RUN * 100 / PWM_MAX_VALUE)


@dataclass(frozen=True, slots=True)
class ShapeConfig:
    """Tunables for the outbound command."""

    deadzone: float = 0.08
    filter_tau: float = 0.06
    speed_limit: float = 0.60
    rotation_limit: float = 0.40

    def clamped(self) -> ShapeConfig:
        """Return a copy with every value forced into a sane range."""
        return ShapeConfig(
            deadzone=min(max(self.deadzone, 0.0), 0.5),
            filter_tau=max(self.filter_tau, 0.0),
            speed_limit=min(max(self.speed_limit, 0.0), 1.0),
            rotation_limit=min(max(self.rotation_limit, 0.0), 1.0),
        )


def floor_map(magnitude: float, limit: float, floor: int = FLOOR_WHEEL) -> float:
    """Map a 0..1 magnitude onto [floor, limit * 100].

    The firmware raises any non-zero PWM below ``PWM_MIN_RUN`` up to it, so
    wheel values 1..15 all produce the same speed. Mapping the stick
    linearly across 0..100 would give a dead stretch and then a lurch, so
    the usable range starts at ``floor`` instead.

    Zero maps to zero, so a centred stick commands a true stop. The floor is
    only reachable once the stick leaves the deadzone, and that step is a
    hardware limit, not a choice: nothing slower than PWM_MIN_RUN exists.

    When the user limit is below the floor the output is pinned to the
    floor, because the hardware cannot go slower and a smaller command
    would be raised to the same PWM anyway.
    """
    if magnitude <= 0.0:
        return 0.0

    ceiling = limit * 100.0
    top = max(ceiling, float(floor))
    return floor + (top - floor) * min(magnitude, 1.0)


def ema_alpha(dt: float, tau: float) -> float:
    """Per-frame smoothing factor for a first-order low-pass filter.

    ``alpha = 1 - exp(-dt / tau)`` keeps the smoothing *time constant*
    fixed when the tick rate changes, unlike a hard-coded coefficient.
    At 60 Hz with tau = 60 ms this gives alpha ~= 0.24.
    """
    if tau <= 0.0:
        return 1.0
    return 1.0 - math.exp(-dt / tau)


class Ema1:
    """First-order low-pass filter over a single float."""

    __slots__ = ("_value", "_seeded")

    def __init__(self) -> None:
        self._value = 0.0
        self._seeded = False

    def update(self, target: float, alpha: float) -> float:
        if not self._seeded:
            self._value = target
            self._seeded = True
        else:
            self._value += (target - self._value) * alpha
        return self._value

    def reset(self) -> None:
        self._value = 0.0
        self._seeded = False

    @property
    def value(self) -> float:
        return self._value


class Shaper:
    """Turns conditioned stick input into a wire-ready command.

    Filtering happens here, on the outbound command, not on the raw stick
    position: the pointer must track the hand immediately even while the
    chassis accelerates smoothly.
    """

    def __init__(self, config: ShapeConfig | None = None) -> None:
        self.config = (config or ShapeConfig()).clamped()
        self._forward = Ema1()
        self._right = Ema1()
        self._rotation = Ema1()

    def apply_config(self, config: ShapeConfig) -> None:
        self.config = config.clamped()

    def reset(self) -> None:
        for axis in (self._forward, self._right, self._rotation):
            axis.reset()

    def target(self, forward: float, right: float, rotation: float) -> DriveVector:
        """Unfiltered command for the current stick state.

        ``forward`` and ``right`` come from ``condition_stick``, so they are
        already deadzoned and unit-circle limited. ``rotation`` is a
        -1..1 value that gets the rotation limit rather than the
        translation limit, since it does not contribute to the translational
        magnitude.
        """
        magnitude = math.hypot(forward, right)
        if magnitude > 0.0:
            scaled = floor_map(magnitude, self.config.speed_limit)
            gain = scaled / magnitude
            forward *= gain
            right *= gain

        ccw = 0.0
        if rotation != 0.0:
            ccw = floor_map(abs(rotation), self.config.rotation_limit)
            if rotation < 0.0:
                ccw = -ccw

        return DriveVector(
            forward=round_half_away(forward),
            right=round_half_away(right),
            ccw=round_half_away(ccw),
        )

    def smooth(self, target: DriveVector, dt: float) -> DriveVector:
        """Filter a target command toward its value over time."""
        alpha = ema_alpha(dt, self.config.filter_tau)
        return DriveVector(
            forward=round_half_away(self._forward.update(target.forward, alpha)),
            right=round_half_away(self._right.update(target.right, alpha)),
            ccw=round_half_away(self._rotation.update(target.ccw, alpha)),
        )


def round_half_away(value: float) -> int:
    """Round half away from zero.

    Python's built-in ``round`` uses banker's rounding, so ``round(0.5)`` is
    0 while ``round(1.5)`` is 2. That asymmetry is invisible in practice but
    makes test expectations confusing, so it is avoided deliberately.
    """
    if value >= 0.0:
        return int(math.floor(value + 0.5))
    return -int(math.floor(-value + 0.5))
