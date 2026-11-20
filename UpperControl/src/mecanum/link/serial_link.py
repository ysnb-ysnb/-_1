"""Real serial link over Bluetooth SPP."""

from __future__ import annotations

import serial

from .transport import LinkTransport, TransportError

DEFAULT_BAUD = 9600


class SerialLink(LinkTransport):
    """pyserial transport.

    The firmware runs at 9600 8N1. The read timeout is intentionally short:
    the caller polls this from its own tick loop and must stay responsive,
    so ``read`` has to return quickly even when nothing arrives.
    """

    def __init__(self, device: str, baud: int = DEFAULT_BAUD) -> None:
        self._device = device
        self._baud = baud
        self._port: serial.Serial | None = None

    def open(self) -> None:
        if self._port is not None:
            return
        try:
            self._port = serial.Serial(
                port=self._device,
                baudrate=self._baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.02,
                write_timeout=0.5,
            )
        except serial.SerialException as exc:
            raise TransportError(f"cannot open {self._device}: {exc}") from exc

    def close(self) -> None:
        port, self._port = self._port, None
        if port is not None:
            try:
                port.close()
            except serial.SerialException:
                pass

    def write(self, payload: bytes) -> None:
        port = self._port
        if port is None:
            raise TransportError("link is not open")
        try:
            port.write(payload)
        except serial.SerialException as exc:
            raise TransportError(f"write failed: {exc}") from exc

    def read(self) -> bytes:
        port = self._port
        if port is None:
            return b""
        try:
            waiting = port.in_waiting
            return port.read(waiting or 1)
        except serial.SerialException as exc:
            raise TransportError(f"read failed: {exc}") from exc
        except OSError as exc:
            # Unplugging a Bluetooth adapter mid-session surfaces here.
            raise TransportError(f"device lost: {exc}") from exc

    @property
    def is_open(self) -> bool:
        return self._port is not None and self._port.is_open
