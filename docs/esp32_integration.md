# Integracao ESP32 Fisico

## Arquitetura

O ESP32 envia telemetria por Internet para a API publica. Ele e o dashboard nao
precisam estar na mesma rede Wi-Fi:

```text
ESP32 -> Wi-Fi com Internet -> HTTPS publico -> FastAPI -> PostgreSQL
Dashboard -> HTTPS publico -> FastAPI -> PostgreSQL
```

O endpoint oficial para firmware e simulador e:

```text
POST https://<api-publica>/api/v1/telemetry/esp
```

`POST /api/v1/iot/telemetry` continua disponivel apenas como compatibilidade
para clientes antigos. Ambos usam exatamente a mesma ingestao autenticada.

## Provisionamento Seguro

1. Crie o equipamento e vincule-o a uma fazenda no dashboard ou pela API.
2. Como `ADMIN` ou usuario com `iot.devices.manage`, crie o dispositivo:

```bash
curl -X POST "https://<api-publica>/api/v1/admin/iot/devices" \
  -H "Authorization: Bearer <JWT_ADMIN>" \
  -H "Content-Type: application/json" \
  -d '{
    "device_identifier": "ESP32-AGRO-001",
    "equipment_id": 1,
    "name": "ESP32 do trator 01",
    "device_type": "ESP32",
    "firmware_version": "agroguardian-esp32-1.0.0",
    "status": "OFFLINE"
  }'
```

3. Guarde a `api_key` retornada nessa resposta. O valor plaintext aparece
somente na criacao e em uma rotacao posterior. O banco guarda apenas bcrypt
hashes.
4. Configure no firmware `DEVICE_ID`, `ESP32_API_KEY`,
`AGROGUARDIAN_API_URL` e a CA usada pelo dominio HTTPS.

O dispositivo nunca envia `equipment_id`, `farm_id`, `client_id` ou API key no
JSON. A API determina o vinculo seguro:

```text
device_id -> equipment -> farm -> client
```

## Contrato Canonico

Headers obrigatorios:

```http
Content-Type: application/json
X-Device-ID: ESP32-AGRO-001
X-API-Key: <API_KEY_DO_DISPOSITIVO>
```

Payload canonico:

```json
{
  "device_id": "ESP32-AGRO-001",
  "operation_type": "campo",
  "firmware_version": "agroguardian-esp32-1.0.0",
  "bme280": {
    "temperature_c": 28.7,
    "humidity_pct": 78.3,
    "pressure_hpa": 1009.6
  },
  "mpu6050": {
    "accel_x": 0.12,
    "accel_y": -0.08,
    "accel_z": 9.74,
    "pitch": 8.4,
    "roll": 3.2,
    "inclination_deg": 8.4
  },
  "jsn_sr04t": {
    "distance_cm": 185.0,
    "timeout": false,
    "out_of_range": false
  },
  "gps": {
    "latitude": -23.455,
    "longitude": -46.533
  },
  "speed_kmh": 0
}
```

`timestamp` e opcional. Sem relogio NTP confiavel, omita-o e o servidor usa
UTC no recebimento. `gps` tambem e opcional enquanto nao houver modulo fisico.
`sequence_number` e opcional, mas o firmware de referencia persiste um contador
no NVS para tornar reenvios idempotentes apos reboot.

Unidades obrigatorias:

- BME280: `temperature_c` em C, `humidity_pct` em %, `pressure_hpa` em hPa.
- JSN-SR04T: `distance_cm` em cm. Nao use HC-SR04 na documentacao fisica.
- MPU-6050: eixos e magnitude em `m/s2`; repouso e aproximadamente
  `9.80665 m/s2`. Pitch, roll e inclinacao sao graus.

Payloads flat antigos continuam sendo normalizados para compatibilidade. O
formato aninhado e a fonte canonica para firmware novo. `pressure_pa` e aceito
somente como adaptador e convertido para hPa.

## Resposta do ESP

```json
{
  "status": "accepted",
  "telemetry_id": 84921,
  "equipment_id": 1,
  "risk_updated": true,
  "risk_score": 76.4,
  "risk_level": "Alto",
  "telemetry_status": "LIVE",
  "data_quality_status": "VALID",
  "confidence_score": 91.0,
  "events": []
}
```

Firmware novo deve usar `risk_level`; `risk_label` e `alert_level` pertencem a
compatibilidades de respostas de previsao legadas.

Erros relevantes:

- `401`: headers ausentes, chave invalida, chave revogada ou dispositivo desconhecido.
- `403`: dispositivo desativado ou `device_id` de header diferente do corpo.
- `409`: sequence repetido ou vinculo de equipamento/fazenda ausente.
- `413`: payload excede `IOT_MAX_PAYLOAD_BYTES`.
- `422`: schema, faixa fisica ou qualidade invalida.
- `429`: limite por dispositivo; respeite `Retry-After`.

