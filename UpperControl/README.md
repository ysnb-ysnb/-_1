# PC 上位机（PySide6）

STM32 X 形麦轮小车的电脑端上位机。一个虚拟摇杆负责平面 360° 平移，
键盘 Q/E 负责原地自转，两者可同时操作，因此能演示麦轮独有的
「边横移边自转」。

## 环境

Python 3.13（PySide6 对 3.14 的 wheel 尚未跟上）。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果激活脚本被策略拦截：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 运行

```powershell
.\run.bat
```

或手动：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m mecanum
```

无硬件时先跑模拟器，把控制链和界面调通：

```powershell
.\run.bat --simulate
```

指定串口：

```powershell
.\run.bat --port COM7
```

## 首次连接

JDY-31 是蓝牙 3.0 SPP 模块，配对后 Windows 会自动创建虚拟串口。

1. 车上电，系统设置里配对 `JDY-31`，PIN 通常是 `1234` 或 `0000`
2. 点界面的 **刷新**，列表里带「蓝牙」标记的是蓝牙口
3. **配对会产生两个 COM 口，只有出站那个能用**。连不上就换另一个试
4. 点 **连接**。连接后会自动发一次 `S`，确保小车静止

链路是否通，看状态区：出现「最近回复：MECANUM X READY」或者
「往返延迟」有数值，就说明双向通信正常。

## 操作

| 操作 | 作用 |
|---|---|
| 鼠标在摇杆区拖拽 | 平面平移，360° 任意方向 |
| `Q` / `E` | 逆时针 / 顺时针自转（300 ms 斜坡） |
| 右侧滑块 | 备用旋转输入，松手自动回中 |
| `Space` | 急停 |
| 摇杆与 Q/E 互不影响 | 可同时使用 |

窗口失去焦点时 Q/E 会自动归零，避免切窗口后小车一直转。

## 界面读数

**四轮 PWM（预测）** 显示的是固件真正会输出的 PWM，由与 `main.c` 相同的
整数运算算出，包括向零截断。三处细节值得注意：

- 黄色条表示该轮正被固件的 `PWM_MIN_RUN` 地板抬升，此时再减小指令也不会更慢
- 红色条表示该轮已接近满占空比
- 「归一化损失」出现时，说明旋转正在吃掉平移速度，这是合成运动的固有代价

## 控制链

```
摇杆/键盘 → 死区 8% → 单位圆限制 → 限速 → PWM 地板重映射 → 一阶滤波 → V 命令
```

`PWM 地板重映射` 是这套界面的关键：固件会把任何非零且低于
`PWM_MIN_RUN` 的 PWM 抬到 60，导致轮值 1~15 全是同一个速度。直接线性
映射会出现「前段推杆不动、然后突然窜出」，所以输出下限直接顶到轮值 16。

## 安全策略

| 场景 | 行为 |
|---|---|
| 连接成功 | 立即发 `S` |
| 摇杆回中 | 发 `V,0,0,0`，按斜坡滑停（不是硬切） |
| 900 ms 无 `V OK` | 进入 FAULT，发 `S`，锁住摇杆 |
| 急停 / 关闭窗口 / 断链 | 立即发 `S` |
| 固件兜底 | 1.2 s 无指令自动停车 |

发送采用 ack 门控：收到上一条 `V OK` 才发下一条，避免指令在蓝牙栈里
堆积导致越推越延迟。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

覆盖死区与单位圆、地板重映射边界、C 截断除法、四轮逆解（对齐
`BluetoothMotorCube/README.md` 的方向表）、ack 门控、看门狗降级，
以及界面的离屏冒烟测试。

生成界面预览图：

```powershell
$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe tools\preview.py
```

## 代码结构

```
src/mecanum/
├── core/          纯逻辑，零 I/O：矢量、摇杆、整形、四轮解算
├── protocol/      编解码与行解析
├── link/          串口、模拟链路、端口枚举
├── runner/        ack 门控、看门狗、状态机
├── input/         旋转斜坡
└── ui/            PySide6 界面
```
