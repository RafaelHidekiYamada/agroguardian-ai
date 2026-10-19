#pragma once

#include <Arduino.h>

#if __has_include("Secrets.h")
#include "Secrets.h"
#define AGROGUARDIAN_USING_EXAMPLE_SECRETS 0
#else
#include "Secrets.example.h"
#define AGROGUARDIAN_USING_EXAMPLE_SECRETS 1
#endif

#ifndef AGRO_WIFI_SSID
#error "Defina AGRO_WIFI_SSID em include/Secrets.h"
#endif
#ifndef AGRO_WIFI_PASSWORD
#error "Defina AGRO_WIFI_PASSWORD em include/Secrets.h"
#endif
#ifndef AGROGUARDIAN_API_URL
#error "Defina AGROGUARDIAN_API_URL em include/Secrets.h"
#endif
#ifndef AGROGUARDIAN_DEVICE_ID
#error "Defina AGROGUARDIAN_DEVICE_ID em include/Secrets.h"
#endif
#ifndef AGROGUARDIAN_DEVICE_API_KEY
#error "Defina AGROGUARDIAN_DEVICE_API_KEY em include/Secrets.h"
#endif

// Identidade e operacao
#define AGROGUARDIAN_FIRMWARE_VERSION "agroguardian-esp32-2.0.0"
#define AGROGUARDIAN_OPERATION_TYPE "campo"

// Periodicidade e rede
#define AGRO_SENSOR_READ_INTERVAL_MS 2000UL
// Com o buffer em flash ativo, este e o intervalo de gravacao/envio com conexao normal.
#define AGRO_SEND_INTERVAL_MS 15000UL
#define AGRO_WIFI_CONNECT_TIMEOUT_MS 20000UL
#define AGRO_WIFI_RETRY_INTERVAL_MS 10000UL
#define AGRO_NTP_SYNC_TIMEOUT_MS 15000UL
#define AGRO_HTTP_CONNECT_TIMEOUT_MS 10000
#define AGRO_HTTP_TIMEOUT_MS 25000
#define AGRO_HTTP_RETRIES 3

// I2C: BME280 e MPU-6050 compartilham o barramento.
#define AGRO_I2C_SDA_PIN 21
#define AGRO_I2C_SCL_PIN 22
#define AGRO_MPU6050_ADDRESS 0x68
#define AGRO_BME280_ADDRESS_PRIMARY 0x76
#define AGRO_BME280_ADDRESS_SECONDARY 0x77

// Referencia de "nivelado" do MPU-6050.
// Com 1, a inclinacao e o angulo entre a gravidade atual e o vetor de referencia
// abaixo, em vez de assumir que o eixo Z aponta para cima. Use quando o modulo
// estiver fixado de pe/de lado. O vetor e a aceleracao (m/s2) lida com a
// montagem parada e nivelada; so a direcao importa. Para recalibrar, leia
// accel_x/y/z no monitor serial com a montagem nivelada e atualize os tres valores.
// Com 0, usa os angulos do MPU6050_tockn (Z para cima).
#define AGRO_MPU_USE_LEVEL_REFERENCE 1
#define AGRO_MPU_LEVEL_REF_X 9.706f
#define AGRO_MPU_LEVEL_REF_Y 1.417f
#define AGRO_MPU_LEVEL_REF_Z -0.778f
// Suavizacao da gravidade usada na inclinacao (0-1; menor = mais suave).
#define AGRO_MPU_TILT_FILTER_ALPHA 0.5f

// HC-SR04. O ECHO e 5 V e exige divisor resistivo/level shifter antes do ESP32.
#define AGRO_ENABLE_ULTRASONIC 1
#define AGRO_ULTRASONIC_MODEL "HC-SR04"
#define AGRO_ULTRASONIC_TRIGGER_PIN 5
#define AGRO_ULTRASONIC_ECHO_PIN 18
#define AGRO_ULTRASONIC_TIMEOUT_US 30000UL
#define AGRO_ULTRASONIC_MIN_CM 2.0f
#define AGRO_ULTRASONIC_MAX_CM 400.0f

// Sensor capacitivo de umidade do solo em ADC1. Calibre seco/molhado na sua unidade.
#define AGRO_ENABLE_SOIL_SENSOR 0
#define AGRO_SOIL_ADC_PIN 34
#define AGRO_SOIL_ADC_DRY 3200
#define AGRO_SOIL_ADC_WET 1300

// Sem GPS fisico, deixe 0: a API usa as coordenadas da fazenda cadastrada.
// Ative somente se estas coordenadas representarem a posicao real do equipamento.
#define AGRO_ENABLE_FIXED_LOCATION 0
#define AGRO_FIXED_LATITUDE -23.4550000
#define AGRO_FIXED_LONGITUDE -46.5330000

// Pagina de diagnostico acessivel apenas na rede local do ESP32.
#define AGRO_ENABLE_LOCAL_WEBSERVER 1

// Reserva blocos no NVS para reduzir desgaste da flash. Lacunas apos reboot sao normais.
#define AGRO_SEQUENCE_RESERVATION_SIZE 128UL

// Buffer store-and-forward em flash (particao "telebuf" de partitions.csv).
// Toda leitura de envio e gravada primeiro no anel; o envio sempre le do anel,
// em ordem cronologica, e so libera o que o servidor confirmou.
// 0 desliga tudo e volta ao comportamento anterior (uma leitura pendente em RAM).
#ifndef AGRO_ENABLE_FLASH_BUFFER
#define AGRO_ENABLE_FLASH_BUFFER 1
#endif
// Intervalo de gravacao sem conexao com o servidor (Wi-Fi/NTP/envio falhando).
// Com a particao atual (463 setores uteis x 85 registros = 39.355 registros):
//   5 s -> ~2,3 dias | 7 s -> ~3,2 dias | 15 s -> ~6,8 dias | 60 s -> ~27 dias.
// Com conexao, a gravacao segue AGRO_SEND_INTERVAL_MS.
#ifndef AGRO_OFFLINE_RECORD_INTERVAL_MS
#define AGRO_OFFLINE_RECORD_INTERVAL_MS 8000UL
#endif
#define AGRO_BUFFER_PARTITION_LABEL "telebuf"
#define AGRO_BUFFER_PARTITION_SUBTYPE 0x40
// Envio em lote: leituras por POST, pausa entre lotes e idade maxima (s) para
// uma leitura unica ir pelo endpoint "ao vivo".
#define AGRO_BATCH_MAX_RECORDS 40
#define AGRO_BATCH_INTERVAL_MS 600UL
#define AGRO_LIVE_MAX_AGE_S 25
// Se o servidor ainda nao tem /batch (404/405), reenvia item a item e tenta o lote de novo depois.
#define AGRO_BATCH_UNSUPPORTED_RETRY_MS 600000UL
// Tarefa FreeRTOS de rede (Wi-Fi, NTP e envio) para nao travar leituras nem o servidor web.
#define AGRO_NET_TASK_STACK_BYTES 12288
#define AGRO_NET_BACKOFF_MIN_MS 2000UL
#define AGRO_NET_BACKOFF_MAX_MS 60000UL
// Ultimo horario valido salvo no NVS (base das estimativas de boots sem NTP).
#define AGRO_LAST_EPOCH_SAVE_INTERVAL_MS 600000UL
