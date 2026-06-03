# Codex Status Light

A USB status light for Codex Desktop, powered by ESP32-C3.

<img src="assets/status-light.png" alt="Codex status light hardware" width="360">

This project turns Codex Desktop activity on macOS into a small physical
traffic light:

```text
idle       green solid
busy       yellow slow blink
attention  red slow blink
```

`attention` means Codex needs you to look at it. It covers confirmations,
permission/input/login prompts, failures, and other blocked states.

The first release is intentionally simple:

- macOS only
- Codex Desktop only
- USB serial only
- ESP32-C3 + a red/yellow/green traffic light module

Wi-Fi and LED strip effects are planned as later versions, but the stable path
is USB first.

## Hardware

Required:

- ESP32-C3 development board
- Red/yellow/green traffic light LED module with `GND`, `R`, `Y`, `G` pins
- USB-C cable that supports data and charging
- 2.54mm female-to-female Dupont wires

Recommended:

- Multimeter for checking continuity and polarity
- Heat shrink tubes or connector housings if you want a sturdier build

## Wiring

```text
Traffic light GND -> ESP32-C3 GND
Traffic light R   -> ESP32-C3 GPIO3
Traffic light Y   -> ESP32-C3 GPIO4
Traffic light G   -> ESP32-C3 GPIO5
```

Do not connect ESP32 `5V` or `3.3V` to the traffic light module unless your
module has a separate `VCC` pin and its datasheet requires it.

See [docs/hardware.md](docs/hardware.md) for the full wiring notes.

## Firmware

Install Arduino CLI and the ESP32 board package, then compile and upload:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32c3 firmware/TrafficLightStatus
arduino-cli upload -p /dev/cu.usbmodem11201 --fqbn esp32:esp32:esp32c3 firmware/TrafficLightStatus
```

Replace `/dev/cu.usbmodem11201` with your actual serial port.

To find the port:

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

## Run The Watcher

Try a dry run first:

```bash
python3 tools/codex_desktop_usb_light.py --once --dry-run
```

Then run it against the ESP32:

```bash
python3 tools/codex_desktop_usb_light.py --port auto
```

For background startup on macOS, see
[docs/install-macos.md](docs/install-macos.md).

For direct state checks, see [docs/manual-test.md](docs/manual-test.md).

## How It Works

The watcher reads Codex Desktop rollout logs from:

```text
~/.codex/sessions/**/rollout-*.jsonl
```

It looks for task lifecycle events:

```text
task_started                  -> busy
task_complete / turn_aborted  -> idle
confirmation / permission     -> attention
task_failed                   -> attention
```

The watcher keeps the USB serial handle open while running. This avoids the
ESP32-C3 resetting on every state update, which was the main cause of delayed
lights during testing.

## Troubleshooting

The most common issue is a charge-only USB cable. The Mac must show a serial
port like `/dev/cu.usbmodem...`.

See [docs/troubleshooting.md](docs/troubleshooting.md) for practical checks.

## Roadmap

- V1: ESP32-C3 + three-color traffic light over USB serial
- V2: WS2812B LED strip or ring with running-light effects
- Later: optional Wi-Fi transport for simple home networks

See [docs/roadmap.md](docs/roadmap.md).

## License

MIT
