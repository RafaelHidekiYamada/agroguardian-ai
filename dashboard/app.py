import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="AgroGuardian AI", layout="wide")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

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
    executive_explanation = resultado.get("executive_explanation", {})
    if executive_explanation and isinstance(executive_explanation, dict):
        st.info(executive_explanation.get("summary", "Sem resumo executivo disponível."))
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

    st.subheader("Mapa da operação")
    mapa_df = pd.DataFrame([{"lat": float(latitude), "lon": float(longitude)}])
    st.map(mapa_df)

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
    st.json(resultado.get("safe_route", {}))

    st.subheader("Explicação")
    st.json(resultado.get("explanation", {}))

    st.subheader("Resposta completa")
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
            "latitude": float(sim_latitude),
            "longitude": float(sim_longitude),
        }

        ok_base, base_result = post_json(PREDICT_URL, payload_base)
        ok_sim, sim_result = post_json(SIMULATE_URL, payload_simulado)

        if ok_base and ok_sim:
            st.success("Simulação executada com sucesso")

            base_score = float(base_result.get("risk_score", 0))
            sim_score = float(sim_result.get("risk_score", 0))
            delta = round(sim_score - base_score, 2)

            c1, c2, c3 = st.columns(3)
            c1.metric("Risco base", base_score)
            c2.metric("Risco simulado", sim_score)
            c3.metric("Variação", delta)

            if delta > 0:
                st.error(f"O cenário simulado aumentou o risco em {delta} pontos.")
            elif delta < 0:
                st.success(f"O cenário simulado reduziu o risco em {abs(delta)} pontos.")
            else:
                st.info("O cenário simulado manteve o mesmo nível de risco.")

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

            st.markdown("#### Fatores do cenário simulado")
            sim_explanation = sim_result.get("explanation", {})
            if sim_explanation and isinstance(sim_explanation, dict):
                sim_expl_df = pd.DataFrame(
                    {"Fator": list(sim_explanation.keys()), "Impacto": list(sim_explanation.values())}
                ).set_index("Fator")
                st.bar_chart(sim_expl_df)
            else:
                st.info("Sem fatores suficientes para o gráfico do cenário simulado.")

            st.markdown("#### Resposta completa do cenário simulado")
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
            st.json(metrics_data)

            if isinstance(metrics_data, dict):
                baseline = metrics_data.get("baseline", {})
                neural = metrics_data.get("neural_network", {})

                if baseline and neural:
                    chart_df = pd.DataFrame(
                        {
                            "Modelo": ["Baseline", "Rede Neural"],
                            "R2": [
                                baseline.get("r2", 0),
                                neural.get("r2", 0),
                            ],
                            "RMSE": [
                                baseline.get("rmse", 0),
                                neural.get("rmse", 0),
                            ],
                        }
                    ).set_index("Modelo")

                    st.markdown("#### Comparativo visual")
                    st.bar_chart(chart_df)
        else:
            show_api_error("Erro ao carregar métricas do modelo", metrics_data)