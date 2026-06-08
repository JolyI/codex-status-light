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
busy       yellow solid, Codex is working
attention  red slow blink, Codex needs you
```

## V2: LED Strip

The LED strip renderer reuses the same Mac watcher and serial protocol. Only
the ESP32 renderer changes.

Tested hardware:

- WS2812B LED strip
- 330 ohm to 470 ohm resistor on the data line
- External 5V power supply for larger strips
- Shared ground between ESP32 and LED power supply

Default effects:

```text
idle       teal slow breathing
busy       cyan/blue/purple/magenta comet chase
attention  amber double pulse
```

## Optional Wi-Fi Transport

Wi-Fi is useful on simple home networks, but it is not the default plan for V1.
Office captive portals often require web login and should not be handled by
storing company credentials on the ESP32.

For reliability, USB remains the recommended transport.
