"""Application entry point."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mecanum",
        description="Upper control for the STM32 mecanum chassis.",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="drive a simulated chassis instead of a serial port",
    )
    parser.add_argument(
        "--port",
        metavar="COMx",
        help="serial port to preselect, for example COM7",
    )
    args = parser.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Mecanum Upper Control")
    apply_theme(app)

    window = MainWindow(simulate=args.simulate)
    if args.port:
        window.select_port(args.port)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
