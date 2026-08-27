#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Preferences.h>
#include <cstring>
#include <math.h>
#include <time.h>

// Install ArduinoJson, Adafruit BME280 Library and Adafruit MPU6050 Library.
// Do not commit real Wi-Fi or API-key values to source control.
const char* WIFI_SSID = "SUA_REDE_WIFI";
const char* WIFI_PASSWORD = "SUA_SENHA_WIFI";
const char* AGROGUARDIAN_API_URL = "https://SEU_HOST_PUBLICO/api/v1/telemetry/esp";
// Paste the public API certificate authority here. HTTPS is mandatory because
// the device API key is sent in every request.
const char* AGROGUARDIAN_TLS_ROOT_CA = "";
const char* DEVICE_ID = "ESP32-TRATOR-001";
const char* ESP32_API_KEY = "SUBSTITUA_PELA_CHAVE_GERADA";
const char* FIRMWARE_VERSION = "agroguardian-esp32-1.0.0";

constexpr uint8_t I2C_SDA_PIN = 21;
constexpr uint8_t I2C_SCL_PIN = 22;
constexpr uint8_t JSN_TRIGGER_PIN = 26;
constexpr uint8_t JSN_ECHO_PIN = 27;
constexpr unsigned long SEND_INTERVAL_MS = 10000;
constexpr unsigned long WIFI_TIMEOUT_MS = 15000;
constexpr unsigned long JSN_TIMEOUT_US = 30000;
constexpr unsigned long HTTP_TIMEOUT_MS = 25000;
constexpr int HTTP_RETRIES = 3;

Adafruit_BME280 bme;
Adafruit_MPU6050 mpu;
Preferences preferences;
bool bmeReady = false;
bool mpuReady = false;
unsigned long lastSendMs = 0;
uint32_t sequenceNumber = 0;

bool connectWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  const unsigned long startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < WIFI_TIMEOUT_MS) {
    delay(250);
  }
  return WiFi.status() == WL_CONNECTED;
}

String utcTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 1000)) {
    return "";
  }
  char buffer[25];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
  return String(buffer);
}

enum DistanceReadStatus {
  DISTANCE_OK,
  DISTANCE_TIMEOUT,
  DISTANCE_OUT_OF_RANGE,
};

DistanceReadStatus readDistanceCm(float& distanceCm) {
  digitalWrite(JSN_TRIGGER_PIN, LOW);
  delayMicroseconds(3);
  digitalWrite(JSN_TRIGGER_PIN, HIGH);
  delayMicroseconds(12);
  digitalWrite(JSN_TRIGGER_PIN, LOW);

  const unsigned long duration = pulseIn(JSN_ECHO_PIN, HIGH, JSN_TIMEOUT_US);
  if (duration == 0) {
    return DISTANCE_TIMEOUT;
  }
  distanceCm = (duration * 0.0343f) / 2.0f;
  return distanceCm >= 0.0f && distanceCm <= 600.0f ? DISTANCE_OK : DISTANCE_OUT_OF_RANGE;
}

float calculateInclinationDeg(float accelX, float accelY, float accelZ) {
  const float magnitude = sqrtf(accelX * accelX + accelY * accelY + accelZ * accelZ);
  if (magnitude <= 0.001f) {
    return NAN;
  }
  const float vertical = fabsf(accelZ) / magnitude;
  return acosf(constrain(vertical, 0.0f, 1.0f)) * 180.0f / PI;
}

float calculatePitchDeg(float accelX, float accelY, float accelZ) {
  return atan2f(accelY, sqrtf(accelX * accelX + accelZ * accelZ)) * 180.0f / PI;
}

float calculateRollDeg(float accelX, float accelY, float accelZ) {
  return atan2f(-accelX, accelZ) * 180.0f / PI;
}

uint32_t nextSequenceNumber() {
  const uint32_t current = sequenceNumber;
  sequenceNumber++;
  preferences.putUInt("sequence", sequenceNumber);
  return current;
}

void appendBme280(JsonDocument& doc) {
  JsonObject bmePayload = doc.createNestedObject("bme280");
  if (!bmeReady) {
    return;
  }
  const float temperatureC = bme.readTemperature();
  const float humidityPct = bme.readHumidity();
  const float pressureHpa = bme.readPressure() / 100.0f;
  if (!isnan(temperatureC)) bmePayload["temperature_c"] = temperatureC;
  if (!isnan(humidityPct)) bmePayload["humidity_pct"] = humidityPct;
  if (!isnan(pressureHpa)) bmePayload["pressure_hpa"] = pressureHpa;
}

