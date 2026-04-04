# Arquitetura do AgroGuardian AI

## Visão geral
O AgroGuardian AI é uma plataforma inteligente de prevenção de sinistros agrícolas que integra dados operacionais, clima, geointeligência, machine learning, explicabilidade, auditoria e dashboard executivo.

## Camadas da solução

### 1. Entrada de dados
- Telemetria simulada/manual
- Coordenadas geográficas
- Dados operacionais
- Clima externo

### 2. Integração e processamento
- `integration_hub`
- `feature_engineering`
- `weather_service`
- `geointelligence`

### 3. IA e decisão
- `risk_model`
- `ml_registry`
- `explainability`
- `route_ai`
- regras de política de alerta

### 4. Governança e segurança
- autenticação JWT
- autorização por perfil
- auditoria
- trilha de previsões
- trilha de telemetria

### 5. Apresentação
- FastAPI
- Swagger/OpenAPI
- Streamlit
- análises em R

## Fluxo principal
Entrada operacional -> clima + geointeligência -> engenharia de atributos -> modelo de risco -> explicação -> alertas -> recomendação -> auditoria -> dashboard

## Módulo central
O `integration_hub` centraliza o contexto operacional e o rastro da decisão, servindo como núcleo integrador entre os módulos do sistema.

## Cloud
### Atual
- Render para API e Dashboard

### Evolução futura
- AWS EC2/ECS
- RDS PostgreSQL
- S3 para artefatos
- CloudWatch para observabilidade
- IAM para controle de acesso

## Segurança
- JWT
- RBAC
- auditoria
- segregação por perfil