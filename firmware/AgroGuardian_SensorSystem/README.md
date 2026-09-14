# AgroGuardian Sensor System (ESP32)

Firmware PlatformIO para enviar BME280, MPU-6050, HC-SR04 e umidade do solo
opcional para a API publica. Cada leitura aceita e armazenada pela API pode
atualizar a decisao de risco da IA.

## O que configurar

Copie `include/Secrets.example.h` para `include/Secrets.h` e altere a copia:

```cpp
#define AGRO_WIFI_SSID "NOME_EXATO_DA_REDE_2_4_GHZ"
#define AGRO_WIFI_PASSWORD "SENHA_DA_REDE"
#define AGROGUARDIAN_API_URL "https://agroguardian-api.onrender.com/api/v1/telemetry/esp"
#define AGROGUARDIAN_DEVICE_ID "DEVICE-ID-CADASTRADO"
#define AGROGUARDIAN_DEVICE_API_KEY "API_KEY_GERADA_PARA_O_DISPOSITIVO"
```

O dispositivo precisa ser criado no dashboard e vinculado a um equipamento de
uma fazenda. Copie o Device ID exatamente, inclusive maiusculas, e guarde a API
key exibida na criacao/rotacao. Usuario e senha de administrador nao entram no
firmware.

O ESP32 usa Wi-Fi 2,4 GHz e recebe IP por DHCP. Para o Render, nao configure IP
fixo, IP do computador, IP do ESP, porta do roteador ou redirecionamento. Ele
faz uma conexao de saida para `agroguardian-api.onrender.com` na porta HTTPS 443.
O IP local mostrado no monitor serial serve apenas para abrir a pagina de
diagnostico na mesma rede.

`include/Secrets.h` e ignorado pelo Git. Nao coloque credenciais reais em
`Secrets.example.h`, `Config.h`, commits, prints ou chamados.

## Ligacao atual

| Modulo | Sinal | ESP32 |
|---|---|---:|
| BME280 | SDA | GPIO 21 |
| BME280 | SCL | GPIO 22 |
| MPU-6050 | SDA | GPIO 21 |
| MPU-6050 | SCL | GPIO 22 |
| HC-SR04 | TRIG | GPIO 5 |
| HC-SR04 | ECHO | GPIO 18, com reducao de 5 V para 3,3 V |
| Solo capacitivo (opcional) | Analogico | GPIO 34 (ADC1) |

BME280 e MPU-6050 devem compartilhar GND com o ESP32. Alimente os modulos I2C
conforme a tensao aceita pelo breakout; para modulos 3,3 V, use 3V3. O ECHO do
HC-SR04 nao pode ser ligado diretamente ao ESP32: use level shifter ou divisor,
por exemplo 1 kohm entre ECHO e GPIO 18 e 2 kohm entre GPIO 18 e GND.

Se a fiacao mudar, altere os pinos em `include/Config.h`. Para habilitar o
sensor de solo, mude `AGRO_ENABLE_SOIL_SENSOR` para `1` e calibre
`AGRO_SOIL_ADC_DRY` e `AGRO_SOIL_ADC_WET` com o proprio sensor. A localizacao
fixa vem desativada; a API usa a fazenda cadastrada. Ative
`AGRO_ENABLE_FIXED_LOCATION` somente se preencher coordenadas reais.

## Compilar, gravar e acompanhar

O projeto usa a placa PlatformIO `esp32dev`. As portas nao sao fixadas no
arquivo de projeto; com a placa conectada, o PlatformIO normalmente detecta a
porta. Se houver mais de uma porta, informe a correta no comando de upload.

```powershell
pio run
pio run --target upload --upload-port COM5
pio device monitor --baud 115200 --port COM5
```

Troque `COM5` pela porta que aparecer no seu computador. Durante o boot, deixe
o MPU-6050 parado para calibrar. Um envio correto mostra HTTP 200, `accepted`, o
`telemetry_id`, a qualidade e o risco retornado. A pagina local fica em
`http://<ip-do-esp>/` e `/json`; ela nunca mostra Wi-Fi ou API key.

Erros 401 indicam Device ID/API key incorretos; 403 indica dispositivo
desativado ou IDs divergentes; 409 indica vinculo ausente ou reutilizacao da
sequencia com outro conteudo; 422 indica campo/unidade/faixa de sensor invalida; 429 aguarda o
tempo indicado pela API. Falhas transitórias e respostas 5xx recebem novas
tentativas com o mesmo `sequence_number`; a leitura pendente fica em RAM para o
ciclo seguinte.

## Dados enviados

O JSON usa objetos canonicos `bme280`, `mpu6050`, `ultrasonic` (identificado
como `HC-SR04`) e `gps` quando habilitado, alem de `soil_moisture_pct` quando o
ADC estiver ativo. Aceleracao e enviada em m/s2, giroscopio em graus/s,
inclinacao em graus, distancia em cm, pressao em hPa e umidade em percentual.
O contador de sequencia e reservado no NVS para impedir duplicatas sem gravar a
flash a cada amostra. HTTPS valida o hostname e a CA; nao existe fallback
inseguro.
