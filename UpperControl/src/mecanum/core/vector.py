"""Drive vector in the body frame."""

from __future__ import annotations

from dataclasses import dataclass

CMD_MIN = -100
CMD_MAX = 100


def clamp_cmd(value: int) -> int:
    """Clamp a command component to the firmware's accepted range."""
    return max(CMD_MIN, min(CMD_MAX, int(value)))


@dataclass(frozen=True, slots=True)
class DriveVector:
    """Normalised chassis command.

    forward  + toward the nose, - toward the tail
    right    + toward the right side, - toward the left
    ccw      + counter-clockwise seen from above, - clockwise

    All three are integers in -100..100, exactly the range the firmware
    accepts in a ``V,forward,right,ccw`` line.
    """

    forward: int = 0
    right: int = 0
    ccw: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "forward", clamp_cmd(self.forward))
        object.__setattr__(self, "right", clamp_cmd(self.right))
        object.__setattr__(self, "ccw", clamp_cmd(self.ccw))

    @property
    def is_zero(self) -> bool:
        """True when nothing is commanded, i.e. the chassis should coast."""
        return self.forward == 0 and self.right == 0 and self.ccw == 0

    @property
    def translation_magnitude(self) -> float:
        """Length of the translational part, in command units."""
        return (self.forward**2 + self.right**2) ** 0.5

    def __str__(self) -> str:
        return f"V,{self.forward},{self.right},{self.ccw}"
