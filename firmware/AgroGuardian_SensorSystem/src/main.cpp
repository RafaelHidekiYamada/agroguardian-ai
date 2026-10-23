#include <Arduino.h>
#include <Wire.h>
#include <Preferences.h>
#include <math.h>
#include <time.h>
#include <cstring>

#include "Config.h"
#include "TlsRootCa.h"

#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

#if AGRO_ENABLE_FLASH_BUFFER
#include <esp_system.h>
#include <sys/time.h>

#include "EspPartitionFlash.h"
#include "TelemetryRing.h"
#include "TimeAnchors.h"
#endif

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
bool sendDeferredActive = false;  // evita comparar com 0 apos 24,8 dias de uptime
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

// Estado compartilhado entre a tarefa do loop (sensores, servidor web) e a
// tarefa de rede. Strings so sao lidas/escritas com este mutex.
SemaphoreHandle_t stateMutex = nullptr;

void lockState() {
  if (stateMutex != nullptr) xSemaphoreTake(stateMutex, portMAX_DELAY);
}

void unlockState() {
  if (stateMutex != nullptr) xSemaphoreGive(stateMutex);
}

void setLastError(const String& message) {
  lockState();
  lastError = message;
  unlockState();
}

#if AGRO_ENABLE_FLASH_BUFFER
agro::EspPartitionFlash bufferFlash(AGRO_BUFFER_PARTITION_LABEL, AGRO_BUFFER_PARTITION_SUBTYPE);
agro::TelemetryRing bufferRing(bufferFlash);
// Todo o firmware usa o anel pela interface; um SdStore pode substituir este ponteiro.
agro::TelemetryStore* bufferStore = &bufferRing;
agro::TimeAnchors timeAnchors;
SemaphoreHandle_t ringMutex = nullptr;
TaskHandle_t networkTaskHandle = nullptr;

bool bufferReady = false;  // anel recuperado e tarefa de rede ativa
uint16_t currentBootId = 0;
uint8_t currentResetReason = 0;
bool anchorSetThisBoot = false;
volatile bool networkHealthy = false;  // true: gravacao no ritmo normal; false: ritmo offline
unsigned long lastRecordMs = 0;
uint32_t droppedBase = 0;       // descartados em boots anteriores (NVS)
uint32_t droppedPersisted = 0;  // descartados deste boot ja gravados no NVS
unsigned long recordWriteFailures = 0;
size_t currentBatchMax = AGRO_BATCH_MAX_RECORDS;
bool batchUnsupported = false;
unsigned long batchUnsupportedUntilMs = 0;
const char* uploadMode = "-";  // "single", "batch" ou "legacy"
agro::TelemetryRecord uploadBuffer[AGRO_BATCH_MAX_RECORDS];
#endif

bool bufferedUplinkActive() {
#if AGRO_ENABLE_FLASH_BUFFER
  return bufferReady;
#else
  return false;
#endif
}

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
    setLastError("Crie include/Secrets.h e preencha Wi-Fi, Device ID e API key");
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
    setLastError("Wi-Fi indisponivel");
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
    setLastError("NTP indisponivel; HTTPS seguro requer relogio correto");
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
#if AGRO_MPU_USE_LEVEL_REFERENCE
    Serial.println("[SENSOR] Inclinacao relativa a referencia de nivelamento (Config.h).");
#endif
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

#if AGRO_MPU_USE_LEVEL_REFERENCE
struct LevelTilt {
  bool valid = false;
  float pitchDeg = NAN;
  float rollDeg = NAN;
  float inclinationDeg = NAN;
};

struct Vec3 {
  float x, y, z;
};

Vec3 vecCross(const Vec3& a, const Vec3& b) {
  return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}

float vecDot(const Vec3& a, const Vec3& b) { return a.x * b.x + a.y * b.y + a.z * b.z; }

Vec3 vecNormalized(const Vec3& v) {
  const float length = sqrtf(vecDot(v, v));
  return {v.x / length, v.y / length, v.z / length};
}

