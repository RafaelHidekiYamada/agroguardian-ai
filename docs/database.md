# Banco de Dados do AgroGuardian AI

## Objetivo

O banco relacional do AgroGuardian AI registra a estrutura organizacional, operacao agricola, contexto ambiental, risco, alertas, recomendacoes, incidentes, auditoria, catalogo de IA e relatorios. PostgreSQL e o banco principal. SQLite continua suportado para desenvolvimento local e testes automatizados.

O modelo e aditivo: tabelas e dados usados pela aplicacao anterior foram preservados. Novos fluxos usam o dominio normalizado sem apagar historicos de predicao, alerta, auditoria ou telemetria existentes.

## Implementacao

- ORM: SQLAlchemy.
- Migrations: Alembic em `alembic/`.
- Modelos legados e compatibilidade: `backend/models.py`.
- Modelos relacionais adicionados: `backend/models_extended.py`.
- Schemas Pydantic seguros: `backend/database_schemas.py`.
- Servico transacional de predicao: `backend/database_services.py`.
- Seed de desenvolvimento: `backend/database_seed.py` e `scripts/seed_database.py`.

`backend/models.py` continua sendo o ponto de importacao usado pela API. O novo modulo separado evita quebrar imports e endpoints atuais enquanto deixa o dominio novo organizado.

## Configuracao

### PostgreSQL

Use uma URL explicita com psycopg:

```env
DATABASE_URL=postgresql+psycopg://USUARIO:SENHA@HOST:5432/agroguardian?sslmode=require
```

As URLs `postgres://` e `postgresql://` tambem sao normalizadas automaticamente para o driver psycopg. O arquivo `render.yaml` provisiona um PostgreSQL no Render e executa a migration antes de iniciar a API.

### SQLite local

```env
DATABASE_URL=sqlite:///./agroguardian.db
```

SQLite ativa `PRAGMA foreign_keys=ON` ao abrir conexoes da aplicacao, para aproximar o comportamento local ao PostgreSQL. Ele e indicado apenas para desenvolvimento e testes de baixo volume.

## Migrations

Instale as dependencias e aplique o schema:

```bash
pip install -r requirements.txt
alembic upgrade head
```

Verifique se o schema e compativel com os modelos:

```bash
alembic current
alembic check
```

Para um SQLite legado ja existente, faca backup antes de executar a migration. A revision detecta o schema anterior, cria somente as tabelas novas e acrescenta colunas, FKs, constraints e indices sem apagar registros.

```bash
copy agroguardian.db agroguardian.backup.db
alembic upgrade head
```

`alembic downgrade -1` e permitido somente em banco vazio criado por esta revision. A migration bloqueia downgrade de banco legado ou de banco com dados, porque esse procedimento seria destrutivo. Para rollback de dados reais, restaure o backup.

## Seed de Desenvolvimento

O seed e idempotente e cria roles, permissoes, administrador, clientes, fazendas, equipamentos, contexto ambiental, catalogo de IA, predicao, fatores, alertas, recomendacoes, incidente, simulacao, configuracoes e dados minimos para o dashboard legado.

Em banco sem um usuario com papel `ADMIN`, defina as credenciais do primeiro
administrador fora do codigo:

```env
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_EMAIL=admin@example.com
INITIAL_ADMIN_PASSWORD=uma-senha-forte-e-secreta
```

Execute depois da migration:

```bash
python scripts/seed_database.py
```

O seed reutiliza o administrador existente sem redefinir senha, sem remover papeis adicionais e sem sobrescrever permissoes ja concedidas. `AUTO_SEED_DEMO=false` e o padrao; habilite-o somente em ambiente local quando desejar que a API execute o seed no startup.

## Tabelas

### Identidade e acesso

| Tabela | Finalidade |
| --- | --- |
| `users` | Usuarios autenticaveis, hash de senha, status, superusuario e timestamps. |
| `roles` | Perfis de sistema, incluindo ADMIN, SOMPO, GESTOR, OPERADOR, ANALISTA e LEITURA. |
| `permissions` | Permissoes por codigo, como `risk.predict` e `reports.export`. |
| `user_roles` | Relacao N:N entre usuarios e roles. |
| `role_permissions` | Relacao N:N entre roles e permissoes. |
| `user_permissions` | Sobrescritas de permissao por usuario. |
| `user_clients` | Acesso de usuario a clientes autorizados. |
| `user_farms` | Acesso de usuario a fazendas autorizadas. |
| `user_equipments` | Acesso de usuario a equipamentos autorizados. |
| `user_access_scopes` | Estrutura legada de escopo, preservada e preparada com `client_id`. |
| `access_events` | Eventos de login, logout e acesso da aplicacao existente. |
| `user_accounts` | Conta legada preservada para compatibilidade de autenticacao. |

