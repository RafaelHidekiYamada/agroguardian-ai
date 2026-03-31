from __future__ import annotations
from typing import Dict, List
import folium

def build_risk_map(latitude: float, longitude: float, risk_score: float, zones: List[Dict]) -> str:
    fmap = folium.Map(location=[latitude, longitude], zoom_start=15, tiles="OpenStreetMap")

    folium.Marker(
        [latitude, longitude],
        tooltip="Posição atual",
        popup=f"Risco atual: {risk_score:.1f}",
        icon=folium.Icon(color="blue", icon="info-sign"),
    ).add_to(fmap)

    for zone in zones:
        folium.Circle(
            location=[zone["lat"], zone["lon"]],
            radius=zone["radius_m"],
            color=zone["color"],
            fill=True,
            fill_opacity=0.35,
            popup=zone["name"],
            tooltip=zone["name"],
        ).add_to(fmap)

    return fmap._repr_html_()
