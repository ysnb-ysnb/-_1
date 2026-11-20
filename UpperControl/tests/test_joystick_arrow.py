"""Direction tests for the on-screen command arrow.

The arrow previously pointed the wrong way for every direction while the
chassis itself drove correctly, because the angle was negated twice. These
tests pin the mapping so it cannot regress.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF

from mecanum.ui.joystick import command_tip

CENTRE = QPointF(100.0, 100.0)
RADIUS = 80.0


def test_stopped_has_no_arrow():
    assert command_tip(CENTRE, RADIUS, 0, 0) is None


def test_forward_points_up():
    # Screen y grows downward, so driving forward must move the tip up.
    tip = command_tip(CENTRE, RADIUS, 100, 0)
    assert tip.x() == pytest.approx(CENTRE.x())
    assert tip.y() < CENTRE.y()


def test_backward_points_down():
    tip = command_tip(CENTRE, RADIUS, -100, 0)
    assert tip.y() > CENTRE.y()


def test_right_points_right():
    tip = command_tip(CENTRE, RADIUS, 0, 100)
    assert tip.x() > CENTRE.x()
    assert tip.y() == pytest.approx(CENTRE.y())


def test_left_points_left():
    tip = command_tip(CENTRE, RADIUS, 0, -100)
    assert tip.x() < CENTRE.x()


def test_diagonal_forward_right_points_up_and_right():
    # This is the case in the bug report: pushing up and to the right.
    tip = command_tip(CENTRE, RADIUS, 71, 71)
    assert tip.x() > CENTRE.x()
    assert tip.y() < CENTRE.y()


def test_length_scales_with_magnitude():
    small = command_tip(CENTRE, RADIUS, 30, 0)
    large = command_tip(CENTRE, RADIUS, 90, 0)
    assert small is not None and large is not None
    small_length = CENTRE.y() - small.y()
    large_length = CENTRE.y() - large.y()
    assert large_length > small_length


def test_length_clamped_to_radius():
    tip = command_tip(CENTRE, RADIUS, 100, 100)
    assert tip is not None
    distance = ((tip.x() - CENTRE.x()) ** 2 + (tip.y() - CENTRE.y()) ** 2) ** 0.5
    assert distance == pytest.approx(RADIUS)


def test_full_stick_reaches_radius():
    tip = command_tip(CENTRE, RADIUS, 100, 0)
    assert tip is not None
    assert CENTRE.y() - tip.y() == pytest.approx(RADIUS)
