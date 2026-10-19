#include "TelemetryRecord.h"

#include <math.h>
#include <string.h>

namespace agro {

namespace {

const uint16_t kCrcNibble[16] = {
  0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
  0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
};

void put16(uint8_t* p, uint16_t v) {
  p[0] = static_cast<uint8_t>(v & 0xFF);
  p[1] = static_cast<uint8_t>(v >> 8);
}

void put32(uint8_t* p, uint32_t v) {
  p[0] = static_cast<uint8_t>(v & 0xFF);
  p[1] = static_cast<uint8_t>((v >> 8) & 0xFF);
  p[2] = static_cast<uint8_t>((v >> 16) & 0xFF);
  p[3] = static_cast<uint8_t>((v >> 24) & 0xFF);
}

void put24(uint8_t* p, int32_t v) {
  const uint32_t u = static_cast<uint32_t>(v) & 0xFFFFFFu;
  p[0] = static_cast<uint8_t>(u & 0xFF);
  p[1] = static_cast<uint8_t>((u >> 8) & 0xFF);
  p[2] = static_cast<uint8_t>((u >> 16) & 0xFF);
}

uint16_t get16(const uint8_t* p) {
  return static_cast<uint16_t>(p[0] | (p[1] << 8));
}

uint32_t get32(const uint8_t* p) {
  return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}

int32_t get24(const uint8_t* p) {
  uint32_t u = static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
               (static_cast<uint32_t>(p[2]) << 16);
  if (u & 0x800000u) {
    u |= 0xFF000000u;
  }
  return static_cast<int32_t>(u);
}

}  // namespace

uint16_t crc16(const uint8_t* data, size_t length) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc = static_cast<uint16_t>((crc << 4) ^ kCrcNibble[((crc >> 12) ^ (data[i] >> 4)) & 0x0F]);
    crc = static_cast<uint16_t>((crc << 4) ^ kCrcNibble[((crc >> 12) ^ (data[i] & 0x0F)) & 0x0F]);
  }
  return crc;
}

void encodeRecord(const TelemetryRecord& r, uint8_t out[kRecordSize]) {
  memset(out, 0, kRecordSize);
  out[0] = static_cast<uint8_t>(r.version & 0x0F);
  out[1] = r.flags;
  put16(out + 2, r.bootId);
  put32(out + 4, r.sequence);
  put32(out + 8, r.epochS);
  put32(out + 12, r.uptimeMs);
  put16(out + 16, static_cast<uint16_t>(r.temperatureDeci));
  put16(out + 18, r.humidityDeci);
  put16(out + 20, r.pressureDeci);
  put24(out + 22, r.accelMilli[0]);
  put24(out + 25, r.accelMilli[1]);
  put24(out + 28, r.accelMilli[2]);
  put16(out + 31, static_cast<uint16_t>(r.gyroUnits[0]));
  put16(out + 33, static_cast<uint16_t>(r.gyroUnits[1]));
  put16(out + 35, static_cast<uint16_t>(r.gyroUnits[2]));
  put16(out + 37, static_cast<uint16_t>(r.pitchDeci));
  put16(out + 39, static_cast<uint16_t>(r.rollDeci));
  put16(out + 41, r.inclinationDeci);
  put16(out + 43, r.distanceDeci);
  out[45] = r.resetReason;
  put16(out + 46, crc16(out, 46));
}

bool decodeRecord(const uint8_t in[kRecordSize], TelemetryRecord& r) {
  if (get16(in + 46) != crc16(in, 46)) {
    return false;
  }
  if ((in[0] & 0x0F) != kRecordVersion) {
    return false;
  }
  r.version = static_cast<uint8_t>(in[0] & 0x0F);
  r.flags = in[1];
  r.bootId = get16(in + 2);
  r.sequence = get32(in + 4);
  r.epochS = get32(in + 8);
  r.uptimeMs = get32(in + 12);
  r.temperatureDeci = static_cast<int16_t>(get16(in + 16));
  r.humidityDeci = get16(in + 18);
  r.pressureDeci = get16(in + 20);
  r.accelMilli[0] = get24(in + 22);
  r.accelMilli[1] = get24(in + 25);
  r.accelMilli[2] = get24(in + 28);
  r.gyroUnits[0] = static_cast<int16_t>(get16(in + 31));
  r.gyroUnits[1] = static_cast<int16_t>(get16(in + 33));
  r.gyroUnits[2] = static_cast<int16_t>(get16(in + 35));
  r.pitchDeci = static_cast<int16_t>(get16(in + 37));
  r.rollDeci = static_cast<int16_t>(get16(in + 39));
  r.inclinationDeci = get16(in + 41);
  r.distanceDeci = get16(in + 43);
  r.resetReason = in[45];
  return true;
}

bool isErasedRecord(const uint8_t in[kRecordSize]) {
  for (size_t i = 0; i < kRecordSize; ++i) {
    if (in[i] != 0xFF) {
      return false;
    }
  }
  return true;
}

int16_t scaleToI16(float value, float factor) {
  if (!isfinite(value)) {
    return kInvalidI16;
  }
  const float scaled = roundf(value * factor);
  if (scaled < -32767.0f || scaled > 32767.0f) {
    return kInvalidI16;
  }
  return static_cast<int16_t>(scaled);
}

uint16_t scaleToU16(float value, float factor) {
  if (!isfinite(value)) {
    return kInvalidU16;
  }
  const float scaled = roundf(value * factor);
  // Reserva 0xFFFD..0xFFFF para sentinelas/codigos.
  if (scaled < 0.0f || scaled > 65000.0f) {
    return kInvalidU16;
  }
  return static_cast<uint16_t>(scaled);
}

int32_t scaleToI24(float value, float factor) {
  if (!isfinite(value)) {
    return kInvalidI24;
  }
  const float scaled = roundf(value * factor);
  if (scaled < -8388607.0f || scaled > 8388607.0f) {
    return kInvalidI24;
  }
  return static_cast<int32_t>(scaled);
}

int16_t scaleGyro(float dps, bool& saturated) {
  if (!isfinite(dps)) {
    return kInvalidI16;
  }
  float scaled = roundf(dps * 50.0f);
  if (scaled > 32767.0f) {
    scaled = 32767.0f;
    saturated = true;
  } else if (scaled < -32767.0f) {
    scaled = -32767.0f;
    saturated = true;
  }
  return static_cast<int16_t>(scaled);
}

float unscaleI16(int16_t raw, float factor) {
  return raw == kInvalidI16 ? NAN : static_cast<float>(raw) / factor;
}

float unscaleU16(uint16_t raw, float factor) {
  return raw == kInvalidU16 ? NAN : static_cast<float>(raw) / factor;
}

float unscaleI24(int32_t raw, float factor) {
  return raw == kInvalidI24 ? NAN : static_cast<float>(raw) / factor;
}

float unscaleGyro(int16_t raw) {
  return raw == kInvalidI16 ? NAN : static_cast<float>(raw) / 50.0f;
}

}  // namespace agro
