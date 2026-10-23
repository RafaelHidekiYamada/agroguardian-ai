# Integracao do ESP32 com o AgroGuardian

## Resultado da integracao

O projeto PlatformIO recebido foi incorporado em
`firmware/AgroGuardian_SensorSystem`. O fluxo de producao e:

```text
Sensores -> ESP32 -> Wi-Fi/HTTPS -> API FastAPI -> PostgreSQL
                                             -> decisao de risco da IA
Dashboard -------------------------------> API/PostgreSQL
```

A API grava a leitura antes de executar clima, geointeligencia e inferencia.
Se essa segunda etapa falhar, a telemetria continua armazenada e a resposta
informa `risk_updated: false`. Um reenvio identico com o mesmo
`sequence_number` devolve a leitura ja criada sem duplicar predicoes ou eventos.

O firmware anterior compilava, mas nao funcionaria em producao porque apontava
para `192.168.0.10`, nao enviava `X-API-Key`, usava TLS sem validar certificado,
nao enviava aceleracao/giroscopio e lia campos de resposta antigos. A versao
integrada corrige esses pontos e identifica corretamente o ultrassonico do ZIP
como HC-SR04.

## 1. Cadastrar a estrutura na dashboard

Acesse o endereco publico do servico `agroguardian-dashboard` no Render (o
hostname pode ter um sufixo, por exemplo `agroguardian-dashboard-xxxx.onrender.com`)
com um administrador e
abra **Equipamentos**. Cadastre nesta ordem:

1. **Fazenda**: cliente, nome, regiao e coordenadas reais.
2. **Equipamento**: selecione a fazenda criada.
3. **ESP32**: selecione o equipamento e defina um identificador, por exemplo
   `ESP32-TRATOR-001`.

Ao clicar em **Gerar credencial**, copie a `api_key`. Ela aparece em texto
somente na criacao ou rotacao. Usuario e senha de administrador nunca entram no
ESP32.

O vinculo usado pela API e armazenado no servidor:

```text
Device ID -> equipamento -> fazenda -> cliente
```

Por isso o firmware nao envia IDs de equipamento, fazenda ou cliente.

## 2. Alterar exatamente estas credenciais no firmware

Na pasta `firmware/AgroGuardian_SensorSystem`, copie:

```powershell
Copy-Item include\Secrets.example.h include\Secrets.h
```

Edite somente `include/Secrets.h`:

```cpp
#define AGRO_WIFI_SSID "NOME_EXATO_DA_REDE_2_4_GHZ"
#define AGRO_WIFI_PASSWORD "SENHA_DA_REDE_WIFI"
#define AGROGUARDIAN_API_URL "https://SEU-SERVICO-API.onrender.com/api/v1/telemetry/esp"
#define AGROGUARDIAN_DEVICE_ID "ESP32-TRATOR-001"
#define AGROGUARDIAN_DEVICE_API_KEY "API_KEY_GERADA_NA_DASHBOARD"
```

Regras para cada valor:

| Campo | Valor correto |
|---|---|
| `AGRO_WIFI_SSID` | Nome exato da rede Wi-Fi 2,4 GHz, respeitando maiusculas |
| `AGRO_WIFI_PASSWORD` | Senha dessa rede |
| `AGROGUARDIAN_API_URL` | `https://<hostname-da-api>/api/v1/telemetry/esp`. Copie o hostname na pagina do servico `agroguardian-api` no Render: ele costuma ter sufixo (por exemplo `agroguardian-api-jhhd.onrender.com`) e nao e o mesmo da dashboard |
| `AGROGUARDIAN_DEVICE_ID` | Mesmo identificador cadastrado na dashboard |
| `AGROGUARDIAN_DEVICE_API_KEY` | Chave gerada especificamente para esse dispositivo |

`Secrets.h` esta ignorado pelo Git. Nao altere `Secrets.example.h` com dados
reais e nao publique a chave em commits, capturas de tela ou logs.

## 3. Rede, host, IP e portas

- Use Wi-Fi **2,4 GHz** com acesso a Internet. O `esp32dev` classico nao usa uma
  rede exclusivamente 5 GHz.
- O roteador entrega o IP do ESP32 por DHCP. Nao e necessario configurar IP
  fixo no ESP, IP do computador, gateway manual ou redirecionamento de porta.
