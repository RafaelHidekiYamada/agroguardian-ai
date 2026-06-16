from __future__ import annotations

from typing import Any, Dict, List


ROUTE_WEIGHTS = {
    "base": 0.18,
    "weather": 0.18,
    "terrain": 0.16,
    "water": 0.15,
    "road_quality": 0.14,
    "roughness": 0.12,
    "history": 0.07,
}


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _risk_label(score: float) -> str:
    if score >= 75:
        return "alto"
    if score >= 45:
        return "medio"
    return "baixo"


def _route_candidates() -> List[Dict[str, Any]]:
    return [
        {
            "name": "Rota A - estrada principal",
            "distance_km": 4.8,
            "estimated_minutes": 18,
            "road_quality": 78,
            "roughness": 22,
            "base": 20,
            "water_exposure": 0.35,
            "slope_exposure": 0.45,
            "segments": [
                {"name": "A1 acesso principal", "risk": 32, "reason": "pavimento melhor e baixa irregularidade"},
                {"name": "A2 curva do canal", "risk": 57, "reason": "aproximacao de canal agricola"},
                {"name": "A3 chegada ao armazem", "risk": 28, "reason": "trecho curto e aberto"},
            ],
        },
        {
            "name": "Rota B - estrada rural curta",
            "distance_km": 3.2,
            "estimated_minutes": 14,
            "road_quality": 55,
            "roughness": 48,
            "base": 14,
            "water_exposure": 0.55,
            "slope_exposure": 0.60,
            "segments": [
                {"name": "B1 atalho rural", "risk": 46, "reason": "menor distancia, mas piso irregular"},
                {"name": "B2 baixada umida", "risk": 71, "reason": "solo mais umido e pouca drenagem"},
                {"name": "B3 ponte estreita", "risk": 64, "reason": "proximidade de agua e manobra limitada"},
            ],
        },
        {
            "name": "Rota C - via alternativa mais longa",
            "distance_km": 5.9,
            "estimated_minutes": 23,
            "road_quality": 86,
            "roughness": 18,
            "base": 24,
            "water_exposure": 0.18,
            "slope_exposure": 0.25,
            "segments": [
                {"name": "C1 contorno alto", "risk": 24, "reason": "maior afastamento de agua"},
                {"name": "C2 estrada firme", "risk": 30, "reason": "melhor qualidade de via"},
                {"name": "C3 retorno ao patio", "risk": 36, "reason": "trecho mais longo, mas controlavel"},
            ],
        },
    ]


def _component_scores(payload: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, float]:
    chuva_mm = float(payload.get("chuva_mm", 0) or 0)
    inclinacao = float(payload.get("inclinacao", 0) or 0)
    historico_sinistros = float(payload.get("historico_sinistros", 0) or 0)
    distancia_agua = float(payload.get("distancia_agua", 999999) or 999999)
    clima = str(payload.get("clima", "")).lower()
    velocidade = float(payload.get("velocidade", 0) or 0)
    solo_instavel = int(payload.get("solo_instavel", 0) or 0)

    weather_score = chuva_mm * 2.0
    if clima in {"chuva", "garoa"}:
        weather_score += 18
    elif clima in {"tempestade", "thunderstorm"}:
        weather_score += 32

    terrain_score = inclinacao * 2.6 * float(candidate["slope_exposure"])
    if solo_instavel == 1:
        terrain_score += 18 * float(candidate["slope_exposure"])

    water_score = max(0.0, 120.0 - distancia_agua) * 0.55 * float(candidate["water_exposure"])
    road_quality_score = 100 - float(candidate["road_quality"])
    roughness_score = float(candidate["roughness"])
    history_score = historico_sinistros * 4.5
    speed_score = max(0.0, velocidade - 12.0) * 1.8

    return {
        "base": float(candidate["base"]),
        "weather": _clamp(weather_score),
        "terrain": _clamp(terrain_score),
        "water": _clamp(water_score),
        "road_quality": _clamp(road_quality_score),
        "roughness": _clamp(roughness_score),
        "history": _clamp(history_score + speed_score),
    }


