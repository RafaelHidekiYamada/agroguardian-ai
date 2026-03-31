from __future__ import annotations
from typing import Dict

FEATURE_ORDER = [
    "umidade_solo",
    "inclinacao",
    "distancia_agua",
    "velocidade",
    "chuva",
    "historico_acidentes",
    "tipo_operacao"
]

CLIMATE_MAP = {
    "sol": 0,
    "nublado": 1,
    "chuva": 2,
    "tempestade": 3,
    "garoa": 4,
}

OPERATION_MAP = {
    "campo": 0,
    "transporte": 1,
    "proximidade_agua": 2,
    "manutencao": 3,
}

def normalize_climate(clima: str) -> int:
    return CLIMATE_MAP.get(clima.lower().strip(), 1)

def normalize_operation(operation_type: str) -> int:
    return OPERATION_MAP.get(operation_type.lower().strip(), 0)

def build_features(data: Dict) -> Dict[str, float]:
    clima_code = normalize_climate(str(data.get("clima", "nublado")))
    operation_code = normalize_operation(str(data.get("operation_type", "campo")))

    features = {
        "umidade_solo": float(data["umidade_solo"]),
        "inclinacao": float(data["inclinacao"]),
        "distancia_agua": float(data["distancia_agua"]),
        "velocidade": float(data["velocidade"]),
        "historico_sinistros": float(data["historico_sinistros"]),
        "chuva_mm": float(data["chuva_mm"]),
        "solo_instavel": float(data["solo_instavel"]),
        "clima_code": float(clima_code),
        "operation_code": float(operation_code),
    }
    return features
