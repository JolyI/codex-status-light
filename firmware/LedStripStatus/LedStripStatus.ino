#include <Arduino.h>
#include <Adafruit_NeoPixel.h>
#include "../TrafficLightStatus/StatusLogic.h"
#if __has_include("WifiSecrets.h")
// 本地 Wi-Fi 密码只放在被 gitignore 的 WifiSecrets.h，避免把真实凭据提交到仓库。
#include "WifiSecrets.h"
#else
#define WIFI_STATUS_LIGHT_ENABLED 0
#endif
#ifndef WIFI_STATUS_LIGHT_UDP_PORT
#define WIFI_STATUS_LIGHT_UDP_PORT 37650
#endif
#if WIFI_STATUS_LIGHT_ENABLED
#include <WiFi.h>
#include <WiFiUdp.h>
#endif
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
#define HOST_COMMAND_TIMEOUT_MS 120000UL

Adafruit_NeoPixel strip(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);
Status currentStatus = Status::Idle;
unsigned long lastCommandAt = 0;
Stream *commandInput = &Serial;
#if WIFI_STATUS_LIGHT_ENABLED
WiFiUDP udp;
unsigned long lastWifiAttemptAt = 0;
const unsigned long WIFI_RETRY_INTERVAL_MS = 5000UL;
#endif

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

const char *statusToText(Status status) {
  switch (status) {
    case Status::Idle:
      return "idle";
    case Status::Busy:
      return "busy";
    case Status::Attention:
      return "attention";
    case Status::Unknown:
      return "unknown";
  }
  return "unknown";
}

void applyStatusText(const char *text) {
  Status parsed = parseStatus(text);
  if (parsed != Status::Unknown) {
    currentStatus = parsed;
    lastCommandAt = millis();
    // 日志只输出解析后的规范状态，避免 UDP/串口输入里的控制字符污染日志。
    Serial.printf("status changed: %s\n", statusToText(parsed));
  }
}

void readCommandFrom(Stream &input) {
  static char buffer[24];
  static int index = 0;

  while (input.available() > 0) {
    char ch = static_cast<char>(input.read());
    if (ch == '\n' || ch == '\r') {
      if (index > 0) {
        buffer[index] = '\0';
        applyStatusText(buffer);
        index = 0;
      }
      continue;
    }

    if (index < static_cast<int>(sizeof(buffer)) - 1) {
      buffer[index++] = ch;
    }
  }
}

#if WIFI_STATUS_LIGHT_ENABLED
void setupWifiUdp() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_STATUS_LIGHT_SSID, WIFI_STATUS_LIGHT_PASSWORD);
  lastWifiAttemptAt = millis();
  if (udp.begin(WIFI_STATUS_LIGHT_UDP_PORT)) {
    Serial.printf("wifi udp listening on port %u\n", WIFI_STATUS_LIGHT_UDP_PORT);
  }
}

void connectWifiIfNeeded(unsigned long now) {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  if (now - lastWifiAttemptAt < WIFI_RETRY_INTERVAL_MS) {
    return;
  }

  // Wi-Fi 重连只按固定间隔触发一次 begin，不能阻塞灯效动画刷新。
  lastWifiAttemptAt = now;
  WiFi.begin(WIFI_STATUS_LIGHT_SSID, WIFI_STATUS_LIGHT_PASSWORD);
}

void readCommandFromUdp() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  int packetSize = udp.parsePacket();
  if (packetSize <= 0) {
    return;
  }

  char buffer[24];
  if (packetSize >= static_cast<int>(sizeof(buffer))) {
    // UDP 包超过命令缓冲区时整包丢弃，避免残余字节影响下一次合法状态包。
    while (udp.available() > 0) {
      udp.read();
    }
    return;
  }

  int length = udp.read(buffer, sizeof(buffer) - 1);
  if (length <= 0) {
    return;
  }

  while (udp.available() > 0) {
    udp.read();
  }

  buffer[length] = '\0';
  applyStatusText(buffer);
}
#endif

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
  Status displayStatus = resolveStatusWithCommandTimeout(currentStatus, lastCommandAt, now, HOST_COMMAND_TIMEOUT_MS);
  switch (displayStatus) {
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
#if WIFI_STATUS_LIGHT_ENABLED
  setupWifiUdp();
#endif
  strip.begin();
  strip.setBrightness(LED_BRIGHTNESS);
  lastCommandAt = millis();
  clearStrip();
  showSolid(0, 24, 12);
}

void loop() {
  unsigned long now = millis();
  readCommandFrom(Serial);
  if (commandInput != &Serial) {
    readCommandFrom(*commandInput);
  }
#if WIFI_STATUS_LIGHT_ENABLED
  connectWifiIfNeeded(now);
  readCommandFromUdp();
#endif
  showStatus(now);
  delay(30);
}
