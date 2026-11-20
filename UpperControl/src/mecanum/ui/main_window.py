"""Main application window and the control loop."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..core.shaper import ShapeConfig, Shaper
from ..core.state import DriveState
from ..core.stick import condition_stick
from ..core.vector import DriveVector
from ..core.wheels import predict
from ..input.source import RampAxis
from ..link.transport import PortInfo, TransportError, list_ports
from ..protocol import ResponseKind
from ..runner.controller import Controller
from .joystick import Joystick
from .rotation_slider import RotationSlider
from .theme import DANGER, OK, TEXT_DIM, WARN, hex_of
from .wheel_bars import WheelBars

TICK_MS = 16
"""UI and control tick, about 60 Hz."""

STATE_TEXT = {
    DriveState.DISCONNECTED: ("未连接", TEXT_DIM),
    DriveState.CONNECTING: ("连接中", WARN),
    DriveState.READY: ("就绪", OK),
    DriveState.DRIVING: ("行驶中", OK),
    DriveState.FAULT: ("故障", WARN),
    DriveState.ESTOP: ("急停", DANGER),
}


class MainWindow(QMainWindow):
    def __init__(self, simulate: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("麦轮小车 上位机")
        self.setMinimumSize(1020, 720)

        self._rotation_key = RampAxis(ramp_s=0.30)
        self._rotation_slider = 0.0
        self._stick = (0.0, 0.0)

        self._config = ShapeConfig()
        self._shaper = Shaper(self._config)

        self._controller: Controller | None = None
        self._simulate = simulate

        self._keys: set[int] = set()
        self._last_tick = time.monotonic()
        self._connected = False

        self._build_ui()
        self._refresh_ports()

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------- ui

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(self._build_link_panel())
        left.addWidget(self._build_drive_panel(), 1)
        layout.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(self._build_status_panel())
        right.addWidget(self._build_wheels_panel(), 1)
        right.addWidget(self._build_limits_panel())
        layout.addLayout(right, 2)

        self.setCentralWidget(central)

        bar = self.statusBar()
        self._status_label = QLabel("未连接")
        bar.addWidget(self._status_label)

    def _build_link_panel(self) -> QGroupBox:
        box = QGroupBox("连接")
        outer = QVBoxLayout(box)
        outer.setSpacing(8)

        row = QHBoxLayout()
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(280)
        row.addWidget(self._port_combo, 1)

        self._refresh_button = QPushButton("刷新")
        self._refresh_button.clicked.connect(self._refresh_ports)
        row.addWidget(self._refresh_button)
        outer.addLayout(row)

        row2 = QHBoxLayout()
        self._connect_button = QPushButton("连接")
        self._connect_button.clicked.connect(self._toggle_connection)
        row2.addWidget(self._connect_button)

        self._sim_check = QCheckBox("模拟器")
        self._sim_check.setChecked(self._simulate)
        self._sim_check.setToolTip(
            "用模拟小车代替串口，不接硬件也能调试整条控制链。"
        )
        row2.addWidget(self._sim_check)
        row2.addStretch(1)
        outer.addLayout(row2)

        return box

    def _build_drive_panel(self) -> QGroupBox:
        box = QGroupBox("驾驶")
        layout = QHBoxLayout(box)
        layout.setSpacing(16)

        self._joystick = Joystick()
        self._joystick.moved.connect(self._on_stick_moved)
        self._joystick.pressed.connect(self._on_stick_pressed)
        self._joystick.released.connect(self._on_stick_released)
        layout.addWidget(self._joystick, 1)

        side = QVBoxLayout()
        side.setSpacing(10)

        self._rotation = RotationSlider()
        self._rotation.value_changed.connect(self._on_rotation_slider)
        side.addWidget(self._rotation, 1)

        keys = QLabel("Q / E 自转")
        keys.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keys.setProperty("role", "dim")
        side.addWidget(keys)

        self._estop_button = QPushButton("急 停")
        self._estop_button.setProperty("role", "danger")
        self._estop_button.setMinimumHeight(56)
        self._estop_button.clicked.connect(self._on_estop)
        side.addWidget(self._estop_button)

        self._clear_button = QPushButton("解除")
        self._clear_button.clicked.connect(self._on_clear)
        side.addWidget(self._clear_button)

        layout.addLayout(side)
        return box

    def _build_status_panel(self) -> QGroupBox:
        box = QGroupBox("状态")
        grid = QGridLayout(box)
        grid.setSpacing(6)

        self._state_label = QLabel("未连接")
        self._state_label.setProperty("role", "heading")
        grid.addWidget(self._state_label, 0, 0, 1, 2)

        self._message_label = QLabel("")
        self._message_label.setProperty("role", "dim")
        self._message_label.setWordWrap(True)
        grid.addWidget(self._message_label, 1, 0, 1, 2)

        self._cmd_label = self._add_readout(grid, 2, "指令")
        self._rtt_label = self._add_readout(grid, 3, "往返延迟")
        self._ack_label = self._add_readout(grid, 4, "回执")
        self._tx_label = self._add_readout(grid, 5, "已发送")
        self._rx_label = self._add_readout(grid, 6, "最近回复")

        # The command readout holds three signed values, so it needs more
        # room than the counters to avoid being clipped.
        grid.setColumnMinimumWidth(1, 150)
        grid.setColumnStretch(1, 1)

        return box

    def _add_readout(self, grid: QGridLayout, row: int, name: str) -> QLabel:
        label = QLabel(name)
        label.setProperty("role", "dim")
        grid.addWidget(label, row, 0)

        value = QLabel("—")
        value.setProperty("role", "value")
        value.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(value, row, 1)
        return value

    def _build_wheels_panel(self) -> QGroupBox:
        box = QGroupBox("四轮 PWM")
        layout = QVBoxLayout(box)
        self._wheels = WheelBars()
        layout.addWidget(self._wheels)
        return box

    def _build_limits_panel(self) -> QGroupBox:
        box = QGroupBox("限速")
        grid = QGridLayout(box)
        grid.setSpacing(8)

        grid.addWidget(self._dim("平移"), 0, 0)
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(5, 100)
        self._speed_slider.setValue(int(self._config.speed_limit * 100))
        self._speed_slider.valueChanged.connect(self._on_limits_changed)
        grid.addWidget(self._speed_slider, 0, 1)
        self._speed_value = self._value_label(f"{self._speed_slider.value()}%")
        grid.addWidget(self._speed_value, 0, 2)

        grid.addWidget(self._dim("旋转"), 1, 0)
        self._rot_slider = QSlider(Qt.Orientation.Horizontal)
        self._rot_slider.setRange(5, 100)
        self._rot_slider.setValue(int(self._config.rotation_limit * 100))
        self._rot_slider.valueChanged.connect(self._on_limits_changed)
        grid.addWidget(self._rot_slider, 1, 1)
        self._rot_value = self._value_label(f"{self._rot_slider.value()}%")
        grid.addWidget(self._rot_value, 1, 2)

        grid.addWidget(self._dim("滤波"), 2, 0)
        self._tau_slider = QSlider(Qt.Orientation.Horizontal)
        self._tau_slider.setRange(0, 200)
        self._tau_slider.setValue(int(self._config.filter_tau * 1000))
        self._tau_slider.valueChanged.connect(self._on_limits_changed)
        grid.addWidget(self._tau_slider, 2, 1)
        self._tau_value = self._value_label(f"{self._tau_slider.value()} ms")
        grid.addWidget(self._tau_value, 2, 2)

        return box

    def _dim(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "dim")
        return label

    def _value_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "value")
        label.setAlignment(Qt.AlignmentFlag.AlignRight)
        label.setMinimumWidth(64)
        return label

    # ---------------------------------------------------------------- ports

    def _refresh_ports(self) -> None:
        current = self._port_combo.currentData()
        self._port_combo.clear()

        ports = list_ports()
        for info in ports:
            self._port_combo.addItem(info.label(), info)

        if not ports:
            self._port_combo.addItem("未找到串口", None)

        if current is not None:
            for index in range(self._port_combo.count()):
                data = self._port_combo.itemData(index)
                if isinstance(data, PortInfo) and data.device == current.device:
                    self._port_combo.setCurrentIndex(index)
                    break

    def select_port(self, device: str) -> None:
        """Select a port by name if it is present, for the --port flag."""
        for index in range(self._port_combo.count()):
            data = self._port_combo.itemData(index)
            if isinstance(data, PortInfo) and data.device.lower() == device.lower():
                self._port_combo.setCurrentIndex(index)
                return
        self._set_message(f"port {device} not found, click Refresh")

    def _toggle_connection(self) -> None:
        if self._connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        self._shaper.reset()
        self._rotation_key.reset()

        try:
            if self._sim_check.isChecked():
                from ..link.fake_link import FakeLink

                transport = FakeLink(ack_delay=0.025, drop_rate=0.02, seed=7)
            else:
                info = self._port_combo.currentData()
                if not isinstance(info, PortInfo):
                    self._set_message("select a serial port first")
                    return
                from ..link.serial_link import SerialLink

                transport = SerialLink(info.device)

            self._controller = Controller(transport)
            self._controller.on_response = self._on_response
            self._controller.open()
        except TransportError as exc:
            self._controller = None
            self._set_message(str(exc))
            return

        self._connected = True
        self._connect_button.setText("断开")
        self._port_combo.setEnabled(False)
        self._refresh_button.setEnabled(False)
        self._sim_check.setEnabled(False)
        self._status_label.setText("已连接")
        self.setFocus()

    def _disconnect(self) -> None:
        if self._controller is not None:
            self._controller.close()
            self._controller = None
        self._connected = False
        self._connect_button.setText("连接")
        self._port_combo.setEnabled(True)
        self._refresh_button.setEnabled(True)
        self._sim_check.setEnabled(True)
        self._status_label.setText("未连接")

        # Never leave the stick visually deflected after a disconnect.
        self._rotation_key.reset()
        self._shaper.reset()
        self._keys.clear()
        self._stick = (0.0, 0.0)
        self._joystick.reset()
        self._joystick.set_locked(True)

    # ---------------------------------------------------------------- input

    def _on_stick_pressed(self) -> None:
        pass

    def _on_stick_released(self) -> None:
        self._stick = (0.0, 0.0)

    def _on_stick_moved(self, x: float, y: float) -> None:
        # The widget already reports normalised -1..1 offsets.
        self._stick = (x, y)

    def _on_rotation_slider(self, value: float) -> None:
        self._rotation_slider = value

    def _on_limits_changed(self) -> None:
        self._config = ShapeConfig(
            deadzone=self._config.deadzone,
            filter_tau=self._tau_slider.value() / 1000.0,
            speed_limit=self._speed_slider.value() / 100.0,
            rotation_limit=self._rot_slider.value() / 100.0,
        )
        self._shaper.apply_config(self._config)
        self._joystick.set_deadzone(self._config.deadzone)
        self._speed_value.setText(f"{self._speed_slider.value()}%")
        self._rot_value.setText(f"{self._rot_slider.value()}%")
        self._tau_value.setText(f"{self._tau_slider.value()} ms")

    def _on_estop(self) -> None:
        self._stick = (0.0, 0.0)
        self._rotation_key.reset()
        self._rotation_slider = 0.0
        self._rotation.reset()
        self._joystick.reset()
        if self._controller is not None:
            self._controller.emergency_stop()

    def _on_clear(self) -> None:
        if self._controller is not None:
            self._controller.clear_estop()
            self._controller.clear_fault()
        self._joystick.set_locked(False)

    def _on_response(self, response) -> None:
        if response.kind is ResponseKind.TIMEOUT:
            # The board stopped itself, so the operator needs to know the
            # commands are not arriving rather than just seeing a stop.
            self._set_message("固件报告超时：指令没有送达")
        elif response.kind is ResponseKind.ERROR:
            self._set_message(f"固件拒绝了指令：{response.raw}")

    # ------------------------------------------------------------ key events

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return

        key = event.key()
        if key in (Qt.Key.Key_Q, Qt.Key.Key_E):
            self._keys.add(key)
            self._update_rotation_target()
            return

        if key == Qt.Key.Key_Space:
            self._on_estop()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return

        key = event.key()
        if key in (Qt.Key.Key_Q, Qt.Key.Key_E):
            self._keys.discard(key)
            self._update_rotation_target()
            return

        super().keyReleaseEvent(event)

    def _update_rotation_target(self) -> None:
        direction = 0
        if Qt.Key.Key_Q in self._keys:
            direction += 1
        if Qt.Key.Key_E in self._keys:
            direction -= 1
        self._rotation_key.hold(direction)

    def focusOutEvent(self, event) -> None:
        # Qt stops delivering key releases once focus is lost, so a held Q
        # would otherwise stay engaged forever and the chassis would keep
        # spinning in the background.
        self._keys.clear()
        self._rotation_key.reset()
        self._rotation_slider = 0.0
        self._rotation.reset()
        super().focusOutEvent(event)

    # ------------------------------------------------------------------ tick

    def _tick(self) -> None:
        now = time.monotonic()
        dt = min(now - self._last_tick, 0.1)
        self._last_tick = now

        rotation_key = self._rotation_key.update(dt)
        rotation = rotation_key if rotation_key != 0.0 else self._rotation_slider

        stick_x, stick_y = self._stick
        forward, right = condition_stick(stick_x, stick_y, self._config.deadzone)

        target = self._shaper.target(forward, right, rotation)
        command = self._shaper.smooth(target, dt)

        model = predict(command)
        self._wheels.set_values(model.wheels, model.pwm, model.normalisation_loss)
        self._joystick.set_command(command.forward, command.right, command.ccw)
        self._rotation.set_command(command.ccw)
        self._rotation.set_keyboard(rotation_key)

        if self._controller is not None:
            if self._controller.state in (DriveState.ESTOP, DriveState.FAULT):
                command = DriveVector()
            self._controller.set_desired(command)
            self._controller.tick()

        self._update_status()

    def _update_status(self) -> None:
        controller = self._controller

        if controller is None:
            text, colour = STATE_TEXT[DriveState.DISCONNECTED]
            self._state_label.setText(text)
            self._state_label.setStyleSheet(f"color: {hex_of(colour)};")
            self._cmd_label.setText("—")
            self._rtt_label.setText("—")
            self._ack_label.setText("—")
            self._tx_label.setText("—")
            self._rx_label.setText("—")
            self._joystick.set_locked(True)
            return

        stats = controller.stats
        text, colour = STATE_TEXT[stats.state]
        self._state_label.setText(text)
        self._state_label.setStyleSheet(f"color: {hex_of(colour)};")

        self._message_label.setText(stats.message)

        if stats.last_sent is None:
            self._cmd_label.setText("停止")
        else:
            vector = stats.last_sent
            self._cmd_label.setText(f"{vector.forward:+d} {vector.right:+d} {vector.ccw:+d}")

        if stats.round_trip_ms is None:
            self._rtt_label.setText("—")
        else:
            self._rtt_label.setText(f"{stats.round_trip_ms:.0f} ms")

        self._ack_label.setText(f"{stats.ack_count} / {stats.sent_count}")
        self._tx_label.setText(str(stats.sent_count))

        if stats.last_response is None:
            self._rx_label.setText("—")
        else:
            self._rx_label.setText(stats.last_response.raw[:24])

        locked = stats.state in (DriveState.ESTOP, DriveState.FAULT)
        self._joystick.set_locked(locked)

    def _set_message(self, text: str) -> None:
        self._message_label.setText(text)

    # ---------------------------------------------------------------- close

    def closeEvent(self, event: QCloseEvent) -> None:
        # Stop the chassis before the window disappears. Relying on the
        # board's timeout would leave it moving for up to 1.2 s.
        self._timer.stop()
        if self._controller is not None:
            self._controller.close()
            self._controller = None
        super().closeEvent(event)