// Inclinacao relativa a referencia de "nivelado" configurada em Config.h.
// Monta um referencial (direita, frente, cima) a partir do vetor de referencia e
// mede a gravidade atual nele: 0 graus = como na referencia, 180 = de cabeca para baixo.
LevelTilt tiltFromLevelReference(float accelX, float accelY, float accelZ) {
  static bool basisReady = false;
  static Vec3 up, forward, right;
  static bool filterReady = false;
  static Vec3 filtered;

  if (!basisReady) {
    up = vecNormalized({AGRO_MPU_LEVEL_REF_X, AGRO_MPU_LEVEL_REF_Y, AGRO_MPU_LEVEL_REF_Z});
    // Eixo do sensor menos alinhado com "cima" serve de base para "frente".
    Vec3 axis = {1.0f, 0.0f, 0.0f};
    float smallest = fabsf(up.x);
    if (fabsf(up.y) < smallest) {
      axis = {0.0f, 1.0f, 0.0f};
      smallest = fabsf(up.y);
    }
    if (fabsf(up.z) < smallest) axis = {0.0f, 0.0f, 1.0f};
    const float along = vecDot(axis, up);
    forward = vecNormalized({axis.x - along * up.x, axis.y - along * up.y, axis.z - along * up.z});
    right = vecCross(forward, up);
    basisReady = true;
  }

  LevelTilt tilt;
  const float magnitude = sqrtf(accelX * accelX + accelY * accelY + accelZ * accelZ);
  // Queda livre ou impacto forte: a gravidade nao e confiavel; nao atualiza a inclinacao.
  if (!isfinite(magnitude) || magnitude < 0.3f * STANDARD_GRAVITY_M_S2 || magnitude > 3.0f * STANDARD_GRAVITY_M_S2) {
    return tilt;
  }

  if (!filterReady) {
    filtered = {accelX, accelY, accelZ};
    filterReady = true;
  } else {
    filtered.x += AGRO_MPU_TILT_FILTER_ALPHA * (accelX - filtered.x);
    filtered.y += AGRO_MPU_TILT_FILTER_ALPHA * (accelY - filtered.y);
    filtered.z += AGRO_MPU_TILT_FILTER_ALPHA * (accelZ - filtered.z);
  }

  const float alongUp = vecDot(filtered, up);
  const float alongForward = vecDot(filtered, forward);
  const float alongRight = vecDot(filtered, right);
  const float filteredMagnitude = sqrtf(vecDot(filtered, filtered));
  if (filteredMagnitude < 1.0f) return tilt;

  constexpr float RAD_TO_DEG_F = 57.2957795f;
  tilt.pitchDeg = atan2f(alongForward, alongUp) * RAD_TO_DEG_F;
  tilt.rollDeg = atan2f(alongRight, alongUp) * RAD_TO_DEG_F;
  tilt.inclinationDeg = acosf(constrain(alongUp / filteredMagnitude, -1.0f, 1.0f)) * RAD_TO_DEG_F;
  tilt.valid = true;
  return tilt;
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
    float roll = mpu.getAngleX();
    float pitch = mpu.getAngleY();
    float levelInclination = NAN;
#if AGRO_MPU_USE_LEVEL_REFERENCE
    const LevelTilt levelTilt = tiltFromLevelReference(accelX, accelY, accelZ);
    roll = levelTilt.rollDeg;
    pitch = levelTilt.pitchDeg;
    levelInclination = levelTilt.inclinationDeg;
#endif

    if (finiteInRange(accelX, -160.0f, 160.0f)) snapshot.accelXMss = accelX;
    if (finiteInRange(accelY, -160.0f, 160.0f)) snapshot.accelYMss = accelY;
    if (finiteInRange(accelZ, -160.0f, 160.0f)) snapshot.accelZMss = accelZ;
    if (finiteInRange(gyroX, -5000.0f, 5000.0f)) snapshot.gyroXDps = gyroX;
    if (finiteInRange(gyroY, -5000.0f, 5000.0f)) snapshot.gyroYDps = gyroY;
    if (finiteInRange(gyroZ, -5000.0f, 5000.0f)) snapshot.gyroZDps = gyroZ;
    if (finiteInRange(pitch, -180.0f, 180.0f)) snapshot.pitchDeg = pitch;
    if (finiteInRange(roll, -180.0f, 180.0f)) snapshot.rollDeg = roll;
    if (isfinite(levelInclination)) {
      snapshot.inclinationDeg = levelInclination;
    } else if (isfinite(snapshot.pitchDeg) || isfinite(snapshot.rollDeg)) {
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
    setLastError("Contador sequence_number esgotado");
    return false;
  }
  if (preferences.putUInt("seq_next", blockEnd) != sizeof(uint32_t)) {
    setLastError("Falha ao reservar sequence_number no NVS");
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

// Blocos de sensores do JSON (BME280, MPU-6050, ultrassonico, solo, GPS fixo).
// Usado tanto pela leitura ao vivo quanto pelos registros recuperados do anel.
void appendSensorBlocks(JsonDocument& document, const SensorSnapshot& s, bool mpuPresent) {
  if (isfinite(s.temperatureC) || isfinite(s.airHumidityPct) || isfinite(s.pressureHpa)) {
    JsonObject bmePayload = document["bme280"].to<JsonObject>();
    if (isfinite(s.temperatureC)) bmePayload["temperature_c"] = rounded(s.temperatureC, 10.0f);
    if (isfinite(s.airHumidityPct)) bmePayload["humidity_pct"] = rounded(s.airHumidityPct, 10.0f);
    if (isfinite(s.pressureHpa)) bmePayload["pressure_hpa"] = rounded(s.pressureHpa, 10.0f);
  }

  if (mpuPresent) {
    JsonObject mpuPayload = document["mpu6050"].to<JsonObject>();
    if (isfinite(s.accelXMss)) mpuPayload["accel_x"] = rounded(s.accelXMss, 1000.0f);
    if (isfinite(s.accelYMss)) mpuPayload["accel_y"] = rounded(s.accelYMss, 1000.0f);
    if (isfinite(s.accelZMss)) mpuPayload["accel_z"] = rounded(s.accelZMss, 1000.0f);
    if (isfinite(s.gyroXDps)) mpuPayload["gyro_x"] = rounded(s.gyroXDps, 100.0f);
    if (isfinite(s.gyroYDps)) mpuPayload["gyro_y"] = rounded(s.gyroYDps, 100.0f);
    if (isfinite(s.gyroZDps)) mpuPayload["gyro_z"] = rounded(s.gyroZDps, 100.0f);
    if (isfinite(s.pitchDeg)) mpuPayload["pitch"] = rounded(s.pitchDeg, 10.0f);
    if (isfinite(s.rollDeg)) mpuPayload["roll"] = rounded(s.rollDeg, 10.0f);
    if (isfinite(s.inclinationDeg)) mpuPayload["inclination_deg"] = rounded(s.inclinationDeg, 10.0f);
  }

#if AGRO_ENABLE_ULTRASONIC
  JsonObject ultrasonicPayload = document["ultrasonic"].to<JsonObject>();
  ultrasonicPayload["sensor_model"] = AGRO_ULTRASONIC_MODEL;
  if (isfinite(s.ultrasonic.distanceCm)) {
    ultrasonicPayload["distance_cm"] = rounded(s.ultrasonic.distanceCm, 10.0f);
  } else {
    ultrasonicPayload["timeout"] = s.ultrasonic.timeout;
    ultrasonicPayload["out_of_range"] = s.ultrasonic.outOfRange;
  }
#endif

#if AGRO_ENABLE_SOIL_SENSOR
  if (isfinite(s.soilMoisturePct)) {
    document["soil_moisture_pct"] = rounded(s.soilMoisturePct, 10.0f);
  }
#endif

#if AGRO_ENABLE_FIXED_LOCATION
  JsonObject gpsPayload = document["gps"].to<JsonObject>();
  gpsPayload["latitude"] = AGRO_FIXED_LATITUDE;
  gpsPayload["longitude"] = AGRO_FIXED_LONGITUDE;
#endif
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

  appendSensorBlocks(document, reading, mpuReady);
}

bool statusCanBeRetried(int status) {
  return status <= 0 || status == 408 || status == 425 || status == 429 || status >= 500;
}

void parseAcceptedResponse(const String& response) {
  JsonDocument document;
  const DeserializationError error = deserializeJson(document, response);
  if (error) {
    setLastError("Resposta 2xx sem JSON valido");
    Serial.println("[API] " + lastError);
    return;
  }

  lockState();
  lastTelemetryId = document["telemetry_id"] | -1L;
  lastRiskScore = document["risk_score"] | NAN;
  lastRiskLevel = document["risk_level"] | "-";
  lastTelemetryStatus = document["telemetry_status"] | "-";
  lastQualityStatus = document["data_quality_status"] | "-";
  unlockState();
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

#if AGRO_ENABLE_FLASH_BUFFER

// ---------------------------------------------------------------------------
// Buffer store-and-forward em flash
//
// Fluxo: a cada intervalo, loop() le os sensores e GRAVA o registro no anel
// (write-ahead). A tarefa de rede (core 0) le do anel, do mais antigo ao mais
// novo, envia e so entao confirma (ack). Assim o fluxo online e o offline sao
// o mesmo e nada se perde em reinicio.
// ---------------------------------------------------------------------------

enum UploadResult {
  kUploadOk,        // algo foi confirmado (ou nada a enviar)
  kUploadRetryNow,  // mudou a estrategia (lote menor, endpoint legado): tentar ja
  kUploadDeferred,  // 429: aguardar Retry-After
  kUploadFailed,    // falha transitoria: backoff exponencial
};

const char* resetReasonName(uint8_t reason) {
  switch (reason) {
    case ESP_RST_POWERON: return "poweron";
    case ESP_RST_EXT: return "external";
    case ESP_RST_SW: return "software";
    case ESP_RST_PANIC: return "panic";
    case ESP_RST_INT_WDT: return "int_wdt";
    case ESP_RST_TASK_WDT: return "task_wdt";
    case ESP_RST_WDT: return "wdt";
    case ESP_RST_DEEPSLEEP: return "deepsleep";
    case ESP_RST_BROWNOUT: return "brownout";
    case ESP_RST_SDIO: return "sdio";
    default: return "unknown";
  }
}

const char* timeQualityName(agro::TimeQuality quality) {
  switch (quality) {
    case agro::kTimeSynced: return "synced";
    case agro::kTimeEstimated: return "estimated";
    default: return "unknown";
  }
}

String isoFromEpoch(uint32_t epochS) {
  const time_t seconds = static_cast<time_t>(epochS);
  struct tm utcTime;
  gmtime_r(&seconds, &utcTime);
  char buffer[25];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &utcTime);
  return String(buffer);
}

String jsonQuote(const char* text) {
  JsonDocument quoted;
  quoted.set(text);
  String result;
  serializeJson(quoted, result);
  return result;
}

String batchApiUrl() {
#ifdef AGROGUARDIAN_BATCH_API_URL
  return String(AGROGUARDIAN_BATCH_API_URL);
#else
  String url = AGROGUARDIAN_API_URL;
  const String legacySuffix = "/api/v1/iot/telemetry";
  if (url.endsWith(legacySuffix)) {
    url = url.substring(0, url.length() - legacySuffix.length()) + "/api/v1/telemetry/esp";
  }
  if (url.endsWith("/")) {
    url.remove(url.length() - 1);
  }
  return url + "/batch";
#endif
}

// --- Registro <-> leitura -------------------------------------------------

agro::TelemetryRecord makeRecord(const SensorSnapshot& s, uint32_t sequence) {
  agro::TelemetryRecord r;
  r.bootId = currentBootId;
  r.sequence = sequence;
  r.uptimeMs = static_cast<uint32_t>(millis());
  r.resetReason = currentResetReason;
  if (clockIsSynchronized()) {
    r.epochS = static_cast<uint32_t>(time(nullptr));
    r.flags |= agro::kFlagClockSynced;
  }
  if (bmeReady) r.flags |= agro::kFlagBmePresent;
  if (mpuReady) r.flags |= agro::kFlagMpuPresent;

  r.temperatureDeci = agro::scaleToI16(s.temperatureC, 10.0f);
  r.humidityDeci = agro::scaleToU16(s.airHumidityPct, 10.0f);
  r.pressureDeci = agro::scaleToU16(s.pressureHpa, 10.0f);
  r.accelMilli[0] = agro::scaleToI24(s.accelXMss, 1000.0f);
  r.accelMilli[1] = agro::scaleToI24(s.accelYMss, 1000.0f);
  r.accelMilli[2] = agro::scaleToI24(s.accelZMss, 1000.0f);
  bool gyroSaturated = false;
  r.gyroUnits[0] = agro::scaleGyro(s.gyroXDps, gyroSaturated);
  r.gyroUnits[1] = agro::scaleGyro(s.gyroYDps, gyroSaturated);
  r.gyroUnits[2] = agro::scaleGyro(s.gyroZDps, gyroSaturated);
  if (gyroSaturated) r.flags |= agro::kFlagGyroSaturated;
  r.pitchDeci = agro::scaleToI16(s.pitchDeg, 10.0f);
  r.rollDeci = agro::scaleToI16(s.rollDeg, 10.0f);
  r.inclinationDeci = agro::scaleToU16(s.inclinationDeg, 10.0f);

  if (isfinite(s.ultrasonic.distanceCm)) {
    const uint16_t distance = agro::scaleToU16(s.ultrasonic.distanceCm, 10.0f);
    r.distanceDeci = (distance == agro::kInvalidU16) ? agro::kDistanceAbsent : distance;
  } else if (s.ultrasonic.timeout) {
    r.distanceDeci = agro::kDistanceTimeout;
  } else if (s.ultrasonic.outOfRange) {
    r.distanceDeci = agro::kDistanceOutOfRange;
  } else {
    r.distanceDeci = agro::kDistanceAbsent;
  }
  return r;
}

SensorSnapshot snapshotFromRecord(const agro::TelemetryRecord& r) {
  SensorSnapshot s;
  s.temperatureC = agro::unscaleI16(r.temperatureDeci, 10.0f);
  s.airHumidityPct = agro::unscaleU16(r.humidityDeci, 10.0f);
  s.pressureHpa = agro::unscaleU16(r.pressureDeci, 10.0f);
  s.accelXMss = agro::unscaleI24(r.accelMilli[0], 1000.0f);
  s.accelYMss = agro::unscaleI24(r.accelMilli[1], 1000.0f);
  s.accelZMss = agro::unscaleI24(r.accelMilli[2], 1000.0f);
  s.gyroXDps = agro::unscaleGyro(r.gyroUnits[0]);
  s.gyroYDps = agro::unscaleGyro(r.gyroUnits[1]);
  s.gyroZDps = agro::unscaleGyro(r.gyroUnits[2]);
  s.pitchDeg = agro::unscaleI16(r.pitchDeci, 10.0f);
  s.rollDeg = agro::unscaleI16(r.rollDeci, 10.0f);
  s.inclinationDeg = agro::unscaleU16(r.inclinationDeci, 10.0f);
  if (r.distanceDeci == agro::kDistanceTimeout) {
    s.ultrasonic.timeout = true;
  } else if (r.distanceDeci == agro::kDistanceOutOfRange) {
    s.ultrasonic.outOfRange = true;
  } else if (r.distanceDeci != agro::kDistanceAbsent) {
    s.ultrasonic.distanceCm = static_cast<float>(r.distanceDeci) / 10.0f;
  }
  return s;
}

// --- Horario sem RTC ------------------------------------------------------

struct ResolvedTime {
  uint32_t epochS;
  agro::TimeQuality quality;
};

ResolvedTime resolveRecordTime(const agro::TelemetryRecord& r) {
  ResolvedTime resolved = {0, agro::kTimeUnknown};
  if (r.epochS != 0 && (r.flags & agro::kFlagClockSynced) != 0) {
    resolved.epochS = r.epochS;
    resolved.quality = agro::kTimeSynced;
    return resolved;
  }
  uint32_t epoch = 0;
  resolved.quality = timeAnchors.resolve(r.bootId, r.uptimeMs, epoch);
  resolved.epochS = epoch;
  return resolved;
}

bool isFreshRecord(const agro::TelemetryRecord& r) {
  if (!clockIsSynchronized()) return false;
  const ResolvedTime resolved = resolveRecordTime(r);
  if (resolved.quality != agro::kTimeSynced || resolved.epochS == 0) return false;
  const long age = static_cast<long>(static_cast<uint32_t>(time(nullptr)) - resolved.epochS);
  return age >= -5 && age <= AGRO_LIVE_MAX_AGE_S;
}

void persistAnchors() {
  uint8_t blob[agro::TimeAnchors::kSerializedSize];
  const size_t length = timeAnchors.serialize(blob, sizeof(blob));
  if (length > 0) {
    preferences.putBytes("anchors", blob, length);
  }
}

void saveLastEpoch() {
  preferences.putUInt("last_epoch", static_cast<uint32_t>(time(nullptr)));
}

// Primeira sincronizacao NTP do boot: fixa a ancora (epoch - uptime). Ela e
// gravada uma unica vez, entao reenviar um registro gera sempre o mesmo horario.
void onClockSynchronized() {
  if (anchorSetThisBoot) return;
  struct timeval now;
  gettimeofday(&now, nullptr);
  const int64_t nowMs = static_cast<int64_t>(now.tv_sec) * 1000 + now.tv_usec / 1000;
  const int64_t anchorMs = nowMs - static_cast<int64_t>(millis());
  if (timeAnchors.setAnchor(currentBootId, anchorMs)) {
    persistAnchors();
  }
  saveLastEpoch();
  anchorSetThisBoot = true;
  Serial.println("[BUFFER] Ancora de horario do boot gravada.");
}

// --- JSON dos registros ---------------------------------------------------

// batchItem=false: mesmo formato da leitura atual (endpoint ao vivo, campos extras opcionais).
// batchItem=true: item do /batch (device_id, versao e tipo de operacao vao no cabecalho do lote).
void buildRecordPayload(JsonDocument& document, const agro::TelemetryRecord& r, bool batchItem) {
  const ResolvedTime resolved = resolveRecordTime(r);
  if (!batchItem) {
    document["device_id"] = AGROGUARDIAN_DEVICE_ID;
    document["operation_type"] = AGROGUARDIAN_OPERATION_TYPE;
    document["firmware_version"] = AGROGUARDIAN_FIRMWARE_VERSION;
  }
  document["sequence_number"] = r.sequence;
  // O endpoint ao vivo so recebe horario "synced"; o lote leva tambem "estimated",
  // sempre acompanhado de time_quality. Sem horario nenhum, o campo e omitido.
  if (resolved.epochS != 0 && (batchItem || resolved.quality == agro::kTimeSynced)) {
    document["timestamp"] = isoFromEpoch(resolved.epochS);
  }
  document["boot_id"] = r.bootId;
  document["uptime_ms"] = r.uptimeMs;
  document["time_quality"] = timeQualityName(resolved.quality);
  if (batchItem) {
    document["reset_reason"] = resetReasonName(r.resetReason);
    document["buffered"] = true;
  }
  appendSensorBlocks(document, snapshotFromRecord(r), (r.flags & agro::kFlagMpuPresent) != 0);
}

// --- Acesso ao anel (protegido por mutex) -----------------------------------

agro::StoreStats bufferStatsSnapshot() {
  agro::StoreStats stats;
  if (ringMutex != nullptr) {
    xSemaphoreTake(ringMutex, portMAX_DELAY);
    stats = bufferStore->stats();
    xSemaphoreGive(ringMutex);
  }
  return stats;
}

void ringAck(uint32_t sequence) {
  xSemaphoreTake(ringMutex, portMAX_DELAY);
  bufferStore->ack(sequence);
  xSemaphoreGive(ringMutex);
  // Persistido a cada confirmacao: se a placa reiniciar, so o que nao foi
  // confirmado e reenviado (o servidor ignora duplicatas por sequence_number).
  preferences.putUInt("acked_seq", sequence);
}

// --- HTTP -------------------------------------------------------------------

int postJson(const String& url, const String& body, String& response, long& retryAfterSeconds) {
  retryAfterSeconds = 0;
  WiFiClientSecure secureClient;
  secureClient.setCACert(AGROGUARDIAN_TLS_ROOT_CA);

  HTTPClient http;
  http.setConnectTimeout(AGRO_HTTP_CONNECT_TIMEOUT_MS);
  http.setTimeout(AGRO_HTTP_TIMEOUT_MS);
  const char* responseHeaders[] = {"Retry-After"};
  http.collectHeaders(responseHeaders, 1);

  if (!http.begin(secureClient, url)) {
    response = "URL HTTPS invalida";
    return 0;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-ID", AGROGUARDIAN_DEVICE_ID);
  http.addHeader("X-API-Key", AGROGUARDIAN_DEVICE_API_KEY);
  http.addHeader("User-Agent", "AgroGuardian-ESP32/" AGROGUARDIAN_FIRMWARE_VERSION);

  const int status = http.POST(body);
  response = status > 0 ? http.getString() : http.errorToString(status);
  if (status == 429 || status == 503) {
    retryAfterSeconds = http.header("Retry-After").toInt();
  }
  http.end();
  return status;
}

UploadResult failureResult(int status, const String& response, long retryAfterSeconds) {
  ++failedSends;
  const String message = response.substring(0, 300);
  setLastError(message);
  Serial.printf("[HTTP] status %d: %s\n", status, message.c_str());
  if (status == 429) {
    if (retryAfterSeconds <= 0) retryAfterSeconds = 60;
    retryAfterSeconds = constrain(retryAfterSeconds, 1L, 3600L);
    sendDeferredUntilMs = millis() + static_cast<unsigned long>(retryAfterSeconds) * 1000UL;
    sendDeferredActive = true;
    return kUploadDeferred;
  }
  if (status == 401) {
    Serial.println("[HTTP] Confira Device ID, API key e cadastro ativo do dispositivo.");
  } else if (status == 403) {
    Serial.println("[HTTP] Dispositivo desativado ou Device ID divergente.");
  }
  return kUploadFailed;
}

// Descarta um registro que o servidor recusou de forma definitiva.
void dropRejectedRecord(const agro::TelemetryRecord& r, int status) {
  Serial.printf("[BUFFER] Registro seq=%lu recusado em definitivo (status %d); descartado.\n",
                static_cast<unsigned long>(r.sequence), status);
  ringAck(r.sequence);
}

// Leitura unica pelo endpoint original (fluxo online normal, ou servidor sem /batch).
UploadResult uploadSingle(const agro::TelemetryRecord& r) {
  JsonDocument document;
  buildRecordPayload(document, r, false);
  String body;
  serializeJson(document, body);
  Serial.printf("[HTTP] POST %s seq=%lu (%u bytes)\n", AGROGUARDIAN_API_URL,
                static_cast<unsigned long>(r.sequence), static_cast<unsigned>(body.length()));

  String response;
  long retryAfter = 0;
  const int status = postJson(AGROGUARDIAN_API_URL, body, response, retryAfter);
  lastHttpStatus = status;
  if (status >= 200 && status < 300) {
    setLastError("");
    parseAcceptedResponse(response);
    ringAck(r.sequence);
    ++successfulSends;
    return kUploadOk;
  }
  // 409 (sequence_number com conteudo diferente) e 422 nao melhoram ao repetir.
  if (status == 409 || status == 422) {
    ++failedSends;
    setLastError(response.substring(0, 300));
    Serial.printf("[HTTP] status %d, resposta da API: %s\n", status, response.substring(0, 300).c_str());
    dropRejectedRecord(r, status);
    return kUploadRetryNow;
  }
  return failureResult(status, response, retryAfter);
}

// Lote: ate AGRO_BATCH_MAX_RECORDS leituras, do mais antigo ao mais novo.
UploadResult uploadBatch(const agro::TelemetryRecord* records, size_t count, bool morePending) {
  String body;
  if (!body.reserve(count * 640 + 512)) {
    setLastError("Sem memoria para montar o lote");
    ++failedSends;
    currentBatchMax = count > 1 ? count / 2 : 1;
    return kUploadFailed;
  }
  const String batchId = String("b") + String(records[0].bootId) + "-" + String(records[0].sequence) +
                         "-" + String(records[count - 1].sequence);
  body += "{\"device_id\":" + jsonQuote(AGROGUARDIAN_DEVICE_ID);
  body += ",\"batch_id\":" + jsonQuote(batchId.c_str());
  body += ",\"firmware_version\":" + jsonQuote(AGROGUARDIAN_FIRMWARE_VERSION);
  body += ",\"operation_type\":" + jsonQuote(AGROGUARDIAN_OPERATION_TYPE);
  body += morePending ? ",\"more_pending\":true" : ",\"more_pending\":false";
  body += ",\"readings\":[";
  for (size_t i = 0; i < count; ++i) {
    if (i > 0) body += ',';
    JsonDocument item;
    buildRecordPayload(item, records[i], true);
    // serializeJson(item, body) substituiria o conteudo de body (perdendo o envelope do lote),
    // entao cada item e serializado em uma String propria e depois anexado.
    String itemJson;
    serializeJson(item, itemJson);
    body += itemJson;
  }
  body += "]}";

  const String url = batchApiUrl();
  Serial.printf("[HTTP] POST %s lote=%s (%u leituras, %u bytes)\n", url.c_str(), batchId.c_str(),
                static_cast<unsigned>(count), static_cast<unsigned>(body.length()));

  String response;
  long retryAfter = 0;
  const int status = postJson(url, body, response, retryAfter);
  lastHttpStatus = status;

  if (status >= 200 && status < 300) {
    JsonDocument parsed;
    if (deserializeJson(parsed, response)) {
      ++failedSends;
      setLastError("Resposta do lote sem JSON valido");
      return kUploadFailed;
    }
    JsonArrayConst results = parsed["results"].as<JsonArrayConst>();
    size_t confirmed = 0;
    size_t accepted = 0;
    size_t duplicates = 0;
    size_t rejected = 0;
    // Avanca o ack somente pelo prefixo contiguo de itens confirmados:
    // accepted, duplicate ou rejected em definitivo.
    for (size_t i = 0; i < count; ++i) {
      bool found = false;
      bool done = false;
      for (JsonObjectConst item : results) {
        const uint32_t itemSequence = item["sequence_number"] | 0xFFFFFFFFu;
        if (itemSequence != records[i].sequence) continue;
        found = true;
        const String result = item["result"] | "";
        if (result == "accepted") {
          ++accepted;
          done = true;
        } else if (result == "duplicate") {
          ++duplicates;
          done = true;
        } else if (result == "rejected" && (item["permanent"] | true)) {
          ++rejected;
          done = true;
        }
        break;
      }
      if (!found || !done) break;
      ++confirmed;
    }
    if (confirmed == 0) {
      ++failedSends;
      setLastError("Lote sem itens confirmados pelo servidor");
      return kUploadFailed;
    }
    ringAck(records[confirmed - 1].sequence);
    successfulSends += accepted + duplicates;
    setLastError("");
    if (parsed["risk_score"].is<float>()) {
      lockState();
      lastRiskScore = parsed["risk_score"].as<float>();
      lastRiskLevel = parsed["risk_level"] | "-";
      unlockState();
    }
    Serial.printf("[HTTP] lote ok: %u aceitas, %u duplicadas, %u recusadas, %u/%u confirmadas\n",
                  static_cast<unsigned>(accepted), static_cast<unsigned>(duplicates),
                  static_cast<unsigned>(rejected), static_cast<unsigned>(confirmed),
                  static_cast<unsigned>(count));
    currentBatchMax = min(static_cast<size_t>(AGRO_BATCH_MAX_RECORDS), currentBatchMax * 2);
    return kUploadOk;
  }

  if (status == 404 || status == 405) {
    // Servidor ainda sem /batch: envia item a item pelo endpoint original.
    batchUnsupported = true;
    batchUnsupportedUntilMs = millis() + AGRO_BATCH_UNSUPPORTED_RETRY_MS;
    Serial.printf("[HTTP] /batch indisponivel (status %d); enviando item a item.\n", status);
    return kUploadRetryNow;
  }
  if (status == 413 || status == 422) {
    // O corpo da resposta traz o campo exato recusado (loc/msg do FastAPI).
    Serial.printf("[HTTP] status %d, resposta da API: %s\n", status, response.substring(0, 300).c_str());
    Serial.printf("[HTTP] corpo enviado (%u bytes): %s\n", static_cast<unsigned>(body.length()),
                  body.substring(0, 900).c_str());
    if (count > 1) {
      // Isola o problema: lote menor (ate 1 leitura por vez).
      currentBatchMax = (status == 413) ? count / 2 : 1;
      Serial.printf("[HTTP] status %d; reduzindo o lote para %u.\n", status,
                    static_cast<unsigned>(currentBatchMax));
      return kUploadRetryNow;
    }
    ++failedSends;
    setLastError(response.substring(0, 300));
    if (status == 422) {
      // Um 422 do lote pode ser problema do envelope ou do servidor, nao da leitura.
      // Antes de descartar, tenta o endpoint ao vivo: so e descartada se os dois recusarem.
      Serial.println("[HTTP] Lote de 1 leitura recusado (422); tentando o endpoint ao vivo antes de descartar.");
      return uploadSingle(records[0]);
    }
    dropRejectedRecord(records[0], status);
    return kUploadRetryNow;
  }
  return failureResult(status, response, retryAfter);
}

UploadResult uploadOnce() {
  xSemaphoreTake(ringMutex, portMAX_DELAY);
  const size_t count = bufferStore->peek(uploadBuffer, currentBatchMax);
  const uint32_t pending = bufferStore->stats().pending;
  xSemaphoreGive(ringMutex);
  if (count == 0) return kUploadOk;

  const bool morePending = pending > count;
  if (!apiUsesHttps()) {
    setLastError("AGROGUARDIAN_API_URL deve usar https://");
    ++failedSends;
    return kUploadFailed;
  }
  if (batchUnsupported && !timeReached(batchUnsupportedUntilMs)) {
    uploadMode = "legacy";
    return uploadSingle(uploadBuffer[0]);
  }
  batchUnsupported = false;
  if (count == 1 && !morePending && isFreshRecord(uploadBuffer[0])) {
    uploadMode = "single";
    return uploadSingle(uploadBuffer[0]);
  }
  uploadMode = "batch";
  return uploadBatch(uploadBuffer, count, morePending);
}

// Tarefa de rede: Wi-Fi, NTP e envio. Roda no core 0 para que a espera por
// rede/TLS nunca bloqueie a leitura dos sensores nem o servidor web local.
void networkTaskMain(void*) {
  unsigned long nextAttemptMs = millis();
  unsigned long backoffMs = 0;
  unsigned long lastEpochSaveMs = millis();

  for (;;) {
    if (WiFi.status() != WL_CONNECTED) {
      networkHealthy = false;
      if (lastWifiAttemptMs == 0 || millis() - lastWifiAttemptMs >= AGRO_WIFI_RETRY_INTERVAL_MS) {
        connectWifi(AGRO_WIFI_CONNECT_TIMEOUT_MS);
      }
      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }
    if (!clockIsSynchronized() && !synchronizeClock(AGRO_NTP_SYNC_TIMEOUT_MS)) {
      networkHealthy = false;
      vTaskDelay(pdMS_TO_TICKS(5000));
      continue;
    }
    if (!anchorSetThisBoot) {
      onClockSynchronized();
    }
    if (millis() - lastEpochSaveMs >= AGRO_LAST_EPOCH_SAVE_INTERVAL_MS) {
      saveLastEpoch();
      lastEpochSaveMs = millis();
    }

    if (sendDeferredActive) {
      if (!timeReached(sendDeferredUntilMs)) {
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(500));
        continue;
      }
      sendDeferredActive = false;
    }
    if (!timeReached(nextAttemptMs)) {
      ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(200));
      continue;
    }
    if (bufferStatsSnapshot().pending == 0) {
      networkHealthy = true;  // enlace ok e nada a enviar
      ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000));
      continue;
    }

    switch (uploadOnce()) {
      case kUploadOk:
        backoffMs = 0;
        networkHealthy = true;
        nextAttemptMs = millis() + AGRO_BATCH_INTERVAL_MS;
        break;
      case kUploadRetryNow:
        nextAttemptMs = millis();
        break;
      case kUploadDeferred:
        networkHealthy = false;
        nextAttemptMs = millis();
        break;
      case kUploadFailed:
      default:
        networkHealthy = false;
        backoffMs = (backoffMs == 0) ? AGRO_NET_BACKOFF_MIN_MS
                                     : min(backoffMs * 2, static_cast<unsigned long>(AGRO_NET_BACKOFF_MAX_MS));
        nextAttemptMs = millis() + backoffMs;
        Serial.printf("[BUFFER] Pendentes mantidos no anel; nova tentativa em %lu ms.\n", backoffMs);
        break;
    }
  }
}

