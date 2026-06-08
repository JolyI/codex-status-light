# Hardware Guide

## Tested Parts

- ESP32-C3 development board
- Red/yellow/green traffic light LED module
- WS2812B 5V LED strip
- 2.54mm female-to-female Dupont wires
- USB-C cable with data support
- 330 ohm resistor for the WS2812B data line
- External 5V power supply for the WS2812B strip

## Traffic Light Pin Mapping

The tested traffic light module exposes four pins:

```text
GND R Y G
```

Connect them to the ESP32-C3 like this:

```text
Traffic light GND -> ESP32-C3 GND
Traffic light R   -> ESP32-C3 GPIO3
Traffic light Y   -> ESP32-C3 GPIO4
Traffic light G   -> ESP32-C3 GPIO5
```

On one tested ESP32-C3 board, the left-side pins from top to bottom were:

```text
5V G 3.3 4 3 2 1 0
```

For that board:

```text
GND -> second pin from top, marked G
Y   -> GPIO4
R   -> GPIO3
```

GPIO5 may be on the other side of the board depending on the exact board
variant. Always follow the silkscreen on your board.

## 5V And 3.3V

For the common traffic light module with `GND`, `R`, `Y`, `G` pins, each color
pin is driven directly by a GPIO. Do not connect `5V` or `3.3V`.

Only connect a power pin if your module has a separate `VCC` pin and its
datasheet says it needs external power.

## Resistors

Many traffic light modules already include resistors on the board. If your
module is a bare LED without onboard resistors, add a current-limiting resistor
for each LED channel.

For WS2812B LED strips, use a 330 ohm to 470 ohm resistor on the data line:

```text
ESP32-C3 GPIO3 -> resistor -> WS2812B DIN / Data
```

## WS2812B LED Strip Wiring

The tested LED strip firmware uses GPIO3 and 30 LEDs by default:

```text
External 5V positive -> LED strip 5V / red wire
External 5V negative -> LED strip GND / thick black wire

ESP32-C3 GND        -> LED strip GND / white or black wire
ESP32-C3 GPIO3      -> 330 ohm resistor -> LED strip DIN / Data / green wire

Computer USB-C cable -> ESP32-C3
```

The external power supply ground, ESP32-C3 ground, and LED strip ground must be
connected together. Do not power the full LED strip from the ESP32-C3 `5V` pin.

## USB Cable

Use a USB-C cable that supports data and charging. A charge-only cable can power
the board but macOS will not show a serial port.

Good sign:

```text
/dev/cu.usbmodem11201
```

Bad sign:

```text
<no usb serial>
```

Current rating such as 1A, 2A, or 3A is not the important part for this
project. Data support is the important part.
