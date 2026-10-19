#pragma once

// Anel circular de registros de 48 bytes sobre uma FlashDevice.
//
// - Escrita registro a registro em slot ja apagado (nunca reescreve setor).
// - 85 registros por setor de 4 KB (4080 bytes uteis).
// - Ao gravar o primeiro slot de um setor, o setor seguinte e apagado
//   (erase-ahead). Se ele ainda tinha registros nao confirmados, eles sao
//   descartados (politica "sobrescrever o mais antigo") e contados em dropped.
// - No boot, begin() varre a particao validando o CRC de cada slot para
//   recuperar head (proximo slot a gravar) e tail (mais antigo pendente).
//   "Pendente" = sequence_number depois do ultimo confirmado (ackedSeq),
//   que o chamador persiste no NVS.
// - Queda de energia no meio da escrita deixa um slot com CRC invalido: ele
//   e contado em corrupt e simplesmente pulado.
//
// Nao e thread-safe: o chamador serializa o acesso.

#include <stddef.h>
#include <stdint.h>

#include "FlashDevice.h"
#include "TelemetryRecord.h"
#include "TelemetryStore.h"

namespace agro {

class TelemetryRing : public TelemetryStore {
 public:
  explicit TelemetryRing(FlashDevice& flash);

  // Varre a flash e recupera head/tail. hasAcked/ackedSeq vem do NVS.
  bool begin(bool hasAcked, uint32_t ackedSeq);
  bool ready() const { return ready_; }

  bool append(const TelemetryRecord& record) override;
  size_t peek(TelemetryRecord* out, size_t maxCount) override;
  void ack(uint32_t lastSeq) override;
  StoreStats stats() const override;

 private:
  uint32_t nextSlot(uint32_t slot) const { return (slot + 1 >= totalSlots_) ? 0 : slot + 1; }
  size_t slotOffset(uint32_t slot) const {
    return static_cast<size_t>(slot / slotsPerSector_) * sectorSize_ +
           static_cast<size_t>(slot % slotsPerSector_) * kRecordSize;
  }
  bool readSlot(uint32_t slot, uint8_t* raw);
  bool isPendingSeq(uint32_t sequence) const;
  bool sectorBlank(uint32_t sector);
  bool eraseSectorAccounted(uint32_t sector);
  void normalizeTail();

  FlashDevice& flash_;
  bool ready_ = false;
  size_t sectorSize_ = 0;
  uint32_t sectors_ = 0;
  uint32_t slotsPerSector_ = 0;
  uint32_t totalSlots_ = 0;

  uint32_t head_ = 0;     // proximo slot a gravar
  uint32_t tail_ = 0;     // slot do pendente mais antigo (== head_ se vazio)
  uint32_t pending_ = 0;
  uint32_t dropped_ = 0;
  uint32_t corrupt_ = 0;
  bool hasAcked_ = false;
  uint32_t ackedSeq_ = 0;
  bool hasLast_ = false;
  uint32_t lastSeq_ = 0;
};

// Comparacao de sequence_number tolerante a volta do contador u32.
inline bool seqAfter(uint32_t a, uint32_t b) { return static_cast<int32_t>(a - b) > 0; }

}  // namespace agro
