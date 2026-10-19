#pragma once

// FlashDevice sobre uma particao de dados do ESP32 (esp_partition). So e
// compilada no firmware; nos testes de PC a biblioteca usa uma flash simulada.

#if defined(ESP_PLATFORM) || defined(ARDUINO_ARCH_ESP32)

#include <esp_partition.h>

#include "FlashDevice.h"

namespace agro {

class EspPartitionFlash : public FlashDevice {
 public:
  EspPartitionFlash(const char* label, uint8_t subtype) : label_(label), subtype_(subtype) {}

  // Falso se a particao nao existir na tabela gravada na placa.
  bool begin() {
    partition_ = esp_partition_find_first(ESP_PARTITION_TYPE_DATA,
                                          static_cast<esp_partition_subtype_t>(subtype_), label_);
    return partition_ != nullptr;
  }

  size_t size() const override { return partition_ ? partition_->size : 0; }
  size_t sectorSize() const override { return 4096; }

  bool read(size_t offset, void* destination, size_t length) override {
    return partition_ && esp_partition_read(partition_, offset, destination, length) == ESP_OK;
  }
  bool write(size_t offset, const void* source, size_t length) override {
    return partition_ && esp_partition_write(partition_, offset, source, length) == ESP_OK;
  }
  bool eraseSector(size_t sectorIndex) override {
    return partition_ && esp_partition_erase_range(partition_, sectorIndex * 4096, 4096) == ESP_OK;
  }

 private:
  const char* label_;
  uint8_t subtype_;
  const esp_partition_t* partition_ = nullptr;
};

}  // namespace agro

#endif
