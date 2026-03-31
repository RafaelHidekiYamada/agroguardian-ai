from __future__ import annotations
from typing import Dict, List

def _score_route(base: float, chuva_mm: float, inclinacao: float, historico_sinistros: float, distancia_agua: float, clima: str, road_quality: float, roughness: float) -> float:
    score = base
    score += chuva_mm * 0.35
    score += inclinacao * 0.9
    score += historico_sinistros * 0.6
    score += max(0, 30 - distancia_agua) * 0.4
    if clima.lower() in {"chuva", "tempestade"}:
        score += 12
    score += (100 - road_quality) * 0.22
    score += roughness * 0.45
    return max(0, min(100, round(score, 2)))

def recommend_route(payload: Dict, origin_name: str = "Ponto atual", destination_name: str = "Armazém / Oficina") -> Dict:
    candidates: List[Dict] = [
        {
            "name": "Rota A - estrada principal",
            "road_quality": 78,
            "roughness": 22,
            "base": 20,
        },
        {
            "name": "Rota B - estrada rural curta",
            "road_quality": 55,
            "roughness": 48,
            "base": 14,
        },
        {
            "name": "Rota C - via alternativa mais longa",
            "road_quality": 86,
            "roughness": 18,
            "base": 24,
        },
    ]

    scored = []
    for c in candidates:
        route_score = _score_route(
            base=c["base"],
            chuva_mm=payload["chuva_mm"],
            inclinacao=payload["inclinacao"],
            historico_sinistros=payload["historico_sinistros"],
            distancia_agua=payload["distancia_agua"],
            clima=payload["clima"],
            road_quality=c["road_quality"],
            roughness=c["roughness"],
        )
        scored.append({
            "name": c["name"],
            "route_score": route_score,
            "road_quality": c["road_quality"],
            "roughness": c["roughness"],
        })

    recommended = min(scored, key=lambda x: x["route_score"])
    rationale = (
        f"A melhor opção é {recommended['name']} porque apresenta o menor índice de risco "
        f"considerando clima, inclinação, histórico e qualidade da via."
    )

    return {
        "recommended_route": recommended["name"],
        "route_score": recommended["route_score"],
        "alternatives": scored,
        "rationale": rationale,
        "origin_name": origin_name,
        "destination_name": destination_name,
    }
