"""Four-wheel PWM readout.

This shows the value each wheel is actually about to receive, computed by
the same integer arithmetic as the firmware. Two things become visible
here that are otherwise only discovered on the floor: the 15 % floor the
firmware enforces, and the translational speed lost when rotation is
combined with translation.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget

from .theme import ACCENT, BORDER, DANGER, OK, PANEL_ALT, TEXT, TEXT_DIM, WARN, mono_font, ui_font

PWM_MAX = 399
PWM_FLOOR = 60

NAMES = ("FL", "FR", "RL", "RR")


class WheelBars(QWidget):
    """Horizontal bars showing predicted PWM per wheel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pwm = (0, 0, 0, 0)
        self._wheels = (0, 0, 0, 0)
        self._loss = 0.0
        self.setMinimumHeight(132)

    def set_values(
        self,
        wheels: tuple[int, int, int, int],
        pwm: tuple[int, int, int, int],
        loss: float = 0.0,
    ) -> None:
        self._wheels = wheels
        self._pwm = pwm
        self._loss = loss
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        label_width = 34
        value_width = 42
        bar_left = label_width + 6
        bar_right = self.width() - value_width - 6
        bar_width = max(bar_right - bar_left, 10)

        # Rows fill the available height so the panel does not end up as a
        # small readout stranded above a block of empty space.
        has_loss = self._loss > 0.001
        bottom_margin = 22 if has_loss else 6
        usable = max(self.height() - bottom_margin, 40.0)
        gap = 6.0
        row_height = max((usable - gap * 3) / 4.0, 16.0)

        for index, name in enumerate(NAMES):
            top = index * (row_height + gap)
            pwm = self._pwm[index]

            painter.setPen(QPen(TEXT_DIM))
            painter.setFont(mono_font(9))
            painter.drawText(
                QRectF(0, top, label_width, row_height),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                name,
            )

            track = QRectF(bar_left, top + 4, bar_width, row_height - 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(PANEL_ALT)
            painter.drawRoundedRect(track, 4, 4)

            # Centre line, so direction is readable at a glance.
            centre = bar_left + bar_width / 2.0
            painter.setPen(QPen(BORDER.lighter(125), 1))
            painter.drawLine(
                int(centre), int(top + 3), int(centre), int(top + row_height - 3)
            )

            if pwm != 0:
                fraction = min(abs(pwm) / PWM_MAX, 1.0)
                length = (bar_width / 2.0) * fraction
                if pwm > 0:
                    bar = QRectF(centre, top + 4, length, row_height - 8)
                else:
                    bar = QRectF(centre - length, top + 4, length, row_height - 8)

                # Colour encodes whether the firmware floor is in effect,
                # which is the most confusing part of tuning this chassis:
                # below the floor every request is the same speed.
                if abs(pwm) <= PWM_FLOOR:
                    colour = WARN
                elif abs(pwm) >= PWM_MAX * 0.95:
                    colour = DANGER
                else:
                    colour = OK if pwm > 0 else ACCENT

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(colour)
                painter.drawRoundedRect(bar, 4, 4)

            painter.setPen(QPen(TEXT))
            painter.setFont(mono_font(9))
            painter.drawText(
                QRectF(self.width() - value_width, top, value_width, row_height),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                f"{pwm:+d}",
            )

        if has_loss:
            painter.setPen(QPen(WARN))
            painter.setFont(ui_font(8))
            painter.drawText(
                QRectF(0, self.height() - 18, self.width(), 16),
                Qt.AlignmentFlag.AlignLeft,
                f"归一化损失 {self._loss * 100:.0f}%",
            )
