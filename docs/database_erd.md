# ERD do Banco AgroGuardian AI

```mermaid
erDiagram
    USERS }o--o{ ROLES : user_roles
    ROLES }o--o{ PERMISSIONS : role_permissions
    USERS ||--o{ USER_PERMISSIONS : overrides
    USERS }o--o{ CLIENTS : user_clients
    USERS }o--o{ FARMS : user_farms
    USERS }o--o{ EQUIPMENT : user_equipments

    CLIENTS ||--o{ FARMS : owns
    FARMS ||--o{ EQUIPMENT : contains
    EQUIPMENT ||--o{ IOT_DEVICES : linked_to
    IOT_DEVICES ||--o{ IOT_TELEMETRY : authenticates
    EQUIPMENT ||--o{ IOT_TELEMETRY : receives
    IOT_TELEMETRY ||--o{ IOT_EVENTS : detects
    IOT_TELEMETRY ||--o{ RISK_PREDICTIONS : informs
    RISK_PREDICTIONS ||--o{ IOT_EVENTS : explains
    CLIENTS ||--o{ OPERATIONS : scopes
    FARMS ||--o{ OPERATIONS : occurs_on
    EQUIPMENT ||--o{ OPERATIONS : uses
    USERS ||--o{ OPERATIONS : operates

    FARMS ||--o{ WEATHER_RECORDS : has
    FARMS ||--o{ SOIL_RECORDS : has
    FARMS ||--o{ TERRAIN_RECORDS : has

    CLIENTS ||--o{ INCIDENTS : records
    FARMS ||--o{ INCIDENTS : records
    EQUIPMENT ||--o{ INCIDENTS : involved_in
    OPERATIONS ||--o{ INCIDENTS : happened_during

    DATASET_VERSIONS ||--o{ MODEL_VERSIONS : trains
    MODEL_VERSIONS ||--o{ RISK_PREDICTIONS : produces
    CLIENTS ||--o{ RISK_PREDICTIONS : owns
    FARMS ||--o{ RISK_PREDICTIONS : contextualizes
    EQUIPMENT ||--o{ RISK_PREDICTIONS : evaluates
    OPERATIONS ||--o{ RISK_PREDICTIONS : contextualizes
    RISK_PREDICTIONS ||--o{ RISK_PREDICTION_FACTORS : explains
    RISK_PREDICTIONS ||--o{ ALERTS : raises
    RISK_PREDICTIONS ||--o{ RECOMMENDATIONS : suggests
    RISK_PREDICTIONS ||--o{ PREVENTED_LOSS_RECORDS : estimates
    RECOMMENDATIONS ||--o{ PREVENTED_LOSS_RECORDS : supports

    CLIENTS ||--o{ ALERTS : receives
    FARMS ||--o{ ALERTS : receives
    EQUIPMENT ||--o{ ALERTS : receives
    OPERATIONS ||--o{ ALERTS : raises
    ALERTS ||--o{ NOTIFICATIONS : notifies
    USERS ||--o{ NOTIFICATIONS : receives

    USERS ||--o{ RISK_SIMULATIONS : runs
    CLIENTS ||--o{ RISK_SIMULATIONS : scopes
    FARMS ||--o{ RISK_SIMULATIONS : scopes
    EQUIPMENT ||--o{ RISK_SIMULATIONS : scopes
    OPERATIONS ||--o{ RISK_SIMULATIONS : scopes

    USERS ||--o{ AUDIT_LOGS : performs
    USERS ||--o{ GENERATED_REPORTS : generates
    CLIENTS ||--o{ GENERATED_REPORTS : scopes
    FARMS ||--o{ GENERATED_REPORTS : scopes
    CLIENTS ||--o{ ALERT_POLICIES : configures
    FARMS ||--o{ ALERT_POLICIES : configures

    USERS {
        int id PK
        string username UK
        string email UK
        boolean is_active
        boolean is_superuser
    }
    CLIENTS {
        int id PK
        string document UK
        string name
        string status
    }
    FARMS {
        int id PK
        int client_id FK
        string name
        string municipality
        string state
    }
    EQUIPMENT {
        int id PK
        int farm_id FK
        string internal_code UK
        string status
    }
    IOT_DEVICES {
        int id PK
        int equipment_id FK
        string device_identifier UK
        string firmware_version
        string status
    }
    IOT_TELEMETRY {
        int id PK
        int iot_device_id FK
        int equipment_id FK
        int sequence_number
        datetime recorded_at
        float temperature_c
        float humidity_pct
        float pressure_hpa
        float distance_cm
        float acceleration_magnitude
        float inclination_deg
        string data_quality_status
        string telemetry_status
        float risk_score
    }
    IOT_EVENTS {
        int id PK
        int device_id FK
        int equipment_id FK
        int telemetry_id FK
        int risk_prediction_id FK
        string event_type
        string severity
    }
    OPERATIONS {
        int id PK
        int client_id FK
        int farm_id FK
        int equipment_id FK
        int operator_user_id FK
        string operation_type
        string status
    }
    RISK_PREDICTIONS {
        int id PK
        int model_version_id FK
        int equipment_id FK
        float risk_score
        string risk_level
        float confidence_score
    }
    RISK_PREDICTION_FACTORS {
        int id PK
        int risk_prediction_id FK
        string factor_name
        float impact_score
        float importance_pct
    }
    ALERTS {
        int id PK
        int risk_prediction_id FK
        string severity
        string status
    }
    RECOMMENDATIONS {
        int id PK
        int risk_prediction_id FK
        string recommendation_type
        float expected_risk_reduction_pct
    }
    PREVENTED_LOSS_RECORDS {
        int id PK
        int risk_prediction_id FK
        int recommendation_id FK
        float risk_reduction_pct
        decimal estimated_savings_brl
    }
    INCIDENTS {
        int id PK
        int equipment_id FK
        string incident_type
        string severity
        datetime occurred_at
    }
    MODEL_VERSIONS {
        int id PK
        int dataset_version_id FK
        string name
        string version
        string status
    }
    DATASET_VERSIONS {
        int id PK
        string name
        string version
        string source_type
    }
    AUDIT_LOGS {
        int id PK
        int user_id FK
        string action
        string entity_type
        string entity_id
    }
```

## Telemetria Fisica

`IOT_TELEMETRY` e o historico canonico do ESP32 fisico. `IOT_EVENTS` registra
sinais relevantes de BME280, JSN-SR04T e MPU-6050 e se relaciona a predicoes e
alertas. Nenhuma tabela `iot_sensor_readings` paralela e necessaria para o
fluxo atual.
