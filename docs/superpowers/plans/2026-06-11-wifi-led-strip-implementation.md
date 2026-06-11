# Wi-Fi 灯条通信 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 WS2812B + ESP32-C3 灯条可以通过家庭 Wi-Fi 接收 Codex 状态，灯条日常只接电源，不再需要插在 Mac 上。

**Architecture:** Python 监听器保留现有状态推断逻辑，新增 `usb` 与 `udp` 两种发送方式，默认继续使用 USB。ESP32-C3 固件保留串口输入，同时在启用 Wi-Fi secrets 时连接 2.4GHz Wi-Fi 并监听 UDP 状态包。

**Tech Stack:** Python `unittest`、Python `socket`、Arduino ESP32 `WiFi.h`、`WiFiUdp.h`、Adafruit NeoPixel、现有 C++ `StatusLogic.h`。

---

## 文件结构

- 修改 `tools/codex_desktop_usb_light.py`：新增 UDP sender、CLI 参数、transport 选择逻辑。
- 修改 `tests/test_codex_desktop_usb_light.py`：新增 UDP sender 和 CLI transport 测试。
- 修改 `firmware/LedStripStatus/LedStripStatus.ino`：新增 Wi-Fi 连接、UDP 读取、非阻塞重连。
- 新增 `firmware/LedStripStatus/WifiSecrets.example.h`：示例 Wi-Fi 配置，不包含真实密码。
- 修改 `.gitignore`：忽略真实 `firmware/LedStripStatus/WifiSecrets.h`。
- 修改 `README.md`、`docs/install-macos.md`、`docs/manual-test.md`、`docs/troubleshooting.md`：补充 Wi-Fi 模式使用和排障。
- 可选修改 `launchd/com.jolyi.codex-status-light.plist.template`：保留 USB 默认，不强制切到 UDP；文档说明用户自己改参数。

---

### Task 1: Python UDP Sender

**Files:**
- Modify: `tests/test_codex_desktop_usb_light.py`
- Modify: `tools/codex_desktop_usb_light.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_codex_desktop_usb_light.py` 的 import 列表里加入 `UdpStateSender`，并在 `PersistentUsbStateSenderTests` 附近新增测试类：

```python
class FakeUdpSocket:
    def __init__(self):
        self.options = []
        self.sent = []
        self.closed = False

    def setsockopt(self, level, option, value):
        self.options.append((level, option, value))

    def sendto(self, payload, target):
        self.sent.append((payload, target))

    def close(self):
        self.closed = True


class UdpStateSenderTests(unittest.TestCase):
    def test_sends_newline_terminated_state_to_configured_target(self):
        fake_socket = FakeUdpSocket()
        sender = UdpStateSender(
            host="192.168.1.255",
            port=37650,
            socket_factory=lambda *_args: fake_socket,
        )

        sender.send("busy")

        self.assertEqual(fake_socket.sent, [(b"busy\n", ("192.168.1.255", 37650))])

    def test_enables_broadcast_for_default_lan_broadcast_host(self):
        fake_socket = FakeUdpSocket()
        sender = UdpStateSender(socket_factory=lambda *_args: fake_socket)

        sender.send("idle")

        self.assertTrue(any(option[2] == 1 for option in fake_socket.options))

    def test_rejects_unsupported_state(self):
        sender = UdpStateSender(socket_factory=lambda *_args: FakeUdpSocket())

        with self.assertRaises(ValueError):
            sender.send("rainbow")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python3 -m unittest tests.test_codex_desktop_usb_light.UdpStateSenderTests -v
```

Expected: FAIL 或 ERROR，错误包含 `cannot import name 'UdpStateSender'` 或 `NameError`。

- [ ] **Step 3: 写最小实现**

在 `tools/codex_desktop_usb_light.py` 增加 import：

```python
import socket
```

在 `PersistentUsbStateSender` 之后新增：

