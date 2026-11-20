"""Mecanum forward kinematics and a bit-exact model of the firmware.

Wheel order matches ``motors[]`` in the firmware: FL, FR, RL, RR.

Keeping a faithful model of the MCU here is deliberate. The host can then
show the PWM each wheel is actually about to receive, which makes the
15% floor and the speed lost to wheel normalisation visible while driving
instead of being discovered on the floor.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cdiv import clamp, trunc_div
from .vector import DriveVector

# Must match the firmware constants.
PWM_MAX_VALUE = 399
PWM_MIN_RUN = 60
WHEEL_CMD_MAX = 100

FL, FR, RL, RR = 0, 1, 2, 3
WHEEL_NAMES = ("FL", "FR", "RL", "RR")


def wheel_speeds(vector: DriveVector) -> tuple[int, int, int, int]:
    """Standard X-layout mecanum inverse kinematics.

    FL = forward + right - ccw
    FR = forward - right + ccw
    RL = forward - right - ccw
    RR = forward + right + ccw

    Returns the raw, un-normalised wheel speeds.
    """
    fwd, right, ccw = vector.forward, vector.right, vector.ccw
    return (
        fwd + right - ccw,
        fwd - right + ccw,
        fwd - right - ccw,
        fwd + right + ccw,
    )


def normalise(wheels: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Scale all wheels down so the largest magnitude is at most 100.

    When translation and rotation are combined the raw wheel values can
    reach 200, so the firmware rescales everything by 100 / max. That is
    why combining translation with rotation makes the chassis slower in
    the translational direction.
    """
    peak = max(abs(w) for w in wheels)
    if peak <= WHEEL_CMD_MAX:
        return wheels
    return tuple(trunc_div(w * WHEEL_CMD_MAX, peak) for w in wheels)  # type: ignore[return-value]


def pwm_for_wheel(wheel: int, trim_percent: int = 100) -> int:
    """Reproduce the firmware's conversion from wheel value to PWM.

    Order is significant: trim, clamp, scale to the timer range, then
    raise anything non-zero up to the minimum run value so the gearbox
    actually breaks away from static friction.
    """
    speed = trunc_div(wheel * trim_percent, 100)
    speed = clamp(speed, -WHEEL_CMD_MAX, WHEEL_CMD_MAX)

    pwm = trunc_div(speed * PWM_MAX_VALUE, 100)
    if pwm != 0 and abs(pwm) < PWM_MIN_RUN:
        pwm = PWM_MIN_RUN if pwm > 0 else -PWM_MIN_RUN
    return pwm


@dataclass(frozen=True, slots=True)
class WheelModel:
    """Predicted firmware output for one command."""

    wheels: tuple[int, int, int, int]
    pwm: tuple[int, int, int, int]
    raw_peak: int = 0

    @property
    def peak_wheel(self) -> int:
        """Largest normalised wheel value, 0..100."""
        return max(abs(w) for w in self.wheels)

    @property
    def normalisation_loss(self) -> float:
        """Fraction of translational speed lost to normalisation, 0..1.

        Must be measured against the *raw* peak, because the normalised
        peak is always at most 100 once clamping has happened. Using the
        normalised value would always report zero loss.
        """
        if self.raw_peak <= WHEEL_CMD_MAX:
            return 0.0
        return 1.0 - WHEEL_CMD_MAX / self.raw_peak


def predict(
    vector: DriveVector,
    trim: tuple[int, int, int, int] = (100, 100, 100, 100),
) -> WheelModel:
    """Compute the wheels and PWM the firmware will produce for ``vector``."""
    raw = wheel_speeds(vector)
    wheels = normalise(raw)
    pwm = tuple(pwm_for_wheel(w, t) for w, t in zip(wheels, trim))
    return WheelModel(
        wheels=wheels,
        pwm=pwm,
        raw_peak=max(abs(w) for w in raw),
    )  # type: ignore[arg-type]
