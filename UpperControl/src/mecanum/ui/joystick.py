"""Click-and-drag virtual joystick.

The pointer offset from the press point is the stick position, clamped to a
radius, rather than an absolute position inside a pad. That relative mode
gives finer control: the operator can keep pushing past the edge by
lifting and pressing again, which absolute pads cannot do.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from .theme import ACCENT, BORDER, DANGER, PANEL, PANEL_ALT, TEXT, TEXT_DIM


class Joystick(QWidget):
    """Circular stick emitting normalised (x, y) with +y downward."""

    moved = Signal(float, float)
    pressed = Signal()
    released = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._origin: QPointF | None = None
        self._current = QPointF(0.0, 0.0)
        self._vector = (0.0, 0.0)
        self._deadzone = 0.08
        self._command = (0, 0, 0)
        self._locked = False

        self.setMinimumSize(280, 280)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ---------------------------------------------------------------- state

    def set_deadzone(self, value: float) -> None:
        self._deadzone = value
        self.update()

    def set_command(self, forward: int, right: int, ccw: int) -> None:
        """Show the command currently being transmitted."""
        self._command = (forward, right, ccw)
        self.update()

    def set_locked(self, locked: bool) -> None:
        """Disable input and show the locked state."""
        self._locked = locked
        if locked:
            self.reset()
        self.setCursor(
            Qt.CursorShape.ForbiddenCursor if locked else Qt.CursorShape.CrossCursor
        )
        self.update()

    def reset(self) -> None:
        self._origin = None
        self._current = QPointF(0.0, 0.0)
        self._vector = (0.0, 0.0)
        self.update()
        self.moved.emit(0.0, 0.0)

    @property
    def vector(self) -> tuple[float, float]:
        return self._vector

    # ---------------------------------------------------------------- events

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._locked or event.button() is not Qt.MouseButton.LeftButton:
            return
        self._origin = event.position()
        self._current = QPointF(0.0, 0.0)
        self._vector = (0.0, 0.0)
        self.pressed.emit()
        self.moved.emit(0.0, 0.0)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._origin is None or self._locked:
            return

        delta = event.position() - self._origin
        radius = self._radius()

        # Clamp to the disc so a diagonal push cannot exceed unit length.
        distance = math.hypot(delta.x(), delta.y())
        if distance > radius:
            scale = radius / distance
            delta = QPointF(delta.x() * scale, delta.y() * scale)

        self._current = delta
        self._vector = (delta.x() / radius, delta.y() / radius)
        self.moved.emit(*self._vector)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() is not Qt.MouseButton.LeftButton:
            return
        if self._origin is None:
            return
        self._origin = None
        self._current = QPointF(0.0, 0.0)
        self._vector = (0.0, 0.0)
        self.released.emit()
        self.moved.emit(0.0, 0.0)
        self.update()

    def leaveEvent(self, event) -> None:
        # Do not drop the press on leave: dragging outside the widget is
        # normal and cancelling it would make fine control impossible.
        super().leaveEvent(event)

    # --------------------------------------------------------------- drawing

    def _centre(self) -> QPointF:
        return QPointF(self.width() / 2.0, self.height() / 2.0)

    def _radius(self) -> float:
        return min(self.width(), self.height()) / 2.0 - 26.0

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        centre = self._centre()
        radius = self._radius()

        # Base disc.
        gradient = QRadialGradient(centre, radius)
        gradient.setColorAt(0.0, PANEL_ALT)
        gradient.setColorAt(1.0, PANEL)
        painter.setBrush(gradient)
        painter.setPen(QPen(BORDER, 1.5))
        painter.drawEllipse(centre, radius, radius)

        # Deadzone ring.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(BORDER.lighter(135), 1, Qt.PenStyle.DashLine))
        inner = radius * self._deadzone
        painter.drawEllipse(centre, inner, inner)

        # Cross-hair and direction labels.
        painter.setPen(QPen(BORDER.lighter(120), 1))
        painter.drawLine(
            QPointF(centre.x() - radius, centre.y()),
            QPointF(centre.x() + radius, centre.y()),
        )
        painter.drawLine(
            QPointF(centre.x(), centre.y() - radius),
            QPointF(centre.x(), centre.y() + radius),
        )

        painter.setPen(QPen(TEXT_DIM))
        painter.setFont(QFont("Segoe UI", 8))
        self._draw_label(painter, centre, radius, "FWD", -90)
        self._draw_label(painter, centre, radius, "BACK", 90)
        self._draw_label(painter, centre, radius, "LEFT", 180)
        self._draw_label(painter, centre, radius, "RIGHT", 0)

        # Command vector, which may differ from the pointer once shaping and
        # filtering are applied.
        fwd, right, _ccw = self._command
        magnitude = math.hypot(fwd, right)
        if magnitude > 0.0:
            scale = min(magnitude / 100.0, 1.0) * radius
            angle = math.atan2(-fwd, right)
            tip = QPointF(
                centre.x() + math.cos(angle) * scale,
                centre.y() - math.sin(angle) * scale,
            )
            painter.setPen(QPen(ACCENT, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(centre, tip)

        # Knob.
        knob = QPointF(centre.x() + self._current.x(), centre.y() + self._current.y())
        active = self._origin is not None
        knob_colour = DANGER if self._locked else (ACCENT if active else TEXT_DIM)
        painter.setPen(QPen(knob_colour, 2))
        painter.setBrush(knob_colour.darker(180))
        painter.drawEllipse(knob, 17, 17)

        # Hint text.
        painter.setPen(QPen(TEXT_DIM))
        painter.setFont(QFont("Segoe UI", 8))
        hint = "LOCKED" if self._locked else "drag to drive"
        painter.drawText(
            QRectF(0, self.height() - 22, self.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            hint,
        )

    def _draw_label(
        self,
        painter: QPainter,
        centre: QPointF,
        radius: float,
        text: str,
        degrees: float,
    ) -> None:
        angle = math.radians(degrees)
        point = QPointF(
            centre.x() + math.cos(angle) * (radius - 12),
            centre.y() + math.sin(angle) * (radius - 12),
        )
        painter.drawText(
            QRectF(point.x() - 26, point.y() - 8, 52, 16),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )
