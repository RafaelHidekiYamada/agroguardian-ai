import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="AgroGuardian AI", layout="wide")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

PREDICT_URL = f"{API_BASE_URL}/api/v1/risk/predict"
SUMMARY_URL = f"{API_BASE_URL}/api/v1/dashboard/summary"
RANKING_URL = f"{API_BASE_URL}/api/v1/dashboard/ranking"
TRENDS_URL = f"{API_BASE_URL}/api/v1/dashboard/trends"
ALERTS_URL = f"{API_BASE_URL}/api/v1/dashboard/alerts"
AUDIT_URL = f"{API_BASE_URL}/api/v1/dashboard/audit"
EQUIPMENT_URL = f"{API_BASE_URL}/api/v1/equipment"
FARMS_URL = f"{API_BASE_URL}/api/v1/farms"


def get_json(url: str) -> tuple[bool, Any]:
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return True, response.json()

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return False, response.json()
        return False, response.text
    except requests.exceptions.RequestException as e:
        return False, str(e)


def post_json(url: str, payload: dict) -> tuple[bool, Any]:
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            return True, response.json()

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return False, response.json()
        return False, response.text
    except requests.exceptions.RequestException as e:
        return False, str(e)


def flatten_metrics(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    flat: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            flat[key] = value
    return flat


def any_to_dataframe(data: Any) -> pd.DataFrame:
    if data is None:
        return pd.DataFrame()

    if isinstance(data, pd.DataFrame):
        return data

    if isinstance(data, list):
        if len(data) == 0:
            return pd.DataFrame()
        if all(isinstance(item, dict) for item in data):
            return pd.DataFrame(data)
        return pd.DataFrame({"valor": data})

    if isinstance(data, dict):
        list_candidates = {k: v for k, v in data.items() if isinstance(v, list)}
        if len(list_candidates) == 1:
            return any_to_dataframe(next(iter(list_candidates.values())))
        return pd.DataFrame([data])

    return pd.DataFrame({"valor": [data]})


def extract_trend_dataframe(data: Any) -> pd.DataFrame:
    df = any_to_dataframe(data)

    if df.empty:
        return df

    # tenta encontrar colunas de tempo e valor
    time_candidates = ["date", "data", "timestamp", "periodo", "mes", "dia"]
    value_candidates = [
        "risk_score", "score", "value", "valor", "avg_risk",
        "media_risco", "trend", "quantidade", "total"
    ]

    time_col = next((c for c in df.columns if c.lower() in time_candidates), None)
    value_col = next((c for c in df.columns if c.lower() in value_candidates), None)

    if time_col and value_col:
        trend_df = df[[time_col, value_col]].copy()
        trend_df.columns = ["Periodo", "Valor"]
        return trend_df

    if len(df.columns) >= 2:
        trend_df = df.iloc[:, :2].copy()
        trend_df.columns = ["Periodo", "Valor"]
        return trend_df

    return df


def show_api_error(title: str, error_data: Any) -> None:
    st.error(title)
    if isinstance(error_data, (dict, list)):
        st.json(error_data)
    else:
        st.write(error_data)


st.title("🌱 AgroGuardian AI")
st.subheader("Plataforma Inteligente de Prevenção de Sinistros Agrícolas")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "Operação em tempo real",
        "Resumo executivo",
        "Ranking",
        "Tendências",
        "Alertas e auditoria",
    ]
)

with tab1:
    st.sidebar.header("Dados da operação")

    equipment_id = st.sidebar.number_input("ID do equipamento", min_value=1, value=1, step=1)
    farm_id = st.sidebar.number_input("ID da fazenda", min_value=1, value=1, step=1)
    region = st.sidebar.text_input("Região", value="Guarulhos - SP")
    operation_type = st.sidebar.selectbox("Tipo de operação", ["campo", "transporte"])

    umidade_solo = st.sidebar.slider("Umidade do solo", 0, 100, 80)
    inclinacao = st.sidebar.slider("Inclinação do terreno", 0, 90, 12)
    distancia_agua = st.sidebar.slider("Distância da água", 0, 1000, 20)
    velocidade = st.sidebar.slider("Velocidade da máquina", 0, 200, 15)
    historico_sinistros = st.sidebar.slider("Histórico de sinistros", 0, 20, 2)
    solo_instavel = st.sidebar.selectbox("Solo instável", [0, 1])

    latitude = st.sidebar.number_input("Latitude", value=-23.455000, format="%.6f")
    longitude = st.sidebar.number_input("Longitude", value=-46.533000, format="%.6f")

    clima_base = st.sidebar.selectbox("Clima base", ["sol", "nublado", "chuva"], index=0)
    chuva_mm_base = st.sidebar.slider("Chuva base (mm)", 0, 100, 0)

    col_a, col_b = st.columns([2, 1])

    with col_a:
        st.markdown("### Predição operacional")
        calcular = st.button("Calcular risco", use_container_width=False)

    with col_b:
        st.subheader("Plataforma Inteligente de Prevenção de Sinistros Agrícolas com IA, clima e telemetria")

    if calcular:
        payload = {
            "equipment_id": int(equipment_id),
            "farm_id": int(farm_id),
            "region": region,
            "operation_type": operation_type,
            "clima": clima_base,
            "umidade_solo": int(umidade_solo),
            "inclinacao": int(inclinacao),
            "distancia_agua": int(distancia_agua),
            "velocidade": int(velocidade),
            "historico_sinistros": int(historico_sinistros),
            "chuva_mm": int(chuva_mm_base),
            "solo_instavel": int(solo_instavel),
            "latitude": float(latitude),
            "longitude": float(longitude),
        }

        ok, resultado = post_json(PREDICT_URL, payload)

        if ok:
            st.success("Predição realizada com sucesso")

            col1, col2, col3 = st.columns(3)
            risk_score = float(resultado.get("risk_score", 0))
            col1.metric("Risk Score", resultado.get("risk_score", "-"))
            col2.metric("Nível de risco", resultado.get("risk_label", "-"))
            col3.metric("Alerta", resultado.get("alert_level", "-"))

            if risk_score > 70:
                st.error("Risco alto")
            elif risk_score > 40:
                st.warning("Risco médio")
            else:
                st.success("Risco baixo")

            st.subheader("Barra de risco")
            st.progress(max(0, min(100, int(risk_score))))

            weather = resultado.get("weather", {})
            st.subheader("Clima usado na análise")
            st.write(f"Fonte: **{weather.get('source', 'desconhecida')}**")
            st.write(f"Condição: **{weather.get('description', 'sem descrição')}**")
            st.write(f"Temperatura: **{weather.get('temperature', '-')} °C**")
            st.write(f"Umidade do ar: **{weather.get('humidity', '-')} %**")
            st.write(f"Vento: **{weather.get('wind_speed', '-')} m/s**")
            st.write(f"Chuva (1h): **{weather.get('rain_mm_1h', '-')} mm**")

            if weather.get("error"):
                st.warning("Clima externo indisponível. O sistema aplicou fallback automático.")

            st.subheader("Alertas")
            alertas = resultado.get("alerts", [])
            if alertas:
                for alerta in alertas:
                    severity = str(alerta.get("severity", "")).lower()
                    message = alerta.get("message", "-")

                    if severity == "high":
                        st.error(message)
                    elif severity == "medium":
                        st.warning(message)
                    else:
                        st.info(message)
            else:
                st.info("Nenhum alerta retornado.")

            st.subheader("Recomendação")
            st.info(resultado.get("recommendation", "Sem recomendação"))

            st.subheader("Mapa da operação")
            mapa_df = pd.DataFrame([{"lat": float(latitude), "lon": float(longitude)}])
            st.map(mapa_df)

            st.subheader("Gráfico de fatores de risco")
            explicacao = resultado.get("explanation", {})
            if explicacao and isinstance(explicacao, dict):
                grafico_df = pd.DataFrame(
                    {"Fator": list(explicacao.keys()), "Impacto": list(explicacao.values())}
                ).set_index("Fator")
                st.bar_chart(grafico_df)
            else:
                st.info("A API não retornou fatores suficientes para o gráfico.")

            st.subheader("Rota segura")
            st.json(resultado.get("safe_route", {}))

            st.subheader("Explicação")
            st.json(resultado.get("explanation", {}))

            st.subheader("Resposta completa")
            st.json(resultado)

        else:
            show_api_error("Erro na API de predição", resultado)

with tab2:
    st.markdown("### Resumo executivo Sompo")

    col_exec1, col_exec2 = st.columns([1, 1])

    with col_exec1:
        ok_summary, summary_data = get_json(SUMMARY_URL)
        if ok_summary:
            metrics = flatten_metrics(summary_data)
            if metrics:
                metric_items = list(metrics.items())[:6]
                cols = st.columns(min(3, len(metric_items)) if metric_items else 1)
                for i, (k, v) in enumerate(metric_items):
                    cols[i % len(cols)].metric(k.replace("_", " ").title(), v)
            else:
                st.json(summary_data)
        else:
            show_api_error("Erro ao carregar resumo executivo", summary_data)

    with col_exec2:
        ok_farms, farms_data = get_json(FARMS_URL)
        if ok_farms:
            df_farms = any_to_dataframe(farms_data)
            st.markdown("#### Fazendas")
            if not df_farms.empty:
                st.dataframe(df_farms, use_container_width=True)
            else:
                st.info("Nenhuma fazenda retornada.")
        else:
            show_api_error("Erro ao carregar fazendas", farms_data)

    ok_equipment, equipment_data = get_json(EQUIPMENT_URL)
    st.markdown("#### Equipamentos")
    if ok_equipment:
        df_equipment = any_to_dataframe(equipment_data)
        if not df_equipment.empty:
            st.dataframe(df_equipment, use_container_width=True)
        else:
            st.info("Nenhum equipamento retornado.")
    else:
        show_api_error("Erro ao carregar equipamentos", equipment_data)

with tab3:
    st.markdown("### Ranking de equipamentos")

    ok_ranking, ranking_data = get_json(RANKING_URL)

    if ok_ranking:
        df_ranking = any_to_dataframe(ranking_data)

        if not df_ranking.empty:
            st.dataframe(df_ranking, use_container_width=True)

            numeric_cols = df_ranking.select_dtypes(include=["number"]).columns.tolist()
            object_cols = df_ranking.select_dtypes(include=["object"]).columns.tolist()

            if numeric_cols and object_cols:
                score_col = numeric_cols[0]
                label_col = object_cols[0]

                chart_df = df_ranking[[label_col, score_col]].copy()
                chart_df.columns = ["Equipamento", "Score"]
                chart_df = chart_df.set_index("Equipamento")

                st.markdown("#### Ranking visual")
                st.bar_chart(chart_df)
            else:
                st.info("Ranking retornado sem colunas adequadas para gráfico.")
        else:
            st.info("Nenhum dado de ranking retornado.")
    else:
        show_api_error("Erro ao carregar ranking", ranking_data)

with tab4:
    st.markdown("### Tendências de risco")

    ok_trends, trends_data = get_json(TRENDS_URL)

    if ok_trends:
        df_trends = extract_trend_dataframe(trends_data)

        if not df_trends.empty:
            st.dataframe(df_trends, use_container_width=True)

            if "Periodo" in df_trends.columns and "Valor" in df_trends.columns:
                plot_df = df_trends.set_index("Periodo")
                st.markdown("#### Evolução do risco")
                st.line_chart(plot_df)
            else:
                st.info("Estrutura de tendências sem colunas esperadas para gráfico.")
        else:
            st.info("Nenhum dado de tendência retornado.")
    else:
        show_api_error("Erro ao carregar tendências", trends_data)

with tab5:
    st.markdown("### Alertas e auditoria")

    col_alerts, col_audit = st.columns(2)

    with col_alerts:
        ok_alerts, alerts_data = get_json(ALERTS_URL)
        st.markdown("#### Alertas recentes")

        if ok_alerts:
            df_alerts = any_to_dataframe(alerts_data)
            if not df_alerts.empty:
                st.dataframe(df_alerts, use_container_width=True)
            else:
                st.info("Nenhum alerta retornado.")
        else:
            show_api_error("Erro ao carregar alertas", alerts_data)

    with col_audit:
        ok_audit, audit_data = get_json(AUDIT_URL)
        st.markdown("#### Auditoria")

        if ok_audit:
            df_audit = any_to_dataframe(audit_data)
            if not df_audit.empty:
                st.dataframe(df_audit, use_container_width=True)
            else:
                st.info("Nenhum dado de auditoria retornado.")
        else:
            show_api_error("Erro ao carregar auditoria", audit_data)