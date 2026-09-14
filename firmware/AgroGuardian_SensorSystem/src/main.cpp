#include <Arduino.h>
#include <Wire.h>
#include <Preferences.h>
#include <math.h>
#include <time.h>
#include <cstring>

#include "Config.h"
#include "TlsRootCa.h"

#include <Adafruit_BME280.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <MPU6050_tockn.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#if AGRO_ENABLE_LOCAL_WEBSERVER
#include <WebServer.h>
#endif

namespace {

constexpr float STANDARD_GRAVITY_M_S2 = 9.80665f;
constexpr time_t MIN_VALID_EPOCH = 1704067200;  // 2024-01-01T00:00:00Z

MPU6050 mpu(Wire);
Adafruit_BME280 bme;
Preferences preferences;

bool bmeReady = false;
bool mpuReady = false;
bool sequencePersistenceReady = false;

#if AGRO_ENABLE_LOCAL_WEBSERVER
WebServer server(80);
bool localWebServerStarted = false;
#endif

struct UltrasonicSnapshot {
  float distanceCm = NAN;
  bool timeout = false;
  bool outOfRange = false;
};

struct SensorSnapshot {
  float temperatureC = NAN;
  float airHumidityPct = NAN;
  float pressureHpa = NAN;
  float soilMoisturePct = NAN;
  float accelXMss = NAN;
  float accelYMss = NAN;
  float accelZMss = NAN;
  float gyroXDps = NAN;
  float gyroYDps = NAN;
  float gyroZDps = NAN;
  float pitchDeg = NAN;
  float rollDeg = NAN;
  float inclinationDeg = NAN;
  UltrasonicSnapshot ultrasonic;
  unsigned long readAtMs = 0;
};

SensorSnapshot reading;

unsigned long lastSensorReadMs = 0;
unsigned long lastSendMs = 0;
unsigned long lastWifiAttemptMs = 0;
unsigned long sendDeferredUntilMs = 0;
String pendingPayloadBody;
bool pendingPayloadReady = false;

uint32_t nextSequence = 0;
uint32_t reservedSequenceLimit = 0;

int lastHttpStatus = 0;
long lastTelemetryId = -1;
float lastRiskScore = NAN;
String lastRiskLevel = "-";
String lastTelemetryStatus = "-";
String lastQualityStatus = "-";
String lastError;
unsigned long successfulSends = 0;
unsigned long failedSends = 0;

bool timeReached(unsigned long target) {
  return static_cast<long>(millis() - target) >= 0;
}

bool finiteInRange(float value, float minimum, float maximum) {
  return isfinite(value) && value >= minimum && value <= maximum;
}

float rounded(float value, float factor) {
  return roundf(value * factor) / factor;
}

void cooperativeDelay(unsigned long durationMs) {
  const unsigned long startedAt = millis();
  while (millis() - startedAt < durationMs) {
#if AGRO_ENABLE_LOCAL_WEBSERVER
    server.handleClient();
#endif
    delay(10);
  }
}

bool secretsConfigured() {
  if (AGROGUARDIAN_USING_EXAMPLE_SECRETS) {
    return false;
  }
  return strlen(AGRO_WIFI_SSID) > 0 &&
         strlen(AGRO_WIFI_PASSWORD) > 0 &&
         strlen(AGROGUARDIAN_DEVICE_ID) > 0 &&
         strlen(AGROGUARDIAN_DEVICE_API_KEY) > 0 &&
         strcmp(AGRO_WIFI_SSID, "SUA_REDE_WIFI_2G") != 0 &&
         strcmp(AGROGUARDIAN_DEVICE_API_KEY, "COLE_AQUI_A_API_KEY_DO_DISPOSITIVO") != 0;
}

bool apiUsesHttps() {
  return String(AGROGUARDIAN_API_URL).startsWith("https://");
}

bool connectWifi(unsigned long timeoutMs) {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }
  if (!secretsConfigured()) {
    lastError = "Crie include/Secrets.h e preencha Wi-Fi, Device ID e API key";
    Serial.println("[CONFIG] " + lastError);
    return false;
  }