### Estrutura operacional

| Tabela | Finalidade |
| --- | --- |
| `clients` | Clientes ou segurados, documento unico quando informado, contato e status. |
| `farms` | Fazendas, vinculadas opcionalmente ao cliente durante transicao de dados legados. |
| `equipment` | Equipamentos agricolas. O nome fisico singular foi mantido para preservar FKs e endpoints existentes. |
| `iot_devices` | Vinculo generico entre dispositivo e equipamento, identificador, firmware, estado e metadados gerais. |
| `operations` | Operacoes de campo, transporte, colheita, pulverizacao, manutencao ou proximidade de agua. |
| `alert_policies` | Politicas por cliente, fazenda e operacao; mantem os limites usados pelo motor atual. |

### Contexto ambiental e geografico

| Tabela | Finalidade |
| --- | --- |
| `weather_records` | Clima por fazenda, fonte, instante de coleta e payload bruto dinamico. |
| `soil_records` | Amostras de solo, textura, materia organica, pH e drenagem. |
| `terrain_records` | Elevacao, inclinacao, distancia de agua e estrada, uso do solo e fonte geografica. |
| `data_sources` | Catalogo de fontes como INMET, NASA POWER, SoilGrids, SRTM e OpenStreetMap. |

### Risco, prevencao e historico

| Tabela | Finalidade |
| --- | --- |
| `risk_predictions` | Predicoes normalizadas, score, nivel, confianca, snapshot de entrada e resumos. |
| `risk_prediction_factors` | Fatores explicaveis de cada predicao, sem compactar todos em um unico JSON. |
| `alerts` | Alertas operacionais normalizados e seu ciclo de reconhecimento e resolucao. |
| `recommendations` | Recomendacoes associadas a predicoes e aplicacao pelo usuario. |
| `risk_simulations` | Comparacao entre condicoes base e simuladas. |
| `prevented_loss_records` | Estimativa de risco reduzido e economia potencial; valores financeiros sao explicitamente estimados no MVP. |
| `incidents` | Historico de sinistros e incidentes por cliente, fazenda, equipamento e operacao. |
| `generated_reports` | Metadados de relatorios gerados, sem armazenar o dashboard inteiro. |

### IA, governanca e configuracao

| Tabela | Finalidade |
| --- | --- |
| `dataset_versions` | Versoes de datasets, origem, volume, checksum e metadata. |
| `model_versions` | Versoes de modelos, metricas, parametros, features, artefato e estado de deploy. |
| `audit_logs` | Auditoria estruturada com usuario, entidade, valores antes/depois, request e IP. Campos legados continuam disponiveis. |
| `system_settings` | Configuracoes alteraveis, como thresholds e politica padrao, sem hardcode. |
| `notifications` | Notificacoes de dashboard; EMAIL, PUSH e WHATSAPP ficam preparados sem integracao externa. |

### Tabelas legadas preservadas

| Tabela | Motivo de preservacao |
| --- | --- |
| `telemetry_records` | Historico operacional usado pelos relatorios e dashboard existentes. |
| `prediction_records` | Historico de predicoes consumido por relatorios, exportacao R e compatibilidade. |
| `alert_records` | Alertas gerados pelo motor existente. |
| `sensor_readings` | Endpoint legado de leitura de sensores ainda exposto pela API. |
| `iot_telemetry` | Telemetria detalhada ja existente no projeto antes desta modelagem. Nao foi expandida por esta entrega. |
| `route_recommendations` | Recomendacoes de rota existentes. |

## Relacionamentos Principais

```text
User <-> Role <-> Permission
User <-> Client / Farm / Equipment

Client -> Farm -> Equipment -> Operation
Equipment -> IoT Device

Farm -> Weather / Soil / Terrain
Operation -> Incident

Risk Prediction -> Factors / Alerts / Recommendations / Prevented Losses
Risk Prediction -> Model Version -> Dataset Version

Alert -> Notification
User -> Audit Log / Generated Report / Risk Simulation
```

O diagrama completo esta em [database_erd.md](database_erd.md).

## Integridade, Constraints e Indices

As principais regras aplicadas pelo banco incluem:

