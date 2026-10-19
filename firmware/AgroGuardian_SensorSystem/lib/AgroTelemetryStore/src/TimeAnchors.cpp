#include "TimeAnchors.h"

#include <string.h>

namespace agro {

void TimeAnchors::clear() {
  for (size_t i = 0; i < kMaxEntries; ++i) {
    entries_[i] = BootTimeEntry();
  }
  next_ = 0;
}

const BootTimeEntry* TimeAnchors::find(uint16_t bootId) const {
  for (size_t i = 0; i < kMaxEntries; ++i) {
    if (entries_[i].used && entries_[i].bootId == bootId) {
      return &entries_[i];
    }
  }
  return nullptr;
}

BootTimeEntry* TimeAnchors::find(uint16_t bootId) {
  for (size_t i = 0; i < kMaxEntries; ++i) {
    if (entries_[i].used && entries_[i].bootId == bootId) {
      return &entries_[i];
    }
  }
  return nullptr;
}

void TimeAnchors::beginBoot(uint16_t bootId, uint32_t lastKnownEpochS) {
  BootTimeEntry* existing = find(bootId);
  if (existing == nullptr) {
    existing = &entries_[next_];
    next_ = static_cast<uint8_t>((next_ + 1) % kMaxEntries);
  }
  *existing = BootTimeEntry();
  existing->bootId = bootId;
  existing->used = true;
  existing->estimateValid = lastKnownEpochS != 0;
  existing->estimateBaseS = lastKnownEpochS;
}

bool TimeAnchors::setAnchor(uint16_t bootId, int64_t anchorMs) {
  BootTimeEntry* entry = find(bootId);
  if (entry == nullptr || entry->anchorValid) {
    return false;
  }
  entry->anchorValid = true;
  entry->anchorMs = anchorMs;
  return true;
}

bool TimeAnchors::hasAnchor(uint16_t bootId) const {
  const BootTimeEntry* entry = find(bootId);
  return entry != nullptr && entry->anchorValid;
}

TimeQuality TimeAnchors::resolve(uint16_t bootId, uint32_t uptimeMs, uint32_t& epochS) const {
  epochS = 0;
  const BootTimeEntry* entry = find(bootId);
  if (entry == nullptr) {
    return kTimeUnknown;
  }
  if (entry->anchorValid) {
    const int64_t epochMs = entry->anchorMs + static_cast<int64_t>(uptimeMs);
    if (epochMs > 0) {
      epochS = static_cast<uint32_t>(epochMs / 1000);
      return kTimeSynced;
    }
  }
  if (entry->estimateValid) {
    epochS = entry->estimateBaseS + uptimeMs / 1000;
    return kTimeEstimated;
  }
  return kTimeUnknown;
}

size_t TimeAnchors::serialize(uint8_t* out, size_t capacity) const {
  if (capacity < kSerializedSize) {
    return 0;
  }
  memset(out, 0, kSerializedSize);
  out[0] = 1;  // versao do blob
  out[1] = next_;
  for (size_t i = 0; i < kMaxEntries; ++i) {
    uint8_t* p = out + 2 + i * 16;
    const BootTimeEntry& e = entries_[i];
    p[0] = static_cast<uint8_t>(e.bootId & 0xFF);
    p[1] = static_cast<uint8_t>(e.bootId >> 8);
    p[2] = static_cast<uint8_t>((e.used ? 1 : 0) | (e.anchorValid ? 2 : 0) | (e.estimateValid ? 4 : 0));
    p[3] = 0;
    for (int b = 0; b < 4; ++b) {
      p[4 + b] = static_cast<uint8_t>((e.estimateBaseS >> (8 * b)) & 0xFF);
    }
    const uint64_t anchor = static_cast<uint64_t>(e.anchorMs);
    for (int b = 0; b < 8; ++b) {
      p[8 + b] = static_cast<uint8_t>((anchor >> (8 * b)) & 0xFF);
    }
  }
  return kSerializedSize;
}

bool TimeAnchors::deserialize(const uint8_t* in, size_t length) {
  if (length != kSerializedSize || in[0] != 1 || in[1] >= kMaxEntries) {
    return false;
  }
  clear();
  next_ = in[1];
  for (size_t i = 0; i < kMaxEntries; ++i) {
    const uint8_t* p = in + 2 + i * 16;
    BootTimeEntry& e = entries_[i];
    e.bootId = static_cast<uint16_t>(p[0] | (p[1] << 8));
    e.used = (p[2] & 1) != 0;
    e.anchorValid = (p[2] & 2) != 0;
    e.estimateValid = (p[2] & 4) != 0;
    e.estimateBaseS = 0;
    for (int b = 0; b < 4; ++b) {
      e.estimateBaseS |= static_cast<uint32_t>(p[4 + b]) << (8 * b);
    }
    uint64_t anchor = 0;
    for (int b = 0; b < 8; ++b) {
      anchor |= static_cast<uint64_t>(p[8 + b]) << (8 * b);
    }
    e.anchorMs = static_cast<int64_t>(anchor);
  }
  return true;
}

}  // namespace agro