  lastWifiAttemptMs = millis();
  Serial.printf("[WiFi] Conectando em \"%s\"...\n", AGRO_WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(AGRO_WIFI_SSID, AGRO_WIFI_PASSWORD);

  const unsigned long startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < timeoutMs) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() != WL_CONNECTED) {
    lastError = "Wi-Fi indisponivel";
    Serial.println("[WiFi] Falha; uma nova tentativa sera feita automaticamente.");
    return false;
  }

  Serial.print("[WiFi] IP por DHCP: ");
  Serial.println(WiFi.localIP());
  Serial.printf("[WiFi] RSSI: %d dBm\n", WiFi.RSSI());
  return true;
}

bool clockIsSynchronized() {
  return time(nullptr) >= MIN_VALID_EPOCH;
}

bool synchronizeClock(unsigned long timeoutMs) {
  if (clockIsSynchronized()) {
    return true;
  }
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  Serial.println("[NTP] Sincronizando horario UTC...");
  configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
  const unsigned long startedAt = millis();
  while (!clockIsSynchronized() && millis() - startedAt < timeoutMs) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (!clockIsSynchronized()) {
    lastError = "NTP indisponivel; HTTPS seguro requer relogio correto";
    Serial.println("[NTP] " + lastError);
    return false;
  }
  Serial.println("[NTP] Horario sincronizado.");
  return true;
}

String utcTimestamp() {
  if (!clockIsSynchronized()) {
    return "";
  }
  const time_t now = time(nullptr);
  struct tm utcTime;
  gmtime_r(&now, &utcTime);
  char buffer[25];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &utcTime);
  return String(buffer);
}