```python
DEFAULT_UDP_HOST = "255.255.255.255"
DEFAULT_UDP_PORT = 37650


class UdpStateSender:
    def __init__(
        self,
        host: str = DEFAULT_UDP_HOST,
        port: int = DEFAULT_UDP_PORT,
        socket_factory=socket.socket,
    ):
        self.host = host
        self.port = port
        self.socket = socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def send(self, state: str) -> None:
        if state not in VISIBLE_STATES:
            raise ValueError(f"Unsupported state: {state}")
        self.socket.sendto(f"{state}\n".encode("utf-8"), (self.host, self.port))

    def close(self) -> None:
        self.socket.close()
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
python3 -m unittest tests.test_codex_desktop_usb_light.UdpStateSenderTests -v
```

Expected: PASS，3 个 UDP sender 测试通过。

- [ ] **Step 5: 运行完整 Python 测试**

Run:

```bash
python3 -m unittest tests.test_codex_desktop_usb_light -v
```

Expected: PASS，所有 Python 测试通过。

- [ ] **Step 6: 提交**

```bash
git add tools/codex_desktop_usb_light.py tests/test_codex_desktop_usb_light.py
git commit -m "feat: 增加 UDP 状态发送器"
```

---

### Task 2: Watcher Transport CLI

**Files:**
- Modify: `tests/test_codex_desktop_usb_light.py`
- Modify: `tools/codex_desktop_usb_light.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_codex_desktop_usb_light.py` 中新增测试，验证 CLI 可以选择 UDP，且不打开真实 socket：

```python
class MainTransportSelectionTests(unittest.TestCase):
    def test_udp_transport_uses_udp_sender(self):
        sent = []

        class FakeUdpSender:
            def __init__(self, host, port):
                self.host = host
                self.port = port

            def send(self, state):
                sent.append((self.host, self.port, state))

            def close(self):
                sent.append(("closed", self.host, self.port))

        with tempfile.TemporaryDirectory() as root:
            sessions_dir = os.path.join(root, "sessions")
            os.mkdir(sessions_dir)
            logs_db = os.path.join(root, "missing.sqlite")
            result = main(
                [
                    "--once",
                    "--transport",
                    "udp",
                    "--udp-host",
                    "192.168.1.255",
                    "--udp-port",
                    "37651",
                    "--logs-db",
                    logs_db,
                    "--sessions-dir",
                    sessions_dir,
                ],
                udp_sender_factory=FakeUdpSender,
            )

        self.assertEqual(result, 0)
        self.assertEqual(sent, [("192.168.1.255", 37651, "idle"), ("closed", "192.168.1.255", 37651)])
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python3 -m unittest tests.test_codex_desktop_usb_light.MainTransportSelectionTests -v
```

Expected: FAIL 或 ERROR，错误包含 `unexpected keyword argument 'udp_sender_factory'` 或 `unrecognized arguments: --transport`。

- [ ] **Step 3: 增加 CLI 参数**

在 `build_parser()` 中加入：

```python
    parser.add_argument("--transport", choices=("usb", "udp"), default="usb")
    parser.add_argument("--udp-host", default=DEFAULT_UDP_HOST)
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT)
```

- [ ] **Step 4: 修改 main sender 初始化**

把 `main` 函数签名改成：

```python
def main(argv=None, sender=None, udp_sender_factory=UdpStateSender) -> int:
```

把现有 `persistent_sender = None` 初始化附近改成：

```python
    persistent_sender = None
    close_sender = None
    if sender is None and not args.dry_run:
        if args.transport == "udp":
            persistent_sender = udp_sender_factory(args.udp_host, args.udp_port)
            close_sender = persistent_sender.close

            def send(port, state, baud_rate=DEFAULT_BAUD_RATE):
                persistent_sender.send(state)
        else:
            persistent_sender = PersistentUsbStateSender(
                args.port,
                args.baud_rate,
                open_settle_seconds=args.serial_open_settle_seconds,
            )
            close_sender = persistent_sender.close

            def send(port, state, baud_rate=DEFAULT_BAUD_RATE):
                persistent_sender.send(state)
    else:
        send = sender or send_usb_state
```

