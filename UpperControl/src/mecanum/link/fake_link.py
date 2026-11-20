"""Simulated links for development without a chassis.

Two purposes: exercising the controller and UI before hardware exists, and
reproducing the failure modes that are hard to trigger on a real bench
(dropped acknowledgements, slow link, silent link).
"""

from __future__ import annotations

import random
import time
from collections import deque

from ..core.vector import DriveVector
from ..protocol import encode_vector, parse_line, Response, ResponseKind
from .transport import LinkTransport, TransportError

BOOT_BANNER = (
    b"MECANUM X READY\r\n"
    b"F/B/L/R=move Q/E=rotate S=stop\r\n"
    b"G/I/H/J=diagonal\r\n"
    b"V,fwd,right,ccw<ENTER>=vector -100..100\r\n"
)


class FakeLink(LinkTransport):
    """In-memory chassis that answers like the firmware.

    ``ack_delay`` is applied by the caller's wall clock, so the model stays
    free of sleeping. ``drop_rate`` simulates lost acknowledgements, which
    is what the latency and watchdog logic exists to survive.
    """

    def __init__(
        self,
        ack_delay: float = 0.025,
        drop_rate: float = 0.0,
        seed: int | None = None,
    ) -> None:
        self.ack_delay = ack_delay
        self.drop_rate = drop_rate
        self._random = random.Random(seed)
        self._open = False
        self._pending: list[tuple[float, bytes]] = []
        self._inbound = bytearray()
        self._line_buffer = bytearray()

        self.last_vector: DriveVector | None = None
        self.commands_received: list[str] = []
        self.writes: list[bytes] = []

    def open(self) -> None:
        if self._open:
            return
        self._open = True
        self._pending.append((time.monotonic() + self.ack_delay, BOOT_BANNER))

    def close(self) -> None:
        self._open = False
        self._pending.clear()
        self._inbound.clear()
        self._line_buffer.clear()

    def write(self, payload: bytes) -> None:
        if not self._open:
            raise TransportError("link is not open")

        self.writes.append(payload)
        self._line_buffer.extend(payload)

        while True:
            index = self._line_buffer.find(b"\n")
            if index < 0:
                break
            raw = bytes(self._line_buffer[:index])
            del self._line_buffer[: index + 1]
            self._handle_command(raw.decode("ascii", errors="replace").strip())

    def _handle_command(self, line: str) -> None:
        if not line:
            return

        self.commands_received.append(line)

        if line == "S":
            self.last_vector = None
            self._reply(b"STOP\r\n")
            return

        if line.startswith("V"):
            parts = line[1:].split(",")
            if parts and parts[0] == "":
                parts = parts[1:]
            try:
                forward, right, ccw = (int(p) for p in parts[:3])
            except (ValueError, TypeError):
                self._reply(b"ERR V,fwd,right,ccw\r\n")
                return
            self.last_vector = DriveVector(forward, right, ccw)
            self._reply(b"V OK\r\n")
            return

        self._reply(b"OK\r\n")

    def _reply(self, payload: bytes) -> None:
        if self.drop_rate and self._random.random() < self.drop_rate:
            return
        self._pending.append((time.monotonic() + self.ack_delay, payload))

    def read(self) -> bytes:
        if not self._open:
            return b""

        now = time.monotonic()
        ready = [item for item in self._pending if item[0] <= now]
        if ready:
            self._pending = [item for item in self._pending if item[0] > now]
            for _, payload in ready:
                self._inbound.extend(payload)

        if not self._inbound:
            return b""

        data = bytes(self._inbound)
        self._inbound.clear()
        return data

    @property
    def is_open(self) -> bool:
        return self._open


class SilentLink(LinkTransport):
    """Opens successfully but never answers.

    Models a paired-but-wrong COM port, which is the most common setup
    mistake: the port opens, writes succeed, and nothing ever comes back.
    """

    def __init__(self) -> None:
        self._open = False
        self.writes: list[bytes] = []

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def write(self, payload: bytes) -> None:
        if not self._open:
            raise TransportError("link is not open")
        self.writes.append(payload)

    def read(self) -> bytes:
        return b""

    @property
    def is_open(self) -> bool:
        return self._open


class ScriptedLink(LinkTransport):
    """Replays canned responses, for parser and watchdog tests."""

    def __init__(self, responses: list[bytes] | None = None) -> None:
        self._open = False
        self._responses: deque[bytes] = deque(responses or [])
        self.writes: list[bytes] = []

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def write(self, payload: bytes) -> None:
        if not self._open:
            raise TransportError("link is not open")
        self.writes.append(payload)

    def push(self, payload: bytes) -> None:
        self._responses.append(payload)

    def read(self) -> bytes:
        return self._responses.popleft() if self._responses else b""

    @property
    def is_open(self) -> bool:
        return self._open