void appendMpu6050(JsonDocument& doc) {
  JsonObject mpuPayload = doc.createNestedObject("mpu6050");
  if (!mpuReady) {
    return;
  }
  sensors_event_t acceleration;
  sensors_event_t gyro;
  sensors_event_t temperature;
  mpu.getEvent(&acceleration, &gyro, &temperature);

  // Adafruit_Sensor returns acceleration in m/s2, which is the API contract.
  const float accelX = acceleration.acceleration.x;
  const float accelY = acceleration.acceleration.y;
  const float accelZ = acceleration.acceleration.z;
  mpuPayload["accel_x"] = accelX;
  mpuPayload["accel_y"] = accelY;
  mpuPayload["accel_z"] = accelZ;

  const float inclinationDeg = calculateInclinationDeg(accelX, accelY, accelZ);
  const float pitchDeg = calculatePitchDeg(accelX, accelY, accelZ);
  const float rollDeg = calculateRollDeg(accelX, accelY, accelZ);
  if (!isnan(pitchDeg)) mpuPayload["pitch"] = pitchDeg;
  if (!isnan(rollDeg)) mpuPayload["roll"] = rollDeg;
  if (!isnan(inclinationDeg)) {
    mpuPayload["inclination_deg"] = inclinationDeg;
  }
}

void appendJsnSr04t(JsonDocument& doc) {
  JsonObject jsnPayload = doc.createNestedObject("jsn_sr04t");
  float distanceCm = 0.0f;
  const DistanceReadStatus status = readDistanceCm(distanceCm);
  if (status == DISTANCE_TIMEOUT) {
    jsnPayload["timeout"] = true;
    return;
  }
  if (status == DISTANCE_OUT_OF_RANGE) {
    jsnPayload["out_of_range"] = true;
    return;
  }
  jsnPayload["distance_cm"] = distanceCm;
}

bool sendTelemetry() {
  if (!connectWifi()) {
    Serial.println("AgroGuardian: Wi-Fi indisponivel");
    return false;
  }

  if (!String(AGROGUARDIAN_API_URL).startsWith("https://")) {
    Serial.println("AgroGuardian: configure uma URL publica HTTPS.");
    return false;
  }
  if (strlen(AGROGUARDIAN_TLS_ROOT_CA) == 0) {
    Serial.println("AgroGuardian: configure o certificado raiz da API HTTPS.");
    return false;
  }

  StaticJsonDocument<1024> doc;
  doc["device_id"] = DEVICE_ID;
  doc["sequence_number"] = nextSequenceNumber();
  doc["operation_type"] = "campo";
  doc["firmware_version"] = FIRMWARE_VERSION;
  const String timestamp = utcTimestamp();
  if (timestamp.length() > 0) {
    doc["timestamp"] = timestamp;
  }
  appendBme280(doc);
  appendMpu6050(doc);
  appendJsnSr04t(doc);

  String body;
  serializeJson(doc, body);
  for (int attempt = 1; attempt <= HTTP_RETRIES; attempt++) {
    WiFiClientSecure secureClient;
    secureClient.setCACert(AGROGUARDIAN_TLS_ROOT_CA);
    HTTPClient http;
    http.setConnectTimeout(8000);
    http.setTimeout(HTTP_TIMEOUT_MS);
    if (!http.begin(secureClient, AGROGUARDIAN_API_URL)) {
      Serial.println("AgroGuardian: URL invalida");
      return false;
    }
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-ID", DEVICE_ID);
    http.addHeader("X-API-Key", ESP32_API_KEY);
    const int statusCode = http.POST(body);
    const String response = http.getString();
    http.end();

    Serial.printf("AgroGuardian tentativa %d: HTTP %d\n", attempt, statusCode);
    if (statusCode >= 200 && statusCode < 300) {
      StaticJsonDocument<384> responseDoc;
      if (deserializeJson(responseDoc, response) == DeserializationError::Ok) {
        const char* riskLevel = responseDoc["risk_level"] | "indisponivel";
        Serial.printf("AgroGuardian risco atualizado: %s\n", riskLevel);
      }
      Serial.println(response);
      return true;
    }
    if (statusCode == 401 || statusCode == 403 || statusCode == 409 || statusCode == 422) {
      Serial.println(response);
      return false;
    }
    delay(500 * attempt);
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  pinMode(JSN_TRIGGER_PIN, OUTPUT);
  pinMode(JSN_ECHO_PIN, INPUT);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  if (preferences.begin("agroguardian", false)) {
    sequenceNumber = preferences.getUInt("sequence", 0);
  } else {
    Serial.println("AgroGuardian: NVS indisponivel; sequence_number pode reiniciar.");
  }
  bmeReady = bme.begin(0x76) || bme.begin(0x77);
  mpuReady = mpu.begin();
  if (mpuReady) {
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  }
  connectWifi();
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
}

void loop() {
  const unsigned long now = millis();
  if (now - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = now;
    sendTelemetry();
  }
}