- O host remoto e o hostname publico do servico da API no Render, via HTTPS na porta TCP 443.
- A rede precisa permitir DNS, HTTPS de saida e NTP. O firmware sincroniza o
  horario antes do TLS.
- O IP local impresso no monitor serial serve somente para abrir
  `http://<ip-do-esp>/` e `http://<ip-do-esp>/json` dentro da mesma rede.
- Nao use a URL da dashboard, `localhost`, `127.0.0.1` ou `192.168.x.x` como
  destino da API de producao.

O firmware inclui as CAs raiz usadas pelas cadeias Google Trust Services e
Let's Encrypt do Render e valida certificado e hostname. Nao existe fallback
com `setInsecure()`.

## 4. Pinos e ajustes do hardware

| Modulo | Sinal | ESP32 |
|---|---|---:|
| BME280 | SDA | GPIO 21 |
| BME280 | SCL | GPIO 22 |
| MPU-6050 | SDA | GPIO 21 |
| MPU-6050 | SCL | GPIO 22 |
| HC-SR04 | TRIG | GPIO 5 |
| HC-SR04 | ECHO | GPIO 18 com reducao de 5 V para 3,3 V |
| Sensor capacitivo de solo, opcional | Analogico | GPIO 34 (ADC1) |

Todos os modulos devem compartilhar GND. O ECHO de 5 V do HC-SR04 nao pode
ser ligado diretamente ao ESP32; use level shifter ou divisor resistivo. Um
exemplo e 1 kohm entre ECHO e GPIO 18 e 2 kohm entre GPIO 18 e GND.

Os ajustes de hardware ficam em `include/Config.h`:

- Se os pinos forem diferentes, altere as macros `AGRO_*_PIN`.
- Para o sensor de solo, troque `AGRO_ENABLE_SOIL_SENSOR` para `1` e calibre
  `AGRO_SOIL_ADC_DRY` e `AGRO_SOIL_ADC_WET` com o proprio sensor.
- Sem GPS, mantenha `AGRO_ENABLE_FIXED_LOCATION` em `0`; a IA usa as
  coordenadas da fazenda cadastrada.
- Se usar uma posicao fixa real, troque essa macro para `1` e preencha
  `AGRO_FIXED_LATITUDE` e `AGRO_FIXED_LONGITUDE`.
- O intervalo de envio online esta em 15 segundos. A leitura de sensores ocorre
  a cada 2 segundos. Sem conexao, o firmware grava uma leitura a cada 8 segundos
  no buffer em flash (veja "Buffer offline e envio em lote").

## 5. Compilar, gravar e monitorar

Abra um terminal na pasta do firmware e execute:

```powershell
pio run
pio run --target upload --upload-port COM5
pio device monitor --baud 115200 --port COM5
```

Troque `COM5` pela porta exibida no seu computador. `platformio.ini` nao fixa a
porta, portanto o PlatformIO tambem pode detecta-la automaticamente. Durante o
boot, mantenha o MPU-6050 parado para a calibracao.

Um ciclo correto mostra no serial:

```text
[WiFi] IP por DHCP: ...
[NTP] Horario sincronizado.
[HTTP] ... status 200
[API] accepted telemetry_id=... risco=... nivel=... qualidade=...
```

Depois de uma queda de conexao, tambem aparece `[HTTP] lote ok: N aceitas, ...`.

## Buffer offline e envio em lote

O firmware grava **toda** leitura primeiro numa particao propria da flash
(`telebuf`, um anel circular de registros de 48 bytes com CRC16) e so libera o
que o servidor confirmou. Assim, queda de Wi-Fi, de Internet ou da propria API
(inclusive a API do Render gratuito acordando) nao perde leituras.

| Situacao | Comportamento |
|---|---|
| Online, sem fila | A leitura atual vai pelo endpoint ao vivo `POST /api/v1/telemetry/esp`, a cada 15 s |
| Offline | A leitura e gravada a cada `AGRO_OFFLINE_RECORD_INTERVAL_MS` (8 s) |
| Voltou a conectar | A fila e enviada do registro mais antigo ao mais novo em lotes de ate 40 leituras por `POST /api/v1/telemetry/esp/batch` |
| Reinicio ou queda de energia | O anel, o `sequence_number` e o `boot_id` ficam na flash/NVS e a fila continua |

