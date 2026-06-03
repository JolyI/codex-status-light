# Manual Test

Use this guide when you want to test the ESP32-C3 and traffic light module
without running Codex Desktop.

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
stty -f /dev/cu.usbmodem11201 115200 raw -echo
printf 'idle\n' > /dev/cu.usbmodem11201
printf 'busy\n' > /dev/cu.usbmodem11201
printf 'attention\n' > /dev/cu.usbmodem11201
```

Expected result:

```text
idle       green solid
busy       yellow slow blink
attention  red slow blink
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
working       -> yellow slow blink
waiting input -> red slow blink
idle          -> green solid
```

Stop with `Ctrl+C` when the test is finished.