// Chamado pelo loop(): grava a leitura no anel ANTES de qualquer envio.
void recordTick() {
  const unsigned long now = millis();
  const unsigned long interval = networkHealthy ? AGRO_SEND_INTERVAL_MS : AGRO_OFFLINE_RECORD_INTERVAL_MS;
  if (now - lastRecordMs < interval) return;
  lastRecordMs = now;

  updateSensors();
  uint32_t sequence = 0;
  if (!acquireSequence(sequence)) {
    ++recordWriteFailures;
    setLastError("Falha ao reservar sequence_number; leitura nao gravada");
    return;
  }
  const agro::TelemetryRecord record = makeRecord(reading, sequence);

  xSemaphoreTake(ringMutex, portMAX_DELAY);
  const bool written = bufferStore->append(record);
  const agro::StoreStats stats = bufferStore->stats();
  xSemaphoreGive(ringMutex);

  if (!written) {
    ++recordWriteFailures;
    setLastError("Falha ao gravar a leitura no buffer em flash");
    Serial.println("[BUFFER] Falha ao gravar a leitura no anel.");
    return;
  }
  if (stats.dropped != droppedPersisted) {
    droppedPersisted = stats.dropped;
    preferences.putUInt("dropped", droppedBase + stats.dropped);
    Serial.printf("[BUFFER] Anel cheio: %lu leituras antigas descartadas neste boot.\n",
                  static_cast<unsigned long>(stats.dropped));
  }
  if (networkTaskHandle != nullptr) {
    xTaskNotifyGive(networkTaskHandle);
  }
}

