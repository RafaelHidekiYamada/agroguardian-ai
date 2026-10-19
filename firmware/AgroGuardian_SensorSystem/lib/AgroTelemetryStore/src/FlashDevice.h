#pragma once

// Abstracao minima de uma regiao de flash NOR (setores apagaveis + escrita
// que so limpa bits). Permite testar o anel no PC com uma flash simulada e
// trocar o meio (partition do ESP32 hoje, cartao SD no futuro).

#include <stddef.h>
#include <stdint.h>

namespace agro {

class FlashDevice {
 public:
  virtual ~FlashDevice() {}
  virtual size_t size() const = 0;
  virtual size_t sectorSize() const = 0;
  virtual bool read(size_t offset, void* destination, size_t length) = 0;
  // Escreve em area ja apagada (0xFF). Nao apaga.
  virtual bool write(size_t offset, const void* source, size_t length) = 0;
  virtual bool eraseSector(size_t sectorIndex) = 0;
};

}  // namespace agro
