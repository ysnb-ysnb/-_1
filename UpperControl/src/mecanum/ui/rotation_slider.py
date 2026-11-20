"""Rotation control: a spring-return slider with keyboard indicator.

The slider is the备用 (fallback) input for rotation. The primary path is
Q/E, because a single mouse cannot drag the stick and the slider at the
same time, and simultaneous translation and rotation is exactly the
capability worth demonstrating on a mecanum chassis.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .theme import ACCENT, BORDER, OK, PANEL_ALT, TEXT, TEXT_DIM, WARN, mono_font, ui_font


class RotationSlider(QWidget):
    """Vertical slider, +up (counter-clockwise), spring-return to centre."""

    value_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._value = 0.0
        self._dragging = False
        self._keyboard = 0.0
        self._command = 0
        self.setMinimumSize(96, 240)
        self.setCursor(Qt.CursorShape.SizeVerCursor)

    # ---------------------------------------------------------------- state

    def set_keyboard(self, value: float) -> None:
        """Reflect the Q/E ramp so the operator sees what is commanded."""
        self._keyboard = max(-1.0, min(1.0, value))
        self.update()

    def set_command(self, ccw: int) -> None:
        self._command = ccw
        self.update()

    def value(self) -> float:
        """Effective rotation input, keyboard taking precedence."""
        return self._keyboard if self._keyboard != 0.0 else self._value

    def reset(self) -> None:
        self._value = 0.0
        self._keyboard = 0.0
        self._dragging = False
        self.update()
        self.value_changed.emit(0.0)

    # ---------------------------------------------------------------- events

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() is not Qt.MouseButton.LeftButton:
            return
        self._dragging = True
        self._update_from_y(event.position().y())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._update_from_y(event.position().y())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() is not Qt.MouseButton.LeftButton:
            return
        self._dragging = False
        # Spring return: releasing must produce an immediate stop, never a
        # chassis that keeps spinning because the slider stayed deflected.
        self._value = 0.0
        self.update()
        self.value_changed.emit(0.0)

    def _update_from_y(self, y: float) -> None:
        span = self._span()
        centre = self.height() / 2.0
        value = (centre - y) / span
        self._value = max(-1.0, min(1.0, value))
        self.update()
        self.value_changed.emit(self._value)

    def _span(self) -> float:
        # Reserve room for the CCW/CW captions and the numeric readout, so
        # the track never overlaps its own labels.
        return max(self.height() / 2.0 - 52.0, 20.0)

    # --------------------------------------------------------------- drawing

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        centre_x = self.width() / 2.0
        centre_y = self.height() / 2.0
        span = self._span()

        track = QRectF(centre_x - 5, centre_y - span, 10, span * 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BORDER)
        painter.drawRoundedRect(track, 5, 5)

        # Centre tick.
        painter.setPen(QPen(TEXT_DIM, 1, Qt.PenStyle.DashLine))
        painter.drawLine(
            int(centre_x - 18), int(centre_y), int(centre_x + 18), int(centre_y)
        )

        active = self.value()
        colour = OK if active > 0 else (WARN if active < 0 else PANEL_ALT)

        if active != 0.0:
            fill = QRectF(
                centre_x - 5,
                centre_y - span * active if active > 0 else centre_y,
                10,
                abs(span * active),
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawRoundedRect(fill, 5, 5)

        # Handle.
        handle_y = centre_y - span * active
        painter.setPen(QPen(TEXT, 1.5))
        painter.setBrush(colour if active != 0.0 else PANEL_ALT)
        painter.drawRoundedRect(
            QRectF(centre_x - 20, handle_y - 9, 40, 18), 5, 5
        )

        # Labels, placed at the true extents so they do not drift as the
        # widget is resized.
        painter.setPen(QPen(TEXT_DIM))
        painter.setFont(ui_font(8))
        painter.drawText(
            QRectF(0, centre_y - span - 24, self.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            "逆时针",
        )
        painter.drawText(
            QRectF(0, centre_y + span + 6, self.width(), 18),
            Qt.AlignmentFlag.AlignCenter,
            "顺时针",
        )

        painter.setPen(QPen(TEXT if self._command else TEXT_DIM))
        painter.setFont(mono_font(11))
        painter.drawText(
            QRectF(0, self.height() - 26, self.width(), 22),
            Qt.AlignmentFlag.AlignCenter,
            f"{self._command:+d}",
        )