void initializeFlashBuffer() {
  if (!sequencePersistenceReady) {
    Serial.println("[BUFFER] NVS indisponivel (sem sequence_number); buffer em flash desativado.");
    return;
  }
  uint16_t bootId = static_cast<uint16_t>(preferences.getUShort("boot_id", 0) + 1);
  if (bootId == 0) bootId = 1;
  preferences.putUShort("boot_id", bootId);
  currentBootId = bootId;
  currentResetReason = static_cast<uint8_t>(esp_reset_reason());

  if (!bufferFlash.begin()) {
    Serial.println("[BUFFER] Particao \"telebuf\" ausente. Grave a tabela de partitions.csv "
                   "(pio run -t erase e depois upload); usando envio direto sem buffer.");
    return;
  }
  // Primeiro uso (ou NVS apagado): a regiao ainda guarda bytes da tabela de
  // particoes anterior. Apaga tudo uma vez para nenhum lixo passar no CRC.
  if (preferences.getUChar("ring_fmt", 0) != 1) {
    Serial.println("[BUFFER] Primeiro uso: apagando a particao telebuf (pode levar ate ~1 minuto)...");
    const size_t sectorCount = bufferFlash.size() / bufferFlash.sectorSize();
    for (size_t sector = 0; sector < sectorCount; ++sector) {
      if (!bufferFlash.eraseSector(sector)) {
        Serial.println("[BUFFER] Falha ao apagar a particao; usando envio direto sem buffer.");
        return;
      }
      delay(1);
    }
    preferences.putUChar("ring_fmt", 1);
    Serial.println("[BUFFER] Particao pronta.");
  }
  const bool hasAcked = preferences.isKey("acked_seq");
  const uint32_t acked = preferences.getUInt("acked_seq", 0);
  const unsigned long scanStartedAt = millis();
  if (!bufferRing.begin(hasAcked, acked)) {
    Serial.println("[BUFFER] Falha ao ler o anel; usando envio direto sem buffer.");
    return;
  }

  // O contador de sequencia nunca pode ficar abaixo do que ja esta gravado
  // (ex.: NVS apagado com o anel ainda cheio).
  const agro::StoreStats stats = bufferStore->stats();
  if (stats.hasRecords && !agro::seqAfter(nextSequence, stats.lastSeq)) {
    nextSequence = stats.lastSeq + 1;
    reservedSequenceLimit = nextSequence + AGRO_SEQUENCE_RESERVATION_SIZE;
    preferences.putUInt("seq_next", reservedSequenceLimit);
    Serial.printf("[BUFFER] sequence_number ajustado para %lu (acima do ultimo gravado).\n",
                  static_cast<unsigned long>(nextSequence));
  }

  droppedBase = preferences.getUInt("dropped", 0);
  droppedPersisted = 0;

  uint8_t blob[agro::TimeAnchors::kSerializedSize];
  if (preferences.getBytesLength("anchors") == sizeof(blob)) {
    preferences.getBytes("anchors", blob, sizeof(blob));
    if (!timeAnchors.deserialize(blob, sizeof(blob))) timeAnchors.clear();
  }
  timeAnchors.beginBoot(currentBootId, preferences.getUInt("last_epoch", 0));
  persistAnchors();

  ringMutex = xSemaphoreCreateMutex();
  if (ringMutex == nullptr) {
    Serial.println("[BUFFER] Sem memoria para o mutex; usando envio direto sem buffer.");
    return;
  }

  Serial.printf("[BUFFER] boot_id=%u reset=%s | anel: %lu pendentes, %lu corrompidos, capacidade %lu (varredura %lu ms)\n",
                static_cast<unsigned>(currentBootId), resetReasonName(currentResetReason),
                static_cast<unsigned long>(stats.pending), static_cast<unsigned long>(stats.corrupt),
                static_cast<unsigned long>(stats.capacityRecords), millis() - scanStartedAt);

  lastRecordMs = millis() - AGRO_SEND_INTERVAL_MS;  // primeira gravacao logo
  if (xTaskCreatePinnedToCore(networkTaskMain, "agro_net", AGRO_NET_TASK_STACK_BYTES, nullptr, 1,
                              &networkTaskHandle, 0) != pdPASS) {
    Serial.println("[BUFFER] Nao foi possivel criar a tarefa de rede; usando envio direto sem buffer.");
    networkTaskHandle = nullptr;
    return;
  }
  bufferReady = true;
}

