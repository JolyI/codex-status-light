#include <Arduino.h>
#include "StatusLogic.h"
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

#define RED_PIN 3
#define YELLOW_PIN 4
#define GREEN_PIN 5

const bool ACTIVE_LOW = false;
const unsigned long STATUS_BLINK_MS = 1200;

Status currentStatus = Status::Idle;

Stream *commandInput = &Serial;

void setPin(int pin, bool on) {
  digitalWrite(pin, ACTIVE_LOW ? !on : on);
}

void setLights(bool red, bool yellow, bool green) {
  setPin(RED_PIN, red);
  setPin(YELLOW_PIN, yellow);
  setPin(GREEN_PIN, green);
}

const char *statusToText(Status status) {
  switch (status) {
    case Status::Idle:
      return "idle";
    case Status::Busy:
      return "busy";
    case Status::Attention:
      return "attention";
    default:
      return "unknown";
  }
}

void showStatus(Status status, unsigned long now) {
  LightState lights = resolveStatusLights(status, now, STATUS_BLINK_MS);
  setLights(lights.red, lights.yellow, lights.green);
}

void applyStatus(Status parsed) {
  if (parsed == Status::Unknown) {
    return;
  }

  currentStatus = parsed;
  Serial.printf("status changed: %s\n", statusToText(parsed));
}

void readCommandFrom(Stream &input) {
  static char buffer[24];
  static int index = 0;

  while (input.available() > 0) {
    char ch = static_cast<char>(input.read());
    if (ch == '\n' || ch == '\r') {
      if (index > 0) {
        buffer[index] = '\0';
        applyStatus(parseStatus(buffer));
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

void setup() {
  pinMode(RED_PIN, OUTPUT);
  pinMode(YELLOW_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);
  setLights(false, false, false);

  Serial.begin(115200);
  setupCommandInput();
  applyStatus(Status::Idle);
}

void loop() {
  unsigned long now = millis();
  readCommandFrom(*commandInput);
  showStatus(currentStatus, now);
}
