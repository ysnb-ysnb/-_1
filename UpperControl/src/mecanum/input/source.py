"""Input primitives.

The virtual stick itself lives in the UI layer because it needs to paint.
What lives here is the pure logic: the rotation ramp, which must be
computed on the control tick rather than on key events so that a held key
produces a smooth ramp instead of a jump.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RawInput:
    """Unconditioned operator input.

    x and y are screen-space stick coordinates in -1..1 with +y downward,
    which is what a pointer naturally produces. ``rotation`` is -1..1 with
    + meaning counter-clockwise.
    """

    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0

    def is_centred(self) -> bool:
        return self.x == 0.0 and self.y == 0.0 and self.rotation == 0.0


class InputSource(Protocol):
    """Anything that can supply a RawInput."""

    def poll(self) -> RawInput: ...

    def reset(self) -> None: ...


class RampAxis:
    """A key-driven axis that ramps toward its target instead of jumping.

    Spinning the chassis at full rate the instant a key is pressed is
    unpleasant and hard on the gearbox, so the value climbs over ``ramp_s``.
    The ramp is advanced from the control tick, not from key events, so its
    speed does not depend on the keyboard repeat rate.

    Direction: +1 is counter-clockwise, which matches the sign convention of
    the ``ccw`` field in the wire protocol.
    """

    def __init__(self, ramp_s: float = 0.30) -> None:
        self._ramp_s = max(ramp_s, 1e-3)
        self._value = 0.0
        self._target = 0.0

    def hold(self, direction: int) -> None:
        """Set the target to -1, 0 or +1."""
        self._target = max(-1, min(1, direction))

    def update(self, dt: float) -> float:
        """Advance the ramp and return the current value."""
        if dt > 0.0:
            step = dt / self._ramp_s
            delta = self._target - self._value
            if abs(delta) <= step:
                self._value = float(self._target)
            else:
                self._value += step if delta > 0 else -step
        return self._value

    def reset(self) -> None:
        self._value = 0.0
        self._target = 0.0

    @property
    def value(self) -> float:
        return self._value

    @property
    def target(self) -> float:
        return self._target
