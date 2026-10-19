#include "TelemetryRing.h"

#include <stdlib.h>
#include <string.h>

namespace agro {

TelemetryRing::TelemetryRing(FlashDevice& flash) : flash_(flash) {}

bool TelemetryRing::readSlot(uint32_t slot, uint8_t* raw) {
  return flash_.read(slotOffset(slot), raw, kRecordSize);
}

bool TelemetryRing::isPendingSeq(uint32_t sequence) const {
  return !hasAcked_ || seqAfter(sequence, ackedSeq_);
}

bool TelemetryRing::sectorBlank(uint32_t sector) {
  uint8_t chunk[256];
  const size_t usable = static_cast<size_t>(slotsPerSector_) * kRecordSize;
  const size_t base = static_cast<size_t>(sector) * sectorSize_;
  for (size_t done = 0; done < usable;) {
    size_t length = usable - done;
    if (length > sizeof(chunk)) {
      length = sizeof(chunk);
    }
    if (!flash_.read(base + done, chunk, length)) {
      return false;
    }
    for (size_t i = 0; i < length; ++i) {
      if (chunk[i] != 0xFF) {
        return false;
      }
    }
    done += length;
  }
  return true;
}

void TelemetryRing::normalizeTail() {
  if (pending_ == 0) {
    tail_ = head_;
    return;
  }
  uint8_t raw[kRecordSize];
  TelemetryRecord record;
  for (uint32_t guard = 0; tail_ != head_ && guard < totalSlots_; ++guard) {
    if (readSlot(tail_, raw) && !isErasedRecord(raw) && decodeRecord(raw, record) &&
        isPendingSeq(record.sequence)) {
      return;
    }
    tail_ = nextSlot(tail_);
  }
  if (tail_ == head_) {
    pending_ = 0;  // nada pendente encontrado: contador estava defasado
  }
}

// Apaga um setor contando os pendentes que serao perdidos (sobrescrita).
bool TelemetryRing::eraseSectorAccounted(uint32_t sector) {
  uint32_t lost = 0;
  uint8_t raw[kRecordSize];
  TelemetryRecord record;
  for (uint32_t i = 0; i < slotsPerSector_; ++i) {
    const uint32_t slot = sector * slotsPerSector_ + i;
    if (readSlot(slot, raw) && !isErasedRecord(raw) && decodeRecord(raw, record) &&
        isPendingSeq(record.sequence)) {
      ++lost;
    }
  }
  if (!flash_.eraseSector(sector)) {
    return false;
  }
  if (lost > 0) {
    dropped_ += lost;
    pending_ = (pending_ > lost) ? (pending_ - lost) : 0;
  }
  if (tail_ / slotsPerSector_ == sector) {
    tail_ = nextSlot(sector * slotsPerSector_ + slotsPerSector_ - 1);
    normalizeTail();
  }
  return true;
}

bool TelemetryRing::begin(bool hasAcked, uint32_t ackedSeq) {
  ready_ = false;
  sectorSize_ = flash_.sectorSize();
  if (sectorSize_ < kRecordSize) {
    return false;
  }
  sectors_ = static_cast<uint32_t>(flash_.size() / sectorSize_);
  slotsPerSector_ = static_cast<uint32_t>(sectorSize_ / kRecordSize);
  if (sectors_ < 3 || slotsPerSector_ == 0) {
    return false;
  }
  totalSlots_ = sectors_ * slotsPerSector_;
  hasAcked_ = hasAcked;
  ackedSeq_ = ackedSeq;
  head_ = 0;
  tail_ = 0;
  pending_ = 0;
  dropped_ = 0;
  corrupt_ = 0;
  hasLast_ = false;
  lastSeq_ = 0;

  uint8_t* buffer = static_cast<uint8_t*>(malloc(sectorSize_));
  if (buffer == nullptr) {
    return false;
  }

  bool anyValid = false;
  uint32_t maxSeq = 0;
  uint32_t maxSlot = 0;
  bool anyPending = false;
  uint32_t minPendingSeq = 0;
  uint32_t minPendingSlot = 0;
  uint32_t pendingCount = 0;
  uint32_t corruptCount = 0;

  for (uint32_t sector = 0; sector < sectors_; ++sector) {
    if (!flash_.read(static_cast<size_t>(sector) * sectorSize_, buffer, sectorSize_)) {
      free(buffer);
      return false;
    }
    for (uint32_t i = 0; i < slotsPerSector_; ++i) {
      const uint8_t* raw = buffer + static_cast<size_t>(i) * kRecordSize;
      if (isErasedRecord(raw)) {
        continue;
      }
      TelemetryRecord record;
      if (!decodeRecord(raw, record)) {
        ++corruptCount;
        continue;
      }
      const uint32_t slot = sector * slotsPerSector_ + i;
      if (!anyValid || seqAfter(record.sequence, maxSeq)) {
        maxSeq = record.sequence;
        maxSlot = slot;
        anyValid = true;
      }
      if (isPendingSeq(record.sequence)) {
        ++pendingCount;
        if (!anyPending || seqAfter(minPendingSeq, record.sequence)) {
          minPendingSeq = record.sequence;
          minPendingSlot = slot;
          anyPending = true;
        }
      }
    }
  }
  free(buffer);

  if (!anyValid) {
    // Particao nova (ou so lixo): comeca do slot 0 e deixa os dois primeiros
    // setores prontos. Os demais sao apagados ao serem alcancados (erase-ahead).
    for (uint32_t sector = 0; sector < 2; ++sector) {
      if (!sectorBlank(sector) && !flash_.eraseSector(sector)) {
        return false;
      }
    }
    ready_ = true;
    return true;
  }

  corrupt_ = corruptCount;
  pending_ = pendingCount;
  hasLast_ = true;
  lastSeq_ = maxSeq;
  head_ = nextSlot(maxSlot);
  tail_ = anyPending ? minPendingSlot : head_;

  // O proximo slot precisa estar apagado. Resto de escrita interrompida
  // (CRC invalido) e pulado; um setor ocupado e apagado inteiro (o mais
  // antigo vira descarte).
  uint8_t probe[kRecordSize];
  for (uint32_t guard = 0; guard < totalSlots_; ++guard) {
    if (!readSlot(head_, probe)) {
      return false;
    }
    if (isErasedRecord(probe)) {
      break;
    }
    if (head_ % slotsPerSector_ == 0) {
      if (!eraseSectorAccounted(head_ / slotsPerSector_)) {
        return false;
      }
      break;
    }
    head_ = nextSlot(head_);
  }
  normalizeTail();
  ready_ = true;
  return true;
}

bool TelemetryRing::append(const TelemetryRecord& record) {
  if (!ready_) {
    return false;
  }
  uint8_t raw[kRecordSize];
  encodeRecord(record, raw);

  for (uint32_t attempt = 0; attempt < 8; ++attempt) {
    const uint32_t slot = head_;
    const uint32_t sector = slot / slotsPerSector_;
    const uint32_t index = slot % slotsPerSector_;

    if (index == 0) {
      // Entrando em um setor novo: tem de estar em branco (erase-ahead ou, se
      // a energia caiu durante o apagamento, apaga agora).
      if (!sectorBlank(sector) && !eraseSectorAccounted(sector)) {
        return false;
      }
    } else {
      uint8_t probe[kRecordSize];
      if (!readSlot(slot, probe)) {
        return false;
      }
      if (!isErasedRecord(probe)) {
        ++corrupt_;
        head_ = nextSlot(head_);
        continue;
      }
    }

    if (!flash_.write(slotOffset(slot), raw, kRecordSize)) {
      ++corrupt_;
      head_ = nextSlot(head_);
      continue;
    }

    head_ = nextSlot(slot);
    hasLast_ = true;
    lastSeq_ = record.sequence;
    if (isPendingSeq(record.sequence)) {
      ++pending_;
    }
    if (pending_ == 0) {
      tail_ = head_;
    }

    if (index == 0) {
      // Erase-ahead: deixa o proximo setor pronto antes de precisar dele.
      const uint32_t next = (sector + 1 >= sectors_) ? 0 : sector + 1;
      if (!sectorBlank(next)) {
        eraseSectorAccounted(next);
      }
    }
    return true;
  }
  return false;
}

size_t TelemetryRing::peek(TelemetryRecord* out, size_t maxCount) {
  if (!ready_ || out == nullptr || maxCount == 0) {
    return 0;
  }
  size_t count = 0;
  uint32_t slot = tail_;
  uint8_t raw[kRecordSize];
  TelemetryRecord record;
  for (uint32_t guard = 0; slot != head_ && count < maxCount && guard < totalSlots_; ++guard) {
    if (readSlot(slot, raw) && !isErasedRecord(raw) && decodeRecord(raw, record) &&
        isPendingSeq(record.sequence)) {
      out[count++] = record;
    }
    slot = nextSlot(slot);
  }
  return count;
}

void TelemetryRing::ack(uint32_t lastSeq) {
  if (!ready_) {
    return;
  }
  if (!hasAcked_ || seqAfter(lastSeq, ackedSeq_)) {
    ackedSeq_ = lastSeq;
    hasAcked_ = true;
  }
  uint8_t raw[kRecordSize];
  TelemetryRecord record;
  for (uint32_t guard = 0; tail_ != head_ && guard < totalSlots_; ++guard) {
    if (readSlot(tail_, raw) && !isErasedRecord(raw) && decodeRecord(raw, record)) {
      if (isPendingSeq(record.sequence)) {
        break;  // primeiro ainda pendente
      }
      if (pending_ > 0) {
        --pending_;
      }
    }
    tail_ = nextSlot(tail_);
  }
  if (pending_ == 0) {
    tail_ = head_;
  }
}

StoreStats TelemetryRing::stats() const {
  StoreStats s;
  s.capacityRecords = (sectors_ > 1) ? (sectors_ - 1) * slotsPerSector_ : 0;
  s.pending = pending_;
  s.dropped = dropped_;
  s.corrupt = corrupt_;
  s.hasAcked = hasAcked_;
  s.ackedSeq = ackedSeq_;
  s.hasRecords = hasLast_;
  s.lastSeq = lastSeq_;
  return s;
}

}  // namespace agro