把 `finally` 改成：

```python
    finally:
        if close_sender is not None:
            close_sender()
```

- [ ] **Step 5: 运行目标测试确认通过**

Run:

```bash
python3 -m unittest tests.test_codex_desktop_usb_light.MainTransportSelectionTests -v
```

Expected: PASS。

- [ ] **Step 6: 运行完整 Python 测试**

Run:

```bash
python3 -m unittest tests.test_codex_desktop_usb_light -v
```

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add tools/codex_desktop_usb_light.py tests/test_codex_desktop_usb_light.py
git commit -m "feat: 支持选择 UDP 监听器通信"
```

---

### Task 3: Wi-Fi Secrets 与忽略规则

**Files:**
- Create: `firmware/LedStripStatus/WifiSecrets.example.h`
- Modify: `.gitignore`
- Modify: `README.md`

- [ ] **Step 1: 新增示例配置文件**

Create `firmware/LedStripStatus/WifiSecrets.example.h`:

```cpp
#pragma once

// 复制为 WifiSecrets.h 后填入家里 2.4GHz Wi-Fi。真实密码文件不要提交。
#define WIFI_STATUS_LIGHT_ENABLED 1
#define WIFI_STATUS_LIGHT_SSID "your-2g-ssid"
#define WIFI_STATUS_LIGHT_PASSWORD "your-wifi-password"
#define WIFI_STATUS_LIGHT_UDP_PORT 37650
```

- [ ] **Step 2: 忽略真实密码文件**

在 `.gitignore` 增加：

```gitignore
firmware/LedStripStatus/WifiSecrets.h
```

- [ ] **Step 3: README 补充配置入口**

在 README 的 WS2812B 上传固件段落前加入：

````markdown
### 可选：启用 Wi-Fi 模式

如果想让灯条只接电源、不插 Mac，复制示例配置：

```bash
cp firmware/LedStripStatus/WifiSecrets.example.h firmware/LedStripStatus/WifiSecrets.h
```

然后编辑 `WifiSecrets.h`，填入家里 2.4GHz Wi-Fi 名称和密码。真实
`WifiSecrets.h` 已被 `.gitignore` 忽略，不要提交。
````

- [ ] **Step 4: 确认真实 secrets 没被追踪**

Run:

```bash
git status --short
```

Expected: 输出里可以有 `WifiSecrets.example.h` 和 `.gitignore`，不应出现真实 `WifiSecrets.h`。

- [ ] **Step 5: 提交**

```bash
git add .gitignore firmware/LedStripStatus/WifiSecrets.example.h README.md
git commit -m "docs: 增加灯条 Wi-Fi 配置示例"
```

---

### Task 4: 固件 Wi-Fi UDP 接收

**Files:**
- Modify: `firmware/LedStripStatus/LedStripStatus.ino`
- Read: `firmware/TrafficLightStatus/StatusLogic.h`

- [ ] **Step 1: 编译当前固件确认基线**

Run:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/LedStripStatus
```

Expected: 当前 USB-only 固件编译通过。如果失败，先记录原始错误，不进入 Wi-Fi 改造。

- [ ] **Step 2: 增加 Wi-Fi include 与默认开关**

在 `LedStripStatus.ino` 顶部 include 区域加入：

```cpp
#if __has_include("WifiSecrets.h")
#include "WifiSecrets.h"
#else
#define WIFI_STATUS_LIGHT_ENABLED 0
#endif

#if WIFI_STATUS_LIGHT_ENABLED
#include <WiFi.h>
#include <WiFiUdp.h>
#ifndef WIFI_STATUS_LIGHT_UDP_PORT
#define WIFI_STATUS_LIGHT_UDP_PORT 37650
#endif
#endif
```

- [ ] **Step 3: 增加 Wi-Fi 状态变量**

