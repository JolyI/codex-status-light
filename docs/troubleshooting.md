# Troubleshooting

## No Serial Port

Run:

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

If you see `<no usb serial>`, check:

- The USB cable supports data, not charging only.
- The ESP32-C3 is fully inserted.
- The USB hub or adapter supports data.
- The board is not in a failed bootloader state.

## Light Is Powered But Does Not React

Check the watcher output:

```bash
python3 tools/codex_desktop_usb_light.py --once --dry-run
```

Then test USB directly:

```bash
python3 tools/codex_desktop_usb_light.py --port auto --once
```

If the command prints a state but the light does not change, recheck wiring:

```text
R -> GPIO3
Y -> GPIO4
G -> GPIO5
GND -> GND
```

## Yellow Appears Late

The watcher should keep the serial port open. If another script repeatedly
opens and closes the ESP32-C3 serial port, the board may reset and the light can
lag.

Use the USB-only firmware in `firmware/TrafficLightStatus`. Avoid older
test firmware with Wi-Fi setup or long startup demos when testing live status.

## Stuck Yellow After Stopping A Task

The current watcher treats these rollout events as idle:

```text
task_complete
turn_aborted
task_aborted
```

Restart the watcher if the USB cable was unplugged:

```bash
launchctl unload "$HOME/Library/LaunchAgents/com.jolyi.codex-status-light.plist" 2>/dev/null || true
launchctl load "$HOME/Library/LaunchAgents/com.jolyi.codex-status-light.plist"
```

## Stuck Green While Codex Is Working

Check whether Codex Desktop is writing rollout logs:

```bash
find "$HOME/.codex/sessions" -name 'rollout-*.jsonl' -mmin -5 | tail
```

Check the aggregate state:

```bash
python3 tools/codex_desktop_usb_light.py --once --dry-run
```

If this prints `busy`, the watcher sees Codex correctly and the issue is likely
USB or firmware. If this prints `idle`, Codex Desktop may have changed its local
log format.

## Permission Or Device Errors

Errors like `Device not configured` usually mean the cable or board was
unplugged while the watcher still had the old serial handle open.

Reconnect the board and restart the watcher:

```bash
launchctl unload "$HOME/Library/LaunchAgents/com.jolyi.codex-status-light.plist" 2>/dev/null || true
launchctl load "$HOME/Library/LaunchAgents/com.jolyi.codex-status-light.plist"
```
