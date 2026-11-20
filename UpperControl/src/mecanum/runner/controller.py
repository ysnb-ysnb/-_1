"""Transmit scheduling, acknowledgement tracking and the watchdog.

The controller is synchronous and driven by ``tick(now)``. It never sleeps
and never spawns a thread, so it can be exercised with a fake clock in
tests and driven from a Qt timer in the real application.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..core.state import DriveState
from ..core.vector import DriveVector
from ..link.transport import LinkTransport, TransportError
from ..protocol import (
    LineBuffer,
    Response,
    ResponseKind,
    encode_stop,
    encode_vector,
    parse_line,
)


@dataclass(frozen=True, slots=True)
class ControllerConfig:
    """Timing constants for the send loop and the watchdog.

    Defaults are chosen against the firmware's behaviour. The board stops
    itself after 1200 ms without a motion command, so a 400 ms keep-alive
    leaves three times the margin.

    ``fault_s`` is deliberately shorter than the firmware timeout: the host
    should give up *before* the board does, so the UI can explain what
    happened instead of showing a chassis that stopped itself for reasons
    the operator cannot see.
    """

    min_send_interval_s: float = 0.05
    """Never send faster than 20 Hz. At 9600 baud a full command plus the
    blocking acknowledgement takes about 24 ms, leaving useful margin."""

    keep_alive_s: float = 0.40
    """Resend the current command if nothing has gone out for this long."""

    ack_wait_s: float = 0.30
    """Do not send a new command while an acknowledgement for the previous
    one is still outstanding for less than this. Sending regardless would
    queue commands inside the Bluetooth stack, which shows up as the
    chassis lagging further behind the longer you drive."""

    fault_s: float = 0.90
    """No acknowledgement for this long after sending means the link is
    not working and the chassis must be commanded to stop."""

    def __post_init__(self) -> None:
        if self.fault_s <= self.ack_wait_s:
            raise ValueError("fault_s must be greater than ack_wait_s")


@dataclass
class LinkStats:
    """Everything the UI needs to display about the link."""

    state: DriveState = DriveState.DISCONNECTED
    last_sent: DriveVector | None = None
    last_sent_at: float = 0.0
    last_ack_at: float = 0.0
    last_rx_at: float = 0.0
    round_trip_ms: float | None = None
    last_response: Response | None = None
    ack_count: int = 0
    error_count: int = 0
    timeout_count: int = 0
    sent_count: int = 0
    message: str = ""

    def ack_age(self, now: float) -> float:
        """Seconds since the last acknowledgement, or inf if none ever came."""
        if self.last_ack_at <= 0.0:
            return float("inf")
        return now - self.last_ack_at


class Controller:
    """Owns the protocol conversation with the chassis."""

    def __init__(
        self,
        transport: LinkTransport,
        config: ControllerConfig | None = None,
        clock=time.monotonic,
    ) -> None:
        self._transport = transport
        self._config = config or ControllerConfig()
        self._clock = clock
        self._lines = LineBuffer()
        self._desired = DriveVector()
        self._pending: tuple[DriveVector, float] | None = None
        self._unacked_since: float | None = None
        self._open = False
        # Two separate latches: a link fault may clear itself once an
        # acknowledgement arrives, an emergency stop may not.
        self._estop_latched = False
        self._fault_latched = False

        self.stats = LinkStats()
        self.on_response = None
        """Optional callback(Response) called for every parsed line."""

    # ---------------------------------------------------------------- link

    def open(self) -> None:
        """Open the transport and move to READY, sending an initial stop."""
        self._transport.open()
        now = self._clock()

        self._open = True
        self._lines.reset()
        self._pending = None
        self._unacked_since = None
        self._estop_latched = False
        self._fault_latched = False
        self.stats = LinkStats(state=DriveState.READY, message="已连接")

        # Never assume the chassis is stationary: a previous session may
        # have left it driving.
        self._write(encode_stop(), None, now)

        # The handshake stop is a one-off and must not pace the first real
        # command, so the send interval starts from zero rather than from it.
        self.stats.last_sent_at = 0.0

    def close(self) -> None:
        """Stop the chassis and close the port."""
        if self._open:
            try:
                self._transport.write(encode_stop())
            except TransportError:
                pass
        self._transport.close()
        self._open = False
        self._pending = None
        self.stats.state = DriveState.DISCONNECTED
        self.stats.message = "已断开"

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def state(self) -> DriveState:
        return self.stats.state

    # ------------------------------------------------------------- control

    def set_desired(self, vector: DriveVector) -> None:
        """Record the newest command from the UI.

        This does not transmit. Sending is the tick's job, which keeps wire
        traffic independent of the input event rate and guarantees a steady
        cadence even while the mouse is still.
        """
        self._desired = vector

    def emergency_stop(self) -> None:
        """Hard stop and latch, ignoring all input until cleared."""
        self._desired = DriveVector()
        self._estop_latched = True
        if not self._open:
            return
        self.stats.state = DriveState.ESTOP
        self.stats.message = "急停已触发"
        self._write(encode_stop(), None, self._clock())

    def clear_estop(self) -> None:
        """Leave the emergency state and return to READY."""
        if self.stats.state is not DriveState.ESTOP:
            return
        self._estop_latched = False
        self._pending = None
        self._unacked_since = None
        self.stats.state = DriveState.READY
        self.stats.last_sent_at = 0.0
        self.stats.message = "急停已解除"

    def clear_fault(self) -> None:
        """Leave the FAULT state after the operator intervenes."""
        if self.stats.state is not DriveState.FAULT:
            return
        self._fault_latched = False
        self._pending = None
        self._unacked_since = None
        self.stats.state = DriveState.READY
        self.stats.last_sent_at = 0.0
        self.stats.message = "故障已解除"

    def stop_now(self) -> None:
        """Send a hard stop without changing the state machine."""
        self._desired = DriveVector()
        if self._open:
            self._write(encode_stop(), None, self._clock())

    # ---------------------------------------------------------------- tick

    def tick(self) -> None:
        """Pump the link. Call at a steady 50 Hz or faster."""
        if not self._open:
            return
        now = self._clock()
        self._drain(now)
        self._maybe_send(now)

    def _drain(self, now: float) -> None:
        try:
            data = self._transport.read()
        except TransportError as exc:
            self._fail(str(exc))
            return

        if data:
            self.stats.last_rx_at = now

        for line in self._lines.feed(data):
            response = parse_line(line)
            self.stats.last_response = response
            self._handle(response, now)
            if self.on_response is not None:
                self.on_response(response)

    def _handle(self, response: Response, now: float) -> None:
        kind = response.kind

        if kind is ResponseKind.ACK or kind is ResponseKind.STOP:
            pending = self._pending
            if pending is not None:
                self.stats.round_trip_ms = (now - pending[1]) * 1000.0
                self._pending = None
            self._unacked_since = None
            self.stats.last_ack_at = now
            self.stats.ack_count += 1

            # An acknowledgement proves the link works, so a fault caused by
            # silence can clear itself. An emergency stop is an operator
            # decision and must never be released by traffic.
            if self.stats.state is DriveState.FAULT and not self._estop_latched:
                self._fault_latched = False
                self.stats.state = DriveState.READY
                self.stats.message = "链路已恢复"
            return

        if kind is ResponseKind.TIMEOUT:
            # The board stopped itself, which means commands are no longer
            # arriving. That is a real fault, not a routine log line.
            self.stats.timeout_count += 1
            self.stats.last_ack_at = 0.0
            self._pending = None
            self._enter_fault("固件超时：指令没有送达")
            return

        if kind is ResponseKind.ERROR:
            self.stats.error_count += 1
            self.stats.message = f"固件拒绝了指令：{response.raw}"

    def _maybe_send(self, now: float) -> None:
        if self._estop_latched or self._fault_latched:
            return
        if self.stats.state not in (DriveState.READY, DriveState.DRIVING):
            return

        # The watchdog is keyed on the *first* unanswered send, not on the
        # newest one. Measuring from the newest would let the resend path
        # keep pushing the deadline forward, so a silently dead link would
        # never be declared faulty and would just transmit forever.
        if self._unacked_since is not None:
            if now - self._unacked_since >= self._config.fault_s:
                self._enter_fault("收不到回执")
                return

        if self._pending is not None:
            outstanding = now - self._pending[1]
            if outstanding < self._config.ack_wait_s:
                # Still waiting politely. Sending now would queue commands
                # inside the Bluetooth stack, which makes the chassis lag
                # further behind the longer you drive.
                return
            # Late but not yet fatal: fall through and resend the newest
            # command rather than waiting forever.

        since_send = now - self.stats.last_sent_at
        if since_send < self._config.min_send_interval_s:
            return

        desired = self._desired
        changed = desired != self.stats.last_sent
        due = since_send >= self._config.keep_alive_s
        if not (changed or due):
            return

        # A zero vector goes out as V,0,0,0, not S: the board ramps down
        # instead of cutting PWM, which is far kinder to the gearbox than a
        # hard cut every time the stick is released.
        self._write(encode_vector(desired), desired, now)

    def _write(self, payload: bytes, vector: DriveVector | None, now: float) -> None:
        try:
            self._transport.write(payload)
        except TransportError as exc:
            self._fail(str(exc))
            return

        self.stats.sent_count += 1
        self.stats.last_sent_at = now

        if vector is None:
            # A stop or handshake write: nothing to match an ack against.
            self._pending = None
            self.stats.last_sent = None
            return

        self.stats.last_sent = vector
        self._pending = (vector, now)
        if self._unacked_since is None:
            self._unacked_since = now
        self.stats.state = DriveState.READY if vector.is_zero else DriveState.DRIVING

    def _enter_fault(self, reason: str) -> None:
        self._fault_latched = True
        self.stats.state = DriveState.FAULT
        self.stats.message = reason
        self._pending = None
        self._unacked_since = None
        try:
            self._transport.write(encode_stop())
        except TransportError:
            pass

    def _fail(self, reason: str) -> None:
        self.stats.state = DriveState.DISCONNECTED
        self.stats.message = reason
        self._open = False
        self._pending = None
        try:
            self._transport.close()
        except Exception:
            pass
