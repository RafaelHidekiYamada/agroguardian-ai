#pragma once

// Copie este arquivo para Secrets.h e altere somente a copia.
// Secrets.h e ignorado pelo Git para que Wi-Fi e API key nao sejam publicados.

#define AGRO_WIFI_SSID "SUA_REDE_WIFI_2G"
#define AGRO_WIFI_PASSWORD "SUA_SENHA_WIFI"

// Endpoint publico da API, nao a URL do dashboard e nem um IP local.
#define AGROGUARDIAN_API_URL "https://agroguardian-api.onrender.com/api/v1/telemetry/esp"

// O Device ID deve ser identico ao cadastrado no dashboard, inclusive maiusculas.
#define AGROGUARDIAN_DEVICE_ID "ESP32-AGRO-001"

// A chave aparece quando o dispositivo IoT e criado ou quando ela e rotacionada.
#define AGROGUARDIAN_DEVICE_API_KEY "COLE_AQUI_A_API_KEY_DO_DISPOSITIVO"
