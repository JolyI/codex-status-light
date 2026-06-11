# Manual Test

Use this guide when you want to test the ESP32-C3 light without running Codex
Desktop. It works for both the traffic light firmware and the WS2812B LED strip
firmware.

## 1. Find The Serial Port

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

If this prints `<no usb serial>`, the USB cable may be charge-only or the board
is not connected correctly.

## 2. Send States

Replace `/dev/cu.usbmodem11201` with your actual port:

```bash
python3 - <<'PY'
import time
from tools.codex_desktop_usb_light import PersistentUsbStateSender

sender = PersistentUsbStateSender("/dev/cu.usbmodem11201", open_settle_seconds=1.5)
for state, seconds in [("idle", 4), ("busy", 12), ("attention", 6), ("idle", 4)]:
    sender.send(state)
    print("sent", state)
    time.sleep(seconds)
sender.close()
PY
```

Expected traffic light result:

```text
idle       green solid
busy       yellow solid
attention  red slow blink
```

Expected WS2812B LED strip result:

```text
idle       teal slow breathing
busy       cyan/blue/purple/magenta comet chase
attention  amber double pulse
```

## 3. Test Wi-Fi UDP States

如果灯条刷入了启用 Wi-Fi 的 `LedStripStatus` 固件，并且 Mac 与 ESP32-C3 在同一个 2.4GHz Wi-Fi / 局域网内，可以直接广播状态到 `255.255.255.255:37650`：

```bash
python3 - <<'PY'
import socket
import time

target = ("255.255.255.255", 37650)
states = [("idle", 4), ("busy", 12), ("attention", 6), ("idle", 4)]

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
try:
    for state, seconds in states:
        sock.sendto((state + "\n").encode("utf-8"), target)
        print("sent", state)
        time.sleep(seconds)
finally:
    sock.close()
PY
```

如果无反应，先确认 ESP32-C3 已连上 2.4GHz Wi-Fi，路由器没有禁用局域网广播，Mac 防火墙没有拦截 Python 发出的 UDP 包。

## 4. Test The Watcher Without USB

```bash
python3 tools/codex_desktop_usb_light.py --once --dry-run
```

This prints the state inferred from Codex Desktop logs without sending anything
to the ESP32.

## 5. Test The Watcher With USB

```bash
python3 tools/codex_desktop_usb_light.py --port auto
```

Start a Codex Desktop task and watch the light:

```text
working       -> busy
waiting input -> attention
idle          -> idle
```

Stop with `Ctrl+C` when the test is finished.
