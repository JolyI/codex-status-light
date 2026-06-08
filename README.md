# Codex Status Light

一个给 Codex Desktop 用的实体状态灯，基于 ESP32-C3。它会读取 macOS 上 Codex Desktop 的运行状态，然后通过 USB 串口同步到外接灯。

<img src="assets/status-light.png" alt="Codex 状态灯实物图" width="360">

当前支持两种硬件形态：

| 版本 | 硬件 | 适合场景 |
| --- | --- | --- |
| V1 | 红/黄/绿三色交通灯模块 | 最简单、最直观 |
| V2 | WS2812B 5V 可编程灯条 | 更适合桌面氛围和跑马灯效果 |

## 状态含义

监听器只对外输出三个可见状态：

```text
idle       空闲，可以继续发任务
busy       Codex 正在工作
attention 需要你处理，比如确认、授权、输入、登录或失败阻塞
```

交通灯版本的默认表现：

```text
idle       绿灯常亮
busy       黄灯常亮
attention  红灯慢闪
```

WS2812B 灯条版本的默认表现：

```text
idle       青绿色慢呼吸
busy       青白头 + 青蓝紫品红渐变尾巴的 comet 跑马灯
attention  琥珀色双脉冲
```

## 硬件

通用必需：

- ESP32-C3 开发板
- 支持数据传输的 USB-C 数据线
- 2.54mm 杜邦线
- Arduino CLI

交通灯版本还需要：

- 红/黄/绿交通灯 LED 模块，常见引脚为 `GND`、`R`、`Y`、`G`

WS2812B 灯条版本还需要：

- WS2812B 5V 灯条
- 5V 外部电源，30 颗低亮度测试时 5V 1A 通常够用，余量更大可用 5V 2A
- 330Ω 到 470Ω 电阻，串在 ESP32-C3 到灯条的 Data 线上
- 热缩管、端子或焊接，用来固定线材

推荐准备：

- 万用表，用来检查通断、极性和共地
- 剥线钳、剪线钳、电烙铁

## 接线

### V1 交通灯

```text
交通灯 GND -> ESP32-C3 GND
交通灯 R   -> ESP32-C3 GPIO3
交通灯 Y   -> ESP32-C3 GPIO4
交通灯 G   -> ESP32-C3 GPIO5
```

如果交通灯模块只有 `GND`、`R`、`Y`、`G`，不要额外连接 ESP32 的 `5V` 或 `3.3V`。只有模块明确带 `VCC` 并且说明书要求供电时，才需要接电源脚。

### V2 WS2812B 灯条

当前固件默认：

```text
LED 数量  30
Data 引脚 ESP32-C3 GPIO3
供电      外部 5V
```

接线方式：

```text
外部 5V 电源正极 -> 灯条 5V / 红线
外部 5V 电源负极 -> 灯条 GND / 粗黑线

ESP32-C3 GND      -> 灯条 GND / 白线或黑线
ESP32-C3 GPIO3    -> 330Ω 电阻 -> 灯条 DIN / Data / 绿线

电脑 USB-C 数据线 -> ESP32-C3
```

重点是共地：

```text
外部电源 GND
ESP32-C3 GND
灯条 GND
```

这三者必须连在一起，否则 Data 信号没有共同参考点，灯条会乱闪、无响应，或者只显示异常颜色。

不要用 ESP32-C3 的 `5V` 引脚给整条 WS2812B 灯条供电。灯条用外部 5V 电源，ESP32-C3 用电脑 USB 数据线供电和通信。

更完整的接线说明见 [docs/hardware.md](docs/hardware.md)。

## 上传固件

先查找串口：

```bash
python3 - <<'PY'
import glob
ports = []
for pattern in [
    "/dev/cu.usbmodem*",
    "/dev/cu.SLAB_USBtoUART*",
    "/dev/cu.wchusbserial*",
    "/dev/cu.usbserial*",
]:
    ports.extend(sorted(glob.glob(pattern)))
print("\n".join(ports) if ports else "<no usb serial>")
PY
```

如果输出 `<no usb serial>`，优先检查 USB 线是不是只支持充电、不支持数据。

### 上传交通灯固件

把 `/dev/cu.usbmodem11401` 替换成你自己的串口：

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/TrafficLightStatus
arduino-cli upload -p /dev/cu.usbmodem11401 --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/TrafficLightStatus
```

### 上传 WS2812B 灯条固件

如果你的灯条不是 30 颗，先修改 [firmware/LedStripStatus/LedStripStatus.ino](firmware/LedStripStatus/LedStripStatus.ino) 里的：

```cpp
#define LED_COUNT 30
```

然后编译并上传：

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/LedStripStatus
arduino-cli upload -p /dev/cu.usbmodem11401 --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/LedStripStatus
```

## 运行监听器

先 dry-run 看看当前推断状态：

```bash
python3 tools/codex_desktop_usb_light.py --once --dry-run
```

然后通过 USB 控制 ESP32：

```bash
python3 tools/codex_desktop_usb_light.py --port auto
```

如果要在 macOS 后台常驻运行，见 [docs/install-macos.md](docs/install-macos.md)。

如果只想手动测试灯是否能切换状态，见 [docs/manual-test.md](docs/manual-test.md)。

## 手动测试

可以不启动 Codex Desktop，直接给 ESP32 发状态：

```bash
python3 - <<'PY'
import time
from tools.codex_desktop_usb_light import PersistentUsbStateSender

sender = PersistentUsbStateSender("/dev/cu.usbmodem11401", open_settle_seconds=1.5)
for state, seconds in [("idle", 4), ("busy", 12), ("attention", 6), ("idle", 4)]:
    sender.send(state)
    print("sent", state)
    time.sleep(seconds)
sender.close()
PY
```

把 `/dev/cu.usbmodem11401` 替换成你自己的串口。

## 工作原理

监听器读取 Codex Desktop 的 rollout 日志：

```text
~/.codex/sessions/**/rollout-*.jsonl
```

然后根据任务生命周期事件推断状态：

```text
task_started                  -> busy
task_complete / turn_aborted  -> idle
confirmation / permission     -> attention
task_failed                   -> attention
recent reasoning/output write -> busy
```

监听器运行时会保持 USB 串口打开，避免 ESP32-C3 因为反复打开串口而重启。它也会在打开串口后设置 DTR/RTS，提升 ESP32-C3 USB CDC 收消息的稳定性。

## 排障

最常见的问题是 USB 线只有充电功能。Mac 必须能看到类似下面这样的串口：

```text
/dev/cu.usbmodem11401
```

如果灯条没有反应，按顺序检查：

1. 灯条外部 5V 是否供电
2. ESP32-C3 是否通过数据线连到电脑
3. ESP32-C3 GND、灯条 GND、外部电源 GND 是否共地
4. ESP32-C3 GPIO3 是否经过 330Ω 到 470Ω 电阻接到灯条 DIN
5. 灯条方向是否接在 DIN 输入端，而不是 DO 输出端
6. `LED_COUNT` 是否和实际灯珠数量一致

更多排障步骤见 [docs/troubleshooting.md](docs/troubleshooting.md)。

## 路线图

- V1：ESP32-C3 + 三色交通灯，通过 USB 串口控制
- V2：ESP32-C3 + WS2812B 灯条，提供跑马灯/氛围灯效果
- 后续：可选 Wi-Fi 通信，适合普通家庭网络

见 [docs/roadmap.md](docs/roadmap.md)。

## 许可证

MIT
