"""Link transport abstraction.

Everything that touches hardware lives behind this interface so that the
controller can be exercised against a fake link in tests and in the UI
before a real chassis is connected.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


class TransportError(RuntimeError):
    """Raised when the link cannot be opened or fails during use."""


@dataclass(frozen=True, slots=True)
class PortInfo:
    """A candidate serial port."""

    device: str
    description: str
    is_bluetooth: bool

    def label(self) -> str:
        mark = "BT" if self.is_bluetooth else "--"
        return f"[{mark}] {self.device} — {self.description}"


class LinkTransport(abc.ABC):
    """Bidirectional byte pipe to the chassis."""

    @abc.abstractmethod
    def open(self) -> None:
        """Open the link. Raises TransportError on failure."""

    @abc.abstractmethod
    def close(self) -> None:
        """Close the link. Must be safe to call when already closed."""

    @abc.abstractmethod
    def write(self, payload: bytes) -> None:
        """Write a complete command. Raises TransportError on failure."""

    @abc.abstractmethod
    def read(self) -> bytes:
        """Return whatever bytes are available, possibly empty.

        Must not block for longer than a few tens of milliseconds, because
        the caller polls it inside its own tick loop.
        """

    @property
    @abc.abstractmethod
    def is_open(self) -> bool:
        """Whether the link is currently usable."""


def list_ports() -> list[PortInfo]:
    """Enumerate serial ports, flagging Bluetooth SPP ones.

    Bluetooth SPP on Windows appears as a virtual COM port whose
    description contains "Standard Serial over Bluetooth". Flagging it
    lets the UI put the right port at the top of the list: a pairing
    normally creates two ports and only the outbound one works.
    """
    from serial.tools import list_ports as _list_ports

    ports: list[PortInfo] = []
    for port in _list_ports.comports():
        description = port.description or ""
        is_bt = "bluetooth" in description.lower()
        ports.append(
            PortInfo(
                device=port.device,
                description=description or "unknown",
                is_bluetooth=is_bt,
            )
        )
    ports.sort(key=lambda p: (not p.is_bluetooth, p.device))
    return ports
