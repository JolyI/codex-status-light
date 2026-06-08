#include <Arduino.h>
#include <Adafruit_NeoPixel.h>
#include "../TrafficLightStatus/StatusLogic.h"
#if ARDUINO_USB_MODE
#include <HWCDC.h>
#if !ARDUINO_USB_CDC_ON_BOOT
HWCDC HWCDCSerial;
#endif
#endif
#if !ARDUINO_USB_MODE
#include <USB.h>
#if !ARDUINO_USB_CDC_ON_BOOT
USBCDC USBSerial;
#endif
#endif

#define LED_PIN 3
#define LED_COUNT 30
#define LED_BRIGHTNESS 42
#define BUSY_TRAIL_LENGTH 16

Adafruit_NeoPixel strip(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);
Status currentStatus = Status::Idle;
Stream *commandInput = &Serial;

void fillColor(uint8_t red, uint8_t green, uint8_t blue, uint8_t from = 0, uint8_t to = LED_COUNT) {
  uint32_t color = strip.Color(red, green, blue);
  for (uint8_t index = from; index < to && index < LED_COUNT; index++) {
    strip.setPixelColor(index, color);
  }
}

void showSolid(uint8_t red, uint8_t green, uint8_t blue) {
  fillColor(red, green, blue);
  strip.show();
}

void clearStrip() {
  strip.clear();
  strip.show();
}

void readCommandFrom(Stream &input) {
  static char buffer[24];
  static int index = 0;

  while (input.available() > 0) {
    char ch = static_cast<char>(input.read());
    if (ch == '\n' || ch == '\r') {
      if (index > 0) {
        buffer[index] = '\0';
        Status parsed = parseStatus(buffer);
        if (parsed != Status::Unknown) {
          currentStatus = parsed;
          Serial.printf("status changed: %s\n", buffer);
        }
        index = 0;
      }
      continue;
    }

    if (index < static_cast<int>(sizeof(buffer)) - 1) {
      buffer[index++] = ch;
    }
  }
}

void setupCommandInput() {
#if ARDUINO_USB_MODE
  HWCDCSerial.begin();
  commandInput = &HWCDCSerial;
#elif !ARDUINO_USB_MODE && !ARDUINO_USB_CDC_ON_BOOT
  USBSerial.begin();
  commandInput = &USBSerial;
#else
  commandInput = &Serial;
#endif
}

void showIdle(unsigned long now) {
  uint8_t phase = (now / 120) % 32;
  uint8_t wave = phase < 16 ? phase : 31 - phase;
  uint8_t pulse = 7 + wave;
  showSolid(0, pulse, pulse / 2);
}

void showBusy(unsigned long now) {
  strip.clear();
  uint8_t head = (now / 75) % LED_COUNT;
  uint16_t drift = (now * 8) % 5000;

  for (uint8_t offset = 0; offset < BUSY_TRAIL_LENGTH && offset < LED_COUNT; offset++) {
    uint8_t index = (head + LED_COUNT - offset) % LED_COUNT;
    uint16_t hue = 32768 + drift + offset * 1700;
    uint8_t value = 28 + ((BUSY_TRAIL_LENGTH - offset) * 140) / BUSY_TRAIL_LENGTH;
    uint8_t saturation = offset == 0 ? 70 : 215 + offset * 2;
    strip.setPixelColor(index, strip.gamma32(strip.ColorHSV(hue, saturation, value)));
  }
  strip.show();
}

void showAttention(unsigned long now) {
  uint8_t phase = (now / 120) % 10;
  bool pulse = phase < 2 || (phase >= 4 && phase < 6);
  uint8_t red = pulse ? 120 : 12;
  uint8_t green = pulse ? 48 : 4;
  showSolid(red, green, 0);
}

void showStatus(unsigned long now) {
  switch (currentStatus) {
    case Status::Idle:
      showIdle(now);
      break;
    case Status::Busy:
      showBusy(now);
      break;
    case Status::Attention:
      showAttention(now);
      break;
    case Status::Unknown:
      clearStrip();
      break;
  }
}

void setup() {
  Serial.begin(115200);
  setupCommandInput();
  strip.begin();
  strip.setBrightness(LED_BRIGHTNESS);
  clearStrip();
  showSolid(0, 24, 12);
}

void loop() {
  unsigned long now = millis();
  readCommandFrom(Serial);
  if (commandInput != &Serial) {
    readCommandFrom(*commandInput);
  }
  showStatus(now);
  delay(30);
}
