"""Wire protocol for the mecanum chassis.

The firmware parses a ``V`` command by buffering every byte up to a line
terminator, so a command must never be split across writes and must always
end with a single ``\\n``. Ack strings are matched against exactly what
``main.c`` prints.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.vector import DriveVector

CMD_TERMINATOR = b"\n"


class ResponseKind(Enum):
    """Classified reply from the chassis."""

    ACK = "ack"
    """A ``V`` command was accepted; the motion timer was refreshed."""

    STOP = "stop"
    """An ``S`` command was executed."""

    TIMEOUT = "timeout"
    """The chassis stopped itself because no command arrived in time.

    This means commands are not reaching the board, so the UI should
    surface it rather than log it quietly.
    """

    ERROR = "error"
    """The chassis rejected a command. Usually a malformed vector."""

    BANNER = "banner"
    """Boot-time informational text."""

    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Response:
    kind: ResponseKind
    raw: str


_BANNERS = (
    "MECANUM X READY",
    "F/B/L/R=move",
    "G/I/H/J=diagonal",
    "V,fwd,right,ccw",
)


def encode_vector(vector: DriveVector) -> bytes:
    """Encode a drive vector for the wire.

    No spaces and no leading ``+``: the firmware's parser skips spaces and
    commas but does not handle a plus sign, so ``V,+5,0,0`` would be read
    as malformed.
    """
    return f"V,{vector.forward},{vector.right},{vector.ccw}".encode("ascii") + CMD_TERMINATOR


def encode_stop() -> bytes:
    """Encode a hard stop.

    ``S`` must be its own line. If it were appended to a pending vector
    buffer the firmware would treat it as vector payload and drop it.
    """
    return b"S" + CMD_TERMINATOR


def parse_line(line: str) -> Response:
    """Classify one complete response line.

    Matching is prefix/substring based because the firmware prints both
    exact strings (``V OK``, ``STOP``) and variable ones (``ERR ...``).
    """
    text = line.strip()
    if not text:
        return Response(ResponseKind.UNKNOWN, line)

    if text == "V OK":
        return Response(ResponseKind.ACK, text)
    if text == "STOP":
        return Response(ResponseKind.STOP, text)
    if text == "STOP timeout":
        return Response(ResponseKind.TIMEOUT, text)
    if text.startswith("ERR"):
        return Response(ResponseKind.ERROR, text)
    if text.startswith(_BANNERS):
        return Response(ResponseKind.BANNER, text)

    return Response(ResponseKind.UNKNOWN, text)


class LineBuffer:
    """Accumulates raw serial bytes and yields complete lines.

    A serial read returns arbitrary fragments, so a line can span several
    reads. This keeps the partial remainder between calls.
    """

    def __init__(self, limit: int = 512) -> None:
        self._buffer = bytearray()
        self._limit = limit

    def feed(self, data: bytes) -> list[str]:
        """Add bytes and return every line that is now complete."""
        if not data:
            return []

        self._buffer.extend(data)

        if len(self._buffer) > self._limit and b"\n" not in self._buffer:
            # A newline never arrived, so the stream is out of sync. Drop
            # the garbage instead of growing without bound.
            self._buffer.clear()
            return []

        lines: list[str] = []
        while True:
            index = self._buffer.find(b"\n")
            if index < 0:
                break
            raw = bytes(self._buffer[:index])
            del self._buffer[: index + 1]
            lines.append(raw.decode("ascii", errors="replace").rstrip("\r"))

        return [line for line in lines if line]

    def reset(self) -> None:
        self._buffer.clear()