#endif  // AGRO_ENABLE_FLASH_BUFFER

bool sendTelemetry() {
  if (!apiUsesHttps()) {
    setLastError("AGROGUARDIAN_API_URL deve usar https://");
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
        sendDeferredActive = true;
      }
      http.end();
    }

    Serial.printf("[HTTP] tentativa %d/%d: status %d\n", attempt, AGRO_HTTP_RETRIES, lastHttpStatus);
    if (lastHttpStatus >= 200 && lastHttpStatus < 300) {
      setLastError("");
      parseAcceptedResponse(finalResponse);
      pendingPayloadBody = "";
      pendingPayloadReady = false;
      ++successfulSends;
      return true;
    }

    setLastError(finalResponse.substring(0, 300));
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
  lockState();
  if (lastTelemetryId >= 0) document["_last_telemetry_id"] = lastTelemetryId;
  if (isfinite(lastRiskScore)) document["_last_risk_score"] = lastRiskScore;
  document["_last_risk_level"] = lastRiskLevel;
  document["_telemetry_status"] = lastTelemetryStatus;
  document["_quality_status"] = lastQualityStatus;
  document["_last_error"] = lastError;
  unlockState();
#if AGRO_ENABLE_FLASH_BUFFER
  document["_buffer_enabled"] = bufferReady;
  if (bufferReady) {
    const agro::StoreStats stats = bufferStatsSnapshot();
    document["_buffer_pending"] = stats.pending;
    document["_buffer_capacity"] = stats.capacityRecords;
    document["_buffer_occupancy_pct"] =
      stats.capacityRecords > 0 ? rounded(100.0f * stats.pending / stats.capacityRecords, 10.0f) : 0.0f;
    document["_buffer_dropped"] = droppedBase + stats.dropped;
    document["_buffer_corrupt"] = stats.corrupt;
    document["_buffer_write_failures"] = recordWriteFailures;
    if (stats.hasAcked) document["_buffer_acked_seq"] = stats.ackedSeq;
    document["_boot_id"] = currentBootId;
    document["_reset_reason"] = resetReasonName(currentResetReason);
    document["_upload_mode"] = uploadMode;
    document["_record_interval_ms"] = networkHealthy ? AGRO_SEND_INTERVAL_MS : AGRO_OFFLINE_RECORD_INTERVAL_MS;
  }
