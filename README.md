# STM32F103C8T6 麦轮蓝牙小车

当前完整工程位于：

```text
BluetoothMotorCube/
```

该目录包含 CubeMX 工程、HAL 驱动和四轮 X 形麦轮控制代码。实现内容包括：

- 四路 20kHz PWM 独立调速
- 标准 X 形麦轮前后、横移、斜向和原地旋转
- 蓝牙单字符方向控制
- `V,forward,right,ccw` 数值矢量控制
- 四轮 PWM 配平与缓启动
- 1.2 秒无指令自动停车

详细接线、命令和调参方法见
[BluetoothMotorCube/README.md](BluetoothMotorCube/README.md)。

编译：

```powershell
cd BluetoothMotorCube
make
```

根目录的 `Makefile`、`src/` 和 `linker.ld` 是最早的裸机蓝牙/左前轮
测试版本，保留用于对照。
