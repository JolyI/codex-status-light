# Roadmap

## V1: Traffic Light

The first stable version is intentionally small:

- Codex Desktop on macOS
- USB serial transport
- ESP32-C3
- Red/yellow/green traffic light module
- Three visible states: `idle`, `busy`, `attention`

The state meanings stay intentionally simple:

```text
idle       green solid, no action needed
busy       yellow slow blink, Codex is working
attention  red slow blink, Codex needs you
```

## V2: LED Strip

The next hardware renderer can reuse the same Mac watcher and serial protocol.
Only the ESP32 renderer needs to change.

Candidate hardware:

- WS2812B LED strip
- WS2812B LED ring
- 330 ohm to 470 ohm resistor on the data line
- External 5V power supply for larger strips
- Shared ground between ESP32 and LED power supply

Possible effects:

```text
idle       dim green or soft breathing
busy       yellow moving pulse
attention  red heartbeat
```

## Optional Wi-Fi Transport

Wi-Fi is useful on simple home networks, but it is not the default plan for V1.
Office captive portals often require web login and should not be handled by
storing company credentials on the ESP32.

For reliability, USB remains the recommended transport.