def _score_route(payload: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    components = _component_scores(payload, candidate)
    weighted_score = sum(components[key] * ROUTE_WEIGHTS[key] for key in ROUTE_WEIGHTS)
    route_score = round(_clamp(weighted_score), 2)

    sorted_components = sorted(components.items(), key=lambda item: item[1], reverse=True)
    top_drivers = [
        {"factor": key, "score": round(value, 2), "weight": round(ROUTE_WEIGHTS[key] * 100, 2)}
        for key, value in sorted_components[:3]
    ]

    segments = []
    route_multiplier = 0.75 + (route_score / 180)
    for segment in candidate["segments"]:
        segment_score = round(_clamp(float(segment["risk"]) * route_multiplier), 2)
        segments.append(
            {
                "name": segment["name"],
                "risk_score": segment_score,
                "risk_label": _risk_label(segment_score),
                "reason": segment["reason"],
            }
        )

    critical_segment = max(segments, key=lambda row: row["risk_score"])

    return {
        "name": candidate["name"],
        "route_score": route_score,
        "risk_label": _risk_label(route_score),
        "distance_km": candidate["distance_km"],
        "estimated_minutes": candidate["estimated_minutes"],
        "road_quality": candidate["road_quality"],
        "roughness": candidate["roughness"],
        "components": {key: round(value, 2) for key, value in components.items()},
        "top_drivers": top_drivers,
        "segments": segments,
        "critical_segment": critical_segment,
        "route_weights": {key: round(value * 100, 2) for key, value in ROUTE_WEIGHTS.items()},
    }


def _operator_steps(route: Dict[str, Any], payload: Dict[str, Any]) -> List[str]:
    steps = [
        f"seguir pela {route['name']} e revisar o trecho {route['critical_segment']['name']}",
        "manter velocidade reduzida nos trechos marcados como medio ou alto",
    ]

    if float(payload.get("chuva_mm", 0) or 0) >= 10:
        steps.append("evitar entrada no trecho critico durante pico de chuva")
    if float(payload.get("distancia_agua", 999999) or 999999) < 80:
        steps.append("manter margem lateral maior em canais, rios e areas alagaveis")
    if int(payload.get("solo_instavel", 0) or 0) == 1:
        steps.append("confirmar firmeza do solo antes de equipamento pesado")

    return steps


def recommend_route(
    payload: Dict[str, Any],
    origin_name: str = "Ponto atual",
    destination_name: str = "Armazem / Oficina",
) -> Dict[str, Any]:
    scored = [_score_route(payload, candidate) for candidate in _route_candidates()]
    scored = sorted(scored, key=lambda row: row["route_score"])

    recommended = scored[0]
    runner_up = scored[1] if len(scored) > 1 else recommended
    safety_margin = round(runner_up["route_score"] - recommended["route_score"], 2)

    avoided = [
        {
            "route": alternative["name"],
            "reason": (
                f"score {alternative['route_score']} contra {recommended['route_score']} "
                f"da rota recomendada; principal fator: {alternative['top_drivers'][0]['factor']}"
            ),
        }
        for alternative in scored[1:]
    ]

    rationale = (
        f"A melhor opcao e {recommended['name']} porque combina menor score de rota "
        f"({recommended['route_score']}) com margem de seguranca de {safety_margin} ponto(s) "
        f"contra a segunda opcao. O trecho mais sensivel e "
        f"{recommended['critical_segment']['name']}: {recommended['critical_segment']['reason']}."
    )

    return {
        "recommended_route": recommended["name"],
        "route_score": recommended["route_score"],
        "risk_label": recommended["risk_label"],
        "alternatives": scored,
        "rationale": rationale,
        "origin_name": origin_name,
        "destination_name": destination_name,
        "route_explanation": {
            "why_selected": rationale,
            "safety_margin": safety_margin,
            "critical_segment": recommended["critical_segment"],
            "top_drivers": recommended["top_drivers"],
            "operator_steps": _operator_steps(recommended, payload),
            "avoided_routes": avoided,
            "route_weights": recommended["route_weights"],
        },
    }
