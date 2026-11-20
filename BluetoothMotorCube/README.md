# STM32F103 X 形四轮麦轮小车

该工程由 STM32CubeMX 生成，使用 Makefile + ARM GCC 构建。当前版本为
无编码器开环控制，支持前后、左右平移、斜向移动和原地旋转。

## 控制引脚

| 车轮 | PWM | IN1 | IN2 |
|---|---|---|---|
| 左前 M1 | PB6 / TIM4_CH1 | PB12 | PB13 |
| 左后 M2 | PB7 / TIM4_CH2 | PB14 | PB15 |
| 右前 M3 | PB8 / TIM4_CH3 | PA0 | PA1 |
| 右后 M4 | PB9 / TIM4_CH4 | PA2 | PA3 |

蓝牙串口：

```text
PA9  -> USART1_TX
PA10 -> USART1_RX
9600 8N1
```

TB6612 的 `VCC` 和 `STBY` 接 5V，`VM` 接 7.4V 电池正极。STM32、
蓝牙、两块 TB6612 和电池负极必须共地。

## X 形麦轮方向

标准 X 形布局中，左前轮和右后轮的滚子方向一致，右前轮和左后轮的
滚子方向一致。若某个轮子的方向相反，可交换该电机接到 `AO1/AO2`
或 `BO1/BO2` 的两根线，也可以在 `motors[]` 中将 `inverted` 改为 1。

以下 `+` 表示车轮上缘朝车头转动：

| 动作 | 左前 | 右前 | 左后 | 右后 |
|---|---:|---:|---:|---:|
| 前进 | + | + | + | + |
| 后退 | - | - | - | - |
| 左移 | - | + | + | - |
| 右移 | + | - | - | + |
| 左转 | - | + | - | + |
| 右转 | + | - | + | - |

## 蓝牙命令

默认速度为 35%，每条移动命令保持 1.2 秒。持续移动时可重复发送方向
命令，或发送 `K` 延长当前动作 1.2 秒。发送 `S` 可立即停车。

| 命令 | 动作 |
|---|---|
| `F` / `B` | 前进 / 后退 |
| `L` / `R` | 左移 / 右移 |
| `Q` / `E` | 原地左转 / 右转 |
| `G` / `I` | 左前斜向 / 右前斜向 |
| `H` / `J` | 左后斜向 / 右后斜向 |
| `+` / `-` | 速度增加 / 减少 10% |
| `K` | 当前动作再保持 1.2 秒 |
| `S` | 立即停车 |

完整矢量控制需要使用换行结束：

```text
V,forward,right,ccw
```

其中：

- `forward`：前进速度，范围 `-100～100`
- `right`：右移速度，范围 `-100～100`
- `ccw`：逆时针旋转速度，范围 `-100～100`

例如：

```text
V,100,0,0      前进
V,0,100,0      右移
V,0,0,100      原地左转
V,70,70,0      右前方移动
V,0,0,-60      原地右转
```

数值矢量同样受 1.2 秒无指令自动停车保护。连续遥控时应以至少 2Hz
的频率重复发送矢量命令。

## PWM 配平

四个轮子速度不一致时，可以调整 `Src/main.c` 里的修正百分比：

```c
static MotorConfig_t motors[4] =
{
  {GPIOB, GPIO_PIN_12, GPIOB, GPIO_PIN_13, TIM_CHANNEL_1, 100, 0, 0},
  {GPIOB, GPIO_PIN_14, GPIOB, GPIO_PIN_15, TIM_CHANNEL_2, 100, 0, 0},
  {GPIOA, GPIO_PIN_0,  GPIOA, GPIO_PIN_1,  TIM_CHANNEL_3, 100, 0, 0},
  {GPIOA, GPIO_PIN_2,  GPIOA, GPIO_PIN_3,  TIM_CHANNEL_4, 100, 0, 0}
};
```

第五个参数是 `trim_percent`，例如偏慢的轮子可提高到 `105`，偏快的
轮子可降低到 `95`。每次调整 2%～5%，然后在平地上测试直线和横移。

## 编译

```powershell
make
```

输出：

```text
build/BluetoothMotorCube.elf
build/BluetoothMotorCube.hex
build/BluetoothMotorCube.bin
```
