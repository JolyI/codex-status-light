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

Traffic light:

```text
R -> GPIO3
Y -> GPIO4
G -> GPIO5
GND -> GND
```

WS2812B LED strip:

```text
ESP32-C3 GPIO3 -> 330 ohm to 470 ohm resistor -> DIN / Data
ESP32-C3 GND   -> LED strip GND
External 5V    -> LED strip 5V
External GND   -> LED strip GND
```

For WS2812B, make sure the external power supply ground, ESP32-C3 ground, and
LED strip ground are connected together.

## Yellow Appears Late

The watcher should keep the serial port open. If another script repeatedly
opens and closes the ESP32-C3 serial port, the board may reset and the light can
lag.

Use the USB-only firmware in `firmware/TrafficLightStatus` or
`firmware/LedStripStatus`. Avoid older test firmware with Wi-Fi setup or long
startup demos when testing live status.

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

## Red Light

Red means Codex needs you to handle something. It does not only mean a failure.

Common causes:

- Codex is waiting for your confirmation.
- A permission, login, browser, or input step needs your action.
- The task failed or hit an error.

The watcher detects common confirmation text from the last Codex message and
maps it to `attention`.

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