#endif

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
  lockState();
  const String riskLevelCopy = lastRiskLevel;
  const String lastErrorCopy = lastError;
  unlockState();
  html += "<tr><td>Nivel de risco</td><td><b>" + riskLevelCopy + "</b></td></tr>";
  html += "<tr><td>HTTP</td><td><b>" + String(lastHttpStatus) + "</b></td></tr>";
  html += "<tr><td>Envios OK / falha</td><td><b>" + String(successfulSends) + " / " + String(failedSends) + "</b></td></tr>";
#if AGRO_ENABLE_FLASH_BUFFER
  if (bufferReady) {
    const agro::StoreStats stats = bufferStatsSnapshot();
    const float occupancy = stats.capacityRecords > 0 ? 100.0f * stats.pending / stats.capacityRecords : 0.0f;
    html += "<tr><td>Buffer pendente</td><td><b>" + String(stats.pending) + " / " + String(stats.capacityRecords) +
            "</b> (" + String(occupancy, 1) + "%)</td></tr>";
    html += "<tr><td>Buffer descartados</td><td><b>" + String(droppedBase + stats.dropped) + "</b></td></tr>";
    html += "<tr><td>Boot / reset</td><td><b>" + String(currentBootId) + " / " + String(resetReasonName(currentResetReason)) +
            "</b></td></tr>";
    html += "<tr><td>Modo de envio</td><td><b>" + String(uploadMode) + "</b></td></tr>";
  }
