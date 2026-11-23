// ESP32 firmware: BME280 -> JSON (schemas/reading.schema.json) -> MQTT topic sensors/<device_id>/reading
// Libraries: PubSubClient, ArduinoJson, Adafruit BME280 (+ Adafruit Unified Sensor).
// No sensor? set USE_FAKE_SENSOR 1 and the board sends synthetic values (still a valid "real device" demo).
// NOTE: ZeroMQ is for host-side testing only; the ESP32 always speaks MQTT.
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <Preferences.h>
#include "secrets.h"            // define WIFI_SSID, WIFI_PASS, MQTT_HOST (see secrets.h.example) - never commit it

#define USE_FAKE_SENSOR 1
#define PUBLISH_EVERY_MS 10000
#define FW_VERSION "1.2.0"

#if !USE_FAKE_SENSOR
#include <Adafruit_BME280.h>
Adafruit_BME280 bme;
#endif

WiFiClient net;
PubSubClient mqtt(net);
Preferences prefs;
String deviceId;
uint32_t bootCount;
uint32_t seq = 0;

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(300);
}

void connectMqtt() {
  while (!mqtt.connected()) {            // reconnect loop: broker restarts must not brick the device
    if (!mqtt.connect(deviceId.c_str())) delay(2000);
  }
}

String isoNow() {
  time_t now; time(&now);
  struct tm t; gmtime_r(&now, &t);
  char buf[25]; strftime(buf, sizeof buf, "%Y-%m-%dT%H:%M:%SZ", &t);
  return String(buf);
}

void setup() {
  Serial.begin(115200);
  String mac = WiFi.macAddress(); mac.replace(":", "");
  deviceId = "esp32-" + mac.substring(6);
  prefs.begin("iot", false);
  bootCount = prefs.getUInt("boots", 0) + 1;           // persisted so reading_id stays unique across reboots
  prefs.putUInt("boots", bootCount);
  connectWifi();
  configTime(0, 0, "pool.ntp.org");                    // event time must be real UTC
  mqtt.setServer(MQTT_HOST, 1883);
#if !USE_FAKE_SENSOR
  bme.begin(0x76);
#endif
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();
  connectMqtt();
  mqtt.loop();

  static uint32_t last = 0;
  if (millis() - last < PUBLISH_EVERY_MS) return;
  last = millis();

  StaticJsonDocument<256> doc;
  doc["reading_id"] = deviceId + "-" + String(bootCount) + "-" + String(seq++);
  doc["device_id"] = deviceId;
  doc["ts"] = isoNow();
#if USE_FAKE_SENSOR
  doc["temperature_c"] = 22.0 + random(-30, 30) / 10.0;
  doc["humidity_pct"] = 50.0 + random(-100, 100) / 10.0;
  doc["pressure_hpa"] = 1013.0;
#else
  doc["temperature_c"] = bme.readTemperature();
  doc["humidity_pct"] = bme.readHumidity();
  doc["pressure_hpa"] = bme.readPressure() / 100.0F;
#endif
  doc["battery_v"] = analogReadMilliVolts(34) * 2 / 1000.0;   // divider on GPIO34
  doc["fw_version"] = FW_VERSION;

  char payload[256];
  size_t n = serializeJson(doc, payload);
  String topic = "sensors/" + deviceId + "/reading";
  mqtt.publish(topic.c_str(), (const uint8_t *)payload, n, false);
}
