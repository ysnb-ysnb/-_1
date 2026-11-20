"""Controller tests driven by a fake clock and scripted links."""

from __future__ import annotations

import pytest

from mecanum.core.state import DriveState
from mecanum.core.vector import DriveVector
from mecanum.link.fake_link import FakeLink, ScriptedLink, SilentLink
from mecanum.runner.controller import Controller, ControllerConfig


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


def make(link, clock, **overrides):
    config = ControllerConfig(**overrides) if overrides else None
    return Controller(link, config=config, clock=clock)


class TestOpenClose:
    def test_open_enters_ready_and_sends_stop(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        assert ctrl.state is DriveState.READY
        # The chassis may have been left driving, so a stop must go out
        # before anything else.
        assert link.writes == [b"S\n"]

    def test_close_sends_stop(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        link.writes.clear()
        ctrl.close()
        assert b"S\n" in link.writes
        assert ctrl.state is DriveState.DISCONNECTED

    def test_close_is_idempotent(self, clock):
        ctrl = make(ScriptedLink(), clock)
        ctrl.open()
        ctrl.close()
        ctrl.close()
        assert ctrl.state is DriveState.DISCONNECTED


class TestAckGating:
    def test_sends_once_then_waits_for_ack(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        link.writes.clear()

        ctrl.set_desired(DriveVector(60, 0, 0))
        ctrl.tick()
        assert len(link.writes) == 1

        # No ack yet, and inside the wait window, so nothing new goes out.
        clock.advance(0.2)
        ctrl.tick()
        assert len(link.writes) == 1

    def test_sends_next_after_ack(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        link.writes.clear()

        ctrl.set_desired(DriveVector(60, 0, 0))
        ctrl.tick()
        link.push(b"V OK\r\n")
        ctrl.tick()
        assert ctrl.stats.ack_count == 1

        clock.advance(0.06)
        ctrl.set_desired(DriveVector(70, 0, 0))
        ctrl.tick()
        assert len(link.writes) == 2

    def test_respects_min_send_interval(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        link.writes.clear()

        ctrl.set_desired(DriveVector(60, 0, 0))
        ctrl.tick()
        link.push(b"V OK\r\n")
        ctrl.tick()

        # A new value inside the 50 ms interval must not be sent yet.
        clock.advance(0.02)
        ctrl.set_desired(DriveVector(80, 0, 0))
        ctrl.tick()
        assert len(link.writes) == 1

    def test_unchanged_value_not_resent_until_keepalive(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        link.writes.clear()

        ctrl.set_desired(DriveVector(60, 0, 0))
        ctrl.tick()
        link.push(b"V OK\r\n")
        ctrl.tick()
        assert len(link.writes) == 1

        # Same value, inside the keep-alive window: no traffic.
        clock.advance(0.1)
        link.push(b"V OK\r\n")
        ctrl.tick()
        assert len(link.writes) == 1

        # Past the keep-alive window the command is refreshed, because the
        # chassis stops itself after 1.2 s of silence.
        clock.advance(0.4)
        ctrl.tick()
        assert len(link.writes) == 2


class TestZeroVector:
    def test_zero_vector_sent_as_soft_stop(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        link.writes.clear()

        ctrl.set_desired(DriveVector(60, 0, 0))
        ctrl.tick()
        link.push(b"V OK\r\n")
        ctrl.tick()

        clock.advance(0.06)
        ctrl.set_desired(DriveVector())
        ctrl.tick()

        # A released stick must ramp down, not cut PWM, so it is a vector
        # command rather than S.
        assert link.writes[-1] == b"V,0,0,0\n"
        assert ctrl.state is DriveState.READY


class TestFault:
    def test_silent_link_enters_fault(self, clock):
        link = SilentLink()
        ctrl = make(link, clock)
        ctrl.open()

        ctrl.set_desired(DriveVector(60, 0, 0))
        ctrl.tick()

        # Just before the threshold nothing has happened yet.
        clock.advance(0.8)
        ctrl.tick()
        assert ctrl.state is DriveState.DRIVING

        clock.advance(0.2)
        ctrl.tick()
        assert ctrl.state is DriveState.FAULT
        # A fault must command a hard stop.
        assert link.writes[-1] == b"S\n"

    def test_fault_blocks_further_motion(self, clock):
        link = SilentLink()
        ctrl = make(link, clock)
        ctrl.open()
        ctrl.set_desired(DriveVector(60, 0, 0))
        ctrl.tick()
        clock.advance(1.0)
        ctrl.tick()
        assert ctrl.state is DriveState.FAULT

        writes_before = len(link.writes)
        ctrl.set_desired(DriveVector(90, 0, 0))
        clock.advance(0.1)
        ctrl.tick()
        assert len(link.writes) == writes_before

    def test_clear_fault_requires_operator(self, clock):
        link = SilentLink()
        ctrl = make(link, clock)
        ctrl.open()
        ctrl.set_desired(DriveVector(60, 0, 0))
        ctrl.tick()
        clock.advance(1.0)
        ctrl.tick()
        assert ctrl.state is DriveState.FAULT

        ctrl.clear_fault()
        assert ctrl.state is DriveState.READY

    def test_board_timeout_is_a_fault(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()

        link.push(b"STOP timeout\r\n")
        ctrl.tick()

        # The board stopped itself, so commands are not arriving: the
        # operator must be told rather than shown a silent stop.
        assert ctrl.state is DriveState.FAULT
        assert ctrl.stats.timeout_count == 1

    def test_fault_recovers_on_ack(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        ctrl.set_desired(DriveVector(60, 0, 0))
        ctrl.tick()
        clock.advance(1.0)
        ctrl.tick()
        assert ctrl.state is DriveState.FAULT

        # An ack proves the link works again. This fault was caused by
        # silence, not by the operator, so it may clear itself. The stick is
        # still deflected, so the controller immediately resumes driving.
        link.push(b"V OK\r\n")
        ctrl.tick()
        assert ctrl.state is DriveState.DRIVING
        assert ctrl.stats.message == "链路已恢复"


class TestEmergencyStop:
    def test_estop_sends_stop_and_latches(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        link.writes.clear()

        ctrl.emergency_stop()
        assert link.writes[-1] == b"S\n"
        assert ctrl.state is DriveState.ESTOP

    def test_estop_blocks_motion(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        ctrl.emergency_stop()
        writes_before = len(link.writes)

        ctrl.set_desired(DriveVector(90, 0, 0))
        clock.advance(0.5)
        ctrl.tick()
        assert len(link.writes) == writes_before

    def test_estop_survives_ack(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        ctrl.emergency_stop()

        # An ack must not silently release the emergency stop.
        link.push(b"V OK\r\n")
        ctrl.tick()
        assert ctrl.state is DriveState.ESTOP

    def test_clear_estop(self, clock):
        ctrl = make(ScriptedLink(), clock)
        ctrl.open()
        ctrl.emergency_stop()
        ctrl.clear_estop()
        assert ctrl.state is DriveState.READY


class TestRoundTrip:
    def test_round_trip_measured(self, clock):
        link = ScriptedLink()
        ctrl = make(link, clock)
        ctrl.open()
        link.writes.clear()

        ctrl.set_desired(DriveVector(60, 0, 0))
        ctrl.tick()
        clock.advance(0.03)
        link.push(b"V OK\r\n")
        ctrl.tick()

        assert ctrl.stats.round_trip_ms == pytest.approx(30.0)


class TestConfigValidation:
    def test_fault_must_exceed_ack_wait(self):
        with pytest.raises(ValueError):
            ControllerConfig(ack_wait_s=1.0, fault_s=0.5)
