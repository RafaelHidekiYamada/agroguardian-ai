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