## Como a IA Usa os Sensores

O modelo ML existente continua recebendo somente suas features treinadas. O
resultado final e auditavel e composto por:

```text
score base do modelo ML
+ ajuste geoespacial/contextual
+ motor operacional IoT (BME280, JSN-SR04T, MPU-6050)
= score final
```

O motor IoT calcula magnitude de aceleracao, pitch/roll absolutos, inclinacao
maxima, anomalia de movimento e possivel impacto. Gravidade normal em repouso
nao e um impacto. Obstaculo, inclinacao, movimento, impacto, temperatura,
umidade e pressao podem alterar o score e viram fatores persistidos em
`RiskPrediction`, eventos IoT, explicacao e recomendacao.

BME280 e uma leitura local do equipamento. OpenWeather permanece como contexto
regional e so preenche temperatura/umidade/pressao se a leitura fisica estiver
ausente; nunca a substitui automaticamente.

Uma leitura `LIVE` e `VALID` ou `PARTIAL` pode atualizar a IA. Historico stale,
offline, suspect ou invalid e preservado, mas nao e usado como evidencia fisica
atual. Com defaults: ate 30 s e `LIVE`, ate 300 s e `STALE`, e depois `OFFLINE`.

## CURL e Simulador

```bash
curl -X POST "https://<api-publica>/api/v1/telemetry/esp" \
  -H "Content-Type: application/json" \
  -H "X-Device-ID: ESP32-AGRO-001" \
  -H "X-API-Key: SUA_API_KEY" \
  -d '{
    "device_id": "ESP32-AGRO-001",
    "operation_type": "campo",
    "bme280": {"temperature_c": 28.7, "humidity_pct": 78.3, "pressure_hpa": 1009.6},
    "mpu6050": {"accel_x": 0.12, "accel_y": -0.08, "accel_z": 9.74, "pitch": 8.4, "roll": 3.2, "inclination_deg": 8.4},
    "jsn_sr04t": {"distance_cm": 185.0, "timeout": false, "out_of_range": false}
  }'
```

O simulador aceita uma URL base ou o endpoint completo e retorna codigo nao-zero
se qualquer envio falhar:

```bash
AGROGUARDIAN_API_URL=https://<api-publica> \
ESP32_DEVICE_ID=ESP32-AGRO-001 \
ESP32_API_KEY=SUA_API_KEY \
python tools/esp32_simulator.py --scenario normal
```

## Dashboard

Usuarios autenticados e autorizados consultam a API publica, nunca o IP local
do ESP32:

```text
GET /api/v1/equipments/{equipment_id}/telemetry/latest
GET /api/v1/equipments/{equipment_id}/telemetry/history?period=1h
GET /api/v1/equipments/{equipment_id}/risk/current
GET /api/v1/equipments/{equipment_id}/iot-events
```

A central de telemetria mostra freshness, qualidade, confianca, BME280,
JSN-SR04T, eixos/magnitude/pitch/roll/inclinacao/impacto do MPU-6050, fatores,
eventos, explicacao e historico com polling opcional.

## Deploy Render

`render.yaml` cria API, dashboard e PostgreSQL. A API inicia com:

```bash
alembic upgrade head && gunicorn -k uvicorn.workers.UvicornWorker -w 1 -b 0.0.0.0:$PORT backend.main:app
```

Configure no servico API:

```text
ENVIRONMENT=production
IOT_AUTH_ENABLED=true
DATABASE_URL=<PostgreSQL Render>
JWT_SECRET_KEY=<secret>
INITIAL_ADMIN_USERNAME=<admin inicial>
INITIAL_ADMIN_EMAIL=<email inicial>
INITIAL_ADMIN_PASSWORD=<senha inicial>
```

Em um banco novo, execute uma vez no Render Shell apos definir
`INITIAL_ADMIN_*`:

```bash
python scripts/seed_database.py
```

Isso inicializa RBAC e o administrador para criar equipamentos e dispositivos.
No dashboard, `API_BASE_URL` explicita tem prioridade. O blueprint tambem passa
o hostname publico da API para formar HTTPS; `API_HOSTPORT` e apenas fallback
interno conhecido. Nunca configure o ESP com localhost, `127.0.0.1` ou
`192.168.x.x` em producao.

## Checklist de Validacao

1. Faça deploy e abra `https://<api-publica>/health`.
2. Inicialize o administrador seguro se o banco for novo.
3. Crie fazenda, equipamento e dispositivo IoT.
4. Copie a API key retornada uma unica vez.
5. Configure a URL HTTPS publica, CA, device ID e key no firmware.
6. Faça upload e confirme `HTTP 200` / `status: accepted` no serial.
7. Confirme a linha em `iot_telemetry` e o dispositivo `ONLINE`.
8. Abra a central de telemetria do dashboard.
9. Confirme `risk_updated`, fatores IoT, explicacao e eventos quando aplicavel.
