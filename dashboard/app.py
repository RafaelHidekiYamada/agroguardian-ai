import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

import pydeck as pdk

st.set_page_config(page_title="AgroGuardian AI", layout="wide")

API_HOSTPORT = os.getenv("API_HOSTPORT", "").strip()
API_BASE_URL = os.getenv("API_BASE_URL", "").strip()
if not API_BASE_URL and API_HOSTPORT:
    API_BASE_URL = f"http://{API_HOSTPORT}"
if not API_BASE_URL:
    API_BASE_URL = "http://127.0.0.1:8000"

PREDICT_URL = f"{API_BASE_URL}/api/v1/risk/predict"
SIMULATE_URL = f"{API_BASE_URL}/api/v1/simulate"
SUMMARY_URL = f"{API_BASE_URL}/api/v1/dashboard/summary"
RANKING_URL = f"{API_BASE_URL}/api/v1/dashboard/ranking"
TRENDS_URL = f"{API_BASE_URL}/api/v1/dashboard/trends"
ALERTS_URL = f"{API_BASE_URL}/api/v1/dashboard/alerts"
AUDIT_URL = f"{API_BASE_URL}/api/v1/dashboard/audit"
EQUIPMENT_URL = f"{API_BASE_URL}/api/v1/equipment"
FARMS_URL = f"{API_BASE_URL}/api/v1/farms"
POLICIES_URL = f"{API_BASE_URL}/api/v1/policies/alerts"
ML_STATUS_URL = f"{API_BASE_URL}/api/v1/ml/status"
ML_METRICS_URL = f"{API_BASE_URL}/api/v1/ml/metrics"
AUTH_LOGIN_URL = f"{API_BASE_URL}/api/v1/auth/login"
AUTH_ME_URL = f"{API_BASE_URL}/api/v1/auth/me"


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ag-bg: #071016;
            --ag-panel: #0d1b22;
            --ag-panel-2: #10242c;
            --ag-line: rgba(115, 232, 214, 0.26);
            --ag-cyan: #49ead8;
            --ag-green: #8cffb2;
            --ag-amber: #ffd166;
            --ag-magenta: #ff5ea8;
            --ag-text: #edf7f5;
            --ag-muted: #9db7b3;
        }

        .stApp {
            background:
                radial-gradient(circle at 12% 0%, rgba(73, 234, 216, 0.16), transparent 28rem),
                linear-gradient(135deg, #071016 0%, #0a1118 42%, #101317 100%);
            color: var(--ag-text);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #081217 0%, #0d1b22 100%);
            border-right: 1px solid var(--ag-line);
        }

        h1, h2, h3 {
            color: var(--ag-text);
            letter-spacing: 0;
        }

        h1 {
            font-weight: 800;
        }

        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(16, 36, 44, 0.95), rgba(8, 18, 23, 0.95));
            border: 1px solid var(--ag-line);
            border-radius: 8px;
            padding: 0.8rem 0.9rem;
            box-shadow: 0 0 0 1px rgba(73, 234, 216, 0.04), 0 14px 38px rgba(0, 0, 0, 0.22);
        }

        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
            color: var(--ag-muted);
        }

        .stButton > button,
        .stFormSubmitButton > button {
            background: linear-gradient(90deg, var(--ag-cyan), var(--ag-green));
            color: #071016;
            border: 0;
            border-radius: 8px;
            font-weight: 800;
            box-shadow: 0 0 22px rgba(73, 234, 216, 0.22);
        }

        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
            border: 0;
            color: #071016;
            filter: brightness(1.06);
        }

        div[data-testid="stAlert"] {
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.12);
        }

        .ag-panel {
            background: linear-gradient(180deg, rgba(16, 36, 44, 0.95), rgba(8, 18, 23, 0.95));
            border: 1px solid var(--ag-line);
            border-radius: 8px;
            padding: 1rem;
            margin: 0.45rem 0 1rem 0;
        }

        .ag-panel strong {
            color: var(--ag-cyan);
        }

        .ag-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.55rem;
        }

        .ag-chip {
            border: 1px solid var(--ag-line);
            background: rgba(73, 234, 216, 0.08);
            border-radius: 999px;
            padding: 0.22rem 0.62rem;
            color: var(--ag-text);
            font-size: 0.86rem;
        }

        .ag-chip.warn {
            border-color: rgba(255, 209, 102, 0.45);
            background: rgba(255, 209, 102, 0.12);
        }

        .ag-chip.hot {
            border-color: rgba(255, 94, 168, 0.5);
            background: rgba(255, 94, 168, 0.12);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


apply_theme()


def init_auth_state() -> None:
    defaults = {
        "auth_token": None,
        "auth_user": None,
        "auth_role": None,
        "auth_full_name": None,
        "auth_email": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_auth_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    token = st.session_state.get("auth_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def login_user(username: str, password: str) -> tuple[bool, str]:
    try:
        response = requests.post(
            AUTH_LOGIN_URL,
            json={"username": username, "password": password},
            timeout=20,
        )

        if response.status_code != 200:
            try:
                data = response.json()
                return False, data.get("detail", "Falha no login")
            except Exception:
                return False, response.text

        login_data = response.json()
        token = login_data.get("access_token")

        me_response = requests.get(
            AUTH_ME_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )

        if me_response.status_code != 200:
            return False, "Login realizado, mas falhou ao carregar perfil do usuário."

        me_data = me_response.json()

        st.session_state["auth_token"] = token
        st.session_state["auth_user"] = me_data.get("username")
        st.session_state["auth_role"] = me_data.get("role")
        st.session_state["auth_full_name"] = me_data.get("full_name")
        st.session_state["auth_email"] = me_data.get("email")

        return True, "Login realizado com sucesso."

    except requests.exceptions.RequestException as e:
        return False, f"Erro de conexão no login: {e}"


def logout_user() -> None:
    st.session_state["auth_token"] = None
    st.session_state["auth_user"] = None
    st.session_state["auth_role"] = None
    st.session_state["auth_full_name"] = None
    st.session_state["auth_email"] = None
    st.rerun()


def get_json(url: str) -> tuple[bool, Any]:
    try:
        response = requests.get(
            url,
            headers=get_auth_headers(),
            timeout=30,
        )
        if response.status_code == 200:
            return True, response.json()

        try:
            return False, response.json()
        except Exception:
            return False, {"detail": response.text, "status_code": response.status_code}
    except requests.exceptions.RequestException as e:
        return False, {"detail": str(e), "status_code": 500}


def post_json(url: str, payload: dict) -> tuple[bool, Any]:
    try:
        response = requests.post(
            url,
            json=payload,
            headers=get_auth_headers(),
            timeout=30,
        )
        if response.status_code in (200, 201):
            return True, response.json()

        try:
            return False, response.json()
        except Exception:
            return False, {"detail": response.text, "status_code": response.status_code}
    except requests.exceptions.RequestException as e:
        return False, {"detail": str(e), "status_code": 500}


def put_json(url: str, payload: dict) -> tuple[bool, Any]:
    try:
        response = requests.put(
            url,
            json=payload,
            headers=get_auth_headers(),
            timeout=30,
        )
        if response.status_code == 200:
            return True, response.json()

        try:
            return False, response.json()
        except Exception:
            return False, {"detail": response.text, "status_code": response.status_code}
    except requests.exceptions.RequestException as e:
        return False, {"detail": str(e), "status_code": 500}


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

    time_candidates = ["date", "data", "timestamp", "periodo", "mes", "dia"]
    value_candidates = [
        "risk_score",
        "score",
        "value",
        "valor",
        "avg_risk",
        "media_risco",
        "trend",
        "quantidade",
        "total",
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


def flatten_metrics(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    flat: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            flat[key] = value
    return flat


def show_api_error(title: str, data: Any) -> None:
    st.error(title)
    if isinstance(data, (dict, list)):
        st.json(data)
    else:
        st.write(data)


def render_prediction_result(resultado: dict, latitude: float, longitude: float) -> None:
    st.success("Predição realizada com sucesso")

    col1, col2, col3 = st.columns(3)
    risk_score = float(resultado.get("risk_score", 0))
    col1.metric("Risk Score", resultado.get("risk_score", "-"))
    col2.metric("Nível de risco", resultado.get("risk_label", "-"))
    col3.metric("Alerta", resultado.get("alert_level", "-"))

    decision_support = resultado.get("decision_support", {})
    if decision_support and isinstance(decision_support, dict):
        st.subheader("Centro de decisao da IA")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Decisao", decision_support.get("decision_label", "-"))
        d2.metric("Prioridade", decision_support.get("priority", "-"))
        d3.metric("Confianca", decision_support.get("confidence_label", "-"))
        d4.metric("Score confianca", decision_support.get("confidence", "-"))

        st.markdown(
            f"""
            <div class="ag-panel">
                <strong>Por que:</strong> {decision_support.get("why", "-")}
            </div>
            """,
            unsafe_allow_html=True,
        )

        action_cols = st.columns(3)
        with action_cols[0]:
            st.markdown("#### Acoes")
            for item in decision_support.get("operational_actions", []):
                st.write(f"- {item}")
        with action_cols[1]:
            st.markdown("#### Monitoramento")
            for item in decision_support.get("monitoring_plan", []):
                st.write(f"- {item}")
        with action_cols[2]:
            st.markdown("#### Escalonamento")
            for item in decision_support.get("escalation", []):
                st.write(f"- {item}")

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

    st.subheader("Resumo executivo da IA")
    st.subheader("Composição do score")
    risk_components = resultado.get("risk_components", {})
    if risk_components and isinstance(risk_components, dict):
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric("Score do modelo", risk_components.get("model_risk_score", "-"))
        rc2.metric("Risco geográfico", risk_components.get("geo_risk_points", "-"))
        rc3.metric("Score bruto", risk_components.get("uncapped_final_score", "-"))
        rc4.metric("Score final", risk_components.get("final_risk_score", "-"))
    else:
        st.info("Sem composição de score disponível.")
    executive_explanation = resultado.get("executive_explanation", {})
    if executive_explanation and isinstance(executive_explanation, dict):
        st.info(executive_explanation.get("summary", "Sem resumo executivo disponível."))
        next_actions = executive_explanation.get("next_actions", [])
        if next_actions:
            st.markdown("#### Proximas acoes")
            for action in next_actions:
                st.write(f"- {action}")
    else:
        st.info("Sem resumo executivo disponível.")

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

    st.subheader("Contexto geográfico")
    geo_context = resultado.get("geo_context", {})

    if geo_context and isinstance(geo_context, dict):
        nearest_water = geo_context.get("nearest_water", {})
        geo_risk = geo_context.get("geo_risk", {})

        g1, g2, g3, g4 = st.columns(4)
        g1.metric("Zona geográfica", geo_risk.get("geo_zone", "-"))
        g2.metric("Zona hídrica", geo_risk.get("water_zone", "-"))
        g3.metric("Distância da água (m)", nearest_water.get("distance_m", "-"))
        g4.metric("Agravantes de terreno", geo_risk.get("terrain_aggravation_points", "-"))

        st.info(geo_risk.get("geo_reason", "Sem justificativa geográfica."))
        st.write(f"**Ponto de água mais próximo:** {nearest_water.get('nearest_name', '-')}")
    else:
        st.info("Sem contexto geográfico disponível.")

    st.subheader("Mapa da operação")

    nearest_water = {}
    if geo_context and isinstance(geo_context, dict):
        nearest_water = geo_context.get("nearest_water", {})

    map_rows = [
        {
            "lat": float(latitude),
            "lon": float(longitude),
            "label": "Máquina",
            "color": [255, 60, 60],
            "radius": 80,
        }
    ]

    if nearest_water.get("nearest_lat") is not None and nearest_water.get("nearest_lon") is not None:
        map_rows.append(
            {
                "lat": float(nearest_water["nearest_lat"]),
                "lon": float(nearest_water["nearest_lon"]),
                "label": "Água mais próxima",
                "color": [60, 160, 255],
                "radius": 70,
            }
        )

    mapa_df = pd.DataFrame(map_rows)

    view_state = pdk.ViewState(
        latitude=float(latitude),
        longitude=float(longitude),
        zoom=13,
        pitch=0,
    )

    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=mapa_df,
        get_position="[lon, lat]",
        get_color="color",
        get_radius="radius",
        pickable=True,
    )

    text_layer = pdk.Layer(
        "TextLayer",
        data=mapa_df,
        get_position="[lon, lat]",
        get_text="label",
        get_size=14,
        get_color=[255, 255, 255],
        get_alignment_baseline="'top'",
    )

    st.pydeck_chart(
        pdk.Deck(
            initial_view_state=view_state,
            layers=[scatter_layer, text_layer],
            tooltip={"text": "{label}"},
        ),
        use_container_width=True,
    )

    st.subheader("Principais fatores de risco")
    explicacao = resultado.get("explanation", {})
    if explicacao and isinstance(explicacao, dict):
        top_items = list(explicacao.items())[:5]
        for fator, impacto in top_items:
            st.write(f"**{fator}:** {impacto}%")
    else:
        st.info("Sem fatores explicativos disponíveis.")

    st.subheader("Gráfico de fatores de risco")
    if explicacao and isinstance(explicacao, dict):
        grafico_df = pd.DataFrame(
            {"Fator": list(explicacao.keys()), "Impacto": list(explicacao.values())}
        ).set_index("Fator")
        st.bar_chart(grafico_df)
    else:
        st.info("A API não retornou fatores suficientes para o gráfico.")

    st.subheader("Rota segura")
    safe_route = resultado.get("safe_route", {})
    if safe_route and isinstance(safe_route, dict):
        route_explanation = safe_route.get("route_explanation", {})
        r1, r2, r3 = st.columns(3)
        r1.metric("Rota", safe_route.get("recommended_route", "-"))
        r2.metric("Score da rota", safe_route.get("route_score", "-"))
        r3.metric("Risco da rota", safe_route.get("risk_label", "-"))

        st.markdown(
            f"""
            <div class="ag-panel">
                <strong>Justificativa:</strong> {safe_route.get("rationale", "-")}
            </div>
            """,
            unsafe_allow_html=True,
        )

        critical = route_explanation.get("critical_segment", {})
        if critical:
            st.warning(
                f"Trecho critico: {critical.get('name', '-')} | "
                f"risco {critical.get('risk_score', '-')} | {critical.get('reason', '-')}"
            )

        steps = route_explanation.get("operator_steps", [])
        if steps:
            st.markdown("#### Passos para o operador")
            for step in steps:
                st.write(f"- {step}")

        alternatives = safe_route.get("alternatives", [])
        if alternatives:
            route_df = pd.DataFrame(
                [
                    {
                        "Rota": item.get("name"),
                        "Score": item.get("route_score"),
                        "Risco": item.get("risk_label"),
                        "Distancia km": item.get("distance_km"),
                        "Minutos": item.get("estimated_minutes"),
                    }
                    for item in alternatives
                ]
            )
            st.dataframe(route_df, use_container_width=True)
    else:
        st.info("Sem rota segura retornada.")

    st.subheader("Explicação")
    st.json(resultado.get("explanation", {}))

    with st.expander("Resposta completa da API"):
        st.json(resultado)


init_auth_state()

st.sidebar.markdown("---")
st.sidebar.subheader("Acesso seguro")

if not st.session_state.get("auth_token"):
    login_username = st.sidebar.text_input("Usuário", key="login_username")
    login_password = st.sidebar.text_input("Senha", type="password", key="login_password")

    if st.sidebar.button("Entrar", key="btn_login"):
        ok, msg = login_user(login_username, login_password)
        if ok:
            st.sidebar.success(msg)
            st.rerun()
        else:
            st.sidebar.error(msg)

    st.title("🌱 AgroGuardian AI")
    st.subheader("Plataforma Inteligente de Prevenção de Sinistros Agrícolas")
    st.warning("Faça login para acessar o dashboard seguro.")
    st.stop()
else:
    st.sidebar.success(f"Logado como: {st.session_state.get('auth_user')}")
    st.sidebar.write(f"Perfil: **{st.session_state.get('auth_role')}**")
    st.sidebar.write(f"Nome: **{st.session_state.get('auth_full_name')}**")

    if st.sidebar.button("Sair", key="btn_logout"):
        logout_user()

st.title("🌱 AgroGuardian AI")
st.subheader("Plataforma Inteligente de Prevenção de Sinistros Agrícolas")

user_role = st.session_state.get("auth_role", "operador")

tab_labels = [
    "Operação em tempo real",
    "Resumo executivo",
    "Ranking",
    "Tendências",
]

if user_role in ("admin", "sompo"):
    tab_labels.append("Alertas e auditoria")

if user_role in ("admin", "gestor"):
    tab_labels.append("Políticas de alerta")

tab_labels.extend(
    [
        "Simulador de risco",
        "IA e ML",
    ]
)

tabs = st.tabs(tab_labels)
tab_map = dict(zip(tab_labels, tabs))

with tab_map["Operação em tempo real"]:
    st.sidebar.header("Dados da operação")

    equipment_id = st.sidebar.number_input("ID do equipamento", min_value=1, value=1, step=1)
    farm_id = st.sidebar.number_input("ID da fazenda", min_value=1, value=1, step=1)
    region = st.sidebar.text_input("Região", value="Guarulhos - SP")
    operation_type = st.sidebar.selectbox(
        "Tipo de operação",
        ["campo", "transporte", "proximidade_agua"],
    )

    umidade_solo = st.sidebar.slider("Umidade do solo", 0, 100, 80)
    inclinacao = st.sidebar.slider("Inclinação do terreno", 0, 90, 12)
    distancia_agua = st.sidebar.slider("Distância da água (manual / fallback)", 0, 1000, 20)
    st.sidebar.caption("A análise principal usa a distância geográfica calculada pelas coordenadas.")
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
        st.markdown("### Estado da integração")
        st.caption(f"API base: {API_BASE_URL}")

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
            render_prediction_result(resultado, latitude, longitude)
        else:
            show_api_error("Erro na API de predição", resultado)

with tab_map["Resumo executivo"]:
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

with tab_map["Ranking"]:
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
                label_col = next((c for c in object_cols if "name" in c.lower()), object_cols[0])

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

with tab_map["Tendências"]:
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

if "Alertas e auditoria" in tab_map:
    with tab_map["Alertas e auditoria"]:
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

if "Políticas de alerta" in tab_map:
    with tab_map["Políticas de alerta"]:
        st.markdown("### Políticas de alerta")

        ok_policies, policies_data = get_json(POLICIES_URL)

        if ok_policies:
            df_policies = any_to_dataframe(policies_data)
            if not df_policies.empty:
                st.dataframe(df_policies, use_container_width=True)
            else:
                st.info("Nenhuma política encontrada.")
        else:
            show_api_error("Erro ao carregar políticas", policies_data)

        st.markdown("### Criar nova política")

        with st.form("nova_politica"):
            name = st.text_input("Nome da política", value="Nova Política")
            policy_operation_type = st.selectbox(
                "Tipo de operação da política",
                ["campo", "transporte", "proximidade_agua", "all"],
                key="policy_operation_type"
            )

            min_risk_alert = st.number_input("Score mínimo para alerta", value=40.0)
            min_risk_block = st.number_input("Score mínimo para bloqueio", value=70.0)
            max_speed = st.number_input("Velocidade máxima", value=25.0)
            max_slope = st.number_input("Inclinação máxima", value=15.0)
            min_distance_water = st.number_input("Distância mínima da água", value=30.0)
            max_rain_mm = st.number_input("Chuva máxima (mm)", value=20.0)

            block_on_water = st.checkbox("Bloquear se estiver próximo da água", value=False)
            block_on_unstable_soil = st.checkbox("Bloquear se solo estiver instável", value=False)
            is_active = st.checkbox("Política ativa", value=True)

            submitted = st.form_submit_button("Salvar política")

            if submitted:
                payload = {
                    "name": name,
                    "operation_type": policy_operation_type,
                    "min_risk_alert": min_risk_alert,
                    "min_risk_block": min_risk_block,
                    "max_speed": max_speed,
                    "max_slope": max_slope,
                    "min_distance_water": min_distance_water,
                    "max_rain_mm": max_rain_mm,
                    "block_on_water": block_on_water,
                    "block_on_unstable_soil": block_on_unstable_soil,
                    "is_active": is_active,
                }

                ok_create, create_data = post_json(POLICIES_URL, payload)

                if ok_create:
                    st.success("Política criada com sucesso. Atualize a página para visualizar.")
                    st.json(create_data)
                else:
                    show_api_error("Erro ao criar política", create_data)

        st.markdown("### Atualizar política existente")

        with st.form("editar_politica"):
            policy_id = st.number_input("ID da política", min_value=1, value=1, step=1)

            edit_name = st.text_input("Nome da política", value="Política Atualizada", key="edit_name")
            edit_operation_type = st.selectbox(
                "Tipo de operação",
                ["campo", "transporte", "proximidade_agua", "all"],
                key="edit_operation_type"
            )

            edit_min_risk_alert = st.number_input("Score mínimo para alerta", value=40.0, key="edit_min_risk_alert")
            edit_min_risk_block = st.number_input("Score mínimo para bloqueio", value=70.0, key="edit_min_risk_block")
            edit_max_speed = st.number_input("Velocidade máxima", value=25.0, key="edit_max_speed")
            edit_max_slope = st.number_input("Inclinação máxima", value=15.0, key="edit_max_slope")
            edit_min_distance_water = st.number_input("Distância mínima da água", value=30.0, key="edit_min_distance_water")
            edit_max_rain_mm = st.number_input("Chuva máxima (mm)", value=20.0, key="edit_max_rain_mm")

            edit_block_on_water = st.checkbox("Bloquear se estiver próximo da água", value=False, key="edit_block_on_water")
            edit_block_on_unstable_soil = st.checkbox("Bloquear se solo estiver instável", value=False, key="edit_block_on_unstable_soil")
            edit_is_active = st.checkbox("Política ativa", value=True, key="edit_is_active")

            submitted_update = st.form_submit_button("Atualizar política")

            if submitted_update:
                payload = {
                    "name": edit_name,
                    "operation_type": edit_operation_type,
                    "min_risk_alert": edit_min_risk_alert,
                    "min_risk_block": edit_min_risk_block,
                    "max_speed": edit_max_speed,
                    "max_slope": edit_max_slope,
                    "min_distance_water": edit_min_distance_water,
                    "max_rain_mm": edit_max_rain_mm,
                    "block_on_water": edit_block_on_water,
                    "block_on_unstable_soil": edit_block_on_unstable_soil,
                    "is_active": edit_is_active,
                }

                ok_update, update_data = put_json(f"{POLICIES_URL}/{int(policy_id)}", payload)

                if ok_update:
                    st.success("Política atualizada com sucesso.")
                    st.json(update_data)
                else:
                    show_api_error("Erro ao atualizar política", update_data)

with tab_map["Simulador de risco"]:
    st.markdown("### Simulador de risco")
    st.caption("Compare um cenário base com um cenário simulado para tomada de decisão preventiva.")

    sim_col1, sim_col2 = st.columns(2)

    with sim_col1:
        st.markdown("#### Cenário base")

        sim_equipment_id = st.number_input("ID do equipamento", min_value=1, value=1, step=1, key="sim_equipment_id")
        sim_farm_id = st.number_input("ID da fazenda", min_value=1, value=1, step=1, key="sim_farm_id")
        sim_region = st.text_input("Região", value="Guarulhos - SP", key="sim_region")
        sim_operation_type = st.selectbox(
            "Tipo de operação",
            ["campo", "transporte", "proximidade_agua"],
            key="sim_operation_type"
        )

        sim_clima = st.selectbox("Clima base", ["sol", "nublado", "chuva"], key="sim_clima")
        sim_umidade_solo = st.slider("Umidade do solo", 0, 100, 80, key="sim_umidade_solo")
        sim_inclinacao = st.slider("Inclinação", 0, 90, 12, key="sim_inclinacao")
        sim_distancia_agua = st.slider("Distância da água", 0, 1000, 20, key="sim_distancia_agua")
        sim_velocidade = st.slider("Velocidade", 0, 200, 15, key="sim_velocidade")
        sim_historico = st.slider("Histórico de sinistros", 0, 20, 2, key="sim_historico")
        sim_chuva_mm = st.slider("Chuva base (mm)", 0, 100, 0, key="sim_chuva_mm")
        sim_solo_instavel = st.selectbox("Solo instável", [0, 1], key="sim_solo_instavel")
        sim_latitude = st.number_input("Latitude", value=-23.455000, format="%.6f", key="sim_latitude")
        sim_longitude = st.number_input("Longitude", value=-46.533000, format="%.6f", key="sim_longitude")

    with sim_col2:
        st.markdown("#### Cenário simulado")

        scenario_name = st.text_input(
            "Nome do cenário",
            value="E se operar amanhã com chuva?",
            key="scenario_name"
        )

        alterar_localizacao = st.checkbox(
            "Alterar localização no cenário simulado",
            value=False,
            key="alterar_localizacao_sim",
        )

        sim2_latitude = sim_latitude
        sim2_longitude = sim_longitude

        if alterar_localizacao:
            sim2_latitude = st.number_input(
                "Latitude simulada",
                value=float(sim_latitude),
                format="%.6f",
                key="sim2_latitude",
            )
            sim2_longitude = st.number_input(
                "Longitude simulada",
                value=float(sim_longitude),
                format="%.6f",
                key="sim2_longitude",
            )

        sim2_clima = st.selectbox("Clima simulado", ["sol", "nublado", "chuva"], index=2, key="sim2_clima")
        sim2_umidade_solo = st.slider("Umidade do solo simulada", 0, 100, 90, key="sim2_umidade_solo")
        sim2_inclinacao = st.slider("Inclinação simulada", 0, 90, 18, key="sim2_inclinacao")
        sim2_distancia_agua = st.slider("Distância da água simulada", 0, 1000, 10, key="sim2_distancia_agua")
        sim2_velocidade = st.slider("Velocidade simulada", 0, 200, 20, key="sim2_velocidade")
        sim2_historico = st.slider("Histórico simulado", 0, 20, 2, key="sim2_historico")
        sim2_chuva_mm = st.slider("Chuva simulada (mm)", 0, 100, 25, key="sim2_chuva_mm")
        sim2_solo_instavel = st.selectbox("Solo instável simulado", [0, 1], index=1, key="sim2_solo_instavel")

    simular = st.button("Executar simulação")

    if simular:
        payload_base = {
            "equipment_id": int(sim_equipment_id),
            "farm_id": int(sim_farm_id),
            "region": sim_region,
            "operation_type": sim_operation_type,
            "clima": sim_clima,
            "umidade_solo": int(sim_umidade_solo),
            "inclinacao": int(sim_inclinacao),
            "distancia_agua": int(sim_distancia_agua),
            "velocidade": int(sim_velocidade),
            "historico_sinistros": int(sim_historico),
            "chuva_mm": int(sim_chuva_mm),
            "solo_instavel": int(sim_solo_instavel),
            "latitude": float(sim_latitude),
            "longitude": float(sim_longitude),
        }

        payload_simulado = {
            "scenario_name": scenario_name,
            "equipment_id": int(sim_equipment_id),
            "farm_id": int(sim_farm_id),
            "region": sim_region,
            "operation_type": sim_operation_type,
            "clima": sim2_clima,
            "umidade_solo": int(sim2_umidade_solo),
            "inclinacao": int(sim2_inclinacao),
            "distancia_agua": int(sim2_distancia_agua),
            "velocidade": int(sim2_velocidade),
            "historico_sinistros": int(sim2_historico),
            "chuva_mm": int(sim2_chuva_mm),
            "solo_instavel": int(sim2_solo_instavel),
            "latitude": float(sim2_latitude),
            "longitude": float(sim2_longitude),
        }

        ok_base, base_result = post_json(PREDICT_URL, payload_base)
        ok_sim, sim_result = post_json(SIMULATE_URL, payload_simulado)

        if ok_base and ok_sim:
            st.success("Simulação executada com sucesso")

            base_score = float(base_result.get("risk_score", 0))
            sim_score = float(sim_result.get("risk_score", 0))
            delta = round(sim_score - base_score, 2)

            base_components = base_result.get("risk_components", {})
            sim_components = sim_result.get("risk_components", {})

            base_raw = float(base_components.get("uncapped_final_score", base_score))
            sim_raw = float(sim_components.get("uncapped_final_score", sim_score))
            raw_delta = round(sim_raw - base_raw, 2)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Risco base", base_score)
            c2.metric("Risco simulado", sim_score)
            c3.metric("Variação final", delta)
            c4.metric("Variação bruta", raw_delta)

            if raw_delta > 0:
                st.error(f"O cenário simulado aumentou o risco bruto em {raw_delta} pontos.")
            elif raw_delta < 0:
                st.success(f"O cenário simulado reduziu o risco bruto em {abs(raw_delta)} pontos.")
            else:
                st.info("O cenário simulado manteve o mesmo risco bruto.")

            comp_df = pd.DataFrame(
                {
                    "Cenário": ["Base", "Simulado"],
                    "Risk Score": [base_score, sim_score],
                }
            ).set_index("Cenário")

            st.markdown("#### Comparativo visual")
            st.bar_chart(comp_df)

            col_base, col_sim = st.columns(2)

            with col_base:
                st.markdown("#### Resultado base")
                st.write(f"**Nível:** {base_result.get('risk_label', '-')}")
                st.write(f"**Alerta:** {base_result.get('alert_level', '-')}")
                st.info(base_result.get("recommendation", "Sem recomendação"))

            with col_sim:
                st.markdown("#### Resultado simulado")
                st.write(f"**Nível:** {sim_result.get('risk_label', '-')}")
                st.write(f"**Alerta:** {sim_result.get('alert_level', '-')}")
                st.info(sim_result.get("recommendation", "Sem recomendação"))

            st.markdown("#### Resumo executivo do cenário simulado")
            sim_exec = sim_result.get("executive_explanation", {})
            if sim_exec and isinstance(sim_exec, dict):
                st.info(sim_exec.get("summary", "Sem resumo executivo disponível."))
            else:
                st.info("Sem resumo executivo disponível.")
            
            st.markdown("#### Contexto geográfico comparado")

            base_geo = base_result.get("geo_context", {})
            sim_geo = sim_result.get("geo_context", {})

            gc1, gc2 = st.columns(2)

            with gc1:
                st.markdown("**Base**")
                if base_geo and isinstance(base_geo, dict):
                    base_nearest = base_geo.get("nearest_water", {})
                    base_risk = base_geo.get("geo_risk", {})
                    st.write(f"Zona: **{base_risk.get('geo_zone', '-')}**")
                    st.write(f"Distância da água: **{base_nearest.get('distance_m', '-')} m**")
                    st.write(f"Risco geográfico: **{base_risk.get('geo_risk_points', '-')}**")
                else:
                    st.info("Sem contexto geográfico base.")

            with gc2:
                st.markdown("**Simulado**")
                if sim_geo and isinstance(sim_geo, dict):
                    sim_nearest = sim_geo.get("nearest_water", {})
                    sim_risk = sim_geo.get("geo_risk", {})
                    st.write(f"Zona: **{sim_risk.get('geo_zone', '-')}**")
                    st.write(f"Distância da água: **{sim_nearest.get('distance_m', '-')} m**")
                    st.write(f"Risco geográfico: **{sim_risk.get('geo_risk_points', '-')}**")
                else:
                    st.info("Sem contexto geográfico simulado.")

            st.markdown("#### Fatores do cenário simulado")
            sim_explanation = sim_result.get("explanation", {})
            if sim_explanation and isinstance(sim_explanation, dict):
                sim_expl_df = pd.DataFrame(
                    {"Fator": list(sim_explanation.keys()), "Impacto": list(sim_explanation.values())}
                ).set_index("Fator")
                st.bar_chart(sim_expl_df)
            else:
                st.info("Sem fatores suficientes para o gráfico do cenário simulado.")

            with st.expander("Resposta completa do cenário simulado"):
                st.json(sim_result)
        else:
            if not ok_base:
                show_api_error("Erro no cálculo do cenário base", base_result)
            if not ok_sim:
                show_api_error("Erro no cálculo do cenário simulado", sim_result)

with tab_map["IA e ML"]:
    st.markdown("### Inteligência Artificial e Machine Learning")

    ok_status, status_data = get_json(ML_STATUS_URL)
    ok_metrics, metrics_data = get_json(ML_METRICS_URL)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Status do modelo em produção")
        if ok_status:
            st.json(status_data)
        else:
            show_api_error("Erro ao carregar status do modelo", status_data)

    with col2:
        st.markdown("#### Métricas dos modelos")
        if ok_metrics:
            if isinstance(metrics_data, dict):
                best_model = metrics_data.get("best_model") or metrics_data.get("tree_search", {})
                recommended_model = metrics_data.get("recommended_model", "-")

                if best_model:
                    regression = best_model.get("regression", {})
                    classification = best_model.get("classification_at_70", {})
                    curve_point = best_model.get("best_curve_point", classification)

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Modelo vencedor", best_model.get("model_name", recommended_model))
                    m2.metric("RMSE", regression.get("rmse", "-"))
                    m3.metric("Accuracy", classification.get("accuracy", "-"))
                    m4.metric("F1 alto risco", curve_point.get("f1", "-"))

                    st.markdown(
                        f"""
                        <div class="ag-panel">
                            <strong>Regra de selecao:</strong> {metrics_data.get("selection_rule", "-")}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    weights = best_model.get("feature_weights", {})
                    if weights:
                        st.markdown("#### Melhores pesos das variaveis")
                        weights_df = pd.DataFrame(
                            {"Variavel": list(weights.keys()), "Peso": list(weights.values())}
                        ).set_index("Variavel")
                        st.bar_chart(weights_df)

                    curve = best_model.get("threshold_curve", [])
                    if curve:
                        st.markdown("#### Curva de threshold para alto risco")
                        curve_df = pd.DataFrame(curve)
                        st.line_chart(curve_df.set_index("threshold")[["accuracy", "f1", "balanced_accuracy"]])

                    if best_model.get("best_params"):
                        st.markdown("#### Melhores parametros")
                        st.json(best_model.get("best_params"))

            st.json(metrics_data)

            if isinstance(metrics_data, dict):
                baseline = metrics_data.get("baseline", {})
                neural = metrics_data.get("neural_network", {})
                metric_value = lambda item, key: item.get(key, item.get("regression", {}).get(key, 0))

                if baseline and neural:
                    chart_df = pd.DataFrame(
                        {
                            "Modelo": ["Baseline", "Rede Neural"],
                            "R2": [
                                metric_value(baseline, "r2"),
                                metric_value(neural, "r2"),
                            ],
                            "RMSE": [
                                metric_value(baseline, "rmse"),
                                metric_value(neural, "rmse"),
                            ],
                        }
                    ).set_index("Modelo")

                    st.markdown("#### Comparativo visual")
                    st.bar_chart(chart_df)
        else:
            show_api_error("Erro ao carregar métricas do modelo", metrics_data)
