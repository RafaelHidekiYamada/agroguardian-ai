# AgroGuardian AI

Plataforma inteligente de prevenção de sinistros agrícolas com:
- **Risk AI**: score de risco de 0 a 100.
- **Smart Alerts**: alertas preventivos para operador e gestor.
- **Safe Route AI**: recomendação de rota mais segura.
- **Risk Map**: mapa de risco por zona da fazenda.
- **Sompo Analytics**: painel executivo com ranking, tendências, auditoria e explicações.

## Por que estas tecnologias
- **FastAPI**: escolhida para a API central porque é rápida, moderna e gera documentação automática em Swagger/ReDoc. Isso deixa o projeto com aparência profissional e facilita a demonstração.
- **Streamlit**: escolhida para o dashboard porque permite criar interface interativa com pouco código, ideal para MVP acadêmico e apresentação executiva.
- **XGBoost + scikit-learn**: XGBoost é forte em dados tabulares; scikit-learn entra como base para treino, métricas, fallback e compatibilidade.
- **OpenWeather**: usado para clima em tempo real quando houver chave de API; sem chave, o sistema usa fallback para continuar funcionando no MVP.
- **OpenStreetMap + Folium**: usados para mapa porque são livres, visuais e baratos para um projeto acadêmico.
- **PostgreSQL**: banco relacional profissional para histórico, auditoria, previsões, alertas e relatórios.
- **Render**: plataforma de deploy escolhida porque conecta o repositório GitHub e faz deploy automático a cada atualização do código.

## Arquitetura
Entrada de dados (telemetria, clima, mapas, histórico) -> API central -> motor de risco -> alertas e explicações -> dashboard Sompo / cliente / operador.

## Como rodar localmente

### 1) Criar ambiente e instalar dependências
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

### 2) Configurar variáveis
Copie `.env.example` para `.env` e ajuste, se quiser.

### 3) Aplicar o banco de dados
```bash
alembic upgrade head
```

Para criar dados locais de desenvolvimento em um banco sem administrador,
defina `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_EMAIL` e
`INITIAL_ADMIN_PASSWORD` no `.env`, depois execute:

```bash
python scripts/seed_database.py
```

Em banco com um usuario de papel `ADMIN`, o seed reutiliza essa conta sem ler
ou redefinir a senha.

PostgreSQL e o banco principal:

```text
DATABASE_URL=postgresql+psycopg://USUARIO:SENHA@HOST:5432/agroguardian?sslmode=require
```

SQLite continua disponivel para desenvolvimento local:

```text
DATABASE_URL=sqlite:///./agroguardian.db
```

Documentacao completa: `docs/database.md` e `docs/database_erd.md`.

### 4) Subir a API
```bash
uvicorn backend.main:app --reload
```

A documentação automática aparece em:
- `/docs`
- `/redoc`

### 5) Subir o dashboard
Em outro terminal:
```bash
streamlit run dashboard/app.py
```

## Deploy no Render
1. Suba o projeto para o GitHub.
2. Crie dois serviços web no Render usando o mesmo repositório:
    - `agroguardian-api`
    - `agroguardian-dashboard`
3. Configure `ENVIRONMENT=production`, `IOT_AUTH_ENABLED=true`, `DATABASE_URL` e `JWT_SECRET_KEY` no serviço da API.
4. Configure `API_BASE_URL=https://<api-publica>` no dashboard quando usar um dominio proprio. O blueprint usa o hostname publico do Render como fallback HTTPS.
5. Defina `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_EMAIL` e `INITIAL_ADMIN_PASSWORD`, depois execute `python scripts/seed_database.py` uma vez no Render Shell para um banco novo.
6. Conecte o Render ao GitHub e ative deploy automático.

## O que o projeto entrega
- Score de risco por equipamento, fazenda, região e operação.
- Alertas por proximidade de água, chuva, velocidade e terreno inclinado.
- Recomendações práticas.
- Mapa com zonas de atenção.
- Explicação dos fatores de risco.
- Auditoria completa das previsões.
- Ranking executivo para a Sompo.
- Simulador de cenário "e se chover amanhã?".

## Novos fluxos de telemetria e risco

### ESP32

O ESP envia leituras autenticadas para:

```bash
POST /api/v1/telemetry/esp
```

Headers obrigatorios:

```http
X-Device-ID: ESP32-TRATOR-001
X-API-Key: <api_key_gerada_no_cadastro>
```

O firmware fisico envia HTTPS para a URL publica da API, sem depender da rede
Wi-Fi do dashboard. Ele envia BME280 (temperatura, umidade e pressao),
JSN-SR04T (distancia em cm) e MPU-6050 (aceleracao e inclinacao). O exemplo de
firmware fica em:

```text
firmware/esp32_agroguardian_telemetry/esp32_agroguardian_telemetry.ino
```

Documentacao do payload:

```text
docs/esp32_integration.md
```

O ESP32 nao informa o `equipment_id` de forma confiavel. A API busca o vinculo
seguro em `iot_devices.device_id -> equipment_id` e rejeita dispositivo
desconhecido, desativado ou com API key invalida.

