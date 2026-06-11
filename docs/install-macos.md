# macOS Install Guide

## 1. Upload The Firmware

Install Arduino CLI:

```bash
brew install arduino-cli
```

Install the ESP32 board package if you have not already:

```bash
arduino-cli core update-index
arduino-cli core install esp32:esp32
```

Find your ESP32-C3 serial port:

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

Compile and upload the traffic light firmware:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/TrafficLightStatus
arduino-cli upload -p /dev/cu.usbmodem11201 --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/TrafficLightStatus
```

如果 WS2812B 灯条需要启用 Wi-Fi，先复制 Wi-Fi 配置示例：

```bash
cp firmware/LedStripStatus/WifiSecrets.example.h firmware/LedStripStatus/WifiSecrets.h
```

然后编辑 `firmware/LedStripStatus/WifiSecrets.h`，填入家里 2.4GHz Wi-Fi 名称和密码。不创建 `WifiSecrets.h` 时，USB 仍然是默认通信方式，Wi-Fi 不会启用。

Or compile and upload the WS2812B LED strip firmware:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/LedStripStatus
arduino-cli upload -p /dev/cu.usbmodem11201 --fqbn esp32:esp32:esp32c3:CDCOnBoot=cdc firmware/LedStripStatus
```

Replace `/dev/cu.usbmodem11201` with your port.

## 2. Test The Watcher

Dry run:

```bash
python3 tools/codex_desktop_usb_light.py --once --dry-run
```

Run against USB:

```bash
python3 tools/codex_desktop_usb_light.py --port auto
```

When a Codex Desktop task starts, the light should become `busy`. When it
finishes or is stopped, the light should return to `idle`. When Codex needs
your confirmation, permission, input, or hits an error, the light should become
`attention`.

## 3. Install As A LaunchAgent

Recommended:

```bash
scripts/install-launch-agent.sh
```

The script writes `~/Library/LaunchAgents/com.jolyi.codex-status-light.plist`
using your current project path and home directory.

Manual install:

Create the log directory:

```bash
mkdir -p "$HOME/.codex/log"
```

Copy the template:

```bash
cp launchd/com.jolyi.codex-status-light.plist.template \
  "$HOME/Library/LaunchAgents/com.jolyi.codex-status-light.plist"
```

Edit the copied plist and replace:

```text
/ABSOLUTE/PATH/TO/codex-status-light
REPLACE_WITH_YOUR_USERNAME
```

with the absolute path to this project and your macOS username.

如果继续使用 USB 模式，不需要修改 plist 里的默认参数。如需 Wi-Fi，加载前先改 `ProgramArguments`：把 plist 中的：

```xml
<string>--port</string>
<string>auto</string>
```

改成：

```xml
<string>--transport</string>
<string>udp</string>
<string>--udp-host</string>
<string>255.255.255.255</string>
<string>--udp-port</string>
<string>37650</string>
```

Mac 和 ESP32-C3 需要在同一个 2.4GHz Wi-Fi / 局域网内，并且灯条固件已按上面的步骤启用 Wi-Fi。

Load it:

```bash
launchctl unload "$HOME/Library/LaunchAgents/com.jolyi.codex-status-light.plist" 2>/dev/null || true
launchctl load "$HOME/Library/LaunchAgents/com.jolyi.codex-status-light.plist"
```

Check logs:

```bash
tail -f "$HOME/.codex/log/codex-status-light.out.log"
tail -f "$HOME/.codex/log/codex-status-light.err.log"
```

## Manual State Test

If the watcher is not running, you can manually send states:

```bash
python3 - <<'PY'
import time
from tools.codex_desktop_usb_light import PersistentUsbStateSender

sender = PersistentUsbStateSender("/dev/cu.usbmodem11201", open_settle_seconds=1.5)
for state, seconds in [("busy", 8), ("idle", 4), ("attention", 6), ("idle", 4)]:
    sender.send(state)
    print("sent", state)
    time.sleep(seconds)
sender.close()
PY
```

Opening the serial port can reset some ESP32-C3 boards. The watcher keeps the
port open to avoid repeated resets.