Capacidade: a particao atual guarda 39.355 registros, cerca de **3,6 dias**
de autonomia gravando a cada 8 s (5 s ~ 2,3 dias; 15 s ~ 6,8 dias; 60 s ~ 27
dias). Para mudar o intervalo, altere `AGRO_OFFLINE_RECORD_INTERVAL_MS` em
`include/Config.h` e grave o firmware de novo. Para desligar o buffer ou
reverter a tabela de particoes, siga `firmware/AgroGuardian_SensorSystem/REVERTER_BUFFER_FLASH.md`.

### Contrato do lote

Mesmos headers do endpoint ao vivo (`X-Device-ID` e `X-API-Key`). O
`device_id` do header precisa ser igual ao do corpo.

```json
{
  "device_id": "ESP32-TRATOR-001",
  "batch_id": "b12-13057-13096",
  "firmware_version": "agroguardian-esp32-2.0.0",
  "operation_type": "campo",
  "more_pending": true,
  "readings": [
    {
      "sequence_number": 13057,
      "timestamp": "2026-10-23T19:41:08Z",
      "boot_id": 12,
      "uptime_ms": 482113,
      "time_quality": "estimated",
      "reset_reason": "poweron",
      "buffered": true,
      "bme280": {"temperature_c": 28.7, "humidity_pct": 78.3, "pressure_hpa": 1009.6},
      "mpu6050": {"accel_x": 0.12, "accel_y": -0.08, "accel_z": 9.74, "inclination_deg": 8.4},
      "ultrasonic": {"sensor_model": "HC-SR04", "distance_cm": 185.0}
    }
  ]
}
```

- `time_quality` indica a confiabilidade do horario da leitura: `synced`
  (NTP no momento da leitura) ou `estimated` (reconstruido a partir do ultimo
  horario valido e do `uptime_ms`, quando o ESP32 reiniciou sem NTP).
- `boot_id` e `uptime_ms` permitem reconstruir a linha do tempo e identificar
  reinicios entre as leituras.
- O servidor aceita ate 100 leituras e 64 KB por lote; o firmware envia ate 40.

Resposta (200). Cada leitura recebe seu proprio resultado, entao uma leitura
invalida nao derruba o lote:

```json
{
  "status": "ok",
  "batch_id": "b12-13057-13096",
  "device_id": "ESP32-TRATOR-001",
  "accepted": 39,
  "duplicates": 1,
  "rejected": 0,
  "results": [
    {"sequence_number": 13057, "result": "accepted", "telemetry_id": 213}
  ],
  "risk_updated": true
}
```

`result` pode ser `accepted`, `duplicate` (mesmo `sequence_number` com o
mesmo conteudo, idempotente) ou `rejected`. Em `rejected`, `permanent: true`
significa que a leitura sera descartada pelo firmware e `permanent: false`
que ele deve tentar de novo. O firmware avanca a confirmacao somente pelo
prefixo contiguo de leituras confirmadas, sem pular nenhuma.

No Serial, um lote bem-sucedido aparece assim:

```text
[HTTP] POST https://<api>/api/v1/telemetry/esp/batch lote=b12-13057-13096 (40 leituras, ... bytes)
[HTTP] lote ok: 40 aceitas, 0 duplicadas, 0 recusadas, 40/40 confirmadas
```

## Banco de dados gratuito do Render: validade e recriacao

O PostgreSQL gratuito do Render **expira 30 dias depois de criado** (ha mais 14
dias de tolerancia; depois o banco e apagado, sem backup) e cada workspace so
pode ter um banco gratuito. Quando isso acontecer:

1. Crie um novo PostgreSQL (plano Free) no Render, na mesma regiao da API
   (hoje Oregon). Banco e API em regioes diferentes nao se enxergam pela rede
   interna.
2. No servico `agroguardian-api` > Environment, atualize `DATABASE_URL` com a
   **Internal Database URL** do banco novo e use *Save, rebuild, and deploy*.
   Cole o valor inteiro, sem espacos nem quebras de linha. O `alembic upgrade
   head` do `startCommand` recria o schema.
3. O banco novo vem **vazio**: confirme as variaveis `INITIAL_ADMIN_*` para
   criar o administrador, depois cadastre de novo fazenda, equipamento e ESP32
   na dashboard.
