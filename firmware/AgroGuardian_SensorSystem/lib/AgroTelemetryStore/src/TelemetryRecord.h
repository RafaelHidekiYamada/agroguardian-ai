#pragma once

// Registro binario de telemetria com tamanho fixo (48 bytes), gravado no anel
// em flash. Little-endian, sem padding implicito: os campos sao empacotados e
// lidos byte a byte em encodeRecord()/decodeRecord().
//
// Layout (offset: tamanho):
//    0: 1  versao (nibble baixo) | nibble alto reservado (0)
//    1: 1  flags (kFlag*)
//    2: 2  boot_id (u16)
//    4: 4  sequence_number (u32)
//    8: 4  epoch_s (u32; 0 = desconhecido)
//   12: 4  uptime_ms (u32; da a volta a cada ~49,7 dias)
//   16: 2  temperatura  i16, unidade 0,1 C
//   18: 2  umidade ar   u16, unidade 0,1 %
//   20: 2  pressao      u16, unidade 0,1 hPa
//   22: 3  accel X      i24, unidade 0,001 m/s2
//   25: 3  accel Y      i24, unidade 0,001 m/s2
//   28: 3  accel Z      i24, unidade 0,001 m/s2
//   31: 2  gyro X       i16, unidade 0,02 dps (satura em +-655,34 dps)
//   33: 2  gyro Y       i16, unidade 0,02 dps
//   35: 2  gyro Z       i16, unidade 0,02 dps
//   37: 2  pitch        i16, unidade 0,1 grau
//   39: 2  roll         i16, unidade 0,1 grau
//   41: 2  inclinacao   u16, unidade 0,1 grau
//   43: 2  distancia    u16, unidade 0,1 cm (codigos: 0xFFFF timeout,
//                       0xFFFE fora de alcance, 0xFFFD sem leitura/sensor)
//   45: 1  reset_reason (esp_reset_reason_t do boot)
//   46: 2  CRC16-CCITT-FALSE dos bytes 0..45
//
// Escalas: preservam a precisao hoje enviada no JSON (temp/umid/pressao/angulos
// 0,1; accel 0,001) e, no giroscopio, 0,02 dps no lugar de 0,01 (o MPU-6050 do
// tockn opera em +-500 dps, LSB fisico ~0,015 dps; 0,01 nao cabe em 16 bits).
// Valor invalido/ausente: sentinela kInvalid* no campo (nunca inventar dado).

#include <stddef.h>
#include <stdint.h>

namespace agro {

constexpr size_t kRecordSize = 48;
constexpr uint8_t kRecordVersion = 1;

constexpr int16_t kInvalidI16 = -32768;
constexpr uint16_t kInvalidU16 = 0xFFFF;
constexpr int32_t kInvalidI24 = -8388608;

constexpr uint16_t kDistanceTimeout = 0xFFFF;
constexpr uint16_t kDistanceOutOfRange = 0xFFFE;
constexpr uint16_t kDistanceAbsent = 0xFFFD;

// Flags do registro.
constexpr uint8_t kFlagBmePresent = 1u << 0;
constexpr uint8_t kFlagMpuPresent = 1u << 1;
constexpr uint8_t kFlagGyroSaturated = 1u << 2;
constexpr uint8_t kFlagClockSynced = 1u << 3;  // epoch_s veio de um relogio sincronizado

struct TelemetryRecord {
  uint8_t version = kRecordVersion;
  uint8_t flags = 0;
  uint16_t bootId = 0;
  uint32_t sequence = 0;
  uint32_t epochS = 0;
  uint32_t uptimeMs = 0;
  int16_t temperatureDeci = kInvalidI16;
  uint16_t humidityDeci = kInvalidU16;
  uint16_t pressureDeci = kInvalidU16;
  int32_t accelMilli[3] = {kInvalidI24, kInvalidI24, kInvalidI24};
  int16_t gyroUnits[3] = {kInvalidI16, kInvalidI16, kInvalidI16};  // 0,02 dps
  int16_t pitchDeci = kInvalidI16;
  int16_t rollDeci = kInvalidI16;
  uint16_t inclinationDeci = kInvalidU16;
  uint16_t distanceDeci = kDistanceAbsent;
  uint8_t resetReason = 0;
};

uint16_t crc16(const uint8_t* data, size_t length);

void encodeRecord(const TelemetryRecord& record, uint8_t out[kRecordSize]);
// Falso se o CRC ou a versao nao baterem (registro corrompido/desconhecido).
bool decodeRecord(const uint8_t in[kRecordSize], TelemetryRecord& record);
// Verdadeiro se os 48 bytes sao 0xFF (slot de flash apagado).
bool isErasedRecord(const uint8_t in[kRecordSize]);

// Conversoes float -> inteiro escalado (kInvalid* se nao finito ou fora da faixa).
int16_t scaleToI16(float value, float factor);
uint16_t scaleToU16(float value, float factor);
int32_t scaleToI24(float value, float factor);
// Giroscopio em 0,02 dps; satura em +-32767 e marca saturated.
int16_t scaleGyro(float dps, bool& saturated);

// Inteiro escalado -> float (NAN para sentinela).
float unscaleI16(int16_t raw, float factor);
float unscaleU16(uint16_t raw, float factor);
float unscaleI24(int32_t raw, float factor);
float unscaleGyro(int16_t raw);

}  // namespace agro
