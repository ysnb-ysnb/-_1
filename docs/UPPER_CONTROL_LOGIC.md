# 二维摇杆上位机控制逻辑

## 1. 控制目标

上位机通过二维摇杆控制麦轮小车在平面内运动：

- 摇杆上下：前进、后退
- 摇杆左右：左移、右移
- 旋转滑块或手柄右摇杆：原地左转、右转
- 松开摇杆：立即停车

二维摇杆只能提供两个平移自由度，原地旋转还需要一个独立输入。

## 2. 坐标和数值约定

车体坐标系：

- `forward`：向车头为正，向车尾为负
- `right`：向车右为正，向车左为负
- `ccw`：从上往下看，逆时针为正，顺时针为负

所有控制量范围为：

```text
-100 ～ +100
```

上位机屏幕坐标通常向下为 Y 正方向，因此摇杆向上时需要转换：

```text
right   = joystick_x
forward = -joystick_y
```

## 3. 输入处理

### 3.1 死区

建议摇杆中心设置 8% 死区：

```text
abs(x) < 0.08 → x = 0
abs(y) < 0.08 → y = 0
```

### 3.2 圆形范围归一化

二维摇杆应限制在单位圆内，不能让斜向输入超过最大范围：

```text
radius = sqrt(x² + y²)

if radius > 1:
    x = x / radius
    y = y / radius
```

### 3.3 平滑滤波

建议使用一阶低通滤波，减少摇杆抖动和电机冲击：

```text
filtered = 0.70 * previous + 0.30 * current
```

以 20Hz 发送时，这个系数大约对应 100～200ms 的响应时间。

### 3.4 速度限制

上位机提供速度上限滑块，默认 60%：

```text
forward_cmd = round(forward * speed_limit)
right_cmd   = round(right   * speed_limit)
rotation_cmd = round(rotation * rotation_limit)
```

建议初始测试速度不超过 50%。

## 4. 蓝牙协议

### 4.1 连续矢量命令

正常控制时，每 50ms 发送一次：

```text
V,forward,right,ccw\n
```

示例：

```text
V,60,0,0
V,0,60,0
V,0,0,60
V,45,45,0
V,-40,0,-30
```

接收端必须收到换行符后，才执行一条完整矢量命令。

### 4.2 停车命令

按场景区分使用：

```text
摇杆回中          V,0,0,0\n   软停，按斜坡减速
急停 / 断链 / 退出 S\n         硬停，立即切断 PWM
```

不应该只依赖 STM32 的自动超时停车。

### 4.3 通信超时

当前 STM32 固件设置为 1.2 秒无有效运动指令后自动停车。上位机建议采用双
保险：

- 持续控制时每 50ms 发送一次
- 连续 200ms 没有收到 `V OK`，上位机立即发送 `S`
- 1.2 秒内没有新命令，STM32 自动停车

### 4.4 速度缩放已移除

旧固件在 `set_motion()` 内把所有分量再乘一次内部 `speed_percent`
（默认 35%），导致上位机的速度滑块失效。该缩放已经删除：

```text
V 命令值直接作为最终归一化目标
STM32 只负责限幅、四轮归一化、PWM 配平和安全保护
```

所以上位机发送 `V,100,0,0` 明确表示请求 100% 前进；限速只由上位机
的速度滑块负责。

### 4.5 软停与硬停

固件区分两种停车：

```text
V,0,0,0   软停：目标归零，按斜坡减速，摇杆回中使用
S         硬停：立即切断 PWM，急停和断链使用
```

上位机摇杆回中时发送 `V,0,0,0` 即可，不要发送 `S`，否则每次松杆都会
硬切 PWM，齿轮箱冲击明显。

## 5. STM32 运动学

四轮顺序固定为：

```text
FL = 左前
FR = 右前
RL = 左后
RR = 右后
```

标准 X 形麦轮：

```text
FL = forward + right - ccw
FR = forward - right + ccw
RL = forward - right - ccw
RR = forward + right + ccw
```

结果归一化：

```text
max_wheel = max(abs(FL), abs(FR), abs(RL), abs(RR))

if max_wheel > 100:
    FL = FL * 100 / max_wheel
    FR = FR * 100 / max_wheel
    RL = RL * 100 / max_wheel
    RR = RR * 100 / max_wheel
```

之后依次执行：

1. 每轮 PWM 配平系数
2. 限幅到 `-100～100`
3. 换算到 `PWM 0～399`
4. 最小启动 PWM
5. PWM 斜坡缓启动
6. 正反向切换强制经过零速度

## 6. 上位机状态机

```text
DISCONNECTED
    ↓ 选择串口并连接
CONNECTING
    ↓ 串口打开成功
READY
    ↓ 摇杆或旋转输入超过死区
DRIVING
    ↓ 摇杆回中或松开
READY

任意状态 → ESTOP → READY
串口断开 → DISCONNECTED
```

状态规则：

- `DISCONNECTED`：禁用摇杆和发送。
- `CONNECTING`：禁止发送运动指令。
- `READY`：连接后先发送 `S`，确认小车停止。
- `DRIVING`：每 50ms 发送一次矢量。
- 摇杆回中：发送一次 `S`，不要继续发送大量零矢量。
- `ESTOP`：立即发送 `S`，直到用户主动解除急停。

## 7. 上位机界面

建议界面包含：

| 区域 | 功能 |
|---|---|
| 串口区 | COM 口选择、刷新、连接、断开 |
| 摇杆区 | 圆形二维虚拟摇杆 |
| 旋转区 | 滑块、旋钮或第二摇杆 |
| 速度区 | 最大平移速度和最大旋转速度 |
| 状态区 | 最近命令、连接状态、超时和错误 |
| 安全区 | 急停按钮、解除急停 |

连接成功后建议自动发送一次：

```text
S
```

## 8. 发送伪代码

```text
if not connected or emergency_stop:
    return

x = read_joystick_x()
y = read_joystick_y()
r = read_rotation_axis()

apply_deadzone(x, y, r)
normalize_to_unit_circle(x, y)
filter(x, y, r)

forward = round(y * -1 * speed_limit)
right = round(x * speed_limit)
ccw = round(r * rotation_limit)

if abs(forward) <= 1 and abs(right) <= 1 and abs(ccw) <= 1:
    send_once("V,0,0,0\n")        # soft stop: ramp coasts down
else:
    send_every_50ms("V,%d,%d,%d\n", forward, right, ccw)
```

只有急停、断链和退出时才发送 `S\n`。

## 9. 验收测试

轮子悬空时依次测试：

1. `V,60,0,0`：四轮上缘朝车头转。
2. `V,-60,0,0`：四轮上缘朝车尾转。
3. `V,0,-60,0`：左前、右后反转，右前、左后正转。
4. `V,0,60,0`：左前、右后正转，右前、左后反转。
5. `V,0,0,60`：左侧两轮反转，右侧两轮正转。
6. `V,0,0,-60`：左侧两轮正转，右侧两轮反转。
7. `V,0,0,0`：四轮按斜坡平滑减速到零。
8. 发送 `S`：四轮立即断电停转。
9. 关闭上位机或断开蓝牙：小车最迟 1.2 秒停车。

完成悬空测试后，再落地以不超过 35% 的速度测试直线和横移。