4. Gere uma **nova API key** do dispositivo, atualize `AGROGUARDIAN_DEVICE_ID`
   e `AGROGUARDIAN_DEVICE_API_KEY` em `include/Secrets.h` e grave o firmware.
   As chaves antigas deixam de valer junto com o banco antigo.

Se o `render.yaml` estiver ligado a um Blueprint no Render, uma sincronizacao do
Blueprint pode sobrescrever a `DATABASE_URL` e a branch dos servicos. Confira
as duas depois de qualquer sincronizacao.

## Contrato enviado pelo firmware

Headers:

```http
Content-Type: application/json
X-Device-ID: ESP32-TRATOR-001
X-API-Key: <chave-do-dispositivo>
```

Exemplo de corpo:

```json
{
  "device_id": "ESP32-TRATOR-001",
  "timestamp": "2026-09-14T18:30:00Z",
  "sequence_number": 128,
  "operation_type": "campo",
  "firmware_version": "agroguardian-esp32-2.0.0",
  "soil_moisture_pct": 61.4,
  "bme280": {
    "temperature_c": 28.7,
    "humidity_pct": 78.3,
    "pressure_hpa": 1009.6
  },
  "mpu6050": {
    "accel_x": 0.12,
    "accel_y": -0.08,
    "accel_z": 9.74,
    "gyro_x": 0.43,
    "gyro_y": 1.18,
    "gyro_z": 0.21,
    "pitch": 8.4,
    "roll": 3.2,
    "inclination_deg": 8.4
  },
  "ultrasonic": {
    "sensor_model": "HC-SR04",
    "distance_cm": 185.0
  }
}
```

As unidades sao: temperatura em C, umidades em %, pressao em hPa, aceleracao
em m/s2, giroscopio em graus/s, angulos em graus e distancia em cm. O firmware
converte a aceleracao em `g` da biblioteca MPU6050_tockn para m/s2.

## Como os dados entram na decisao

Cada leitura fica em `iot_telemetry`, incluindo BME280, MPU-6050, umidade real
do solo, bateria, ultrassonico e GPS. O JSON original sanitizado tambem fica
preservado para auditoria.

Uma leitura recente e `VALID` ou `PARTIAL` alimenta a decisao imediatamente:

- a umidade do solo nao entra no calculo de risco (sem sensor de solo no projeto); se um dispositivo enviar `soil_moisture_pct`, o valor apenas fica armazenado;
- temperatura, umidade do ar e pressao locais prevalecem sobre clima regional;
- GPS influencia o contexto geoespacial sem alterar o cadastro mestre da
  fazenda;
- distancia gera risco de obstaculo;
- aceleracao, giroscopio e inclinacao geram movimento, impacto e tombamento;
- os fatores, a explicacao, os eventos e o score retornado ficam vinculados a
  mesma telemetria.

O historico tambem pode ser exportado para evoluir ou retreinar modelos, mas o
sistema nao retreina automaticamente com cada amostra. Ele usa cada leitura na
inferencia e preserva o historico para auditoria e treinamento controlado.

## Diagnostico de erros

| HTTP | Significado e acao |
|---:|---|
| 200 | Leitura armazenada; consulte `risk_updated` para saber se houve nova decisao |
| 401 | Device ID/API key ausente ou incorreto, chave revogada ou dispositivo desconhecido |
| 403 | Dispositivo desativado ou Device ID do header diferente do corpo (`Device ID do header diverge do payload.`). Em testes pelo `/docs`, use o mesmo `device_id` no header e no corpo |
| 409 | Mesmo `sequence_number` foi reutilizado com conteudo diferente ou falta vinculo |
| 413 | Lote com leituras demais ou grande demais; o firmware divide o lote |
| 422 | No endpoint ao vivo: campo, faixa ou unidade de sensor invalida. No `/batch`: corpo que nao e JSON valido ou envelope invalido (leituras individuais ruins voltam como `rejected` dentro de um 200). O firmware imprime o corpo da resposta no Serial; o campo exato esta em `loc` e `msg` |
| 429 | Limite temporario; o firmware respeita `Retry-After` |
| 5xx/timeout | O firmware repete o mesmo pacote com o mesmo numero de sequencia |

O Render gratuito pode levar cerca de um minuto para sair do estado ocioso. O
firmware usa timeout ampliado e tres tentativas; a leitura permanece
idempotente caso a API tenha gravado antes de a resposta chegar.
