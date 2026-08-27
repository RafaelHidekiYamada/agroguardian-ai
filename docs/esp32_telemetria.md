# Telemetria ESP32

Use `docs/esp32_integration.md` as the canonical contract. The official sender
route is `POST /api/v1/telemetry/esp`; the old `/api/v1/iot/telemetry` route is
compatibility-only. The physical MVP
uses only these sensor groups:

- BME280: temperature, air humidity, and pressure in hPa.
- JSN-SR04T: obstacle distance in cm.
- MPU-6050: acceleration on three axes and inclination in degrees.

The dashboard and risk engine consume records from `iot_telemetry`, not the
legacy `sensor_readings` table. Every accepted reading keeps raw payload,
canonical values, derived motion values, data quality, freshness, and an
optional linked risk prediction.

Run the HTTPS simulator after provisioning a device. `AGROGUARDIAN_API_URL` can
be the public API base URL or the full official endpoint:

```bash
AGROGUARDIAN_API_URL=https://<api-publica> ESP32_DEVICE_ID=ESP32-TRATOR-001 ESP32_API_KEY=SUA_CHAVE python tools/esp32_simulator.py --scenario normal
AGROGUARDIAN_API_URL=https://<api-publica> ESP32_DEVICE_ID=ESP32-TRATOR-001 ESP32_API_KEY=SUA_CHAVE python tools/esp32_simulator.py --scenario obstacle_near
AGROGUARDIAN_API_URL=https://<api-publica> ESP32_DEVICE_ID=ESP32-TRATOR-001 ESP32_API_KEY=SUA_CHAVE python tools/esp32_simulator.py --scenario inclination_high
AGROGUARDIAN_API_URL=https://<api-publica> ESP32_DEVICE_ID=ESP32-TRATOR-001 ESP32_API_KEY=SUA_CHAVE python tools/esp32_simulator.py --scenario accel_anormal
AGROGUARDIAN_API_URL=https://<api-publica> ESP32_DEVICE_ID=ESP32-TRATOR-001 ESP32_API_KEY=SUA_CHAVE python tools/esp32_simulator.py --scenario temperature_high
AGROGUARDIAN_API_URL=https://<api-publica> ESP32_DEVICE_ID=ESP32-TRATOR-001 ESP32_API_KEY=SUA_CHAVE python tools/esp32_simulator.py --scenario humidity_high
```

Export canonical telemetry for model training without raw payloads or device
credentials:

```bash
python scripts/export_iot_dataset.py --equipment-id 1 --output data_science_r/data/equipment_1_telemetry.csv
```
