# STM32F103C8T6 麦轮小车

当前固件用于测试左前轮电机和 TB6612FNG A 路驱动，轮子必须悬空。

## 蓝牙串口

| 蓝牙模块 | STM32F103C8T6 |
|---|---|
| VCC | 5V |
| GND | GND |
| TXD | PA10 / USART1_RX |
| RXD | PA9 / USART1_TX |

蓝牙串口参数：

```text
9600 8N1
```

## TB6612 左前轮接线

| TB6612 引脚 | 连接 |
|---|---|
| PWMA | PB6 / TIM4_CH1 |
| AIN1 | PB12 |
| AIN2 | PB13 |
| STBY | 3.3V |
| VCC | 3.3V |
| GND | STM32 GND、电池负极 |
| VM | 7.4V 电池正极 |
| AO1 | 左前电机一根线 |
| AO2 | 左前电机另一根线 |

`AO1/AO2` 的电机线方向可以交换。若正转和反转与预期相反，只需交换
这两根线，或者在固件中交换 `AIN1/AIN2`。

建议在 `VM` 和 `GND` 之间并联 1000uF 电解电容，注意正负极。STM32、
蓝牙、TB6612 和电池负极必须共地。禁止把 7.4V 接到 `VCC`。

## 蓝牙测试命令

手机发送单个字符，不需要加换行：

| 命令 | 动作 |
|---|---|
| `F` | 左前轮 25% 占空比正转 1.5 秒 |
| `B` | 左前轮 25% 占空比反转 1.5 秒 |
| `S` | 立即停止 |

每次启动均自动发送命令说明。测试期间轮子必须悬空，电机线要固定，
防止旋转时甩出。

## 编译

```powershell
make
```

生成：

- `build/left_front_motor_test.hex`
- `build/left_front_motor_test.bin`
- `build/left_front_motor_test.elf`

串口下载使用 `.hex` 文件。烧录前断开蓝牙模块的 TXD/RXD，连接 CH340：

```text
CH340 TXD -> PA10
CH340 RXD -> PA9
CH340 GND -> GND
```

设置 `BOOT0=1、BOOT1=0`，复位后烧录；烧录完成设置
`BOOT0=0、BOOT1=0`，复位运行。
