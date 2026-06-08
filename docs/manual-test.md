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

## 3. Test The Watcher Without USB

```bash
python3 tools/codex_desktop_usb_light.py --once --dry-run
```

This prints the state inferred from Codex Desktop logs without sending anything
to the ESP32.

## 4. Test The Watcher With USB

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