在全局变量区加入：

```cpp
#if WIFI_STATUS_LIGHT_ENABLED
WiFiUDP udp;
unsigned long lastWifiAttemptAt = 0;
const unsigned long WIFI_RETRY_INTERVAL_MS = 5000UL;
#endif
```

- [ ] **Step 4: 抽出状态应用函数**

在 `readCommandFrom` 前新增：

```cpp
void applyStatusText(const char *text) {
  Status parsed = parseStatus(text);
  if (parsed != Status::Unknown) {
    currentStatus = parsed;
    lastCommandAt = millis();
    Serial.printf("status changed: %s\n", text);
  }
}
```

把 `readCommandFrom` 中的解析块替换为：

```cpp
        buffer[index] = '\0';
        applyStatusText(buffer);
        index = 0;
```

- [ ] **Step 5: 增加 Wi-Fi 连接函数**

在 `setupCommandInput()` 后新增：

```cpp
#if WIFI_STATUS_LIGHT_ENABLED
void connectWifiIfNeeded(unsigned long now) {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  if (lastWifiAttemptAt != 0 && now - lastWifiAttemptAt < WIFI_RETRY_INTERVAL_MS) {
    return;
  }

  lastWifiAttemptAt = now;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_STATUS_LIGHT_SSID, WIFI_STATUS_LIGHT_PASSWORD);
}

void setupWifiUdp() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_STATUS_LIGHT_SSID, WIFI_STATUS_LIGHT_PASSWORD);
  lastWifiAttemptAt = millis();
  udp.begin(WIFI_STATUS_LIGHT_UDP_PORT);
  Serial.printf("wifi udp listening on port %d\n", WIFI_STATUS_LIGHT_UDP_PORT);
}
#endif
```

- [ ] **Step 6: 增加 UDP 读取函数**

在 Wi-Fi 函数区域继续加入：

```cpp
#if WIFI_STATUS_LIGHT_ENABLED
void readCommandFromUdp() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  int packetSize = udp.parsePacket();
  if (packetSize <= 0) {
    return;
  }

  char buffer[24];
  int length = udp.read(buffer, sizeof(buffer) - 1);
  if (length <= 0) {
    return;
  }

  buffer[length] = '\0';
  applyStatusText(buffer);
}
#endif
```

- [ ] **Step 7: 接入 setup 和 loop**

在 `setup()` 的 `setupCommandInput();` 后加入：

```cpp
#if WIFI_STATUS_LIGHT_ENABLED
  setupWifiUdp();
#endif
```

在 `loop()` 的串口读取后加入：

```cpp
#if WIFI_STATUS_LIGHT_ENABLED
  connectWifiIfNeeded(now);
  readCommandFromUdp();
#endif
```

- [ ] **Step 8: 编译 USB 默认模式**

