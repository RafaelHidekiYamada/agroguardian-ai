#pragma once

// Reconstrucao de horario sem RTC.
//
// Cada registro guarda boot_id + uptime_ms (e epoch_s so se o relogio estava
// sincronizado na hora da gravacao). Para os demais, o horario e recuperado
// depois a partir de uma ancora por boot:
//   - ancora (anchorMs = epoch_ms - uptime_ms no instante da 1a sincronizacao
//     NTP daquele boot): horario "synced", imutavel (o mesmo registro gera
//     sempre o mesmo timestamp, o que mantem a idempotencia no reenvio);
//   - base estimada (ultimo epoch conhecido, salvo no NVS, no inicio do boot):
//     horario "estimated" (pode estar atrasado pelo tempo em que a placa ficou
//     desligada);
//   - nenhuma das duas: "unknown" (epoch 0). Nunca se inventa horario.
// Guarda os 8 boots mais recentes; a tabela e serializada em um blob de NVS.

#include <stddef.h>
#include <stdint.h>

namespace agro {

enum TimeQuality : uint8_t {
  kTimeUnknown = 0,
  kTimeEstimated = 1,
  kTimeSynced = 2,
};

struct BootTimeEntry {
  uint16_t bootId = 0;
  bool used = false;
  bool anchorValid = false;
  bool estimateValid = false;
  uint32_t estimateBaseS = 0;
  int64_t anchorMs = 0;
};

class TimeAnchors {
 public:
  static const size_t kMaxEntries = 8;
  static const size_t kSerializedSize = 2 + kMaxEntries * 16;

  void clear();
  // Registra um boot novo. lastKnownEpochS = 0 se nunca houve horario valido.
  void beginBoot(uint16_t bootId, uint32_t lastKnownEpochS);
  // Define a ancora do boot (so a primeira chamada vale). Retorna true se gravou.
  bool setAnchor(uint16_t bootId, int64_t anchorMs);
  bool hasAnchor(uint16_t bootId) const;
  // Resolve o horario de um registro. epochS recebe 0 quando unknown.
  TimeQuality resolve(uint16_t bootId, uint32_t uptimeMs, uint32_t& epochS) const;

  size_t serialize(uint8_t* out, size_t capacity) const;
  bool deserialize(const uint8_t* in, size_t length);

 private:
  const BootTimeEntry* find(uint16_t bootId) const;
  BootTimeEntry* find(uint16_t bootId);

  BootTimeEntry entries_[kMaxEntries];
  uint8_t next_ = 0;  // proxima posicao a sobrescrever (a mais antiga)
};

}  // namespace agro
