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

Compile and upload:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3 firmware/TrafficLightStatus
arduino-cli upload -p /dev/cu.usbmodem11201 --fqbn esp32:esp32:esp32c3 firmware/TrafficLightStatus
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

When a Codex Desktop task starts, the light should become yellow. When it
finishes or is stopped, the light should return to green. When Codex needs
your confirmation, permission, input, or hits an error, the light should become
red.

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
stty -f /dev/cu.usbmodem11201 115200 raw -echo
printf 'busy\n' > /dev/cu.usbmodem11201
printf 'idle\n' > /dev/cu.usbmodem11201
printf 'attention\n' > /dev/cu.usbmodem11201
```

Opening the serial port can reset some ESP32-C3 boards. The watcher keeps the
port open to avoid repeated resets.