Run:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/LedStripStatus
```

Expected: PASS。没有 `WifiSecrets.h` 时仍然是 USB 默认模式。

- [ ] **Step 9: 用示例 secrets 进行编译检查**

Run:

```bash
cp firmware/LedStripStatus/WifiSecrets.example.h firmware/LedStripStatus/WifiSecrets.h
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/LedStripStatus
rm firmware/LedStripStatus/WifiSecrets.h
```

Expected: PASS。编译完成后真实 `WifiSecrets.h` 已删除。

- [ ] **Step 10: 提交**

```bash
git add firmware/LedStripStatus/LedStripStatus.ino
git commit -m "feat: 灯条固件接收 Wi-Fi UDP 状态"
```

---

### Task 5: 使用文档与后台服务说明

**Files:**
- Modify: `README.md`
- Modify: `docs/install-macos.md`
- Modify: `docs/manual-test.md`
- Modify: `docs/troubleshooting.md`

- [ ] **Step 1: README 增加 Wi-Fi 运行命令**

在 “运行监听器” 段落加入：

````markdown
通过 Wi-Fi 控制灯条：

```bash
python3 tools/codex_desktop_usb_light.py --transport udp --udp-host 255.255.255.255 --udp-port 37650
```

灯条需要已经刷入启用 Wi-Fi 的 `LedStripStatus` 固件，并接在家里同一个 2.4GHz
Wi-Fi 网络里。
````

- [ ] **Step 2: 安装文档增加 LaunchAgent 参数修改示例**

在 `docs/install-macos.md` 的 LaunchAgent 段落加入：

````markdown
如果要让后台服务走 Wi-Fi，把 plist 里的参数改成：

```xml
<string>--transport</string>
<string>udp</string>
<string>--udp-host</string>
<string>255.255.255.255</string>
<string>--udp-port</string>
<string>37650</string>
```

保留 USB 模式时不需要改这个配置。
````

- [ ] **Step 3: 手动测试文档增加 UDP 发包**

在 `docs/manual-test.md` 增加：

````markdown
## Wi-Fi UDP 手动测试

```bash
python3 - <<'PY'
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
for state in ["idle", "busy", "attention", "idle"]:
    sock.sendto((state + "\n").encode("utf-8"), ("255.255.255.255", 37650))
    print("sent", state)
PY
```
````

- [ ] **Step 4: 排障文档增加 Wi-Fi 检查点**

在 `docs/troubleshooting.md` 增加：

```markdown
## Wi-Fi 灯条无反应

检查：

- ESP32-C3 供电正常，灯条外部 5V 供电正常。
- `WifiSecrets.h` 里填写的是 2.4GHz Wi-Fi，不是 5GHz-only 网络。
- Mac 和 ESP32-C3 在同一个局域网。
- 路由器没有关闭局域网广播。
- Mac 防火墙没有拦截 Python 发送 UDP。
- watcher 使用了 `--transport udp --udp-port 37650`。
```

- [ ] **Step 5: 提交**

```bash
git add README.md docs/install-macos.md docs/manual-test.md docs/troubleshooting.md
git commit -m "docs: 补充 Wi-Fi 灯条使用说明"
```

---

### Task 6: 端到端验证

**Files:**
- Read: all modified files

- [ ] **Step 1: 运行 Python 测试**

Run:

```bash
python3 -m unittest tests.test_codex_desktop_usb_light -v
```

Expected: PASS。

- [ ] **Step 2: 运行 C++ 共享逻辑测试**

Run:

```bash
c++ -std=c++17 firmware/TrafficLightStatus/test_status_logic.cpp -o /tmp/test_status_logic && /tmp/test_status_logic
```

Expected: 命令退出码为 0，无断言失败。

- [ ] **Step 3: 编译交通灯固件**

Run:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/TrafficLightStatus
```

Expected: PASS。

- [ ] **Step 4: 编译灯条固件 USB 默认模式**

Run:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/LedStripStatus
```

Expected: PASS。

- [ ] **Step 5: 编译灯条固件 Wi-Fi 模式**

Run:

```bash
cp firmware/LedStripStatus/WifiSecrets.example.h firmware/LedStripStatus/WifiSecrets.h
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/LedStripStatus
rm firmware/LedStripStatus/WifiSecrets.h
```

Expected: PASS，最后 `git status --short` 不显示真实 `WifiSecrets.h`。

- [ ] **Step 6: dry-run 当前状态**

Run:

```bash
python3 tools/codex_desktop_usb_light.py --once --dry-run
```

Expected: 输出 `idle`、`busy` 或 `attention` 之一。

- [ ] **Step 7: UDP 监听器单次发送**

Run:

```bash
python3 tools/codex_desktop_usb_light.py --once --transport udp --udp-host 255.255.255.255 --udp-port 37650
```

Expected: 输出当前状态，不报 socket 错误。

- [ ] **Step 8: 最终提交或确认无改动**

Run:

```bash
git status --short
```

Expected: 只剩用户原本未纳入本次工作的改动，或工作区干净。