`/api/v1/iot/telemetry` continua como alias de compatibilidade; firmware e
simulador novos usam `/api/v1/telemetry/esp`.

### Administracao e RBAC

Login JWT:

```bash
POST /api/v1/auth/login
GET  /api/v1/auth/me
POST /api/v1/auth/change-password
POST /api/v1/auth/logout
```

Nao ha credenciais padrao de producao. Em banco novo, defina todas as
variaveis `INITIAL_ADMIN_*` e execute `python scripts/seed_database.py` para
criar o primeiro administrador com senha hash bcrypt.

Roles e permissoes sao persistidas nas tabelas `roles`, `permissions`,
`user_roles`, `role_permissions` e `user_permissions`. Novas senhas e API keys
sao armazenadas com hash bcrypt.

Endpoints administrativos:

```bash
GET    /api/v1/admin/users
POST   /api/v1/admin/users
GET    /api/v1/admin/users/{id}
PUT    /api/v1/admin/users/{id}
DELETE /api/v1/admin/users/{id}
PUT    /api/v1/admin/users/{id}/permissions
POST   /api/v1/admin/users/{id}/reset-password
GET    /api/v1/admin/roles
GET    /api/v1/admin/permissions
```

### Dispositivos IoT e telemetria

```bash
GET    /api/v1/iot/devices
GET    /api/v1/iot/devices/{device_id}
GET    /api/v1/admin/iot/devices/{id}
POST   /api/v1/admin/iot/devices
PUT    /api/v1/admin/iot/devices/{id}
DELETE /api/v1/admin/iot/devices/{id}

GET /api/v1/equipments
POST /api/v1/admin/equipments
PUT /api/v1/admin/equipments/{equipment_id}
DELETE /api/v1/admin/equipments/{equipment_id}

GET /api/v1/equipments/{equipment_id}/telemetry/latest
GET /api/v1/equipments/{equipment_id}/telemetry/history
GET /api/v1/equipments/{equipment_id}/iot-events
GET /api/v1/equipments/{equipment_id}/risk/current
```

Cada leitura gera novo registro em `iot_telemetry`; o historico nao e
sobrescrito.

### Simulador ESP32

Cadastre um dispositivo no dashboard ou via `POST /api/v1/admin/iot/devices` e
guarde a API key retornada. Depois:

```bash
AGROGUARDIAN_API_URL=https://<api-publica> ESP32_DEVICE_ID=ESP32-TRATOR-001 ESP32_API_KEY=SUA_KEY python tools/esp32_simulator.py --scenario normal
AGROGUARDIAN_API_URL=https://<api-publica> ESP32_DEVICE_ID=ESP32-TRATOR-001 ESP32_API_KEY=SUA_KEY python tools/esp32_simulator.py --scenario obstacle_near --count 5 --interval 2
```

Cenarios: `normal`, `obstacle_near`, `inclination_high`, `accel_anormal`,
`temperature_high`, `humidity_high`.

### Como a telemetria influencia a IA

O backend deriva features do MPU-6050:

```text
acceleration_magnitude
max_tilt_angle
movement_anomaly_score
possible_impact
```

BME280 adiciona temperatura, umidade e pressao; JSN-SR04T adiciona distancia;
MPU-6050 adiciona aceleracao e inclinacao. Esses campos entram em
`build_features`, `calculate_contextual_risk`, `build_alerts` e
`build_structured_explanation`. A resposta de risco inclui `explainable_ai`,
`confidence_score`, `telemetry_status` e `data_quality_status`.

### Scores agregados

Novos endpoints:

```bash
GET /api/v1/risk/regions
GET /api/v1/risk/equipment
GET /api/v1/risk/equipment/{equipment_id}/history
GET /api/v1/telemetry/sensors/latest
```

O score por equipamento usa historico recente, media historica, pico de risco e
taxa de alto risco. O score por regiao usa a mesma logica agrupando por regiao.

### Dados reais para ML

O treino agora prefere dados historicos reais da NASA POWER Daily API para
temperatura, umidade, pressao, precipitacao e vento em regioes agricolas
brasileiras. Como ainda nao ha base real de sinistros dos equipamentos, o target
`risk_score` e gerado por heuristica operacional transparente ate que sinistros
reais sejam anexados ao projeto.

```bash
python -m ml.training_data --start 20240101 --end 20251231 --force
python -m ml.train_decision_trees
python -m ml.evaluate_models
```

Arquivos gerados:

```text
ml/data/nasa_power_agroguardian_training.csv
ml/data/nasa_power_agroguardian_training.metadata.json
ml/saved_models/best_risk_model.joblib
ml/model_metrics.json
```

### Geolocalizacao precisa

A geointeligencia consulta OpenStreetMap via Overpass para localizar rios,
corpos d'agua e canais proximos. Se o Overpass estiver indisponivel, o sistema
usa fallback local marcado explicitamente em `geo_context.nearest_water.source`.

Configuracoes:

```bash
OVERPASS_API_URL=https://overpass-api.de/api/interpreter
ENABLE_OVERPASS_GEO=true
GEO_SEARCH_RADIUS_M=3000
```
