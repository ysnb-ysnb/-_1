"""Render a screenshot of the window with the simulator driving.

Runs on the normal Windows platform plugin rather than ``offscreen``,
because the offscreen plugin does not load system fonts on Windows and
every glyph comes out as a box.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication  # noqa: E402

from mecanum.ui.main_window import MainWindow  # noqa: E402
from mecanum.ui.theme import apply_theme  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv[:1])
    apply_theme(app)

    window = MainWindow(simulate=True)
    window.resize(1120, 800)
    window.show()

    window._sim_check.setChecked(True)
    window._connect()

    # Drive diagonally with rotation so the readouts are populated.
    window._on_stick_moved(-0.55, -0.62)
    window._rotation_slider = 0.45
    for _ in range(45):
        window._tick()

    app.processEvents()

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_preview.png")
    window.grab().save(out)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
