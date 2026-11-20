"""Drive state machine."""

from __future__ import annotations

from enum import Enum, auto


class DriveState(Enum):
    """Connection and control state of the link."""

    DISCONNECTED = auto()
    """No usable serial port. Stick input is ignored."""

    CONNECTING = auto()
    """Port is opening. No motion command may be sent yet."""

    READY = auto()
    """Connected and stationary. Waiting for stick input."""

    DRIVING = auto()
    """A non-zero vector is being sent repeatedly."""

    FAULT = auto()
    """Acknowledgements stopped arriving. Stick input is locked out until
    the operator explicitly clears the fault."""

    ESTOP = auto()
    """Emergency stop engaged. Only an explicit clear leaves this state."""

    @property
    def can_drive(self) -> bool:
        """Whether motion commands are permitted in this state."""
        return self in (DriveState.READY, DriveState.DRIVING)

    @property
    def is_live(self) -> bool:
        """Whether the port is open, regardless of whether driving is allowed."""
        return self is not DriveState.DISCONNECTED and self is not DriveState.CONNECTING
