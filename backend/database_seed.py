"""Idempotent development seed for the relational AgroGuardian schema."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from . import models
from .config import settings
from .database import SessionLocal
from .security import ALL_PERMISSIONS, DEFAULT_ROLE_PERMISSIONS, hash_password


class SeedConfigurationError(ValueError):
    """Raised when an initial administrator has not been configured safely."""


def _permission_name(code: str) -> str:
    return code.replace(".", " ").replace("_", " ").title()


def _get_or_create_client(
    db: Session,
    *,
    name: str,
    corporate_name: str,
    document: str,
    region: str,
) -> models.Client:
    client = db.query(models.Client).filter(models.Client.document == document).first()
    if client is None:
        client = models.Client(
            name=name,
            corporate_name=corporate_name,
            document=document,
            client_type=models.ClientType.COMPANY,
            email="operacoes@agroguardian.local",
            phone="+55 11 4000-0000",
            status=models.ClientStatus.ACTIVE,
            region=region,
            notes="Registro demonstrativo para desenvolvimento local.",
        )
        db.add(client)
        db.flush()
    return client


def _get_or_create_farm(
    db: Session,
    *,
    client: models.Client,
    name: str,
    region: str,
    municipality: str,
    state: str,
    latitude: float,
    longitude: float,
) -> models.Farm:
    farm = (
        db.query(models.Farm)
        .filter(models.Farm.client_id == client.id, models.Farm.name == name)
        .first()
    )
    if farm is None:
        farm = models.Farm(
            client_id=client.id,
            name=name,
            region=region,
            municipality=municipality,
            state=state,
            country="BR",
            latitude=latitude,
            longitude=longitude,
            total_area_ha=850.0,
            cultivated_area_ha=620.0,
            main_crop="Soja",
            status="active",
            notes="Propriedade demonstrativa para o dashboard.",
        )
        db.add(farm)
        db.flush()
    return farm


def _get_or_create_equipment(
    db: Session,
    *,
    farm: models.Farm,
    client: models.Client,
    name: str,
    equipment_type: str,
    internal_code: str,
) -> models.Equipment:
    equipment = db.query(models.Equipment).filter(models.Equipment.internal_code == internal_code).first()
    if equipment is None:
        equipment = models.Equipment(
            farm_id=farm.id,
            name=name,
            equipment_type=equipment_type,
            client_name=client.name,
            manufacturer="AgroGuardian Demo",
            model="AG-100",
            year=2024,
            internal_code=internal_code,
            status="active",
            purchase_value=250000.0,
            estimated_repair_cost=32800.0,
            notes="Equipamento demonstrativo para desenvolvimento local.",
        )
        db.add(equipment)
        db.flush()
    return equipment


def _seed_roles_and_permissions(db: Session) -> dict[str, models.Role]:
    permissions: dict[str, models.Permission] = {}
    for code in ALL_PERMISSIONS:
        permission = db.query(models.Permission).filter(models.Permission.code == code).first()
        if permission is None:
            permission = models.Permission(code=code, name=_permission_name(code), description=code)
            db.add(permission)
            db.flush()
        elif not permission.name:
            permission.name = _permission_name(code)
        permissions[code] = permission

    roles: dict[str, models.Role] = {}
    for role_name, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = db.query(models.Role).filter(models.Role.name == role_name).first()
        if role is None:
            role = models.Role(
                name=role_name,
                description=f"Perfil de sistema {role_name}",
                is_system_role=True,
            )
            db.add(role)
            db.flush()
        role.is_system_role = True
        granted_codes = {permission.code for permission in role.permissions}
        role.permissions.extend(
            permissions[code]
            for code in sorted(permission_codes)
            if code not in granted_codes
        )
        roles[role_name] = role
    return roles


def _ensure_admin(db: Session, roles: dict[str, models.Role]) -> models.User:
    username = settings.initial_admin_username.strip()
    email = settings.initial_admin_email.strip().lower()
    password = settings.initial_admin_password
    credentials_supplied = any((username, email, password))

    if credentials_supplied:
        if not username or not email or not password:
            raise SeedConfigurationError(
                "Defina todas as variaveis INITIAL_ADMIN_* ou nenhuma delas ao reutilizar um ADMIN existente."
            )
        admin = db.query(models.User).filter(models.User.username == username).first()
        if admin is None:
            admin = models.User(
                name="Administrador AgroGuardian",
                username=username,
                email=email,
                password_hash=hash_password(password),
                status="active",
                is_active=True,
                is_superuser=True,
            )
            db.add(admin)
            db.flush()
    else:
        admin = (
            db.query(models.User)
            .join(models.User.roles)
            .filter(models.Role.name == "ADMIN", models.User.is_active.is_(True))
            .order_by(models.User.id)
            .first()
        )
        if admin is None:
            raise SeedConfigurationError(
                "Defina INITIAL_ADMIN_USERNAME, INITIAL_ADMIN_EMAIL e INITIAL_ADMIN_PASSWORD para criar o primeiro ADMIN."
            )

    # Existing administrators retain credentials and any additional roles.
    admin.is_active = True
    admin.is_superuser = True
    if roles["ADMIN"] not in admin.roles:
        admin.roles.append(roles["ADMIN"])
    return admin


def _seed_reference_sources(db: Session) -> None:
    sources = (
        ("IBGE PAM", "IBGE", "agricultural", "Producao Agricola Municipal", "https://www.ibge.gov.br/"),
        ("CONAB", "CONAB", "agricultural", "Dados nacionais de safra", "https://www.conab.gov.br/"),
        ("INMET", "INMET", "weather", "Dados meteorologicos", "https://portal.inmet.gov.br/"),
        ("NASA POWER", "NASA", "weather", "Dados climaticos diarios", "https://power.larc.nasa.gov/"),
        ("SoilGrids", "ISRIC", "soil", "Atributos de solo", "https://soilgrids.org/"),
        ("SRTM", "NASA", "terrain", "Modelo digital de elevacao", "https://www2.jpl.nasa.gov/srtm/"),
        ("HydroRIVERS", "HydroSHEDS", "hydrography", "Rede hidrografica", "https://www.hydrosheds.org/"),
        ("MapBiomas", "MapBiomas", "land_use", "Cobertura e uso do solo", "https://mapbiomas.org/"),
        ("NASA FIRMS", "NASA", "fire", "Monitoramento de focos de calor", "https://firms.modaps.eosdis.nasa.gov/"),
        ("OpenStreetMap", "OpenStreetMap", "map", "Dados cartograficos abertos", "https://www.openstreetmap.org/"),
    )
    for name, provider, source_type, description, url in sources:
        record = (
            db.query(models.DataSource)
            .filter(models.DataSource.name == name, models.DataSource.provider == provider)
            .first()
        )
        if record is None:
            db.add(
                models.DataSource(
                    name=name,
                    provider=provider,
                    source_type=source_type,
                    description=description,
                    url_reference=url,
                )
            )


def _seed_legacy_dashboard_history(
    db: Session,
    *,
    farm: models.Farm,
    equipment: models.Equipment,
) -> None:
    if db.query(models.PredictionRecord).filter(models.PredictionRecord.source == "database_seed").first():
        return

    payload = {
        "equipment_id": equipment.id,
        "farm_id": farm.id,
        "region": farm.region,
        "operation_type": "campo",
        "clima": "chuva",
        "umidade_solo": 78.0,
        "inclinacao": 11.0,
        "distancia_agua": 35.0,
        "velocidade": 14.0,
        "historico_sinistros": 4.0,
        "chuva_mm": 22.0,
        "solo_instavel": 1,
        "latitude": farm.latitude,
        "longitude": farm.longitude,
    }
    prediction = models.PredictionRecord(
        model_version="database-seed",
        source="database_seed",
        input_payload=payload,
        predicted_risk=78.0,
        risk_label="Alto",
        alert_level="HIGH",
        explanation={"umidade_solo": 24.0, "chuva_mm": 21.0, "velocidade": 13.0},
        recommendation="Reduzir velocidade e replanejar a operacao se a chuva persistir.",
        safe_route="Rota alternativa com maior distancia da agua.",
        weather_payload={"source": "SIMULATION", "rain_mm": 22.0},
    )
    db.add(prediction)
    db.flush()
    db.add(
        models.TelemetryRecord(
            **payload,
            predicted_risk=78.0,
            risk_label="Alto",
            alert_level="HIGH",
            recommendation=prediction.recommendation,
            safe_route=prediction.safe_route,
            explanation=prediction.explanation,
        )
    )
    db.add(
        models.AlertRecord(
            alert_type="high_risk",
            severity="HIGH",
            message="Risco elevado identificado no historico demonstrativo.",
            context=payload,
            equipment_id=equipment.id,
            risk_prediction_id=prediction.id,
        )
    )


def seed_database(db: Session) -> dict[str, int]:
    """Seed normalized and legacy dashboard data in one transaction.

    Password material is accepted only through INITIAL_ADMIN_* when an initial
    administrator must be created. Existing ADMIN accounts are reused without
    reading or resetting their credentials.
    """
    try:
        roles = _seed_roles_and_permissions(db)
        admin = _ensure_admin(db, roles)

        client = _get_or_create_client(
            db,
            name="Fazenda Santa Helena",
            corporate_name="Fazenda Santa Helena Ltda.",
            document="00000000000191",
            region="Ribeirao Preto - SP",
        )
        legacy_client = _get_or_create_client(
            db,
            name="Cliente Demo",
            corporate_name="Cliente Demo Agroindustrial Ltda.",
            document="00000000000272",
            region="Guarulhos - SP",
        )
        farm = _get_or_create_farm(
            db,
            client=client,
            name="Fazenda Santa Helena",
            region="Ribeirao Preto - SP",
            municipality="Ribeirao Preto",
            state="SP",
            latitude=-21.1704,
            longitude=-47.8103,
        )

        # Preserve historical records while connecting unowned legacy farms to
        # a dedicated demo client instead of deleting or rewriting them.
        for legacy_farm in db.query(models.Farm).filter(models.Farm.client_id.is_(None)).all():
            legacy_farm.client_id = legacy_client.id

        tractor = _get_or_create_equipment(
            db,
            farm=farm,
            client=client,
            name="Trator 01",
            equipment_type="tractor",
            internal_code="TRATOR-01",
        )
        harvester = _get_or_create_equipment(
            db,
            farm=farm,
            client=client,
            name="Colheitadeira 01",
            equipment_type="harvester",
            internal_code="COLHEITADEIRA-01",
        )
        sprayer = _get_or_create_equipment(
            db,
            farm=farm,
            client=client,
            name="Pulverizador 01",
            equipment_type="sprayer",
            internal_code="PULVERIZADOR-01",
        )

        for granted_collection, resource in (
            (admin.clients, client),
            (admin.farms, farm),
            (admin.equipments, tractor),
            (admin.equipments, harvester),
            (admin.equipments, sprayer),
        ):
            if resource not in granted_collection:
                granted_collection.append(resource)

        _seed_reference_sources(db)
        now = datetime.now(timezone.utc)
        operation = (
            db.query(models.Operation)
            .filter(models.Operation.farm_id == farm.id, models.Operation.equipment_id == tractor.id)
            .first()
        )
        if operation is None:
            operation = models.Operation(
                client_id=client.id,
                farm_id=farm.id,
                equipment_id=tractor.id,
                operation_type=models.OperationType.FIELD,
                crop_type="Soja",
                started_at=now - timedelta(hours=2),
                finished_at=now - timedelta(hours=1),
                status=models.OperationStatus.COMPLETED,
                operator_user_id=admin.id,
                notes="Operacao demonstrativa usada pelo seed de desenvolvimento.",
            )
            db.add(operation)
            db.flush()

        if not db.query(models.WeatherRecord).filter(models.WeatherRecord.farm_id == farm.id).first():
            db.add(
                models.WeatherRecord(
                    farm_id=farm.id,
                    source=models.WeatherSource.SIMULATION,
                    recorded_at=now,
                    temperature_c=27.4,
                    humidity_pct=81.0,
                    precipitation_mm=22.0,
                    wind_speed_kmh=14.0,
                    pressure_hpa=1009.0,
                    weather_condition="chuva",
                    raw_data_json={"seed": True},
                )
            )
        if not db.query(models.SoilRecord).filter(models.SoilRecord.farm_id == farm.id).first():
            db.add(
                models.SoilRecord(
                    farm_id=farm.id,
                    source=models.SoilSource.MANUAL,
                    sampled_at=now,
                    soil_moisture_pct=78.0,
                    clay_pct=38.0,
                    sand_pct=42.0,
                    silt_pct=20.0,
                    organic_carbon=2.2,
                    ph=6.1,
                    bulk_density=1.25,
                    drainage_class="moderada",
                    raw_data_json={"seed": True},
                )
            )
        if not db.query(models.TerrainRecord).filter(models.TerrainRecord.farm_id == farm.id).first():
            db.add(
                models.TerrainRecord(
                    farm_id=farm.id,
                    latitude=farm.latitude,
                    longitude=farm.longitude,
                    elevation_m=546.0,
                    slope_deg=8.5,
                    distance_to_water_m=35.0,
                    distance_to_road_m=120.0,
                    road_type="estrada rural",
                    land_use_class="agricultura",
                    source=models.TerrainSource.SRTM,
                )
            )

        dataset = (
            db.query(models.DatasetVersion)
            .filter(models.DatasetVersion.name == "agroguardian_seed_dataset", models.DatasetVersion.version == "1")
            .first()
        )
        if dataset is None:
            dataset = models.DatasetVersion(
                name="agroguardian_seed_dataset",
                version="1",
                description="Dataset demonstrativo para inicializar o catalogo de ML.",
                source_type=models.DatasetSourceType.SIMULATED,
                record_count=1,
                feature_count=14,
                file_path="ml/data/nasa_power_agroguardian_training.csv",
                checksum="seed",
                created_by_user_id=admin.id,
                metadata_json={"seed": True},
            )
            db.add(dataset)
            db.flush()
        model_version = (
            db.query(models.ModelVersion)
            .filter(models.ModelVersion.name == "agroguardian_risk_model", models.ModelVersion.version == settings.model_version)
            .first()
        )
        if model_version is None:
            model_version = models.ModelVersion(
                name="agroguardian_risk_model",
                version=settings.model_version,
                algorithm="HistGradientBoostingRegressor",
                status=models.ModelStatus.ACTIVE,
                dataset_version_id=dataset.id,
                trained_at=now,
                deployed_at=now,
                accuracy=0.99,
                precision_score=0.98,
                recall_score=0.98,
                f1_score=0.98,
                roc_auc=0.99,
                metrics_json={"seed": True},
                parameters_json={"source": "development seed"},
                feature_list_json=["umidade_solo", "chuva_mm", "velocidade"],
                artifact_path="ml/saved_models/best_risk_model.joblib",
            )
            db.add(model_version)
            db.flush()

        prediction = (
            db.query(models.RiskPrediction)
            .filter(models.RiskPrediction.equipment_id == tractor.id)
            .first()
        )
        if prediction is None:
            prediction = models.RiskPrediction(
                client_id=client.id,
                farm_id=farm.id,
                equipment_id=tractor.id,
                operation_id=operation.id,
                risk_score=78.0,
                risk_level=models.RiskLevel.HIGH,
                confidence_score=87.0,
                main_risk_factor="precipitation",
                model_version_id=model_version.id,
                input_snapshot_json={"rain_mm": 22.0, "soil_moisture_pct": 78.0, "speed_kmh": 14.0},
                explanation_summary="Chuva e umidade do solo elevam o risco operacional.",
                recommendation_summary="Reduzir velocidade e revisar a rota antes da operacao.",
            )
            db.add(prediction)
            db.flush()
            db.add_all(
                [
                    models.RiskPredictionFactor(
                        risk_prediction_id=prediction.id,
                        factor_name="precipitation",
                        factor_category="weather",
                        raw_value=22.0,
                        normalized_value=0.74,
                        unit="mm",
                        impact_score=22.0,
                        importance_pct=27.0,
                        explanation="Precipitacao acima do limite operacional.",
                    ),
                    models.RiskPredictionFactor(
                        risk_prediction_id=prediction.id,
                        factor_name="soil_moisture",
                        factor_category="soil",
                        raw_value=78.0,
                        normalized_value=0.78,
                        unit="pct",
                        impact_score=18.0,
                        importance_pct=23.0,
                        explanation="Solo umido reduz a estabilidade da operacao.",
                    ),
                ]
            )
            alert = models.Alert(
                client_id=client.id,
                farm_id=farm.id,
                equipment_id=tractor.id,
                operation_id=operation.id,
                risk_prediction_id=prediction.id,
                alert_type="high_risk",
                severity=models.AlertSeverity.HIGH,
                title="Risco operacional elevado",
                message="A combinacao de chuva e solo umido requer restricao operacional.",
                status=models.AlertStatus.OPEN,
            )
            db.add(alert)
            db.flush()
            recommendation = models.Recommendation(
                risk_prediction_id=prediction.id,
                equipment_id=tractor.id,
                recommendation_type=models.RecommendationType.OPERATIONAL,
                title="Reduzir velocidade e replanejar a rota",
                description="Evitar area proxima a agua enquanto as condicoes de solo permanecerem instaveis.",
                expected_risk_reduction_pct=31.0,
                priority=models.RecommendationPriority.HIGH,
            )
            db.add(recommendation)
            db.flush()
            db.add(
                models.PreventedLossRecord(
                    equipment_id=tractor.id,
                    risk_prediction_id=prediction.id,
                    recommendation_id=recommendation.id,
                    previous_risk_score=78.0,
                    new_risk_score=54.0,
                    risk_reduction_pct=30.77,
                    possible_prevented_loss=Decimal("32800.00"),
                    estimated_savings_brl=Decimal("32800.00"),
                    calculation_method="Estimativa demonstrativa baseada em custo medio de reparo.",
                    notes="Valor financeiro simulado para o MVP.",
                )
            )
            db.add(
                models.Notification(
                    user_id=admin.id,
                    alert_id=alert.id,
                    notification_type=models.NotificationType.DASHBOARD,
                    title=alert.title,
                    message=alert.message,
                )
            )

        if not db.query(models.Incident).filter(models.Incident.farm_id == farm.id).first():
            db.add(
                models.Incident(
                    client_id=client.id,
                    farm_id=farm.id,
                    equipment_id=harvester.id,
                    operation_id=operation.id,
                    incident_type=models.IncidentType.STUCK,
                    severity=models.IncidentSeverity.MEDIUM,
                    occurred_at=now - timedelta(days=7),
                    latitude=farm.latitude,
                    longitude=farm.longitude,
                    description="Registro demonstrativo de atolamento em solo umido.",
                    estimated_damage_brl=Decimal("8500.00"),
                    was_preventable=True,
                    status=models.IncidentStatus.CLOSED,
                )
            )
        if not db.query(models.RiskSimulation).filter(models.RiskSimulation.user_id == admin.id).first():
            db.add(
                models.RiskSimulation(
                    user_id=admin.id,
                    client_id=client.id,
                    farm_id=farm.id,
                    equipment_id=tractor.id,
                    operation_id=operation.id,
                    base_risk_score=78.0,
                    simulated_risk_score=54.0,
                    risk_difference=-24.0,
                    risk_difference_pct=-30.77,
                    base_conditions_json={"rain_mm": 22.0, "speed_kmh": 14.0},
                    simulated_conditions_json={"rain_mm": 5.0, "speed_kmh": 8.0},
                    recommendation="Operar somente apos reduzir chuva e velocidade.",
                )
            )

        for key, value, description in (
            ("risk_threshold_low", {"value": 40}, "Limite superior para risco baixo."),
            ("risk_threshold_medium", {"value": 70}, "Limite superior para risco medio."),
            ("risk_threshold_high", {"value": 85}, "Limite para bloqueio operacional."),
            ("default_alert_policy", {"value": "Politica Preventiva Santa Helena"}, "Politica padrao de demonstracao."),
        ):
            setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
            if setting is None:
                db.add(
                    models.SystemSetting(
                        key=key,
                        value_json=value,
                        description=description,
                        updated_by_user_id=admin.id,
                    )
                )

        policy = db.query(models.AlertPolicy).filter(models.AlertPolicy.name == "Politica Preventiva Santa Helena").first()
        if policy is None:
            db.add(
                models.AlertPolicy(
                    client_id=client.id,
                    farm_id=farm.id,
                    name="Politica Preventiva Santa Helena",
                    description="Bloqueia operacao quando condicoes de solo e clima excedem os limites definidos.",
                    operation_type="campo",
                    risk_threshold=70.0,
                    severity="HIGH",
                    action_type="REPLAN",
                    min_risk_alert=40.0,
                    min_risk_block=70.0,
                    max_speed=20.0,
                    max_slope=12.0,
                    min_distance_water=25.0,
                    max_rain_mm=15.0,
                    block_on_water=False,
                    block_on_unstable_soil=True,
                    is_active=True,
                )
            )

        _seed_legacy_dashboard_history(db, farm=farm, equipment=tractor)
        seed_audit = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.action == "DATABASE_SEED_COMPLETED",
                models.AuditLog.entity_id == "development-seed",
            )
            .first()
        )
        if seed_audit is None:
            db.add(
                models.AuditLog(
                    actor="system",
                    action="DATABASE_SEED_COMPLETED",
                    payload={"source": "scripts/seed_database.py"},
                    user_id=admin.id,
                    entity_type="database",
                    entity_id="development-seed",
                    new_values_json={"admin_username": admin.username},
                    metadata_json={"sensitive_values_omitted": True},
                )
            )
        db.commit()
        return {
            "admin_id": admin.id,
            "client_id": client.id,
            "farm_id": farm.id,
            "equipment_count": 3,
        }
    except Exception:
        db.rollback()
        raise


def seed_database_from_environment() -> dict[str, int]:
    db = SessionLocal()
    try:
        return seed_database(db)
    finally:
        db.close()