bool i2cDevicePresent(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void initializeSensors() {
  Wire.begin(AGRO_I2C_SDA_PIN, AGRO_I2C_SCL_PIN);
  Wire.setClock(100000);

  bmeReady = bme.begin(AGRO_BME280_ADDRESS_PRIMARY) ||
             bme.begin(AGRO_BME280_ADDRESS_SECONDARY);
  Serial.println(bmeReady ? "[SENSOR] BME280 pronto." : "[SENSOR] BME280 nao encontrado em 0x76/0x77.");

  if (i2cDevicePresent(AGRO_MPU6050_ADDRESS)) {
    mpu.begin();
    Serial.println("[SENSOR] Mantenha o MPU-6050 parado durante a calibracao.");
    mpu.calcGyroOffsets(true, 1000, 1000);
    mpuReady = true;
    Serial.println("[SENSOR] MPU-6050 pronto.");
  } else {
    Serial.println("[SENSOR] MPU-6050 nao encontrado em 0x68.");
  }

#if AGRO_ENABLE_ULTRASONIC
  pinMode(AGRO_ULTRASONIC_TRIGGER_PIN, OUTPUT);
  pinMode(AGRO_ULTRASONIC_ECHO_PIN, INPUT);
  digitalWrite(AGRO_ULTRASONIC_TRIGGER_PIN, LOW);
#endif

#if AGRO_ENABLE_SOIL_SENSOR
  analogReadResolution(12);
  pinMode(AGRO_SOIL_ADC_PIN, INPUT);
#endif
}

UltrasonicSnapshot readUltrasonic() {
  UltrasonicSnapshot result;
#if AGRO_ENABLE_ULTRASONIC
  float validSamples[3];
  int validCount = 0;
  int timeoutCount = 0;

  for (int i = 0; i < 3; ++i) {
    digitalWrite(AGRO_ULTRASONIC_TRIGGER_PIN, LOW);
    delayMicroseconds(3);
    digitalWrite(AGRO_ULTRASONIC_TRIGGER_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(AGRO_ULTRASONIC_TRIGGER_PIN, LOW);

    const unsigned long duration = pulseIn(
      AGRO_ULTRASONIC_ECHO_PIN,
      HIGH,
      AGRO_ULTRASONIC_TIMEOUT_US
    );
    if (duration == 0) {
      ++timeoutCount;
    } else {
      const float distanceCm = (duration * 0.0343f) / 2.0f;
      if (distanceCm >= AGRO_ULTRASONIC_MIN_CM && distanceCm <= AGRO_ULTRASONIC_MAX_CM) {
        validSamples[validCount++] = distanceCm;
      }
    }
    delay(30);
  }

  for (int i = 0; i < validCount - 1; ++i) {
    for (int j = i + 1; j < validCount; ++j) {
      if (validSamples[j] < validSamples[i]) {
        const float temporary = validSamples[i];
        validSamples[i] = validSamples[j];
        validSamples[j] = temporary;
      }
    }
  }

  if (validCount == 1) {
    result.distanceCm = validSamples[0];
  } else if (validCount == 2) {
    result.distanceCm = (validSamples[0] + validSamples[1]) / 2.0f;
  } else if (validCount == 3) {
    result.distanceCm = validSamples[1];
  } else {
    result.timeout = timeoutCount == 3;
    result.outOfRange = !result.timeout;
  }
#endif
  return result;
}

#if AGRO_ENABLE_SOIL_SENSOR
float readSoilMoisturePct() {
  if (AGRO_SOIL_ADC_DRY == AGRO_SOIL_ADC_WET) {
    return NAN;
  }
  long total = 0;
  for (int i = 0; i < 10; ++i) {
    total += analogRead(AGRO_SOIL_ADC_PIN);
    delay(5);
  }
  const float raw = total / 10.0f;
  const float moisture = (AGRO_SOIL_ADC_DRY - raw) * 100.0f /
                         static_cast<float>(AGRO_SOIL_ADC_DRY - AGRO_SOIL_ADC_WET);
  return constrain(moisture, 0.0f, 100.0f);
}
#endif

void updateSensors() {
  SensorSnapshot snapshot;

  if (bmeReady) {
    const float temperature = bme.readTemperature();
    const float humidity = bme.readHumidity();
    const float pressure = bme.readPressure() / 100.0f;
    if (finiteInRange(temperature, -40.0f, 85.0f)) snapshot.temperatureC = temperature;
    if (finiteInRange(humidity, 0.0f, 100.0f)) snapshot.airHumidityPct = humidity;
    if (finiteInRange(pressure, 300.0f, 1100.0f)) snapshot.pressureHpa = pressure;
  }

  if (mpuReady) {
    mpu.update();
    const float accelX = mpu.getAccX() * STANDARD_GRAVITY_M_S2;
    const float accelY = mpu.getAccY() * STANDARD_GRAVITY_M_S2;
    const float accelZ = mpu.getAccZ() * STANDARD_GRAVITY_M_S2;
    const float gyroX = mpu.getGyroX();
    const float gyroY = mpu.getGyroY();
    const float gyroZ = mpu.getGyroZ();
    const float roll = mpu.getAngleX();
    const float pitch = mpu.getAngleY();

    if (finiteInRange(accelX, -160.0f, 160.0f)) snapshot.accelXMss = accelX;
    if (finiteInRange(accelY, -160.0f, 160.0f)) snapshot.accelYMss = accelY;
    if (finiteInRange(accelZ, -160.0f, 160.0f)) snapshot.accelZMss = accelZ;
    if (finiteInRange(gyroX, -5000.0f, 5000.0f)) snapshot.gyroXDps = gyroX;
    if (finiteInRange(gyroY, -5000.0f, 5000.0f)) snapshot.gyroYDps = gyroY;
    if (finiteInRange(gyroZ, -5000.0f, 5000.0f)) snapshot.gyroZDps = gyroZ;
    if (finiteInRange(pitch, -180.0f, 180.0f)) snapshot.pitchDeg = pitch;
    if (finiteInRange(roll, -180.0f, 180.0f)) snapshot.rollDeg = roll;
    if (isfinite(snapshot.pitchDeg) || isfinite(snapshot.rollDeg)) {
      const float absolutePitch = isfinite(snapshot.pitchDeg) ? fabsf(snapshot.pitchDeg) : 0.0f;
      const float absoluteRoll = isfinite(snapshot.rollDeg) ? fabsf(snapshot.rollDeg) : 0.0f;
      snapshot.inclinationDeg = max(absolutePitch, absoluteRoll);
    }
  }

  snapshot.ultrasonic = readUltrasonic();

#if AGRO_ENABLE_SOIL_SENSOR
  snapshot.soilMoisturePct = readSoilMoisturePct();
#endif

  snapshot.readAtMs = millis();
  reading = snapshot;
}

bool reserveSequenceBlock() {
  if (!sequencePersistenceReady) {
    return false;
  }
  const uint32_t blockStart = preferences.getUInt("seq_next", 0);
  const uint32_t blockEnd = blockStart + AGRO_SEQUENCE_RESERVATION_SIZE;
  if (blockEnd < blockStart || blockEnd == blockStart) {
    lastError = "Contador sequence_number esgotado";
    return false;
  }
  if (preferences.putUInt("seq_next", blockEnd) != sizeof(uint32_t)) {
    lastError = "Falha ao reservar sequence_number no NVS";
    return false;
  }
  nextSequence = blockStart;
  reservedSequenceLimit = blockEnd;
  return true;
}

bool acquireSequence(uint32_t& sequence) {
  if (!sequencePersistenceReady) {
    return false;
  }
  if (nextSequence == reservedSequenceLimit && !reserveSequenceBlock()) {
    return false;
  }
  sequence = nextSequence++;
  return true;
}

void initializeSequencePersistence() {
  sequencePersistenceReady = preferences.begin("agroguardian", false);
  if (!sequencePersistenceReady) {
    Serial.println("[NVS] Indisponivel; sequence_number sera omitido.");
    return;
  }
  if (!reserveSequenceBlock()) {
    sequencePersistenceReady = false;
    Serial.println("[NVS] Falha ao reservar contador; sequence_number sera omitido.");
    return;
  }
  Serial.printf("[NVS] sequence_number reservado a partir de %lu.\n", static_cast<unsigned long>(nextSequence));
}

void buildPayload(JsonDocument& document, bool includeSequence, uint32_t sequence) {
  document["device_id"] = AGROGUARDIAN_DEVICE_ID;
  document["operation_type"] = AGROGUARDIAN_OPERATION_TYPE;
  document["firmware_version"] = AGROGUARDIAN_FIRMWARE_VERSION;
  if (includeSequence) {
    document["sequence_number"] = sequence;
  }

  const String timestamp = utcTimestamp();
  if (timestamp.length() > 0) {
    document["timestamp"] = timestamp;
  }

  if (isfinite(reading.temperatureC) || isfinite(reading.airHumidityPct) || isfinite(reading.pressureHpa)) {
    JsonObject bmePayload = document["bme280"].to<JsonObject>();
    if (isfinite(reading.temperatureC)) bmePayload["temperature_c"] = rounded(reading.temperatureC, 10.0f);
    if (isfinite(reading.airHumidityPct)) bmePayload["humidity_pct"] = rounded(reading.airHumidityPct, 10.0f);
    if (isfinite(reading.pressureHpa)) bmePayload["pressure_hpa"] = rounded(reading.pressureHpa, 10.0f);
  }

  if (mpuReady) {
    JsonObject mpuPayload = document["mpu6050"].to<JsonObject>();
    if (isfinite(reading.accelXMss)) mpuPayload["accel_x"] = rounded(reading.accelXMss, 1000.0f);
    if (isfinite(reading.accelYMss)) mpuPayload["accel_y"] = rounded(reading.accelYMss, 1000.0f);
    if (isfinite(reading.accelZMss)) mpuPayload["accel_z"] = rounded(reading.accelZMss, 1000.0f);
    if (isfinite(reading.gyroXDps)) mpuPayload["gyro_x"] = rounded(reading.gyroXDps, 100.0f);
    if (isfinite(reading.gyroYDps)) mpuPayload["gyro_y"] = rounded(reading.gyroYDps, 100.0f);
    if (isfinite(reading.gyroZDps)) mpuPayload["gyro_z"] = rounded(reading.gyroZDps, 100.0f);
    if (isfinite(reading.pitchDeg)) mpuPayload["pitch"] = rounded(reading.pitchDeg, 10.0f);
    if (isfinite(reading.rollDeg)) mpuPayload["roll"] = rounded(reading.rollDeg, 10.0f);
    if (isfinite(reading.inclinationDeg)) mpuPayload["inclination_deg"] = rounded(reading.inclinationDeg, 10.0f);
  }

#if AGRO_ENABLE_ULTRASONIC
  JsonObject ultrasonicPayload = document["ultrasonic"].to<JsonObject>();
  ultrasonicPayload["sensor_model"] = AGRO_ULTRASONIC_MODEL;
  if (isfinite(reading.ultrasonic.distanceCm)) {
    ultrasonicPayload["distance_cm"] = rounded(reading.ultrasonic.distanceCm, 10.0f);
  } else {
    ultrasonicPayload["timeout"] = reading.ultrasonic.timeout;
    ultrasonicPayload["out_of_range"] = reading.ultrasonic.outOfRange;
  }
#endif

#if AGRO_ENABLE_SOIL_SENSOR
  if (isfinite(reading.soilMoisturePct)) {
    document["soil_moisture_pct"] = rounded(reading.soilMoisturePct, 10.0f);
  }
#endif

#if AGRO_ENABLE_FIXED_LOCATION
  JsonObject gpsPayload = document["gps"].to<JsonObject>();
  gpsPayload["latitude"] = AGRO_FIXED_LATITUDE;
  gpsPayload["longitude"] = AGRO_FIXED_LONGITUDE;
#endif
}

bool statusCanBeRetried(int status) {
  return status <= 0 || status == 408 || status == 425 || status == 429 || status >= 500;
}

void parseAcceptedResponse(const String& response) {
  JsonDocument document;
  const DeserializationError error = deserializeJson(document, response);
  if (error) {
    lastError = "Resposta 2xx sem JSON valido";
    Serial.println("[API] " + lastError);
    return;
  }

  lastTelemetryId = document["telemetry_id"] | -1L;
  lastRiskScore = document["risk_score"] | NAN;
  lastRiskLevel = document["risk_level"] | "-";
  lastTelemetryStatus = document["telemetry_status"] | "-";
  lastQualityStatus = document["data_quality_status"] | "-";
  const bool riskUpdated = document["risk_updated"] | false;

  Serial.printf(
    "[API] accepted telemetry_id=%ld risco=%.2f nivel=%s atualizado=%s qualidade=%s\n",
    lastTelemetryId,
    lastRiskScore,
    lastRiskLevel.c_str(),
    riskUpdated ? "sim" : "nao",
    lastQualityStatus.c_str()
  );
}

bool sendTelemetry() {
  if (!apiUsesHttps()) {
    lastError = "AGROGUARDIAN_API_URL deve usar https://";
    Serial.println("[CONFIG] " + lastError);
    ++failedSends;
    return false;
  }
  if (!connectWifi(AGRO_WIFI_CONNECT_TIMEOUT_MS)) {
    ++failedSends;
    return false;
  }
  if (!synchronizeClock(AGRO_NTP_SYNC_TIMEOUT_MS)) {
    ++failedSends;
    return false;
  }

  if (!pendingPayloadReady) {
    uint32_t sequence = 0;
    const bool hasSequence = acquireSequence(sequence);
    JsonDocument payload;
    buildPayload(payload, hasSequence, sequence);
    pendingPayloadBody = "";
    serializeJson(payload, pendingPayloadBody);
    pendingPayloadReady = true;
  } else {
    Serial.println("[HTTP] Reenviando a leitura pendente com o mesmo sequence_number.");
  }

  Serial.printf("[HTTP] POST %s (%u bytes)\n", AGROGUARDIAN_API_URL, pendingPayloadBody.length());
  Serial.println("[HTTP] " + pendingPayloadBody);

  String finalResponse;
  for (int attempt = 1; attempt <= AGRO_HTTP_RETRIES; ++attempt) {
    WiFiClientSecure secureClient;
    secureClient.setCACert(AGROGUARDIAN_TLS_ROOT_CA);

    HTTPClient http;
    http.setConnectTimeout(AGRO_HTTP_CONNECT_TIMEOUT_MS);
    http.setTimeout(AGRO_HTTP_TIMEOUT_MS);
    const char* responseHeaders[] = {"Retry-After"};
    http.collectHeaders(responseHeaders, 1);

    if (!http.begin(secureClient, AGROGUARDIAN_API_URL)) {
      lastHttpStatus = 0;
      finalResponse = "URL HTTPS invalida";
    } else {
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-Device-ID", AGROGUARDIAN_DEVICE_ID);
      http.addHeader("X-API-Key", AGROGUARDIAN_DEVICE_API_KEY);
      http.addHeader("User-Agent", "AgroGuardian-ESP32/" AGROGUARDIAN_FIRMWARE_VERSION);

      lastHttpStatus = http.POST(pendingPayloadBody);
      finalResponse = lastHttpStatus > 0 ? http.getString() : http.errorToString(lastHttpStatus);

      if (lastHttpStatus == 429) {
        long retryAfterSeconds = http.header("Retry-After").toInt();
        if (retryAfterSeconds <= 0) retryAfterSeconds = 60;
        retryAfterSeconds = constrain(retryAfterSeconds, 1L, 3600L);
        sendDeferredUntilMs = millis() + static_cast<unsigned long>(retryAfterSeconds) * 1000UL;
      }
      http.end();
    }

    Serial.printf("[HTTP] tentativa %d/%d: status %d\n", attempt, AGRO_HTTP_RETRIES, lastHttpStatus);
    if (lastHttpStatus >= 200 && lastHttpStatus < 300) {
      lastError = "";
      parseAcceptedResponse(finalResponse);
      pendingPayloadBody = "";
      pendingPayloadReady = false;
      ++successfulSends;
      return true;
    }

    lastError = finalResponse.substring(0, 300);
    Serial.println("[HTTP] " + lastError);
    if (lastHttpStatus == 401) {
      Serial.println("[HTTP] Confira Device ID, API key e cadastro ativo do dispositivo.");
    } else if (lastHttpStatus == 403) {
      Serial.println("[HTTP] Dispositivo desativado ou Device ID divergente.");
    } else if (lastHttpStatus == 409) {
      Serial.println("[HTTP] Confira o vinculo com equipamento/fazenda ou sequence_number duplicado.");
    } else if (lastHttpStatus == 422) {
      Serial.println("[HTTP] A API rejeitou formato, unidade ou faixa de algum sensor.");
    }

    if (!statusCanBeRetried(lastHttpStatus) || lastHttpStatus == 429 || attempt == AGRO_HTTP_RETRIES) {
      break;
    }
    cooperativeDelay(1000UL << (attempt - 1));
  }

  if (!statusCanBeRetried(lastHttpStatus)) {
    pendingPayloadBody = "";
    pendingPayloadReady = false;
  } else {
    Serial.println("[HTTP] Leitura mantida em RAM para o proximo ciclo de envio.");
  }
  ++failedSends;
  return false;
}

#if AGRO_ENABLE_LOCAL_WEBSERVER
void handleStatusJson() {
  JsonDocument document;
  buildPayload(document, false, 0);
  document["_uptime_s"] = millis() / 1000UL;
  document["_wifi_connected"] = WiFi.status() == WL_CONNECTED;
  if (WiFi.status() == WL_CONNECTED) document["_wifi_rssi_dbm"] = WiFi.RSSI();
  document["_last_http_status"] = lastHttpStatus;
  document["_successful_sends"] = successfulSends;
  document["_failed_sends"] = failedSends;
  document["_pending_retry"] = pendingPayloadReady;
  if (lastTelemetryId >= 0) document["_last_telemetry_id"] = lastTelemetryId;
  if (isfinite(lastRiskScore)) document["_last_risk_score"] = lastRiskScore;
  document["_last_risk_level"] = lastRiskLevel;
  document["_telemetry_status"] = lastTelemetryStatus;
  document["_quality_status"] = lastQualityStatus;
  document["_last_error"] = lastError;

  String response;
  serializeJson(document, response);
  server.send(200, "application/json; charset=utf-8", response);
}

String tableRow(const char* label, float value, const char* unit, int decimalPlaces) {
  const String formatted = isfinite(value) ? String(value, decimalPlaces) : String("--");
  return "<tr><td>" + String(label) + "</td><td><b>" + formatted + "</b> " + String(unit) + "</td></tr>";
}

void handleHome() {
  String html = "<!doctype html><html lang='pt-br'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<meta http-equiv='refresh' content='5'><title>AgroGuardian ESP32</title><style>"
                "body{font-family:system-ui,sans-serif;background:#071016;color:#edf7f5;padding:24px}"
                "table{border-collapse:collapse;margin-top:12px}td{padding:6px 14px;border-bottom:1px solid #24514c}"
                "h1,a{color:#49ead8}small{color:#9db7b3}</style></head><body><h1>AgroGuardian - ";
  html += AGROGUARDIAN_DEVICE_ID;
  html += "</h1><table>";
  html += tableRow("Temperatura", reading.temperatureC, "&deg;C", 1);
  html += tableRow("Umidade do ar", reading.airHumidityPct, "%", 1);
  html += tableRow("Pressao", reading.pressureHpa, "hPa", 1);
  html += tableRow("Umidade do solo", reading.soilMoisturePct, "%", 1);
  html += tableRow("Pitch", reading.pitchDeg, "&deg;", 1);
  html += tableRow("Roll", reading.rollDeg, "&deg;", 1);
  html += tableRow("Distancia HC-SR04", reading.ultrasonic.distanceCm, "cm", 1);
  html += tableRow("Ultimo risco", lastRiskScore, "", 2);
  html += "<tr><td>Nivel de risco</td><td><b>" + lastRiskLevel + "</b></td></tr>";
  html += "<tr><td>HTTP</td><td><b>" + String(lastHttpStatus) + "</b></td></tr>";
  html += "<tr><td>Envios OK / falha</td><td><b>" + String(successfulSends) + " / " + String(failedSends) + "</b></td></tr>";
  html += "</table><p><small>Destino: " + String(AGROGUARDIAN_API_URL) + "</small></p>";
  if (lastError.length() > 0) html += "<p><small>Ultimo erro: " + lastError + "</small></p>";
  html += "<p><a href='/json'>JSON de diagnostico</a></p></body></html>";
  server.send(200, "text/html; charset=utf-8", html);
}

void startLocalWebServer() {
  if (localWebServerStarted || WiFi.status() != WL_CONNECTED) {
    return;
  }
  server.on("/", handleHome);
  server.on("/json", handleStatusJson);
  server.begin();
  localWebServerStarted = true;
  Serial.print("[WEB] Diagnostico local: http://");
  Serial.print(WiFi.localIP());
  Serial.println('/');
}
#endif

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println("\n=== AgroGuardian ESP32 - telemetria segura ===");

  initializeSequencePersistence();
  initializeSensors();
  connectWifi(AGRO_WIFI_CONNECT_TIMEOUT_MS);
  synchronizeClock(AGRO_NTP_SYNC_TIMEOUT_MS);

#if AGRO_ENABLE_LOCAL_WEBSERVER
  startLocalWebServer();
#endif

  updateSensors();
  lastSensorReadMs = millis();
  lastSendMs = millis() - AGRO_SEND_INTERVAL_MS;
}

void loop() {
#if AGRO_ENABLE_LOCAL_WEBSERVER
  server.handleClient();
#endif

  const unsigned long now = millis();
  if (now - lastSensorReadMs >= AGRO_SENSOR_READ_INTERVAL_MS) {
    lastSensorReadMs = now;
    updateSensors();
  }

  if (WiFi.status() != WL_CONNECTED && now - lastWifiAttemptMs >= AGRO_WIFI_RETRY_INTERVAL_MS) {
    connectWifi(AGRO_WIFI_CONNECT_TIMEOUT_MS);
  }

#if AGRO_ENABLE_LOCAL_WEBSERVER
  startLocalWebServer();
#endif

  if (now - lastSendMs >= AGRO_SEND_INTERVAL_MS && timeReached(sendDeferredUntilMs)) {
    lastSendMs = now;
    updateSensors();
    sendTelemetry();
  }

  delay(5);
}