- `users.username` e `users.email` unicos.
- `clients.document` unico quando preenchido.
- `equipment.serial_number` e `equipment.internal_code` unicos quando preenchidos.
- `dataset_versions(name, version)` e `model_versions(name, version)` unicos.
- Score de risco e confianca entre 0 e 100.
- Umidade, importancia percentual e reducao esperada entre 0 e 100.
- pH entre 0 e 14; latitude e longitude em faixas geograficas validas.
- Custos e valores estimados nao negativos.
- Enums portaveis com check constraints para niveis de risco, alertas, incidentes, modelos, datasets, fontes ambientais e status operacionais.
- FKs com `RESTRICT` para dados historicos e `CASCADE` somente nas tabelas de concessao de acesso N:N.

Indices compostos cobrem consultas frequentes, incluindo:

- `risk_predictions(equipment_id, created_at)` e `risk_predictions(farm_id, created_at)`.
- `alerts(equipment_id, status, created_at)` e `alerts(status, created_at)`.
- `operations(equipment_id, started_at)`.
- `weather_records(farm_id, recorded_at)`.
- `soil_records(farm_id, sampled_at)`.
- `incidents(equipment_id, occurred_at)`.
- `audit_logs(entity_type, entity_id, created_at)`.
- `iot_telemetry(equipment_id, timestamp)` e `iot_telemetry(device_id, timestamp)` preservados do fluxo existente.

## Deletes e Historico

Usuarios, clientes, fazendas, equipamentos, dispositivos e politicas usam `is_active` ou status para desativacao logica. O sistema nao deve apagar fisicamente historicos de predicao, alertas, incidentes, auditoria ou telemetria.

As tabelas N:N de acesso podem ser limpas com cascade porque representam apenas autorizacao, nao historico de negocio. Todas as outras FKs historicas usam `RESTRICT` para impedir exclusoes que deixariam registros sem contexto.

## JSON e JSONB

JSON e usado somente para dados dinamicos ou snapshots:

- `risk_predictions.input_snapshot_json`.
- payloads brutos ambientais.
- metricas, parametros e features de modelos.
- metadados de datasets, dispositivos e configuracoes.
- condicoes de simulacao e parametros de relatorios.

No PostgreSQL esses campos usam JSONB. Dados pesquisados com frequencia, como score, status, equipamento, fazenda e timestamps, permanecem em colunas tipadas e indexadas.

## Transacoes

`create_risk_prediction_bundle()` em `backend/database_services.py` grava, em uma unica transacao:

```text
RiskPrediction
-> RiskPredictionFactor
-> Alert
-> Recommendation
-> AuditLog
```

Qualquer falha em uma FK, constraint ou insercao dependente executa rollback de todo o bundle.

## Telemetria IoT Fisica

O schema aprovado reutiliza `iot_devices` e `iot_telemetry`, sem criar uma
tabela paralela. A revisao Alembic `c5d18e7a32bf` adiciona os campos canonicos
de ESP32 de forma aditiva e cria `iot_events`.

`iot_devices` guarda identificador, equipamento vinculado, firmware, status,
hash bcrypt da API key, revogacao, ultimo contato e metadados. A key plaintext
nunca e armazenada.

`iot_telemetry` guarda o dispositivo/equipamento autenticado, timestamp UTC,
recebimento, BME280, MPU-6050, JSN-SR04T, GPS opcional, qualidade, freshness,
confianca, score, explicacao, payload redigido e referencias de predicao.
`risk_predictions.telemetry_id`, `iot_events` e `alerts.iot_event_id` mantem a
trilha da leitura ate a decisao e alerta.

PostgreSQL aplica FKs e checks canonicos. SQLite de desenvolvimento preserva
tabelas legadas sem recriacao destrutiva; as invariantes adicionais sao
validadas pela aplicacao e pelos testes. Para alto volume futuro, PostgreSQL
normal e suficiente inicialmente; TimescaleDB continua opcional.

Para baixo volume, PostgreSQL normal e suficiente. Se a telemetria se tornar uma serie temporal de alto volume, a evolucao pode considerar PostgreSQL com TimescaleDB. TimescaleDB nao e dependencia desta entrega.

## Backup

Exemplo simples de backup PostgreSQL:

```bash
pg_dump --format=custom --file=agroguardian.backup.dump "$DATABASE_URL"
```

Restaure em ambiente separado antes de qualquer migration ou downgrade de recuperacao:

```bash
pg_restore --clean --if-exists --dbname="$DATABASE_URL" agroguardian.backup.dump
```

## Testes

Os testes em `tests/` aplicam Alembic em um SQLite descartavel e validam unicidade, FKs, constraints de score, relacionamentos, soft delete, fatores, alertas, recomendacoes, incidentes, auditoria e atomicidade da criacao de predicao.