#endif
  html += "</table><p><small>Destino: " + String(AGROGUARDIAN_API_URL) + "</small></p>";
  if (lastErrorCopy.length() > 0) html += "<p><small>Ultimo erro: " + lastErrorCopy + "</small></p>";
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

  stateMutex = xSemaphoreCreateMutex();
  initializeSequencePersistence();
  initializeSensors();
#if AGRO_ENABLE_FLASH_BUFFER
  // Com o buffer ativo, Wi-Fi/NTP/envio ficam na tarefa de rede e o setup nao espera por eles.
  initializeFlashBuffer();
#endif
  if (!bufferedUplinkActive()) {
    connectWifi(AGRO_WIFI_CONNECT_TIMEOUT_MS);
    synchronizeClock(AGRO_NTP_SYNC_TIMEOUT_MS);
  }

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

  if (!bufferedUplinkActive() && WiFi.status() != WL_CONNECTED &&
      now - lastWifiAttemptMs >= AGRO_WIFI_RETRY_INTERVAL_MS) {
    connectWifi(AGRO_WIFI_CONNECT_TIMEOUT_MS);
  }

#if AGRO_ENABLE_LOCAL_WEBSERVER
  startLocalWebServer();
#endif

#if AGRO_ENABLE_FLASH_BUFFER
  if (bufferReady) {
    recordTick();  // grava no anel; a tarefa de rede envia
  } else
#endif
  {
    if (sendDeferredActive && timeReached(sendDeferredUntilMs)) {
      sendDeferredActive = false;
    }
    if (now - lastSendMs >= AGRO_SEND_INTERVAL_MS && !sendDeferredActive) {
      lastSendMs = now;
      updateSensors();
      sendTelemetry();
    }
  }

  delay(5);
}
