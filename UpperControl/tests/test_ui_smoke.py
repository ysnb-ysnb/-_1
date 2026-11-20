"""Offscreen smoke test: build the window, simulate driving, no crashes.

Qt is exercised with the offscreen platform plugin so this runs in CI and
on a headless machine.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp):
    from mecanum.ui.main_window import MainWindow
    from mecanum.ui.theme import apply_theme

    apply_theme(qapp)
    win = MainWindow(simulate=True)
    win.show()
    yield win
    win.close()


def test_window_builds(window):
    assert window.windowTitle() == "Mecanum Upper Control"
    assert window._joystick is not None
    assert window._wheels is not None


def test_connect_simulator(window):
    window._sim_check.setChecked(True)
    window._connect()
    assert window._connected
    assert window._controller is not None
    assert window._controller.state.name == "READY"


def test_tick_without_connection_is_safe(window):
    # Must not raise even though nothing is connected.
    for _ in range(10):
        window._tick()


def test_command_flows_to_controller(window):
    window._connect()
    window._on_stick_moved(0.0, -1.0)  # push up
    for _ in range(30):
        window._tick()
    assert window._controller.stats.last_sent is not None
    assert window._controller.stats.last_sent.forward > 0


def test_estop_locks_stick(window):
    window._connect()
    window._on_estop()
    assert window._controller.state.name == "ESTOP"
    window._on_stick_moved(0.0, -1.0)
    window._tick()
    # Emergency stop must ignore stick input entirely.
    assert window._controller.state.name == "ESTOP"


def test_clear_estop_unlocks(window):
    window._connect()
    window._on_estop()
    window._on_clear()
    assert window._controller.state.name == "READY"


def test_disconnect_sends_stop(window):
    window._connect()
    controller = window._controller
    window._on_stick_moved(0.0, -1.0)
    for _ in range(20):
        window._tick()
    link = controller._transport
    window._disconnect()
    assert b"S\n" in link.writes


def test_state_colour_is_a_valid_stylesheet_literal():
    # Interpolating a QColor into a stylesheet silently breaks every
    # subsequent style rule, so colours must go through hex_of.
    from mecanum.core.state import DriveState
    from mecanum.ui.main_window import STATE_TEXT
    from mecanum.ui.theme import hex_of

    for state in DriveState:
        _text, colour = STATE_TEXT[state]
        literal = hex_of(colour)
        assert literal.startswith("#")
        assert len(literal) == 7


def test_status_updates_emit_no_stylesheet_warnings(qapp, window, capsys):
    window._connect()
    for _ in range(5):
        window._tick()
    window._disconnect()
    window._tick()
    captured = capsys.readouterr()
    assert "Could not parse stylesheet" not in captured.err
