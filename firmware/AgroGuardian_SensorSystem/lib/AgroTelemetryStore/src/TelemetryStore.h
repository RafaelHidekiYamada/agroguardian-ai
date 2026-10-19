#pragma once

// Interface do armazenamento de telemetria pendente. Hoje a unica
// implementacao e o anel em flash (TelemetryRing); um modulo de cartao SD
// pode implementar a mesma interface sem alterar o restante do firmware.

#include <stddef.h>
#include <stdint.h>

#include "TelemetryRecord.h"

namespace agro {

struct StoreStats {
  uint32_t capacityRecords = 0;  // capacidade nominal (setores - 1 de folga) * registros/setor
  uint32_t pending = 0;          // registros validos ainda nao confirmados
  uint32_t dropped = 0;          // pendentes sobrescritos desde o boot
  uint32_t corrupt = 0;          // slots com CRC invalido encontrados
  bool hasAcked = false;
  uint32_t ackedSeq = 0;         // ultimo sequence_number confirmado
  bool hasRecords = false;
  uint32_t lastSeq = 0;          // maior sequence_number gravado
};

class TelemetryStore {
 public:
  virtual ~TelemetryStore() {}
  // Grava o registro (write-ahead). Sobrescreve o mais antigo se estiver cheio.
  virtual bool append(const TelemetryRecord& record) = 0;
  // Copia ate maxCount registros pendentes, do mais antigo ao mais novo.
  virtual size_t peek(TelemetryRecord* out, size_t maxCount) = 0;
  // Confirma tudo ate lastSeq (inclusive); libera esses registros.
  virtual void ack(uint32_t lastSeq) = 0;
  virtual StoreStats stats() const = 0;
};

}  // namespace agro
