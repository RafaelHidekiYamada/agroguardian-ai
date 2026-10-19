# Como reverter o buffer de telemetria em flash

O buffer store-and-forward (Fase 1) existe para guardar leituras no próprio
ESP32 enquanto não há Wi-Fi/internet. Ele ocupa espaço da flash de 4 MB e
mudou a tabela de partições. Se um módulo de cartão SD for adotado, este
arquivo explica como voltar atrás, total ou parcialmente.

## O que foi adicionado ou alterado (somente firmware)

| Arquivo | Mudança |
|---|---|
| `partitions.csv` | **novo** – tabela com OTA + partição `telebuf` (anel de telemetria) |
| `platformio.ini` | linha `board_build.partitions = partitions.csv` |
| `include/Config.h` | bloco de defines `AGRO_ENABLE_FLASH_BUFFER`, `AGRO_OFFLINE_RECORD_INTERVAL_MS`, `AGRO_BATCH_*`, etc. |
| `src/main.cpp` | gravação no anel antes do envio, tarefa de rede (FreeRTOS), envio em lote, estatísticas em `/json` e na página local, mutex para as strings de status |
| `lib/AgroTelemetryStore/` | **nova** – registro de 48 bytes + CRC16, anel circular, âncoras de horário, interface `TelemetryStore` |
| `REVERTER_BUFFER_FLASH.md` | este arquivo |

Backend e dashboard (endpoint `/batch`, segmentos, SEM_SINAL) **não** fazem
parte desta reversão: continuam úteis com o SD, que também enviaria pelo lote.

## Valores originais

- `platformio.ini`: não havia `board_build.partitions`; valia a tabela padrão
  do framework Arduino-ESP32 para a placa `esp32dev` (nvs 20 KB, otadata 8 KB,
  dois slots de app de 1,25 MB e SPIFFS).
- `Config.h`: não havia nenhum dos defines do bloco "Buffer store-and-forward".
- `main.cpp`: uma única leitura pendente em RAM, Wi-Fi/NTP/envio dentro do
  `loop()`. O original está no Git (último commit anterior a esta mudança).
- Binário original: 1.019.536 bytes (77,8 % do slot padrão de 1.310.720).

A tabela nova mantém `nvs` (0x9000, 20 KB), `otadata` (0xE000) e `app0`
(0x10000) nos mesmos offsets da padrão. Por isso o NVS (sequence_number,
boot_id, último confirmado) **sobrevive** à troca de tabela, nos dois sentidos.

## Nível 1 – desligar o buffer (sem mexer nas partições)

1. Em `include/Config.h`, troque para `#define AGRO_ENABLE_FLASH_BUFFER 0`.
2. Compile e grave normalmente.

O firmware volta ao comportamento anterior (uma leitura pendente em RAM, envio
no `loop()`). A partição `telebuf` fica sem uso. Os dados que ainda estavam no
anel e não foram enviados **ficam na flash mas não são mais enviados**; para
não perdê-los, deixe o buffer ligado até `Buffer pendente = 0` em `/json`
(`_buffer_pending`).

## Nível 2 – devolver o espaço da flash (voltar à tabela padrão)

1. Faça o Nível 1.
2. Em `platformio.ini`, apague (ou comente) a linha
   `board_build.partitions = partitions.csv`.
3. Apague `partitions.csv` (ou mantenha-o fora do build).
4. `pio run` e `pio run -t upload` (o upload regrava a tabela de partições
   junto com o app). **Não** é preciso `erase`: o NVS fica no mesmo lugar.
5. O binário volta a ter o slot padrão de 1,25 MB (~1,3 MB de folga para
   crescer; hoje o firmware ocupa ~1,0 MB).

Atenção: não rode `pio run -t erase` nem apague o NVS sem necessidade. Sem o
NVS o contador `sequence_number` recomeça de zero e o servidor responde 409
(sequência já usada) para leituras novas até passar do último número usado.

## Nível 3 – remover o código por completo

- Se as mudanças **não** foram commitadas: a partir da raiz do repositório,
  `git checkout -- firmware/AgroGuardian_SensorSystem/src/main.cpp
  firmware/AgroGuardian_SensorSystem/include/Config.h
  firmware/AgroGuardian_SensorSystem/platformio.ini` e apague
  `firmware/AgroGuardian_SensorSystem/lib/`, `partitions.csv` e este arquivo.
- Se foram commitadas: `git revert <hash-do-commit>` (ou volte à branch/tag
  anterior). Depois faça o Nível 2 para a tabela de partições da placa.

## Trocar o anel em flash por cartão SD

O resto do firmware só fala com `agro::TelemetryStore`
(`lib/AgroTelemetryStore/src/TelemetryStore.h`): `append`, `peek`, `ack` e
`stats`. Para usar um SD:

1. Crie `SdStore : public agro::TelemetryStore` (por exemplo um arquivo de
   registros de 48 bytes no SD, com o mesmo `TelemetryRecord`).
2. Em `main.cpp`, troque `bufferStore = &bufferRing` por `bufferStore = &sdStore`
   e inicialize o SD no lugar do bloco `bufferFlash.begin()` / `bufferRing.begin()`.
3. Volte à tabela padrão (Nível 2) e, se quiser, ajuste
   `AGRO_OFFLINE_RECORD_INTERVAL_MS` (com o SD o limite deixa de ser o espaço).

O envio em lote, a ordem cronológica, a confirmação por `sequence_number` e a
reconstrução de horário (boot_id + uptime + âncora NTP) continuam iguais.
