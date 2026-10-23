import json
import os
from html import escape as _html_escape
import sys
import time
from datetime import datetime, timedelta, timezone
from datetime import time as time_cls
from typing import Any
from urllib.parse import quote

import altair as alt
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from timeutils import LOCAL_TZ, LOCAL_TZ_LABEL, format_local_time, localize_time_columns  # noqa: E402

import pydeck as pdk

st.set_page_config(page_title="AgroGuardian AI", layout="wide")

def resolve_api_base_url() -> str:
    api_hostport = os.getenv("API_HOSTPORT", "").strip()
    configured_url = os.getenv("API_BASE_URL", "").strip()
    public_hostname = os.getenv("API_PUBLIC_HOSTNAME", "").strip()
    environment = os.getenv("ENVIRONMENT", "development").strip().lower()
    if configured_url:
        return configured_url.rstrip("/")
    if public_hostname:
        if public_hostname.startswith(("http://", "https://")):
            return public_hostname.rstrip("/")
        return f"https://{public_hostname}".rstrip("/")
    if api_hostport:
        return f"http://{api_hostport}".rstrip("/")

    if environment not in {"development", "dev", "test", "testing"}:
        return ""

    for candidate in ("http://127.0.0.1:8000", "http://127.0.0.1:8001"):
        try:
            health = requests.get(f"{candidate}/health", timeout=1.5)
            openapi = requests.get(f"{candidate}/openapi.json", timeout=1.5)
            paths = openapi.json().get("paths", {}) if openapi.status_code == 200 else {}
            if health.status_code == 200 and "/api/v1/auth/login" in paths:
                return candidate
        except requests.exceptions.RequestException:
            continue
    return "http://127.0.0.1:8000"


API_BASE_URL = resolve_api_base_url()

PREDICT_URL = f"{API_BASE_URL}/api/v1/risk/predict"
ESP_TELEMETRY_URL = f"{API_BASE_URL}/api/v1/telemetry/esp"
SIMULATE_URL = f"{API_BASE_URL}/api/v1/simulate"
SUMMARY_URL = f"{API_BASE_URL}/api/v1/dashboard/summary"
RANKING_URL = f"{API_BASE_URL}/api/v1/dashboard/ranking"
REGION_RISK_URL = f"{API_BASE_URL}/api/v1/risk/regions"
EQUIPMENT_RISK_URL = f"{API_BASE_URL}/api/v1/risk/equipment"
TRENDS_URL = f"{API_BASE_URL}/api/v1/dashboard/trends"
ALERTS_URL = f"{API_BASE_URL}/api/v1/dashboard/alerts"
AUDIT_URL = f"{API_BASE_URL}/api/v1/dashboard/audit"
EQUIPMENT_URL = f"{API_BASE_URL}/api/v1/equipment"
EQUIPMENTS_URL = f"{API_BASE_URL}/api/v1/equipments"
FARMS_URL = f"{API_BASE_URL}/api/v1/farms"
POLICIES_URL = f"{API_BASE_URL}/api/v1/policies/alerts"
ML_STATUS_URL = f"{API_BASE_URL}/api/v1/ml/status"
ML_METRICS_URL = f"{API_BASE_URL}/api/v1/ml/metrics"
AUTH_LOGIN_URL = f"{API_BASE_URL}/api/v1/auth/login"
AUTH_ME_URL = f"{API_BASE_URL}/api/v1/auth/me"
ADMIN_USERS_URL = f"{API_BASE_URL}/api/v1/admin/users"
ADMIN_ROLES_URL = f"{API_BASE_URL}/api/v1/admin/roles"
ADMIN_PERMISSIONS_URL = f"{API_BASE_URL}/api/v1/admin/permissions"
ADMIN_FARMS_URL = f"{API_BASE_URL}/api/v1/admin/farms"
ADMIN_EQUIPMENTS_URL = f"{API_BASE_URL}/api/v1/admin/equipments"
IOT_DEVICES_URL = f"{API_BASE_URL}/api/v1/iot/devices"
ADMIN_IOT_DEVICES_URL = f"{API_BASE_URL}/api/v1/admin/iot/devices"


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

        #MainMenu, footer, header {
            visibility: hidden;
        }

        .block-container {
            padding-top: 1.1rem;
            padding-bottom: 2rem;
            max-width: 1680px;
        }

        [data-testid="stSidebar"] .block-container,
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1rem;
        }

        .ag-brand {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            padding: 0.9rem 0.65rem 1.2rem 0.65rem;
            border-bottom: 1px solid rgba(73, 234, 216, 0.14);
            margin-bottom: 0.75rem;
        }

        .ag-logo {
            width: 42px;
            height: 42px;
            display: grid;
            place-items: center;
            border-radius: 12px;
            color: #071016;
            font-weight: 900;
            background: linear-gradient(135deg, var(--ag-green), var(--ag-cyan));
            box-shadow: 0 0 30px rgba(73, 234, 216, 0.32);
        }

        .ag-brand-title {
            font-size: 1.06rem;
            font-weight: 850;
            color: var(--ag-text);
            line-height: 1.1;
        }

        .ag-brand-subtitle {
            color: var(--ag-muted);
            font-size: 0.74rem;
            margin-top: 0.25rem;
        }

        .ag-sompo-card {
            margin-top: 1.25rem;
            border: 1px solid rgba(73, 234, 216, 0.14);
            border-radius: 14px;
            padding: 1rem;
            background:
                radial-gradient(circle at 20% 100%, rgba(49, 233, 129, 0.18), transparent 9rem),
                linear-gradient(180deg, rgba(12, 28, 38, 0.92), rgba(4, 12, 19, 0.96));
            min-height: 160px;
        }

        .ag-sompo-mark {
            color: var(--ag-text);
            font-size: 1.15rem;
            font-weight: 900;
        }

        .ag-sompo-copy {
            color: var(--ag-muted);
            font-size: 0.78rem;
            margin-top: 0.6rem;
            line-height: 1.45;
        }

        .ag-topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 1rem 1.1rem;
            margin-bottom: 1rem;
            border: 1px solid rgba(73, 234, 216, 0.16);
            border-radius: 14px;
            background:
                linear-gradient(135deg, rgba(11, 29, 39, 0.96), rgba(8, 18, 27, 0.92)),
                radial-gradient(circle at 80% 0%, rgba(73, 234, 216, 0.16), transparent 20rem);
            box-shadow: 0 18px 52px rgba(0, 0, 0, 0.24);
        }

        .ag-eyebrow {
            color: var(--ag-cyan);
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 800;
        }

        .ag-page-title {
            font-size: 1.65rem;
            font-weight: 900;
            color: var(--ag-text);
            margin-top: 0.1rem;
        }

        .ag-page-subtitle {
            color: var(--ag-muted);
            font-size: 0.9rem;
            margin-top: 0.16rem;
        }

        .ag-user-pill {
            min-width: 210px;
            display: flex;
            justify-content: flex-end;
            color: var(--ag-muted);
            font-size: 0.86rem;
        }

        .ag-user-pill strong {
            color: var(--ag-text);
        }

        .ag-grid-card {
            position: relative;
            min-height: 105px;
            padding: 1rem;
            border: 1px solid rgba(73, 234, 216, 0.17);
            border-radius: 12px;
            background:
                linear-gradient(180deg, rgba(18, 39, 50, 0.92), rgba(8, 18, 27, 0.95)),
                radial-gradient(circle at 100% 0%, rgba(73, 234, 216, 0.12), transparent 13rem);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035), 0 18px 45px rgba(0, 0, 0, 0.2);
            overflow: hidden;
        }

        .ag-grid-card:after {
            content: "";
            position: absolute;
            right: 0;
            top: 0;
            width: 4px;
            height: 100%;
            background: linear-gradient(180deg, var(--ag-cyan), transparent);
            opacity: 0.6;
        }

        .ag-card-title {
            color: var(--ag-muted);
            font-size: 0.78rem;
            font-weight: 760;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.55rem;
        }

        .ag-card-value {
            color: var(--ag-text);
            font-size: clamp(1.35rem, 3vw, 2.15rem);
            line-height: 1;
            font-weight: 900;
        }

        .ag-card-meta {
            margin-top: 0.55rem;
            color: var(--ag-muted);
            font-size: 0.82rem;
        }

        .ag-delta-up {
            color: var(--ag-green);
            font-weight: 800;
        }

        .ag-delta-warn {
            color: var(--ag-amber);
            font-weight: 800;
        }

        .ag-delta-hot {
            color: #ff6b6b;
            font-weight: 800;
        }

        .ag-section-card {
            border: 1px solid rgba(73, 234, 216, 0.16);
            border-radius: 14px;
            padding: 0.95rem;
            background: linear-gradient(180deg, rgba(12, 28, 38, 0.88), rgba(7, 16, 24, 0.93));
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.2);
            min-height: 100%;
        }

        .ag-section-title {
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: var(--ag-text);
            font-size: 0.98rem;
            font-weight: 850;
            margin-bottom: 0.85rem;
        }

        .ag-link {
            color: var(--ag-cyan);
            font-size: 0.78rem;
            font-weight: 700;
        }

        .ag-alert-row,
        .ag-activity-row,
        .ag-ranking-row {
            border: 1px solid rgba(255, 255, 255, 0.055);
            border-radius: 10px;
            background: rgba(255, 255, 255, 0.035);
            padding: 0.75rem 0.8rem;
            margin-bottom: 0.62rem;
        }

        .ag-alert-title,
        .ag-ranking-title {
            color: var(--ag-text);
            font-size: 0.88rem;
            font-weight: 800;
        }

        .ag-alert-meta,
        .ag-ranking-meta {
            color: var(--ag-muted);
            font-size: 0.76rem;
            margin-top: 0.18rem;
        }

        .ag-progress {
            height: 9px;
            border-radius: 99px;
            background: rgba(255, 255, 255, 0.08);
            overflow: hidden;
            margin-top: 0.45rem;
        }

        .ag-progress-fill {
            height: 100%;
            border-radius: 99px;
            background: linear-gradient(90deg, var(--ag-green), var(--ag-amber), #ff4d4d);
            box-shadow: 0 0 18px rgba(73, 234, 216, 0.24);
        }

        .ag-factor-card {
            text-align: center;
            border: 1px solid rgba(73, 234, 216, 0.14);
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.035);
            padding: 0.9rem 0.7rem;
            min-height: 96px;
        }

        .ag-factor-name {
            color: var(--ag-muted);
            font-size: 0.76rem;
        }

        .ag-factor-value {
            color: var(--ag-text);
            font-size: 1.55rem;
            font-weight: 900;
            margin-top: 0.2rem;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.45rem;
            border-bottom: 1px solid rgba(73, 234, 216, 0.12);
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 9px 9px 0 0;
            color: var(--ag-muted);
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(73, 234, 216, 0.08);
            border-bottom: 0;
        }

        .stTabs [aria-selected="true"] {
            color: var(--ag-cyan);
            background: linear-gradient(180deg, rgba(73, 234, 216, 0.16), rgba(73, 234, 216, 0.04));
            box-shadow: 0 0 24px rgba(73, 234, 216, 0.16);
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
        "auth_permissions": [],
        "login_busy": False,
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
    username = username.strip()
    if not username or not password:
        return False, "Informe usuario e senha."

    try:
        response = requests.post(
            AUTH_LOGIN_URL,
            json={"username": username, "password": password},
            timeout=35,
        )

        if response.status_code == 429:
            time.sleep(2)
            response = requests.post(
                AUTH_LOGIN_URL,
                json={"username": username, "password": password},
                timeout=35,
            )
            if response.status_code == 429:
                return False, "Servidor ocupado por alguns segundos. Aguarde e tente entrar novamente."

        if response.status_code == 404:
            return False, f"Endpoint de login nao encontrado em {API_BASE_URL}. Reinicie o dashboard ou ajuste API_BASE_URL para http://127.0.0.1:8001."

        if response.status_code != 200:
            try:
                data = response.json()
                return False, data.get("detail", "Falha no login")
            except Exception:
                return False, "Nao foi possivel autenticar agora. Tente novamente em alguns segundos."

        login_data = response.json()
        token = login_data.get("access_token")
        if not token:
            return False, "Login sem token retornado pela API."

        st.session_state["auth_token"] = token
        st.session_state["auth_user"] = login_data.get("username", username)
        st.session_state["auth_role"] = login_data.get("role", "operador")
        st.session_state["auth_full_name"] = login_data.get("username", username)
        st.session_state["auth_email"] = None
        st.session_state["auth_permissions"] = login_data.get("permissions", [])

        ok_me, me_data = get_json(AUTH_ME_URL)
        if ok_me and isinstance(me_data, dict):
            st.session_state["auth_role"] = me_data.get("role", st.session_state["auth_role"])
            st.session_state["auth_full_name"] = me_data.get("full_name", st.session_state["auth_full_name"])
            st.session_state["auth_email"] = me_data.get("email")
            st.session_state["auth_permissions"] = me_data.get("permissions", st.session_state["auth_permissions"])

        return True, "Login realizado com sucesso."

    except requests.exceptions.Timeout:
        return False, "A API demorou para responder. Aguarde alguns segundos e tente novamente."
    except requests.exceptions.RequestException as exc:
        return False, f"Conexao com a API indisponivel em {API_BASE_URL}. Inicie o backend ou ajuste API_BASE_URL. Detalhe: {exc}"


def logout_user() -> None:
    st.session_state["auth_token"] = None
    st.session_state["auth_user"] = None
    st.session_state["auth_role"] = None
    st.session_state["auth_full_name"] = None
    st.session_state["auth_email"] = None
    st.session_state["auth_permissions"] = []
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


def post_json(url: str, payload: dict, extra_headers: dict[str, str] | None = None) -> tuple[bool, Any]:
    try:
        headers = get_auth_headers()
        if extra_headers:
            headers.update(extra_headers)
        response = requests.post(
            url,
            json=payload,
            headers=headers,
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


def put_json(url: str, payload: dict, extra_headers: dict[str, str] | None = None) -> tuple[bool, Any]:
    try:
        headers = get_auth_headers()
        if extra_headers:
            headers.update(extra_headers)
        response = requests.put(
            url,
            json=payload,
            headers=headers,
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


def delete_json(url: str) -> tuple[bool, Any]:
    try:
        response = requests.delete(url, headers=get_auth_headers(), timeout=30)
        if response.status_code in (200, 202, 204):
            if response.text:
                return True, response.json()
            return True, {"status": "ok"}
        try:
            return False, response.json()
        except Exception:
            return False, {"detail": response.text, "status_code": response.status_code}
    except requests.exceptions.RequestException as e:
        return False, {"detail": str(e), "status_code": 500}


def any_to_dataframe(data: Any) -> pd.DataFrame:
    return localize_time_columns(_any_to_dataframe_utc(data))


def _any_to_dataframe_utc(data: Any) -> pd.DataFrame:
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


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def format_measurement(value: Any, unit: str, precision: int = 1) -> str:
    if value is None:
        return "N/D"
    try:
        return f"{float(value):.{precision}f} {unit}".strip()
    except (TypeError, ValueError):
        return "N/D"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def has_permission(permission: str) -> bool:
    return permission in set(st.session_state.get("auth_permissions") or [])


def has_any_permission(*permissions: str) -> bool:
    user_permissions = set(st.session_state.get("auth_permissions") or [])
    return any(permission in user_permissions for permission in permissions)


def format_compact_number(value: Any) -> str:
    number = safe_float(value)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M".replace(".", ",")
    if number >= 1_000:
        return f"{number / 1_000:.1f}k".replace(".", ",")
    if number == int(number):
        return f"{int(number):,}".replace(",", ".")
    return f"{number:.1f}".replace(".", ",")


def format_currency(value: Any) -> str:
    number = safe_float(value)
    if number >= 1_000_000:
        return f"R$ {number / 1_000_000:.1f}M".replace(".", ",")
    if number >= 1_000:
        return f"R$ {number / 1_000:.1f}k".replace(".", ",")
    return f"R$ {number:,.0f}".replace(",", ".")


# Premissa ilustrativa usada apenas nas estimativas de impacto da Visao Geral.
AVERAGE_CLAIM_COST_BRL = 32800


def render_sidebar_brand() -> None:
    st.sidebar.markdown(
        """
        <div class="ag-brand">
            <div class="ag-logo">AG</div>
            <div>
                <div class="ag-brand-title">AgroGuardian AI</div>
                <div class="ag-brand-subtitle">Prevencao de Sinistros Agricolas</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_topbar(title: str, subtitle: str) -> None:
    user = st.session_state.get("auth_user") or "-"
    role = st.session_state.get("auth_role") or "-"
    st.markdown(
        f"""
        <div class="ag-topbar">
            <div>
                <div class="ag-eyebrow">AgroGuardian Command Center</div>
                <div class="ag-page-title">{title}</div>
                <div class="ag-page-subtitle">{subtitle}</div>
            </div>
            <div class="ag-user-pill">
                <div><strong>{user}</strong><br>{role}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(title: str, value: str, meta: str, delta: str = "", tone: str = "up") -> None:
    delta_class = {
        "up": "ag-delta-up",
        "warn": "ag-delta-warn",
        "hot": "ag-delta-hot",
    }.get(tone, "ag-delta-up")
    delta_html = f' <span class="{delta_class}">{delta}</span>' if delta else ""
    st.markdown(
        f"""
        <div class="ag-grid-card">
            <div class="ag-card-title">{title}</div>
            <div class="ag-card-value">{value}</div>
            <div class="ag-card-meta">{meta}{delta_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Navegacao lateral, fazenda atual e atalhos entre paginas
# ---------------------------------------------------------------------------
NAV_GROUPS_BASE = [
    (
        "Monitoramento",
        [
            ("Visão Geral", None),
            ("Operação em tempo real", None),
            ("Telemetria", ("telemetry.view",)),
            ("Alertas e auditoria", ("audit.view", "alerts.view")),
            ("Equipamentos", ("equipments.view",)),
        ],
    ),
    (
        "Analise",
        [
            ("Resumo executivo", None),
            ("Ranking", None),
            ("Risco regional", None),
            ("Tendências", None),
            ("Simulador de risco", None),
            ("IA e ML", None),
        ],
    ),
]
# Fora das paginas da fazenda selecionada: pertence ao usuario logado.
NAV_ADMIN_GROUP = (
    "Conta e administracao",
    [
        ("Políticas de alerta", ("alerts.manage", "settings.manage")),
        ("Administracao", ("users.view",)),
    ],
)
NAV_DISPLAY = {"Administracao": "Administração", "Políticas de alerta": "Políticas de alerta"}
PAGE_SUBTITLES = {
    "Visão Geral": "Painel completo de gestao de riscos agricolas.",
    "Operação em tempo real": "Simule entradas e calcule o risco operacional.",
    "Telemetria": "Leituras do ESP32, movimento do trator e conectividade.",
    "Alertas e auditoria": "Alertas gerados e trilha de auditoria.",
    "Equipamentos": "Fazendas, equipamentos e dispositivos IoT.",
    "Resumo executivo": "Indicadores consolidados para a Sompo.",
    "Ranking": "Equipamentos ordenados por risco.",
    "Risco regional": "Risco agregado por regiao.",
    "Tendências": "Evolucao do risco ao longo do tempo.",
    "Simulador de risco": "Teste cenarios sem afetar os dados reais.",
    "IA e ML": "Modelos, metricas e explicabilidade.",
    "Políticas de alerta": "Regras que geram alertas (valem para o usuario logado).",
    "Administracao": "Usuarios, perfis e permissoes (valem para o usuario logado).",
}
NAV_CSS = """
<style>
.ag-nav-group{font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;color:#7fb7b0;margin:.85rem 0 .3rem}
.ag-nav-admin{border-top:1px solid rgba(255,200,87,.4);margin-top:1.1rem;padding-top:.65rem;color:#ffc857;
font-size:.7rem;letter-spacing:.14em;text-transform:uppercase}
.ag-nav-admin small{display:block;letter-spacing:0;text-transform:none;color:#9aa9ad;font-size:.72rem;margin-top:.15rem}
[class*="st-key-nav_"] button,[class*="st-key-navadm_"] button{justify-content:flex-start;text-align:left;
min-height:2.05rem;padding:.3rem .7rem}
[class*="st-key-navadm_"] button{border-left:3px solid #ffc857}
[class*="st-key-nav_"] button[data-testid="stBaseButton-secondary"],[class*="st-key-navadm_"] button[data-testid="stBaseButton-secondary"]{
background:rgba(16,36,44,.7);color:#cfe3e6;box-shadow:none;border:1px solid rgba(73,234,216,.14);font-weight:600}
[class*="st-key-nav_"] button[data-testid="stBaseButton-secondary"]:hover,[class*="st-key-navadm_"] button[data-testid="stBaseButton-secondary"]:hover{
background:rgba(73,234,216,.14);color:#ffffff;border:1px solid rgba(73,234,216,.4)}
.stButton > button[data-testid="stBaseButton-tertiary"]{background:none;box-shadow:none;color:#49ead8;font-weight:700;border:0}
.stButton > button[data-testid="stBaseButton-tertiary"]:hover{color:#ffffff;background:rgba(73,234,216,.1)}
[data-testid="stPopover"] button,button[data-testid="stPopoverButton"]{background:rgba(16,36,44,.95);color:#e8f1f2;
border:1px solid rgba(73,234,216,.35);box-shadow:none}
.ag-farm-card{border:1px solid rgba(73,234,216,.28);border-radius:10px;padding:.6rem .75rem;margin:.5rem 0 .4rem;
background:linear-gradient(180deg, rgba(16,36,44,.95), rgba(8,18,23,.95))}
.ag-farm-eyebrow{font-size:.68rem;letter-spacing:.12em;text-transform:uppercase;color:#7fb7b0}
.ag-farm-name{font-size:1.02rem;font-weight:700;color:#e8f1f2;overflow-wrap:anywhere}
.ag-farm-meta{font-size:.74rem;color:#8fa3a8;overflow-wrap:anywhere}
</style>
"""
ALL_FARMS_LABEL = "Todas as fazendas"


def go_to_page(page: str) -> None:
    """Callback de botoes: troca a pagina ativa do menu lateral."""
    st.session_state["nav_page"] = page


def restore_kept_widgets() -> None:
    """Preserva widgets com chave 'keep_*' ao trocar de pagina.

    O Streamlit descarta o estado de widgets que nao foram desenhados na execucao;
    sem isto, filtros e colunas escolhidos se perderiam ao navegar entre paginas.
    """
    kept = st.session_state.setdefault("_kept_widgets", {})
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith("keep_"):
            kept[key] = st.session_state[key]
    for key, value in kept.items():
        if key not in st.session_state:
            st.session_state[key] = value


def sanitize_choice_state(key: str, options: list, multiple: bool = False) -> None:
    """Remove valores guardados que nao existem mais nas opcoes (evita erro do Streamlit)."""
    if key not in st.session_state:
        return
    value = st.session_state[key]
    if multiple:
        st.session_state[key] = [item for item in (value or []) if item in options]
    elif value not in options:
        del st.session_state[key]


def build_nav_groups() -> tuple[list[tuple[str, list[str]]], list[str]]:
    def allowed(permissions: tuple[str, ...] | None) -> bool:
        return permissions is None or has_any_permission(*permissions)

    groups = []
    for title, items in NAV_GROUPS_BASE:
        pages = [name for name, permissions in items if allowed(permissions)]
        if pages:
            groups.append((title, pages))
    admin_pages = [name for name, permissions in NAV_ADMIN_GROUP[1] if allowed(permissions)]
    return groups, admin_pages


def render_sidebar_navigation() -> str:
    groups, admin_pages = build_nav_groups()
    available = [page for _, pages in groups for page in pages] + admin_pages
    st.session_state["_available_pages"] = available
    active = st.session_state.get("nav_page")
    if active not in available:
        active = available[0]
        st.session_state["nav_page"] = active

    st.sidebar.markdown(NAV_CSS, unsafe_allow_html=True)
    for title, pages in groups:
        st.sidebar.markdown(f'<div class="ag-nav-group">{title}</div>', unsafe_allow_html=True)
        for page in pages:
            st.sidebar.button(
                NAV_DISPLAY.get(page, page),
                key=f"nav_{page}",
                use_container_width=True,
                type="primary" if page == active else "secondary",
                on_click=go_to_page,
                args=(page,),
            )
    if admin_pages:
        st.sidebar.markdown(
            f'<div class="ag-nav-admin">{NAV_ADMIN_GROUP[0]}<small>Vale para o usuario logado, '
            "nao para a fazenda selecionada.</small></div>",
            unsafe_allow_html=True,
        )
        for page in admin_pages:
            st.sidebar.button(
                NAV_DISPLAY.get(page, page),
                key=f"navadm_{page}",
                use_container_width=True,
                type="primary" if page == active else "secondary",
                on_click=go_to_page,
                args=(page,),
            )
    return active


def _as_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def render_sidebar_farm_selector() -> None:
    """Campo fixo com a fazenda visualizada; quem tem mais de uma pode alternar (ou ver todas)."""
    from html import escape

    ok_farms, farms = get_json(FARMS_URL)
    ok_equipment, equipments = get_json(EQUIPMENTS_URL)
    farm_rows = [row for row in farms if isinstance(row, dict)] if ok_farms and isinstance(farms, list) else []
    equipment_rows = (
        [row for row in equipments if isinstance(row, dict)] if ok_equipment and isinstance(equipments, list) else []
    )

    def _farm_id(row: dict) -> int | None:
        return _as_int(row.get("farm_id", row.get("id")))

    def _farm_name(row: dict) -> str:
        return str(row.get("farm_name") or row.get("name") or f"Fazenda {_farm_id(row)}")

    if not farm_rows and equipment_rows:
        seen: dict[int, dict] = {}
        for item in equipment_rows:
            farm_key = _as_int(item.get("farm_id"))
            if farm_key is not None and farm_key not in seen:
                seen[farm_key] = {"farm_id": farm_key, "farm_name": item.get("farm_name")}
        farm_rows = list(seen.values())

    # Quem so enxerga parte dos equipamentos (escopo de acesso) so ve as fazendas desses equipamentos.
    is_admin = str(st.session_state.get("auth_role") or "").upper() == "ADMIN"
    equipment_farm_ids = {_as_int(item.get("farm_id")) for item in equipment_rows} - {None}
    if is_admin or not ok_equipment:
        accessible = farm_rows
    else:
        accessible = [row for row in farm_rows if _farm_id(row) in equipment_farm_ids]

    labels = {f"{_farm_name(row)} (ID {_farm_id(row)})": row for row in accessible if _farm_id(row) is not None}
    options = list(labels)
    if len(options) > 1:
        options = [ALL_FARMS_LABEL] + options

    chosen = ALL_FARMS_LABEL
    if len(options) > 1:
        sanitize_choice_state("keep_farm_select", options)
        with st.sidebar:
            st.markdown('<div class="ag-farm-eyebrow">Fazenda visualizada</div>', unsafe_allow_html=True)
            chosen = st.selectbox(
                "Fazenda visualizada",
                options,
                key="keep_farm_select",
                label_visibility="collapsed",
                help="Filtra as paginas de monitoramento e analise pela fazenda escolhida.",
            )
    elif len(options) == 1:
        chosen = options[0]
    else:
        chosen = ""

    selected_row = labels.get(chosen)
    if selected_row is not None:
        farm_id = _farm_id(selected_row)
        farm_equipment = [item for item in equipment_rows if _as_int(item.get("farm_id")) == farm_id]
        ctx = {
            "farm_id": farm_id,
            "farm_name": _farm_name(selected_row),
            "equipment_ids": {_as_int(item.get("equipment_id", item.get("id"))) for item in farm_equipment} - {None},
            "equipment_names": {
                str(item.get("equipment_name") or item.get("name")) for item in farm_equipment if item.get("name")
            },
        }
        region = selected_row.get("region") or ""
        meta = " | ".join(part for part in (str(region) if region else "", f"{len(farm_equipment)} equipamento(s)") if part)
        title, subtitle = _farm_name(selected_row), meta
    else:
        ctx = {"farm_id": None, "farm_name": ALL_FARMS_LABEL, "equipment_ids": set(), "equipment_names": set()}
        count = len(accessible)
        title = ALL_FARMS_LABEL if accessible else "Nenhuma fazenda disponivel"
        subtitle = f"{count} fazenda(s) com acesso" if accessible else ""
    st.session_state["_farm_ctx"] = ctx
    st.sidebar.markdown(
        f'<div class="ag-farm-card"><div class="ag-farm-eyebrow">Fazenda atual</div>'
        f'<div class="ag-farm-name">{escape(title)}</div><div class="ag-farm-meta">{escape(subtitle)}</div></div>',
        unsafe_allow_html=True,
    )


def row_in_selected_farm(row: dict, kind: str = "auto") -> bool:
    ctx = st.session_state.get("_farm_ctx") or {}
    farm_id = ctx.get("farm_id")
    if farm_id is None:
        return True
    if kind == "farm":
        row_farm = _as_int(row.get("farm_id", row.get("id")))
        return row_farm is None or row_farm == farm_id
    if row.get("farm_id") is not None:
        return _as_int(row.get("farm_id")) == farm_id
    if row.get("equipment_id") is not None:
        return _as_int(row.get("equipment_id")) in (ctx.get("equipment_ids") or set())
    name = row.get("equipment_name") or row.get("equipment")
    if name is not None and ctx.get("equipment_names"):
        return str(name) in ctx["equipment_names"]
    if row.get("farm_name"):
        return row.get("farm_name") == ctx.get("farm_name")
    return True


def filter_rows_by_farm(rows: Any, kind: str = "auto") -> Any:
    if not isinstance(rows, list):
        return rows
    return [row for row in rows if not isinstance(row, dict) or row_in_selected_farm(row, kind)]


def filter_df_by_farm(df: pd.DataFrame, kind: str = "auto") -> pd.DataFrame:
    ctx = st.session_state.get("_farm_ctx") or {}
    if df.empty or ctx.get("farm_id") is None:
        return df
    mask = df.apply(lambda row: row_in_selected_farm(row.to_dict(), kind), axis=1)
    return df[mask]


def selected_farm_caption() -> str:
    ctx = st.session_state.get("_farm_ctx") or {}
    return ctx.get("farm_name") or ""


PERMISSION_GROUP_LABELS = {
    "users": "Usuarios",
    "roles": "Perfis",
    "farms": "Fazendas",
    "equipments": "Equipamentos",
    "telemetry": "Telemetria",
    "alerts": "Alertas",
    "audit": "Auditoria",
    "risk": "Risco",
    "settings": "Configuracoes",
    "ml": "IA e ML",
    "iot": "Dispositivos IoT",
    "policies": "Politicas",
}


def render_permission_checklist(
    title: str,
    key_prefix: str,
    options: list[str],
    descriptions: dict[str, str],
    selected: list[str] | None = None,
    help_text: str = "",
) -> list[str]:
    """Lista de permissoes em caixas de marcacao, agrupadas, recolhivel e com descricao de cada uma."""
    selected_set = set(selected or [])
    chosen: list[str] = []
    label = f"{title} ({len(selected_set)} marcada(s) ao abrir)" if selected_set else title
    with st.expander(label, expanded=False):
        if help_text:
            st.caption(help_text)
        if not options:
            st.info("Nenhuma permissao disponivel (verifique sua permissao para listar).")
        groups: dict[str, list[str]] = {}
        for code in options:
            groups.setdefault(str(code).split(".")[0], []).append(code)
        for group, codes in groups.items():
            st.markdown(f"**{PERMISSION_GROUP_LABELS.get(group, group.title())}**")
            for code in codes:
                if st.checkbox(code, value=code in selected_set, key=f"{key_prefix}_{code}"):
                    chosen.append(code)
                description = descriptions.get(code)
                if description:
                    st.caption(description)
    return chosen



def begin_section(title: str, link: str = "", target: str = "") -> None:
    """Titulo de secao; com `target`, o link vira um botao que leva direto a pagina correspondente."""
    link_html = ""
    if link and target:
        if target in (st.session_state.get("_available_pages") or []):
            title_col, link_col = st.columns([0.66, 0.34], vertical_alignment="center")
            with title_col:
                st.markdown(
                    f"""
                    <div class="ag-section-card">
                        <div class="ag-section-title"><span>{title}</span></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with link_col:
                st.button(
                    f"{link} →",
                    key=f"goto_{target}_{title}",
                    on_click=go_to_page,
                    args=(target,),
                    type="tertiary",
                    use_container_width=True,
                )
            return
    elif link:
        link_html = f'<span class="ag-link">{link}</span>'
    st.markdown(
        f"""
        <div class="ag-section-card">
            <div class="ag-section-title"><span>{title}</span>{link_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def end_section() -> None:
    return None


def render_alert_cards(alerts_data: Any, limit: int = 4) -> None:
    alerts = alerts_data if isinstance(alerts_data, list) else []
    if not alerts:
        st.info("Nenhum alerta recente.")
        return

    for alert in alerts[:limit]:
        severity = str(alert.get("severity", "low")).lower()
        tone = "hot" if severity == "high" else "warn" if severity == "medium" else ""
        title = str(alert.get("type", "alerta")).replace("_", " ").title()
        message = alert.get("message", "-")
        timestamp = format_local_time(alert.get("timestamp"), "%Y-%m-%d %H:%M", default="")
        st.markdown(
            f"""
            <div class="ag-alert-row">
                <div class="ag-chip-row"><span class="ag-chip {tone}">{severity}</span><span class="ag-chip">{timestamp}</span></div>
                <div class="ag-alert-title">{title}</div>
                <div class="ag-alert-meta">{message}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_ranking_cards(ranking_data: Any, limit: int = 5) -> None:
    rows = ranking_data if isinstance(ranking_data, list) else []
    if not rows:
        st.info("Sem ranking disponivel.")
        return

    for index, row in enumerate(rows[:limit], start=1):
        score = safe_float(row.get("risk_score", row.get("avg_risk_score")))
        width = max(6, min(100, score))
        st.markdown(
            f"""
            <div class="ag-ranking-row">
                <div class="ag-ranking-title">{index}. {row.get("equipment_name", "-")}</div>
                <div class="ag-ranking-meta">{row.get("equipment_type", "-")} | {row.get("risk_label", row.get("latest_risk_label", "-"))} | score {score:.1f}</div>
                <div class="ag-progress"><div class="ag-progress-fill" style="width:{width}%"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_factor_cards(metrics_data: Any) -> None:
    weights = {}
    if isinstance(metrics_data, dict):
        tree = metrics_data.get("tree_search", {})
        weights = tree.get("feature_weights", {}) if isinstance(tree, dict) else {}

    if not weights:
        weights = {
            "velocidade": 23.49,
            "chuva_mm": 21.35,
            "solo_instavel": 13.25,
            "inclinacao": 11.42,
        }

    labels = {
        "velocidade": "Velocidade",
        "chuva_mm": "Chuva intensa",
        "solo_instavel": "Solo instavel",
        "inclinacao": "Inclinacao",
        "historico_sinistros": "Historico",
        "distancia_agua": "Proximidade da agua",
        "temperatura_c": "Temperatura",
        "umidade_ar": "Umidade do ar",
        "pressao_hpa": "Pressao",
        "distancia_obstaculo": "Obstaculo",
        "gps_accuracy_m": "Precisao GPS",
    }

    top = list(weights.items())[:5]
    cols = st.columns(len(top))
    for col, (name, value) in zip(cols, top):
        with col:
            st.markdown(
                f"""
                <div class="ag-factor-card">
                    <div class="ag-factor-name">{labels.get(name, name)}</div>
                    <div class="ag-factor-value">{safe_float(value):.0f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_overview_dashboard() -> None:
    ok_summary, summary_data = get_json(SUMMARY_URL)
    ok_trends, trends_data = get_json(TRENDS_URL)
    ok_ranking, ranking_data = get_json(EQUIPMENT_RISK_URL)
    if not ok_ranking:
        ok_ranking, ranking_data = get_json(RANKING_URL)
    ok_region_risk, region_risk_data = get_json(REGION_RISK_URL)
    ok_alerts, alerts_data = get_json(ALERTS_URL)
    ok_farms, farms_data = get_json(FARMS_URL)
    ok_metrics, metrics_data = get_json(ML_METRICS_URL)
    # Ranking e alertas seguem a fazenda selecionada; os KPIs vem agregados do servidor.
    ranking_data = filter_rows_by_farm(ranking_data) if ok_ranking else ranking_data
    alerts_data = filter_rows_by_farm(alerts_data) if ok_alerts else alerts_data

    summary = summary_data if ok_summary and isinstance(summary_data, dict) else {}
    total_predictions = safe_int(summary.get("total_predictions"))
    avg_risk = safe_float(summary.get("avg_risk_score"))
    high_risk = safe_int(summary.get("high_risk_predictions"))
    medium_risk = safe_int(summary.get("medium_risk_predictions"))
    low_risk = safe_int(summary.get("low_risk_predictions"))
    potential_claims = max(0, high_risk * 2 + medium_risk)
    estimated_savings = potential_claims * AVERAGE_CLAIM_COST_BRL

    kpi_cols = st.columns(5)
    with kpi_cols[0]:
        render_metric_card("Total de previsoes", format_compact_number(total_predictions), "acumuladas")
    with kpi_cols[1]:
        render_metric_card("Risco medio", f"{avg_risk:.0f}/100", "nivel operacional", "medio" if avg_risk >= 41 else "baixo", "warn")
    with kpi_cols[2]:
        render_metric_card("Alertas criticos", format_compact_number(high_risk), "alto risco detectado", "", "hot")
    with kpi_cols[3]:
        render_metric_card("Sinistros potenciais", format_compact_number(potential_claims), "estimativa ilustrativa")
    with kpi_cols[4]:
        render_metric_card("Economia estimada", format_currency(estimated_savings), "estimativa ilustrativa")

    if (st.session_state.get("_farm_ctx") or {}).get("farm_id") is not None:
        st.caption(
            "Indicadores acima consideram todas as fazendas; ranking e alertas mostram so a fazenda "
            f"{selected_farm_caption()}."
        )

    left, middle, right = st.columns([1.08, 1.62, 0.92])

    with left:
        begin_section("Distribuicao de risco")
        risk_rows = pd.DataFrame(
            {
                "Nivel": ["Baixo", "Medio", "Alto"],
                "Previsoes": [low_risk, medium_risk, high_risk],
            }
        )
        if risk_rows["Previsoes"].sum() == 0:
            risk_rows["Previsoes"] = [45, 35, 20]

        donut = (
            alt.Chart(risk_rows)
            .mark_arc(innerRadius=58, outerRadius=96, cornerRadius=4)
            .encode(
                theta=alt.Theta("Previsoes:Q"),
                color=alt.Color(
                    "Nivel:N",
                    scale=alt.Scale(
                        domain=["Baixo", "Medio", "Alto"],
                        range=["#31e981", "#ffd166", "#ff4d4d"],
                    ),
                    legend=alt.Legend(orient="right", title=None),
                ),
                tooltip=["Nivel:N", "Previsoes:Q"],
            )
            .properties(height=255)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(donut, use_container_width=True)
        st.caption(f"{format_compact_number(total_predictions)} previsoes acumuladas")
        end_section()

        begin_section("Ranking de equipamentos", "Ver ranking", target="Ranking")
        render_ranking_cards(ranking_data if ok_ranking else [])
        end_section()

    with middle:
        top_mid_1, top_mid_2 = st.columns([0.9, 1.15])
        with top_mid_1:
            begin_section("Tendencia de risco")
            trend_df = any_to_dataframe(trends_data if ok_trends else [])
            if not trend_df.empty:
                date_col = "date" if "date" in trend_df.columns else trend_df.columns[0]
                numeric_cols = trend_df.select_dtypes(include=["number"]).columns.tolist()
                risk_col = "avg_risk" if "avg_risk" in trend_df.columns else numeric_cols[0] if numeric_cols else None
                if risk_col:
                    trend_plot = trend_df[[date_col, risk_col]].copy()
                    trend_plot.columns = ["Data", "Risco"]
                    line = (
                        alt.Chart(trend_plot)
                        .mark_line(point=True, color="#28e8ff", strokeWidth=3)
                        .encode(x=alt.X("Data:N", title=None), y=alt.Y("Risco:Q", title=None), tooltip=["Data:N", "Risco:Q"])
                        .properties(height=250)
                    )
                    st.altair_chart(line, use_container_width=True)
                else:
                    st.info("Tendencia sem coluna numerica.")
            else:
                st.info("Sem tendencia disponivel.")
            end_section()

        with top_mid_2:
            begin_section("Risk Map")
            farm_rows = farms_data if ok_farms and isinstance(farms_data, list) else []
            if farm_rows:
                map_df = pd.DataFrame(farm_rows).rename(columns={"latitude": "lat", "longitude": "lon"})
                region_rows = region_risk_data if ok_region_risk and isinstance(region_risk_data, list) else []
                risk_by_region = {row.get("region"): safe_float(row.get("risk_score")) for row in region_rows}
                map_df["risk"] = map_df["region"].map(risk_by_region).fillna(45)
            else:
                map_df = pd.DataFrame(
                    [
                        {"lat": -23.455, "lon": -46.533, "farm_name": "Fazenda Modelo", "risk": 72},
                        {"lat": -23.520, "lon": -46.187, "farm_name": "Vista Verde", "risk": 48},
                        {"lat": -23.480, "lon": -46.420, "farm_name": "Boa Vista", "risk": 64},
                    ]
                )

            map_df["color"] = map_df["risk"].apply(
                lambda score: [255, 77, 77, 190] if score >= 70 else [255, 209, 102, 190] if score >= 41 else [49, 233, 129, 190]
            )
            view_state = pdk.ViewState(
                latitude=float(map_df["lat"].mean()),
                longitude=float(map_df["lon"].mean()),
                zoom=9,
                pitch=0,
            )
            layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position="[lon, lat]",
                get_fill_color="color",
                get_radius=900,
                pickable=True,
            )
            st.pydeck_chart(
                pdk.Deck(initial_view_state=view_state, layers=[layer], tooltip={"text": "{farm_name}\\nRisco: {risk}"}),
                use_container_width=True,
            )
            st.markdown('<div class="ag-chip-row"><span class="ag-chip">Baixo risco</span><span class="ag-chip warn">Medio risco</span><span class="ag-chip hot">Alto risco</span></div>', unsafe_allow_html=True)
            end_section()

        begin_section("Estimativa de impacto")
        st.markdown(
            f'<div class="ag-chip-row"><span class="ag-chip">Economia estimada</span><span class="ag-chip">{format_currency(estimated_savings)}</span></div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Estimativa ilustrativa, nao e resultado medido. Premissas: cada previsao de alto risco "
            f"equivale a 2 sinistros potenciais, cada previsao de medio risco a 1, e o custo medio "
            f"por sinistro e {format_currency(AVERAGE_CLAIM_COST_BRL)}."
        )
        end_section()

    with right:
        begin_section("Alertas recentes", "Ver todos", target="Alertas e auditoria")
        render_alert_cards(alerts_data if ok_alerts else [])
        end_section()

        begin_section("Status do modelo")
        tree = metrics_data.get("tree_search", {}) if ok_metrics and isinstance(metrics_data, dict) else {}
        classification = tree.get("classification_at_70", {}) if isinstance(tree, dict) else {}
        st.markdown(
            f"""
            <div class="ag-alert-row">
                <div class="ag-chip-row"><span class="ag-chip">Ativo</span><span class="ag-chip">{metrics_data.get("recommended_model", "-") if isinstance(metrics_data, dict) else "-"}</span></div>
                <div class="ag-alert-title">Motor de decisao operacional</div>
                <div class="ag-alert-meta">Accuracy {safe_float(classification.get("accuracy")) * 100:.1f}% | F1 {safe_float(classification.get("f1")) * 100:.1f}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        end_section()

    begin_section("Fatores de risco mais frequentes")
    render_factor_cards(metrics_data if ok_metrics else {})
    end_section()


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
    st.write(f"Pressao: **{weather.get('pressure_hpa', '-')} hPa**")
    st.write(f"Vento: **{weather.get('wind_speed', '-')} m/s**")
    st.write(f"Chuva (1h): **{weather.get('rain_mm_1h', '-')} mm**")

    if weather.get("error"):
        st.warning("Clima externo indisponível. O sistema aplicou fallback automático.")

    st.subheader("Resumo executivo da IA")
    st.subheader("Composição do score")
    risk_components = resultado.get("risk_components", {})
    if risk_components and isinstance(risk_components, dict):
        rc1, rc2, rc3, rc4, rc5 = st.columns(5)
        rc1.metric("Score do modelo", risk_components.get("model_risk_score", "-"))
        rc2.metric("Risco geográfico", risk_components.get("geo_risk_points", "-"))
        rc3.metric("Risco sensores", risk_components.get("sensor_risk_points", "-"))
        rc4.metric("Score bruto", risk_components.get("uncapped_final_score", "-"))
        rc5.metric("Score final", risk_components.get("final_risk_score", "-"))
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
        precision = geo_context.get("precision", {})
        if precision:
            st.write(f"**Fonte geo:** {precision.get('water_source', '-')} | **Precisao GPS:** {precision.get('estimated_gps_accuracy_m', '-')} m")
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

    structured = resultado.get("explainable_ai", {})
    if structured and isinstance(structured, dict):
        st.subheader("Explicabilidade estruturada")
        st.info(structured.get("summary", "Sem resumo estruturado."))
        sx1, sx2, sx3 = st.columns(3)
        sx1.metric("Confianca", structured.get("confidence_score", "-"))
        sx2.metric("Telemetria", structured.get("telemetry_status", "-"))
        sx3.metric("Qualidade", structured.get("data_quality_status", "-"))
        factors = structured.get("factors", [])
        if factors:
            st.dataframe(any_to_dataframe(factors), use_container_width=True)
        issues = structured.get("data_quality_issues") or []
        if issues:
            st.warning(" | ".join(str(item) for item in issues))

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

render_sidebar_brand()
restore_kept_widgets()

if not st.session_state.get("auth_token"):
    st.sidebar.subheader("Acesso seguro")
    with st.sidebar.form("login_form"):
        login_username = st.text_input("Usuário", key="login_username")
        login_password = st.text_input("Senha", type="password", key="login_password")
        submitted_login = st.form_submit_button(
            "Entrar",
            disabled=bool(st.session_state.get("login_busy")),
        )

    if submitted_login and not st.session_state.get("login_busy"):
        st.session_state["login_busy"] = True
        with st.sidebar:
            with st.spinner("Entrando..."):
                ok, msg = login_user(login_username, login_password)
        st.session_state["login_busy"] = False
        if ok:
            st.sidebar.success(msg)
            st.rerun()
        else:
            st.sidebar.error(msg)

    render_topbar("Acesso Seguro", "Entre para acessar o centro de decisao agricola.")
    st.warning("Faça login para acessar o dashboard seguro.")
    st.stop()
else:
    render_sidebar_farm_selector()
    active_page = render_sidebar_navigation()
    st.sidebar.divider()
    st.sidebar.markdown(
        f'<div style="font-size:.78rem;color:#9fb3b8">Logado como <b style="color:#e8f1f2">{_html_escape(str(st.session_state.get("auth_user")))}</b> '
        f'({_html_escape(str(st.session_state.get("auth_role")))})<br>{_html_escape(str(st.session_state.get("auth_full_name") or ""))}</div>',
        unsafe_allow_html=True,
    )
    if st.sidebar.button("Sair", key="btn_logout"):
        logout_user()

st.sidebar.markdown(
    """
    <div class="ag-sompo-card">
        <div class="ag-sompo-mark">SOMPO</div>
        <div class="ag-sompo-copy">Tecnologia e inovacao para um agro mais seguro, com IA operacional e prevencao de sinistros.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

from html import escape as _escape_html  # noqa: E402

_farm_name_for_topbar = selected_farm_caption()
_subtitle = PAGE_SUBTITLES.get(active_page, "")
if active_page not in {name for name, _ in NAV_ADMIN_GROUP[1]} and _farm_name_for_topbar:
    _subtitle = f"{_subtitle} Fazenda: {_escape_html(_farm_name_for_topbar)}."
render_topbar(NAV_DISPLAY.get(active_page, active_page), _subtitle)

user_role = str(st.session_state.get("auth_role", "OPERADOR")).upper()

if active_page == "Visão Geral":
    render_overview_dashboard()

if active_page == "Operação em tempo real":
    with st.expander("Dados da operação (simulados)", expanded=True):
        st.caption("Entradas manuais usadas para calcular o risco nesta tela.")

        equipment_id = st.number_input("ID do equipamento", min_value=1, value=1, step=1)
        farm_id = st.number_input("ID da fazenda", min_value=1, value=1, step=1)
        region = st.text_input("Região", value="Guarulhos - SP")
        operation_type = st.selectbox(
            "Tipo de operação",
            ["campo", "transporte", "proximidade_agua"],
        )

        inclinacao = st.slider("Inclinação do terreno", 0, 90, 12)
        distancia_agua = st.slider("Distância da água (manual / fallback)", 0, 1000, 20)
        st.caption("A análise principal usa a distância geográfica calculada pelas coordenadas.")
        velocidade = st.slider("Velocidade da máquina", 0, 200, 15)
        historico_sinistros = st.slider("Histórico de sinistros", 0, 20, 2)
        solo_instavel = st.selectbox("Solo instável", [0, 1])

        latitude = st.number_input("Latitude", value=-23.4550000, step=0.000001, format="%.7f")
        longitude = st.number_input("Longitude", value=-46.5330000, step=0.000001, format="%.7f")

        clima_base = st.selectbox("Clima base", ["sol", "nublado", "chuva"], index=0)
        chuva_mm_base = st.slider("Chuva base (mm)", 0, 100, 0)

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

    st.markdown("### Telemetria ESP32")
    with st.expander("Enviar leitura fisica de teste", expanded=False):
        esp_col1, esp_col2, esp_col3 = st.columns(3)
        with esp_col1:
            esp_device_id = st.text_input("Device ID", value="ESP32-TRATOR-001", key="esp_device_id")
            esp_api_key = st.text_input("API Key do dispositivo", type="password", key="esp_api_key")
            esp_temperature = st.number_input("BME280 temperatura C", value=28.5, step=0.1, key="esp_temperature")
            esp_humidity = st.number_input("BME280 umidade %", min_value=0.0, max_value=100.0, value=78.0, step=0.5, key="esp_humidity")
            esp_pressure = st.number_input("BME280 pressao hPa", min_value=300.0, max_value=1100.0, value=1010.0, step=0.5, key="esp_pressure")
        with esp_col2:
            esp_accel_x = st.number_input("MPU accel X", value=0.12, step=0.01, key="esp_accel_x")
            esp_accel_y = st.number_input("MPU accel Y", value=-0.08, step=0.01, key="esp_accel_y")
            esp_accel_z = st.number_input("MPU accel Z", value=9.74, step=0.01, key="esp_accel_z")
            esp_inclination = st.number_input("MPU inclinacao graus", min_value=0.0, max_value=180.0, value=float(inclinacao), step=0.1, key="esp_inclination")
        with esp_col3:
            esp_distance = st.number_input("HC-SR04 distancia cm", min_value=0.0, value=185.0, step=1.0, key="esp_distance")
            esp_battery_voltage = st.number_input("Bateria V", min_value=0.0, max_value=30.0, value=5.0, step=0.1, key="esp_battery_voltage")
            esp_send = st.button("Enviar leitura ESP32", key="btn_send_esp")

        if esp_send:
            sequence = int(st.session_state.get("esp_sequence_number", int(time.time())))
            st.session_state["esp_sequence_number"] = sequence + 1
            esp_payload = {
                "device_id": esp_device_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "sequence_number": sequence,
                "operation_type": operation_type,
                "firmware_version": "dashboard-physical-test",
                "battery_voltage": float(esp_battery_voltage),
                "bme280": {
                    "temperature_c": float(esp_temperature),
                    "humidity_pct": float(esp_humidity),
                    "pressure_hpa": float(esp_pressure),
                },
                "mpu6050": {
                    "accel_x": float(esp_accel_x),
                    "accel_y": float(esp_accel_y),
                    "accel_z": float(esp_accel_z),
                    "inclination_deg": float(esp_inclination),
                },
                "ultrasonic": {"sensor_model": "HC-SR04", "distance_cm": float(esp_distance)},
            }

            ok_esp, esp_result = post_json(
                ESP_TELEMETRY_URL,
                esp_payload,
                extra_headers={"X-Device-ID": esp_device_id, "X-API-Key": esp_api_key},
            )
            if ok_esp:
                st.success("Leitura ESP32 recebida e analisada.")
                st.json(esp_result)
            else:
                show_api_error("Erro ao enviar leitura ESP32", esp_result)

if active_page == "Resumo executivo":
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
            df_farms = filter_df_by_farm(any_to_dataframe(farms_data), kind="farm")
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
        df_equipment = filter_df_by_farm(any_to_dataframe(equipment_data))
        if not df_equipment.empty:
            st.dataframe(df_equipment, use_container_width=True)
        else:
            st.info("Nenhum equipamento retornado.")
    else:
        show_api_error("Erro ao carregar equipamentos", equipment_data)

if active_page == "Ranking":
    st.markdown("### Ranking de equipamentos")

    ok_ranking, ranking_data = get_json(EQUIPMENT_RISK_URL)
    if not ok_ranking:
        ok_ranking, ranking_data = get_json(RANKING_URL)

    if ok_ranking:
        df_ranking = filter_df_by_farm(any_to_dataframe(ranking_data))

        if not df_ranking.empty:
            st.dataframe(df_ranking, use_container_width=True)

            numeric_cols = df_ranking.select_dtypes(include=["number"]).columns.tolist()
            object_cols = df_ranking.select_dtypes(include=["object"]).columns.tolist()

            if numeric_cols and object_cols:
                score_col = "risk_score" if "risk_score" in df_ranking.columns else "avg_risk_score" if "avg_risk_score" in df_ranking.columns else numeric_cols[0]
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

if active_page == "Risco regional":
    st.markdown("### Score de risco por regiao")

    ok_regions, region_data = get_json(REGION_RISK_URL)

    if ok_regions:
        df_regions = any_to_dataframe(region_data)
        if not df_regions.empty:
            st.dataframe(df_regions, use_container_width=True)

            if {"region", "risk_score"}.issubset(df_regions.columns):
                chart_df = df_regions[["region", "risk_score"]].copy()
                chart_df.columns = ["Regiao", "Score"]
                st.markdown("#### Ranking regional")
                st.bar_chart(chart_df.set_index("Regiao"))

            if {"latitude", "longitude", "risk_score"}.issubset(df_regions.columns):
                map_df = df_regions.dropna(subset=["latitude", "longitude"]).copy()
                if not map_df.empty:
                    map_df["lat"] = map_df["latitude"].astype(float)
                    map_df["lon"] = map_df["longitude"].astype(float)
                    map_df["risk"] = map_df["risk_score"].astype(float)
                    map_df["color"] = map_df["risk"].apply(
                        lambda score: [255, 77, 77, 190] if score >= 70 else [255, 209, 102, 190] if score >= 41 else [49, 233, 129, 190]
                    )
                    view_state = pdk.ViewState(
                        latitude=float(map_df["lat"].mean()),
                        longitude=float(map_df["lon"].mean()),
                        zoom=6,
                        pitch=0,
                    )
                    layer = pdk.Layer(
                        "ScatterplotLayer",
                        data=map_df,
                        get_position="[lon, lat]",
                        get_fill_color="color",
                        get_radius=18000,
                        pickable=True,
                    )
                    st.pydeck_chart(
                        pdk.Deck(initial_view_state=view_state, layers=[layer], tooltip={"text": "{region}\\nScore: {risk}"}),
                        use_container_width=True,
                    )
        else:
            st.info("Nenhum dado regional retornado.")
    else:
        show_api_error("Erro ao carregar risco regional", region_data)

if active_page == "Tendências":
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

# --- Telemetria: conectividade e grafico customizavel -----------------------

TELEMETRY_METRIC_LABELS = {
    "temperature_c": "Temperatura (C)",
    "humidity_pct": "Umidade do ar (%)",
    "pressure_hpa": "Pressao (hPa)",
    "altitude_m": "Altitude (m)",
    "battery_voltage": "Bateria (V)",
    "accel_x": "Acelerometro X (m/s2)",
    "accel_y": "Acelerometro Y (m/s2)",
    "accel_z": "Acelerometro Z (m/s2)",
    "acceleration_magnitude": "Aceleracao total (m/s2)",
    "gyro_x": "Giroscopio X (dps)",
    "gyro_y": "Giroscopio Y (dps)",
    "gyro_z": "Giroscopio Z (dps)",
    "gyro_magnitude": "Giroscopio total (dps)",
    "pitch": "Pitch (graus)",
    "roll": "Roll (graus)",
    "inclination_deg": "Inclinacao (graus)",
    "max_tilt_angle": "Inclinacao maxima (graus)",
    "movement_anomaly_score": "Anomalia de movimento",
    "possible_impact": "Possivel impacto (0/1)",
    "distance_cm": "Distancia ultrassonico (cm)",
    "obstacle_distance_cm": "Distancia do obstaculo (cm)",
    "obstacle_detected": "Obstaculo detectado (0/1)",
    "gps_accuracy_m": "Precisao GPS (m)",
    "gps_satellites": "Satelites GPS",
    "confidence_score": "Confianca (%)",
    "risk_score": "Risk score",
    "telemetry_age_seconds": "Idade da leitura (s)",
    "ingestion_delay_seconds": "Atraso de entrega (s)",
    "uptime_ms": "Uptime do ESP32 (ms)",
    "boot_id": "Boot ID",
    "sequence_number": "Numero de sequencia",
}
# Colunas numericas que identificam registros e nao sao medicoes.
# boot_id e confidence_score ficam fora dos graficos (continuam na operacao e na tabela de leituras).
TELEMETRY_METRIC_EXCLUDED = {
    "id", "iot_device_id", "equipment_id", "latitude", "longitude", "boot_id", "confidence_score",
}
TELEMETRY_DEFAULT_METRICS = ["temperature_c", "humidity_pct", "acceleration_magnitude", "distance_cm"]
TELEMETRY_CHART_TYPES = ["Linha", "Area", "Barras", "Pontos"]
TELEMETRY_RESAMPLE_OPTIONS = {
    "Automatico": "auto",
    "Sem agrupar (leituras originais)": None,
    "10 segundos": "10s",
    "30 segundos": "30s",
    "1 minuto": "1min",
    "5 minutos": "5min",
    "15 minutos": "15min",
    "1 hora": "1h",
    "6 horas": "6h",
}
TELEMETRY_AGGREGATIONS = {"Media": "mean", "Minimo": "min", "Maximo": "max", "Mediana": "median"}
TELEMETRY_LAYOUTS = [
    "Um grafico por metrica",
    "Sobrepostas (valores originais)",
    "Sobrepostas (normalizado 0-100)",
]
TELEMETRY_SOURCES = ["Todas", "Somente buffer (offline com coleta)", "Somente ao vivo"]
TELEMETRY_SEGMENT_LABELS = {
    "online": "Online",
    "offline_com_coleta": "Offline com coleta",
    "sem_dados": "Sem dados",
    "reiniciou": "Reiniciou",
}
TELEMETRY_SEGMENT_COLORS = {
    "Online": "#1b7f5c",
    "Offline com coleta": "#e08a00",
    "Sem dados": "#8a8f98",
    "Reiniciou": "#c0392b",
}
TELEMETRY_PERIOD_HOURS = {"5m": 1, "1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 168, "all": 168, "custom": 168}


def telemetry_numeric_frame(hist_df: pd.DataFrame) -> pd.DataFrame:
    """Colunas numericas utilizaveis como metrica (dicts, textos e vazias ficam de fora)."""
    columns: dict[str, pd.Series] = {}
    for column in hist_df.columns:
        if column in TELEMETRY_METRIC_EXCLUDED:
            continue
        series = hist_df[column]
        if series.dtype == bool:
            series = series.astype(int)
        elif series.dtype == object:
            try:
                series = pd.to_numeric(series, errors="coerce")
            except (TypeError, ValueError):
                continue
        elif not pd.api.types.is_numeric_dtype(series):
            continue
        if series.notna().sum() == 0:
            continue
        columns[column] = series.astype(float)
    return pd.DataFrame(columns, index=hist_df.index)


def telemetry_auto_resample_rule(span_seconds: float, target_points: int = 600) -> str | None:
    if span_seconds <= 0:
        return None
    needed = span_seconds / target_points
    for rule, seconds in (("10s", 10), ("30s", 30), ("1min", 60), ("5min", 300), ("15min", 900), ("1h", 3600)):
        if needed <= seconds:
            return rule if needed > 5 else None
    return "6h"


def render_metric_explorer(hist_df: pd.DataFrame, time_col: str, key_prefix: str) -> None:
    """Grafico resumido e customizavel do log de telemetria (escolha de metricas, tipo e agrupamento)."""
    if time_col not in hist_df.columns:
        return
    frame = hist_df.copy()
    frame[time_col] = pd.to_datetime(frame[time_col], errors="coerce")
    frame = frame.dropna(subset=[time_col]).sort_values(time_col)
    if frame.empty:
        return

    st.markdown("#### Grafico customizavel")
    st.caption(
        "Resuma o log de telemetria em um grafico: escolha as metricas, o tipo, o agrupamento no tempo "
        f"e a escala. Horarios no fuso {LOCAL_TZ_LABEL}. Arraste para mover e use a roda do mouse para dar zoom."
    )

    source_choice = st.selectbox("Origem das leituras", TELEMETRY_SOURCES, key=f"{key_prefix}_source")
    if "ingestion_mode" in frame.columns:
        if source_choice == TELEMETRY_SOURCES[1]:
            frame = frame[frame["ingestion_mode"] == "buffered"]
        elif source_choice == TELEMETRY_SOURCES[2]:
            frame = frame[frame["ingestion_mode"] != "buffered"]
    elif source_choice != TELEMETRY_SOURCES[0]:
        st.caption("Origem indisponivel: o servidor ainda nao informa o modo de envio das leituras.")
    if frame.empty:
        st.info("Nenhuma leitura para a origem selecionada.")
        return

    numeric = telemetry_numeric_frame(frame)
    available = list(numeric.columns)
    if not available:
        st.info("Sem metricas numericas no periodo selecionado.")
        return
    labels = {column: TELEMETRY_METRIC_LABELS.get(column, column) for column in available}
    # Metricas conhecidas primeiro, na ordem do dicionario; as demais em ordem alfabetica.
    known = [column for column in TELEMETRY_METRIC_LABELS if column in available]
    others = sorted(column for column in available if column not in TELEMETRY_METRIC_LABELS)
    options = known + others
    default_metrics = [column for column in TELEMETRY_DEFAULT_METRICS if column in options] or options[:2]

    selected = st.multiselect(
        "Metricas",
        options,
        default=default_metrics,
        format_func=lambda column: labels[column],
        key=f"{key_prefix}_metrics",
    )
    c1, c2, c3 = st.columns(3)
    chart_type = c1.selectbox("Tipo", TELEMETRY_CHART_TYPES, key=f"{key_prefix}_type")
    layout = c2.selectbox("Disposicao e escala", TELEMETRY_LAYOUTS, key=f"{key_prefix}_layout")
    resample_label = c3.selectbox(
        "Agrupar no tempo", list(TELEMETRY_RESAMPLE_OPTIONS), key=f"{key_prefix}_resample"
    )
    aggregation_label = "Media"
    if TELEMETRY_RESAMPLE_OPTIONS[resample_label] is not None:
        aggregation_label = st.radio(
            "Funcao de resumo", list(TELEMETRY_AGGREGATIONS), horizontal=True, key=f"{key_prefix}_agg"
        )
    show_restarts = False
    if "boot_id" in frame.columns and frame["boot_id"].notna().any():
        show_restarts = st.checkbox("Marcar reinicios do ESP32", value=True, key=f"{key_prefix}_restarts")

    if not selected:
        st.info("Escolha ao menos uma metrica para montar o grafico.")
        return

    series = numeric[selected].copy()
    series.index = frame[time_col].values
    span_seconds = (series.index.max() - series.index.min()) / pd.Timedelta(seconds=1)
    rule = TELEMETRY_RESAMPLE_OPTIONS[resample_label]
    if rule == "auto":
        rule = telemetry_auto_resample_rule(float(span_seconds))
    if rule:
        series = series.resample(rule).agg(TELEMETRY_AGGREGATIONS[aggregation_label]).dropna(how="all")
    if series.empty:
        st.info("Sem pontos para desenhar com este agrupamento.")
        return

    plot = series.copy()
    plot.index.name = "tempo"
    long = plot.reset_index().melt("tempo", var_name="coluna", value_name="valor").dropna(subset=["valor"])
    long["metrica"] = long["coluna"].map(labels)
    if layout == TELEMETRY_LAYOUTS[2]:
        spans = long.groupby("coluna")["valor"].transform(lambda values: values.max() - values.min())
        minimums = long.groupby("coluna")["valor"].transform("min")
        long["normalizado"] = ((long["valor"] - minimums) / spans.where(spans > 0) * 100).fillna(50.0)
        y_field, y_title = "normalizado", "Normalizado (0-100)"
    else:
        y_field, y_title = "valor", None

    restart_times = pd.DataFrame({"tempo": []})
    if show_restarts:
        boots = frame[[time_col, "boot_id"]].dropna()
        changed = boots["boot_id"].ne(boots["boot_id"].shift()) & boots["boot_id"].shift().notna()
        restart_times = pd.DataFrame({"tempo": boots.loc[changed, time_col].values})

    st.caption(
        f"{len(frame)} leituras resumidas em {len(plot)} pontos por metrica"
        + (f" (agrupadas a cada {rule}, {aggregation_label.lower()})." if rule else ".")
    )

    def _mark(chart):
        if chart_type == "Area":
            return chart.mark_area(opacity=0.35, line=True)
        if chart_type == "Barras":
            return chart.mark_bar()
        if chart_type == "Pontos":
            return chart.mark_circle(size=40)
        return chart.mark_line()

    def _panel(data: pd.DataFrame, height: int, y_title_override: str | None, with_color: bool) -> Any:
        encodings = dict(
            x=alt.X("tempo:T", title=None),
            y=alt.Y(f"{y_field}:Q", title=y_title_override, scale=alt.Scale(zero=(chart_type == "Barras"))),
            tooltip=[
                alt.Tooltip("tempo:T", title="Horario", format="%Y-%m-%d %H:%M:%S"),
                alt.Tooltip("metrica:N", title="Metrica"),
                alt.Tooltip("valor:Q", title="Valor", format=".3f"),
            ],
        )
        if with_color:
            encodings["color"] = alt.Color("metrica:N", legend=alt.Legend(orient="bottom", title=None))
        layer = _mark(alt.Chart(data)).encode(**encodings).properties(height=height)
        if not restart_times.empty:
            rules = (
                alt.Chart(restart_times)
                .mark_rule(color=TELEMETRY_SEGMENT_COLORS["Reiniciou"], strokeDash=[4, 3])
                .encode(x="tempo:T", tooltip=[alt.Tooltip("tempo:T", title="Reiniciou", format="%Y-%m-%d %H:%M:%S")])
            )
            layer = alt.layer(layer, rules)
        return layer

    with alt.data_transformers.enable(max_rows=None):
        if layout == TELEMETRY_LAYOUTS[0]:
            panels = []
            for column in selected:
                part = long[long["coluna"] == column]
                if part.empty:
                    continue
                panels.append(_panel(part, 140, labels[column], False).interactive(bind_y=False))
            if panels:
                st.altair_chart(alt.vconcat(*panels), use_container_width=True)
        else:
            st.altair_chart(_panel(long, 320, y_title, True).interactive(bind_y=False), use_container_width=True)


def format_duration_hm(seconds: Any) -> str:
    """Duracao legivel em horas e minutos (ex.: '1 h 05 min', '6 min'); abaixo de 1 min mostra segundos."""
    try:
        total = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return "-"
    if total < 60:
        return f"{total} s"
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


CONNECTIVITY_CARD_CSS = """
<style>
.ag-conn-card{border:1px solid var(--ag-line, rgba(73,234,216,.18));border-radius:8px;padding:.4rem .65rem;
background:linear-gradient(180deg, rgba(16,36,44,.95), rgba(8,18,23,.95));min-height:3.6rem;margin-bottom:.4rem}
.ag-conn-title{font-size:.72rem;color:var(--ag-muted, #8fa3a8);margin-bottom:.05rem}
.ag-conn-value{font-size:1.1rem;font-weight:700;line-height:1.25;color:var(--ag-text, #e8f1f2);
overflow-wrap:anywhere;display:flex;align-items:center;gap:.45rem}
.ag-conn-meta{font-size:.68rem;color:var(--ag-muted, #8fa3a8);margin-top:.15rem;overflow-wrap:anywhere}
.ag-conn-dot{display:inline-block;width:.7rem;height:.7rem;border-radius:50%;flex:none}
</style>
"""
CONNECTIVITY_TONE_COLORS = {"ok": "#1b7f5c", "warn": "#e08a00", "off": "#8a8f98", "bad": "#c0392b"}


def render_connectivity_card(title: str, value: str, meta: str = "", tone: str = "") -> None:
    from html import escape

    color = CONNECTIVITY_TONE_COLORS.get(tone)
    dot = f'<span class="ag-conn-dot" style="background:{color}"></span>' if color else ""
    st.markdown(
        f'<div class="ag-conn-card"><div class="ag-conn-title">{escape(title)}</div>'
        f'<div class="ag-conn-value">{dot}<span>{escape(value)}</span></div>'
        f'<div class="ag-conn-meta">{escape(meta)}</div></div>',
        unsafe_allow_html=True,
    )


def render_connectivity_cards(
    data: dict, summary: dict, timeline: pd.DataFrame, generated: pd.Timestamp
) -> None:
    """Cartoes de conectividade em horas e minutos: ao vivo, offline com coleta e sem dados (perdido)."""
    st.markdown(CONNECTIVITY_CARD_CSS, unsafe_allow_html=True)

    def _seconds(kind: str) -> float:
        label = TELEMETRY_SEGMENT_LABELS[kind]
        part = timeline[timeline["Estado"] == label] if not timeline.empty else timeline
        if part.empty:
            return 0.0
        return float((part["Fim"] - part["Inicio"]).dt.total_seconds().clip(lower=0).sum())

    signal = data.get("signal_status")
    last_seen = pd.to_datetime(data.get("last_seen_at"), utc=True, errors="coerce")
    since_contact = (
        f"contato ha {format_duration_hm((generated - last_seen).total_seconds())}"
        if pd.notna(last_seen) and pd.notna(generated)
        else "sem contato registrado"
    )
    last_reset = ""
    for segment in reversed(data.get("segments", [])):
        if segment.get("kind") == "reiniciou":
            last_reset = f"ultimo: {segment.get('reset_reason') or 'motivo desconhecido'}"
            break
    missing = int(summary.get("missing_readings", 0) or 0)
    lost_seconds = _seconds("sem_dados")

    row1 = st.columns(3)
    with row1[0]:
        render_connectivity_card(
            "Sinal",
            "Com sinal" if signal == "COM_SINAL" else "Sem sinal" if signal == "SEM_SINAL" else "-",
            since_contact,
            "ok" if signal == "COM_SINAL" else "off",
        )
    with row1[1]:
        render_connectivity_card(
            "Ultimo contato",
            format_local_time(data.get("last_seen_at"), "%H:%M:%S"),
            format_local_time(data.get("last_seen_at"), "%d/%m/%Y", default=""),
        )
    with row1[2]:
        restarts = int(summary.get("restarts", 0) or 0)
        render_connectivity_card(
            "Reinicios do ESP32", str(restarts), last_reset if restarts else "nenhum no periodo"
        )
    row2 = st.columns(3)
    with row2[0]:
        render_connectivity_card(
            "Tempo ao vivo",
            format_duration_hm(_seconds("online")),
            f"{int(summary.get('online_readings', 0) or 0)} leituras enviadas na hora",
            "ok",
        )
    with row2[1]:
        render_connectivity_card(
            "Offline com coleta",
            format_duration_hm(_seconds("offline_com_coleta")),
            f"{int(summary.get('offline_com_coleta_readings', 0) or 0)} leituras guardadas e entregues depois",
            "warn",
        )
    with row2[2]:
        render_connectivity_card(
            "Sem dados (perdido)",
            format_duration_hm(lost_seconds),
            f"{missing} leitura(s) nao recebida(s)"
            if missing
            else ("sem coleta neste intervalo" if lost_seconds else "nenhuma lacuna"),
            "off" if lost_seconds else "",
        )


def render_connectivity_timeline(device_id: str | None, period_code: str) -> None:
    """Faixa de conectividade e linha do tempo: online, offline com coleta, reiniciou e sem dados."""
    if not device_id:
        return
    hours = TELEMETRY_PERIOD_HOURS.get(period_code, 24)
    ok, data = get_json(f"{IOT_DEVICES_URL}/{quote(str(device_id), safe='')}/telemetry/segments?hours={hours}")
    st.markdown("#### Conectividade")
    if not ok or not isinstance(data, dict):
        st.caption("Linha do tempo de conectividade indisponivel (servidor sem o recurso ou sem permissao).")
        return
    summary = data.get("summary") or {}

    generated = pd.to_datetime(data.get("generated_at"), utc=True, errors="coerce")
    rows = []
    for segment in data.get("segments", []):
        kind = segment.get("kind")
        label = TELEMETRY_SEGMENT_LABELS.get(kind, str(kind))
        if kind == "reiniciou":
            at = pd.to_datetime(segment.get("at"), utc=True, errors="coerce")
            rows.append(
                {
                    "Estado": label,
                    "Inicio": at,
                    "Fim": at,
                    "Leituras": None,
                    "Duracao (s)": 0.0,
                    "Detalhe": f"boot {segment.get('from_boot_id')} -> {segment.get('to_boot_id')}"
                    + (f" | reset: {segment['reset_reason']}" if segment.get("reset_reason") else ""),
                }
            )
            continue
        start = pd.to_datetime(segment.get("start"), utc=True, errors="coerce")
        end = pd.to_datetime(segment.get("end"), utc=True, errors="coerce")
        if pd.isna(end):
            end = generated
        detail = ""
        if kind == "sem_dados":
            detail = f"{segment.get('missing_readings', 0)} leitura(s) nao recebida(s) (sequencia pulada)"
            if segment.get("open"):
                detail += " | em aberto"
        elif kind == "offline_com_coleta":
            detail = f"entregue em {format_local_time(segment.get('delivered_at'))} | atraso max {segment.get('max_delay_seconds', 0)} s"
        rows.append(
            {
                "Estado": label,
                "Inicio": start,
                "Fim": end,
                "Leituras": segment.get("readings"),
                "Duracao (s)": segment.get("duration_seconds")
                if segment.get("duration_seconds") is not None
                else (round((end - start).total_seconds(), 1) if pd.notna(start) and pd.notna(end) else None),
                "Detalhe": detail,
            }
        )
    if rows:
        timeline = pd.DataFrame(rows)
        for column in ("Inicio", "Fim"):
            timeline[column] = timeline[column].dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)
    else:
        timeline = pd.DataFrame(columns=["Estado", "Inicio", "Fim", "Leituras", "Duracao (s)", "Detalhe"])
    render_connectivity_cards(data, summary, timeline, generated)
    if period_code == "30d":
        st.caption("A linha do tempo cobre no maximo as ultimas 168 horas (7 dias).")
    if summary.get("currently_silent"):
        st.warning("O dispositivo esta sem enviar dados neste momento (segmento 'Sem dados' em aberto).")
    if summary.get("unknown_time_readings"):
        st.caption(
            f"{summary['unknown_time_readings']} leitura(s) sem horario confiavel do ESP32 "
            "foram datadas na chegada e nao entram na deteccao de lacunas."
        )
    if not rows:
        st.info("Sem segmentos de telemetria no periodo.")
        return

    bars = timeline[timeline["Estado"] != TELEMETRY_SEGMENT_LABELS["reiniciou"]]
    marks = timeline[timeline["Estado"] == TELEMETRY_SEGMENT_LABELS["reiniciou"]]
    order = list(TELEMETRY_SEGMENT_COLORS)
    color_scale = alt.Scale(domain=order, range=[TELEMETRY_SEGMENT_COLORS[name] for name in order])
    tooltip = [
        alt.Tooltip("Estado:N"),
        alt.Tooltip("Inicio:T", format="%Y-%m-%d %H:%M:%S"),
        alt.Tooltip("Fim:T", format="%Y-%m-%d %H:%M:%S"),
        alt.Tooltip("Leituras:Q"),
        alt.Tooltip("Detalhe:N"),
    ]
    layers = []
    if not bars.empty:
        layers.append(
            alt.Chart(bars)
            .mark_bar(height=18, minBandSize=3)
            .encode(
                x=alt.X("Inicio:T", title=None),
                x2="Fim:T",
                y=alt.Y("Estado:N", sort=order, title=None),
                color=alt.Color("Estado:N", scale=color_scale, legend=None),
                tooltip=tooltip,
            )
        )
    if not marks.empty:
        layers.append(
            alt.Chart(marks)
            .mark_point(shape="diamond", size=140, filled=True)
            .encode(
                x=alt.X("Inicio:T", title=None),
                y=alt.Y("Estado:N", sort=order, title=None),
                color=alt.Color("Estado:N", scale=color_scale, legend=None),
                tooltip=tooltip,
            )
        )
    if layers:
        st.altair_chart(alt.layer(*layers).properties(height=130), use_container_width=True)
    with st.expander("Segmentos (detalhe)"):
        st.dataframe(timeline, use_container_width=True)


TRACTOR_3D_HTML = """
<!doctype html><html><head><meta charset="utf-8">
<style>
html,body{margin:0;background:transparent;font-family:Segoe UI,Arial,sans-serif;color:#e8f1f2}
#box{position:relative;width:100%;height:__HEIGHT__px;border:1px solid rgba(73,234,216,.22);border-radius:10px;
background:radial-gradient(circle at 50% 30%,#12303b 0%,#0a1a22 70%);overflow:hidden;touch-action:none;cursor:grab}
#info{position:absolute;left:10px;top:8px;font-size:12px;line-height:1.55;pointer-events:none;
background:rgba(7,16,24,.62);padding:6px 9px;border-radius:8px}
#legend{position:absolute;right:10px;bottom:8px;font-size:11px;line-height:1.5;pointer-events:none;
background:rgba(7,16,24,.62);padding:5px 9px;border-radius:8px;color:#b7c8cc}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:middle}
#hint{position:absolute;left:10px;bottom:8px;font-size:11px;color:#7f9498;pointer-events:none}
</style></head><body>
<div id="box"><div id="info"></div><div id="legend"></div><div id="hint">Arraste para girar a vista</div></div>
<script src="__THREE_SRC__"></script>
<script>
(function(){
const D = __DATA__;
const box = document.getElementById('box');
if (typeof THREE === 'undefined') {
  box.insertAdjacentHTML('beforeend','<div style="padding:2.2rem 1rem;color:#9fb3b8;font-size:13px">Visualizador 3D indisponivel: a biblioteca three.js nao foi carregada (verifique a conexao com a internet do navegador).</div>');
  return;
}
const num = (v, d) => (v === null || v === undefined || isNaN(v)) ? 0 : v;
let W = box.getBoundingClientRect().width || 640, H = __HEIGHT__;
const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
renderer.setPixelRatio(window.devicePixelRatio || 1);
renderer.setSize(W, H);
box.insertBefore(renderer.domElement, box.firstChild);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, W / H, 0.1, 100);
scene.add(new THREE.AmbientLight(0xffffff, 0.72));
const sun = new THREE.DirectionalLight(0xffffff, 0.75); sun.position.set(4, 8, 5); scene.add(sun);
scene.add(new THREE.GridHelper(12, 24, 0x2b5560, 0x16303a));

const riskColors = {baixo:0x2fd27d, medio:0xffc857, alto:0xff5d5d};
const riskKey = String(D.risk_level || '').toLowerCase();
const riskColor = riskKey.indexOf('alt') === 0 || riskKey.indexOf('high') === 0 || riskKey.indexOf('crit') === 0 ? riskColors.alto
  : riskKey.indexOf('med') === 0 ? riskColors.medio : riskColors.baixo;
const ring = new THREE.Mesh(new THREE.RingGeometry(2.55, 2.7, 64), new THREE.MeshBasicMaterial({color:riskColor, side:THREE.DoubleSide}));
ring.rotation.x = -Math.PI / 2; ring.position.y = 0.01; scene.add(ring);

const pivot = new THREE.Group(); pivot.position.y = 0.8; scene.add(pivot);
const model = new THREE.Group(); model.position.y = -0.8; pivot.add(model);
const lam = (c, o) => new THREE.MeshLambertMaterial(Object.assign({color:c}, o || {}));
function addBox(w, h, d, x, y, z, m){ const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), m); mesh.position.set(x, y, z); model.add(mesh); return mesh; }
function addWheel(r, wdt, x, z){
  const tire = new THREE.Mesh(new THREE.CylinderGeometry(r, r, wdt, 28), lam(0x20262b));
  tire.rotation.x = Math.PI / 2; tire.position.set(x, r, z); model.add(tire);
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.55, r * 0.55, wdt + 0.02, 20), lam(0xe6b422));
  hub.rotation.x = Math.PI / 2; hub.position.set(x, r, z); model.add(hub);
}
addBox(2.7, 0.45, 1.0, 0, 0.75, 0, lam(0x2e9d4f));
addBox(1.35, 0.6, 0.82, 0.78, 1.18, 0, lam(0x25803f));
addBox(1.0, 0.95, 0.92, -0.6, 1.42, 0, lam(0x9fd4e8, {transparent:true, opacity:0.55}));
addBox(1.15, 0.08, 1.05, -0.6, 1.93, 0, lam(0x1f6b36));
const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.7, 12), lam(0x333a40)); pipe.position.set(1.05, 1.8, 0.2); model.add(pipe);
addWheel(0.66, 0.38, -0.95, 0.72); addWheel(0.66, 0.38, -0.95, -0.72);
addWheel(0.4, 0.28, 1.05, 0.66); addWheel(0.4, 0.28, 1.05, -0.66);

// Sensor (X frente, Y esquerda, Z cima) -> cena (X frente, Y cima, Z direita)
const mapV = v => new THREE.Vector3(v[0], v[2], -v[1]);
function thickArrow(dir, origin, length, color){
  const g = new THREE.Group(); const m = new THREE.MeshBasicMaterial({color:color});
  const head = Math.min(0.55, length * 0.4), shaft = Math.max(0.05, length - head);
  const s = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, shaft, 10), m); s.position.y = shaft / 2; g.add(s);
  const c = new THREE.Mesh(new THREE.ConeGeometry(0.14, head, 14), m); c.position.y = shaft + head / 2; g.add(c);
  g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize());
  g.position.copy(origin); return g;
}
// aceleracao dinamica (medida menos a gravidade estimada)
let dynText = 'estavel';
if (D.dyn) {
  const v = mapV(D.dyn), mag = v.length();
  if (mag > 0.15) {
    pivot.add(thickArrow(v, new THREE.Vector3(0, 1.15, 0), Math.min(3.2, 1.0 + mag * 0.6), 0xff9f1c));
    const ax = Math.abs(D.dyn[0]), ay = Math.abs(D.dyn[1]), az = Math.abs(D.dyn[2]);
    let dirTxt = ax >= ay && ax >= az ? (D.dyn[0] >= 0 ? 'para a frente' : 'para tras')
      : ay >= az ? (D.dyn[1] >= 0 ? 'para a esquerda' : 'para a direita') : (D.dyn[2] >= 0 ? 'para cima' : 'para baixo');
    dynText = mag.toFixed(1) + ' m/s2 ' + dirTxt;
  }
} else { dynText = 'sem dados'; }
// giroscopio: arcos em volta de cada eixo, proporcionais a taxa de giro (graus/s)
const rates = D.gyro ? [num(D.gyro[0]), num(D.gyro[2]), -num(D.gyro[1])] : [0, 0, 0];
const axes = [
  {u:[0,1,0], v:[0,0,1], R:1.35, color:0xff5d5d},
  {u:[0,0,1], v:[1,0,0], R:1.9,  color:0x5dffb0},
  {u:[1,0,0], v:[0,1,0], R:1.6,  color:0x5da8ff},
];
axes.forEach((a, i) => {
  const w = rates[i]; if (Math.abs(w) < 4) return;
  const sweep = Math.min(1.7 * Math.PI, Math.max(0.45, Math.abs(w) / 90 * Math.PI)), sign = w >= 0 ? 1 : -1;
  const u = new THREE.Vector3(...a.u), v = new THREE.Vector3(...a.v), pts = [];
  for (let k = 0; k <= 40; k++) {
    const ang = sign * sweep * k / 40;
    pts.push(u.clone().multiplyScalar(Math.cos(ang) * a.R).add(v.clone().multiplyScalar(Math.sin(ang) * a.R)).add(new THREE.Vector3(0, 0.55, 0)));
  }
  const tube = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 60, 0.04, 8), new THREE.MeshBasicMaterial({color:a.color}));
  pivot.add(tube);
  const endAng = sign * sweep;
  const tangent = u.clone().multiplyScalar(-Math.sin(endAng)).add(v.clone().multiplyScalar(Math.cos(endAng))).multiplyScalar(sign).normalize();
  const cone = new THREE.Mesh(new THREE.ConeGeometry(0.15, 0.36, 14), new THREE.MeshBasicMaterial({color:a.color}));
  cone.position.copy(pts[pts.length - 1]); cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tangent); pivot.add(cone);
});
// inclinacao do trator (pitch: nariz para cima; roll: lado direito para baixo)
const rad = d => num(d) * Math.PI / 180;
pivot.rotation.set(rad(D.roll), 0, rad(D.pitch), 'XYZ');

const f1 = v => (v === null || v === undefined || isNaN(v)) ? 'N/D' : Number(v).toFixed(1);
const rateTxt = n => Math.abs(n) < 4 ? 'parado' : (n >= 0 ? '+' : '') + n.toFixed(0) + ' dps';
document.getElementById('info').innerHTML =
  '<b>Inclinacao</b> ' + f1(D.inclination) + ' deg &nbsp;|&nbsp; pitch ' + f1(D.pitch) + ' &nbsp;roll ' + f1(D.roll) +
  '<br><b>Aceleracao dinamica</b> ' + dynText +
  '<br><b>Giro</b> rolagem ' + rateTxt(rates[0]) + ' &middot; arfagem ' + rateTxt(-rates[2]) + ' &middot; guinada ' + rateTxt(rates[1]);
document.getElementById('legend').innerHTML =
  '<span class="sw" style="background:#ff9f1c"></span>seta: aceleracao dinamica (tamanho = intensidade)<br>' +
  '<span class="sw" style="background:#ff5d5d"></span>rolagem <span class="sw" style="background:#5da8ff;margin-left:6px"></span>arfagem ' +
  '<span class="sw" style="background:#5dffb0;margin-left:6px"></span>guinada (arcos = giro)<br>' +
  '<span class="sw" style="background:#' + riskColor.toString(16).padStart(6,'0') + '"></span>anel: nivel de risco ' + (D.risk_level || 'N/D');

let theta = 0.75, phi = 0.38, radius = 8.2, drag = null;
function render(){
  camera.position.set(radius * Math.cos(phi) * Math.cos(theta), radius * Math.sin(phi) + 0.9, radius * Math.cos(phi) * Math.sin(theta));
  camera.lookAt(0, 0.9, 0); renderer.render(scene, camera);
}
const el = renderer.domElement;
el.addEventListener('pointerdown', e => { drag = {x:e.clientX, y:e.clientY}; el.setPointerCapture(e.pointerId); box.style.cursor = 'grabbing'; });
el.addEventListener('pointerup', () => { drag = null; box.style.cursor = 'grab'; });
el.addEventListener('pointermove', e => {
  if (!drag) return;
  theta -= (e.clientX - drag.x) * 0.008; phi = Math.min(1.3, Math.max(0.05, phi + (e.clientY - drag.y) * 0.006));
  drag = {x:e.clientX, y:e.clientY}; render();
});
window.addEventListener('resize', () => {
  W = box.getBoundingClientRect().width || W; renderer.setSize(W, H); camera.aspect = W / H; camera.updateProjectionMatrix(); render();
});
render();
})();
</script></body></html>
"""


# ---------------------------------------------------------------------------
# Central de Telemetria: painel enxuto, trator 3D e tabela de leituras
# ---------------------------------------------------------------------------
# (id, rotulo, visivel por padrao). O usuario liga/desliga cada bloco em "Personalizar painel".
TELEMETRY_PANEL_SECTIONS = [
    ("status", "Resumo de status", True),
    ("trator", "Trator 3D (movimento)", True),
    ("sensores", "Sensores principais", True),
    ("conectividade", "Conectividade", True),
    ("grafico", "Grafico customizavel", True),
    ("leituras", "Tabela de leituras", True),
    ("ambiente", "Ambiente (BME280)", False),
    ("movimento_cru", "Aceleracao e giroscopio (valores)", False),
    ("gps_energia", "GPS e bateria", False),
    ("qualidade", "Qualidade do dado", False),
    ("ia", "Explicacao da IA", False),
]
TELEMETRY_PERIOD_CHOICES = {
    "Ultimos 5 minutos": "5m",
    "Ultima hora": "1h",
    "Ultimas 6 horas": "6h",
    "24 horas": "24h",
    "7 dias": "7d",
    "30 dias": "30d",
    "Tudo (ate 5000 leituras)": "all",
    "Personalizado": "custom",
}
TELEMETRY_EVENT_PERIODS = {"5m", "1h", "6h", "24h", "7d", "30d"}
THREE_JS_SRC = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"
MINI_TILE_CSS = """
<style>
.ag-mini-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:.45rem;margin:.2rem 0 .6rem}
.ag-mini{border:1px solid var(--ag-line, rgba(73,234,216,.18));border-radius:8px;padding:.35rem .6rem;
background:linear-gradient(180deg, rgba(16,36,44,.95), rgba(8,18,23,.95))}
.ag-mini-label{font-size:.68rem;color:var(--ag-muted, #8fa3a8);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ag-mini-value{font-size:1rem;font-weight:700;color:var(--ag-text, #e8f1f2);display:flex;align-items:center;gap:.35rem;
overflow-wrap:anywhere}
.ag-mini-dot{display:inline-block;width:.55rem;height:.55rem;border-radius:50%;flex:none}
</style>
"""


def reset_telemetry_panel() -> None:
    for section_id, _label, default in TELEMETRY_PANEL_SECTIONS:
        st.session_state[f"keep_tp_{section_id}"] = default


def render_mini_tiles(items: list[tuple[str, Any, str]]) -> None:
    """Caixas compactas (rotulo + valor) em grade; tom opcional: ok, warn, bad, off."""
    from html import escape

    st.markdown(MINI_TILE_CSS, unsafe_allow_html=True)
    cells = []
    for label, value, tone in items:
        color = CONNECTIVITY_TONE_COLORS.get(tone)
        dot = f'<span class="ag-mini-dot" style="background:{color}"></span>' if color else ""
        cells.append(
            f'<div class="ag-mini"><div class="ag-mini-label">{escape(str(label))}</div>'
            f'<div class="ag-mini-value">{dot}<span>{escape(str(value))}</span></div></div>'
        )
    st.markdown('<div class="ag-mini-grid">' + "".join(cells) + "</div>", unsafe_allow_html=True)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def risk_tone(level: Any) -> str:
    text = str(level or "").lower()
    if text.startswith(("alt", "high", "crit")):
        return "bad"
    if text.startswith(("med",)):
        return "warn"
    return "ok" if text else ""


def estimate_gravity_vector(hist_df: pd.DataFrame, window: int = 60) -> list[float] | None:
    """Gravidade no referencial do sensor = mediana das ultimas leituras (independe da montagem)."""
    columns = ["accel_x", "accel_y", "accel_z"]
    if hist_df.empty or not set(columns).issubset(hist_df.columns):
        return None
    recent = hist_df[columns].apply(pd.to_numeric, errors="coerce").dropna().tail(window)
    if len(recent) < 3:
        return None
    return [float(recent[column].median()) for column in columns]


def render_tractor_3d(latest: dict, hist_df: pd.DataFrame) -> None:
    """Trator 3D inclinado (pitch/roll) com seta de aceleracao dinamica e arcos de giro do giroscopio."""
    accel = [_finite(latest.get(key)) for key in ("accel_x", "accel_y", "accel_z")]
    gravity = estimate_gravity_vector(hist_df)
    dyn = None
    if gravity is not None and all(value is not None for value in accel):
        dyn = [accel[i] - gravity[i] for i in range(3)]
    gyro = [_finite(latest.get(key)) for key in ("gyro_x", "gyro_y", "gyro_z")]
    payload = {
        "pitch": _finite(latest.get("pitch")),
        "roll": _finite(latest.get("roll")),
        "inclination": _finite(latest.get("inclination_deg")),
        "dyn": dyn,
        "gyro": [value or 0.0 for value in gyro] if any(value is not None for value in gyro) else None,
        "risk_level": str(latest.get("risk_level") or ""),
    }
    height = 380
    html = (
        TRACTOR_3D_HTML.replace("__HEIGHT__", str(height))
        .replace("__THREE_SRC__", THREE_JS_SRC)
        .replace("__DATA__", json.dumps(payload))
    )
    components.html(html, height=height + 6)
    st.caption(
        "Assume sensor com X para a frente, Y para a esquerda e Z para cima. A aceleracao dinamica e a "
        "leitura atual menos a gravidade estimada pelas ultimas leituras; arcos aparecem acima de 4 graus/s."
    )


READING_COLUMN_LABELS = {
    "recorded_at": "Horario da leitura",
    "received_at": "Recebido pelo servidor",
    "ingestion_mode": "Origem do envio",
    "time_quality": "Qualidade do horario",
    "data_quality_status": "Qualidade do dado",
    "data_quality_issues": "Problemas de qualidade",
    "missing_sensors": "Sensores ausentes",
    "risk_level": "Nivel de risco",
    "risk_score": "Risk score",
    "explicacao": "Explicacao da IA",
    "eventos": "Eventos",
    "tipos_de_evento": "Tipos de evento",
    "gravidade_max": "Gravidade maxima",
    "descricao_eventos": "Descricao dos eventos",
    "device_id": "Dispositivo",
    "possible_impact": "Possivel impacto",
    "obstacle_detected": "Obstaculo detectado",
    "ingestion_delay_seconds": "Atraso de entrega (s)",
    "telemetry_status": "Status da telemetria",
}
READING_PRESETS = {
    "Essenciais": [
        "recorded_at", "risk_level", "risk_score", "inclination_deg", "distance_cm", "acceleration_magnitude",
        "possible_impact", "battery_voltage", "data_quality_status", "eventos", "tipos_de_evento",
    ],
    "Movimento (MPU)": [
        "recorded_at", "accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z", "pitch", "roll",
        "inclination_deg", "acceleration_magnitude", "movement_anomaly_score", "possible_impact",
    ],
    "Ambiente e energia": [
        "recorded_at", "temperature_c", "humidity_pct", "pressure_hpa", "altitude_m", "battery_voltage",
    ],
    "Eventos e IA": [
        "recorded_at", "risk_level", "risk_score", "eventos", "tipos_de_evento", "gravidade_max",
        "descricao_eventos", "explicacao",
    ],
    "Todas as colunas": None,
}
EVENT_SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def reading_label(column: str) -> str:
    return READING_COLUMN_LABELS.get(column) or TELEMETRY_METRIC_LABELS.get(column) or column


def build_readings_frame(hist_df: pd.DataFrame, events: list[dict]) -> pd.DataFrame:
    """Uma linha por leitura com tudo o que foi gerado a partir dela (risco, qualidade, eventos, IA)."""
    frame = hist_df.copy()
    if "explanation" in frame.columns:
        frame["explicacao"] = frame["explanation"].apply(
            lambda value: value.get("summary") if isinstance(value, dict) else value
        )
    for column in list(frame.columns):
        values = frame[column]
        if values.map(lambda value: isinstance(value, dict)).any():
            frame = frame.drop(columns=[column])
        elif values.map(lambda value: isinstance(value, list)).any():
            frame[column] = values.map(
                lambda value: " | ".join(str(item) for item in value) if isinstance(value, list) else value
            )

    by_reading: dict[int, list[dict]] = {}
    for event in events or []:
        reading_id = _as_int(event.get("telemetry_id"))
        if reading_id is not None:
            by_reading.setdefault(reading_id, []).append(event)

    def _summarize(reading_id: Any, field: str) -> Any:
        items = by_reading.get(_as_int(reading_id) if reading_id is not None else None, [])
        if field == "eventos":
            return len(items)
        if not items:
            return None
        if field == "tipos_de_evento":
            return ", ".join(sorted({str(item.get("event_type")) for item in items if item.get("event_type")}))
        if field == "gravidade_max":
            return max((str(item.get("severity") or "") for item in items), key=lambda s: EVENT_SEVERITY_ORDER.get(s.upper(), 0))
        return " | ".join(str(item.get("description")) for item in items if item.get("description"))

    id_series = frame["id"] if "id" in frame.columns else pd.Series([None] * len(frame), index=frame.index)
    for field in ("eventos", "tipos_de_evento", "gravidade_max", "descricao_eventos"):
        frame[field] = id_series.map(lambda reading_id, f=field: _summarize(reading_id, f))
    return frame


def render_readings_table(hist_df: pd.DataFrame, events: list[dict], events_truncated: bool) -> None:
    """Registro de leituras do equipamento: colunas, ordem e filtros escolhidos pelo usuario."""
    frame = build_readings_frame(hist_df, events)
    if frame.empty:
        st.info("Sem leituras no periodo selecionado.")
        return
    all_columns = list(frame.columns)
    st.caption(
        f"{len(frame)} leitura(s) no periodo. Cada linha traz o que foi gerado a partir da leitura: "
        f"risco, qualidade, eventos e explicacao. Horarios no fuso {LOCAL_TZ_LABEL}."
    )
    if len(frame) >= 5000:
        st.caption("Limite de 5000 leituras atingido: reduza o periodo para ver as mais antigas.")
    if events_truncated:
        st.caption("Ha mais de 1000 eventos no periodo; leituras mais antigas podem aparecer sem eventos.")

    with st.expander("Colunas, ordem e filtros", expanded=False):
        preset_names = list(READING_PRESETS)
        sanitize_choice_state("keep_rd_preset", preset_names)
        preset = st.selectbox("Conjunto de colunas", preset_names, key="keep_rd_preset")
        preset_columns = READING_PRESETS[preset]
        default_columns = all_columns if preset_columns is None else [c for c in preset_columns if c in all_columns]
        columns_key = f"keep_rd_columns_{preset}"
        sanitize_choice_state(columns_key, all_columns, multiple=True)
        st.session_state.setdefault(columns_key, default_columns)
        visible = st.multiselect(
            "Colunas visiveis (adicione ou remova)",
            all_columns,
            format_func=reading_label,
            key=columns_key,
        )

        f1, f2, f3 = st.columns(3)
        sort_options = visible or all_columns
        sanitize_choice_state("keep_rd_sort", sort_options)
        st.session_state.setdefault("keep_rd_sort", "recorded_at" if "recorded_at" in sort_options else sort_options[0])
        sort_column = f1.selectbox("Ordenar por", sort_options, format_func=reading_label, key="keep_rd_sort")
        sanitize_choice_state("keep_rd_order", ["Mais recentes primeiro", "Mais antigas primeiro"])
        st.session_state.setdefault("keep_rd_order", "Mais recentes primeiro")
        newest_first = f2.radio(
            "Ordem", ["Mais recentes primeiro", "Mais antigas primeiro"], key="keep_rd_order"
        ) == "Mais recentes primeiro"
        st.session_state.setdefault("keep_rd_only_events", False)
        only_events = f3.checkbox("So leituras com eventos", key="keep_rd_only_events")

        g1, g2, g3, g4 = st.columns(4)
        filtered = frame
        for column, widget, label in (
            ("risk_level", g1, "Nivel de risco"),
            ("ingestion_mode", g2, "Origem do envio"),
            ("data_quality_status", g3, "Qualidade do dado"),
            ("gravidade_max", g4, "Gravidade do evento"),
        ):
            if column in filtered.columns:
                options = sorted({str(value) for value in filtered[column].dropna()})
                if options:
                    key = f"keep_rd_f_{column}"
                    sanitize_choice_state(key, options, multiple=True)
                    chosen = widget.multiselect(label, options, key=key)
                    if chosen:
                        filtered = filtered[filtered[column].astype(str).isin(chosen)]
        if only_events:
            filtered = filtered[filtered["eventos"] > 0]
        st.session_state.setdefault("keep_rd_search", "")
        search = st.text_input("Buscar texto (eventos, explicacao, problemas)", key="keep_rd_search")
        if search.strip():
            text_columns = [c for c in ("tipos_de_evento", "descricao_eventos", "explicacao", "data_quality_issues") if c in filtered.columns]
            needle = search.strip().lower()
            mask = pd.Series(False, index=filtered.index)
            for column in text_columns:
                mask |= filtered[column].astype(str).str.lower().str.contains(needle, regex=False, na=False)
            filtered = filtered[mask]

    shown_columns = [c for c in (visible or default_columns) if c in filtered.columns]
    if not shown_columns:
        st.info("Escolha ao menos uma coluna.")
        return
    if sort_column in filtered.columns:
        try:
            filtered = filtered.sort_values(sort_column, ascending=not newest_first, na_position="last", kind="stable")
        except TypeError:
            filtered = filtered.sort_values(
                sort_column, ascending=not newest_first, na_position="last", kind="stable", key=lambda col: col.astype(str)
            )
    table = filtered[shown_columns].rename(columns={c: reading_label(c) for c in shown_columns})
    st.caption(f"Exibindo {len(table)} de {len(frame)} leitura(s). Clique no cabecalho da coluna para reordenar.")
    st.dataframe(table, use_container_width=True, hide_index=True, height=460)
    st.download_button(
        "Baixar CSV (colunas e filtros atuais)",
        table.to_csv(index=False).encode("utf-8-sig"),
        file_name="leituras_telemetria.csv",
        mime="text/csv",
        key="rd_download",
    )



if active_page == "Telemetria":
    st.markdown("### Central de Telemetria")

    ok_equipment, equipment_rows = get_json(EQUIPMENTS_URL)
    equipment_df = filter_df_by_farm(any_to_dataframe(equipment_rows if ok_equipment else []))
    if equipment_df.empty:
        st.info(
            "Nenhum equipamento disponivel para telemetria"
            + (f" na fazenda {selected_farm_caption()}." if (st.session_state.get("_farm_ctx") or {}).get("farm_id") is not None else ".")
        )
    else:
        labels = [
            f"{int(row['equipment_id'])} - {row.get('equipment_name', row.get('name', 'Equipamento'))}"
            for _, row in equipment_df.iterrows()
        ]
        period_labels = list(TELEMETRY_PERIOD_CHOICES)
        sanitize_choice_state("keep_tel_equipment", labels)
        sanitize_choice_state("keep_tel_period", period_labels)
        st.session_state.setdefault("keep_tel_period", "Ultima hora")
        st.session_state.setdefault("keep_tel_auto", False)
        st.session_state.setdefault("keep_tel_seconds", 5)
        for _section_id, _section_label, _section_default in TELEMETRY_PANEL_SECTIONS:
            st.session_state.setdefault(f"keep_tp_{_section_id}", _section_default)

        top = st.columns([2.4, 1.9, 0.9, 1.5], vertical_alignment="bottom")
        selected_label = top[0].selectbox("Equipamento", labels, key="keep_tel_equipment")
        selected_equipment_id = int(selected_label.split(" - ")[0])
        period_label = top[1].selectbox("Periodo", period_labels, key="keep_tel_period")
        period_code = TELEMETRY_PERIOD_CHOICES[period_label]
        auto_refresh = top[2].checkbox("Auto", key="keep_tel_auto", help="Atualiza so a area de leituras.")

        with top[3].popover("Personalizar painel", use_container_width=True):
            st.caption("Escolha o que aparece nesta tela.")
            show = {}
            for section_id, section_label, section_default in TELEMETRY_PANEL_SECTIONS:
                show[section_id] = st.checkbox(section_label, key=f"keep_tp_{section_id}")
            refresh_seconds = st.number_input(
                "Atualizar a cada (s)", min_value=2, max_value=60, step=1, key="keep_tel_seconds"
            )
            st.button("Restaurar padrao", on_click=reset_telemetry_panel, key="tp_reset")

        start_iso = end_iso = None
        range_ready = True
        if period_code == "custom":
            today_local = datetime.now(LOCAL_TZ).date()
            st.session_state.setdefault("keep_tel_range", (today_local - timedelta(days=1), today_local))
            picked = st.date_input(
                "Intervalo (horario local)",
                max_value=today_local,
                key="keep_tel_range",
            )
            days = list(picked) if isinstance(picked, (list, tuple)) else [picked]
            if len(days) == 2:
                start_dt = datetime.combine(days[0], time_cls.min).replace(tzinfo=LOCAL_TZ)
                end_dt = datetime.combine(days[1], time_cls.max).replace(tzinfo=LOCAL_TZ)
                start_iso = start_dt.astimezone(timezone.utc).isoformat()
                end_iso = end_dt.astimezone(timezone.utc).isoformat()
            else:
                range_ready = False
                st.info("Escolha a data final do intervalo.")

        def _render_telemetry_live(equipment_id, period_code, start_iso, end_iso, show):
            # Fragmento: com "Auto" ligado, so este bloco recarrega a cada N segundos
            # (st.fragment run_every), sem time.sleep/st.rerun nem travar o resto da pagina.
            base_url = f"{API_BASE_URL}/api/v1/equipments/{equipment_id}"
            history_url = f"{base_url}/telemetry/history?period={period_code}&limit=5000"
            if period_code == "custom" and start_iso and end_iso:
                history_url += f"&start={quote(start_iso, safe='')}&end={quote(end_iso, safe='')}"
            events_period = period_code if period_code in TELEMETRY_EVENT_PERIODS else "all"
            ok_latest, latest_data = get_json(f"{base_url}/telemetry/latest")
            ok_history, history_data = get_json(history_url)
            ok_events, events_data = get_json(f"{base_url}/iot-events?period={events_period}&limit=1000")

            latest = latest_data.get("telemetry") if ok_latest and isinstance(latest_data, dict) else None
            hist_df = (
                any_to_dataframe(history_data.get("history", [])) if ok_history and isinstance(history_data, dict) else pd.DataFrame()
            )
            events = events_data.get("events", []) if ok_events and isinstance(events_data, dict) else []

            if not latest:
                st.info("Ainda nao ha telemetria IoT para este equipamento.")
            else:
                if show.get("status"):
                    status_text = str(latest_data.get("device_status", latest.get("telemetry_status", "-")))
                    status_tone = (
                        "ok" if status_text.lower() in {"live", "online", "active"}
                        else "warn" if status_text.lower() == "stale" else "bad"
                    )
                    risk_score = _finite(latest.get("risk_score"))
                    render_mini_tiles(
                        [
                            ("ESP32", latest.get("device_id", "-"), ""),
                            ("Status", status_text, status_tone),
                            ("Ultimo dado", "ha " + format_duration_hm(latest.get("telemetry_age_seconds") or 0), ""),
                            (
                                "Risco",
                                f"{risk_score:.0f} - {latest.get('risk_level', '-')}" if risk_score is not None else str(latest.get("risk_level", "-")),
                                risk_tone(latest.get("risk_level")),
                            ),
                            ("Qualidade do dado", latest.get("data_quality_status", "-"), ""),
                        ]
                    )
                if show.get("trator"):
                    st.markdown("#### Movimento do trator")
                    render_tractor_3d(latest, hist_df)
                if show.get("sensores"):
                    if latest.get("distance_cm") is None and latest.get("obstacle_detected") is False:
                        distance_text = "Fora de alcance"
                    else:
                        distance_text = format_measurement(latest.get("distance_cm"), "cm")
                    render_mini_tiles(
                        [
                            ("Inclinacao", format_measurement(latest.get("inclination_deg"), "deg"), ""),
                            (
                                "Pitch / Roll",
                                f"{format_measurement(latest.get('pitch'), 'deg')} / {format_measurement(latest.get('roll'), 'deg')}",
                                "",
                            ),
                            ("Obstaculo (ultrassom)", distance_text, "bad" if latest.get("obstacle_detected") else ""),
                            ("Impacto", "SIM" if latest.get("possible_impact") else "NAO", "bad" if latest.get("possible_impact") else "ok"),
                            ("Movimento anomalo", format_measurement(latest.get("movement_anomaly_score"), "", 2), ""),
                            ("Bateria", format_measurement(latest.get("battery_voltage"), "V", 2), ""),
                        ]
                    )
                if show.get("ambiente"):
                    st.markdown("#### Ambiente (BME280)")
                    render_mini_tiles(
                        [
                            ("Temperatura", format_measurement(latest.get("temperature_c"), "C"), ""),
                            ("Umidade", format_measurement(latest.get("humidity_pct"), "%"), ""),
                            ("Pressao", format_measurement(latest.get("pressure_hpa"), "hPa"), ""),
                            ("Altitude", format_measurement(latest.get("altitude_m"), "m"), ""),
                        ]
                    )
                if show.get("movimento_cru"):
                    st.markdown("#### Aceleracao e giroscopio")
                    render_mini_tiles(
                        [
                            ("Accel X", format_measurement(latest.get("accel_x"), "m/s2", 2), ""),
                            ("Accel Y", format_measurement(latest.get("accel_y"), "m/s2", 2), ""),
                            ("Accel Z", format_measurement(latest.get("accel_z"), "m/s2", 2), ""),
                            ("Accel total", format_measurement(latest.get("acceleration_magnitude"), "m/s2", 2), ""),
                            ("Giro X", format_measurement(latest.get("gyro_x"), "dps", 1), ""),
                            ("Giro Y", format_measurement(latest.get("gyro_y"), "dps", 1), ""),
                            ("Giro Z", format_measurement(latest.get("gyro_z"), "dps", 1), ""),
                            ("Giro total", format_measurement(latest.get("gyro_magnitude"), "dps", 1), ""),
                        ]
                    )
                if show.get("gps_energia"):
                    st.markdown("#### GPS e bateria")
                    render_mini_tiles(
                        [
                            ("Bateria", format_measurement(latest.get("battery_voltage"), "V", 2), ""),
                            ("Precisao GPS", format_measurement(latest.get("gps_accuracy_m"), "m"), ""),
                            ("Satelites GPS", latest.get("gps_satellites") if latest.get("gps_satellites") is not None else "N/D", ""),
                            ("Latitude", format_measurement(latest.get("latitude"), "", 6), ""),
                            ("Longitude", format_measurement(latest.get("longitude"), "", 6), ""),
                        ]
                    )
                if show.get("qualidade"):
                    st.markdown("#### Qualidade do dado")
                    render_mini_tiles(
                        [
                            ("Qualidade", latest.get("data_quality_status", "-"), ""),
                            ("Confianca", format_measurement(latest.get("confidence_score"), "%"), ""),
                            ("Qualidade do horario", latest.get("time_quality") or "N/D", ""),
                            ("Origem do envio", latest.get("ingestion_mode") or "N/D", ""),
                        ]
                    )
                    issues = latest.get("data_quality_issues") or []
                    if issues:
                        st.caption("Qualidade: " + " | ".join(str(issue) for issue in issues))
                    st.caption(
                        f"Recebido: {format_local_time(latest.get('received_at'))} ({LOCAL_TZ_LABEL}) | "
                        f"Origem: {'ESP32 fisico' if latest.get('iot_device_id') else 'legado'}"
                    )
                if show.get("ia"):
                    explanation = latest.get("explanation") or {}
                    st.markdown("#### Explicacao da IA")
                    if explanation:
                        st.info(explanation.get("summary", "Sem resumo."))
                        if explanation.get("recommendation"):
                            st.caption(f"Recomendacao: {explanation['recommendation']}")
                        factors = explanation.get("factors", [])
                        if factors:
                            st.dataframe(any_to_dataframe(factors), use_container_width=True)
                    else:
                        st.caption("Sem explicacao para a leitura mais recente.")

                if show.get("conectividade"):
                    render_connectivity_timeline(
                        latest.get("device_id"), period_code if period_code in TELEMETRY_PERIOD_HOURS else "24h"
                    )

            if not ok_history:
                show_api_error("Erro ao carregar historico de telemetria", history_data)
            elif hist_df.empty:
                st.info("Sem leituras no periodo selecionado.")
            else:
                time_col = "recorded_at" if "recorded_at" in hist_df.columns else "timestamp"
                if show.get("grafico"):
                    render_metric_explorer(hist_df, time_col, f"tel_{equipment_id}")
                    if "time_quality" in hist_df.columns:
                        approximate = int(hist_df["time_quality"].isin(["estimated", "unknown"]).sum())
                        if approximate:
                            st.caption(
                                f"{approximate} leitura(s) com horario estimado ou desconhecido "
                                "(coluna time_quality); o grafico as posiciona pelo horario registrado."
                            )
                if show.get("leituras"):
                    st.markdown("#### Leituras do equipamento")
                    render_readings_table(hist_df, events, events_truncated=len(events) >= 1000)

        if range_ready:
            live_args = (selected_equipment_id, period_code, start_iso, end_iso, show)
            if auto_refresh:
                st.fragment(run_every=int(refresh_seconds))(_render_telemetry_live)(*live_args)
            else:
                _render_telemetry_live(*live_args)


if active_page == "Equipamentos":
    if active_page == "Equipamentos":
        st.markdown("### Equipamentos e Dispositivos IoT")
        onboarding_message = st.session_state.pop("iot_onboarding_message", None)
        if onboarding_message:
            st.success(onboarding_message)

        ok_farms, farm_rows = get_json(FARMS_URL)
        if ok_farms:
            farm_df = filter_df_by_farm(any_to_dataframe(farm_rows), kind="farm")
            st.markdown("#### Fazendas")
            st.dataframe(farm_df, use_container_width=True)
        else:
            show_api_error("Erro ao carregar fazendas", farm_rows)
            farm_df = pd.DataFrame()

        ok_equipment, equipment_rows = get_json(EQUIPMENTS_URL)
        if ok_equipment:
            equipment_df = filter_df_by_farm(any_to_dataframe(equipment_rows))
            st.markdown("#### Equipamentos")
            st.dataframe(equipment_df, use_container_width=True)
        else:
            show_api_error("Erro ao carregar equipamentos", equipment_rows)
            equipment_df = pd.DataFrame()

        ok_devices, device_rows = get_json(IOT_DEVICES_URL)
        st.markdown("#### Dispositivos IoT")
        if ok_devices:
            devices_df = any_to_dataframe(device_rows)
            st.dataframe(devices_df, use_container_width=True)
        else:
            show_api_error("Erro ao carregar dispositivos", device_rows)
            devices_df = pd.DataFrame()

        if has_permission("farms.create"):
            with st.expander("Cadastrar fazenda", expanded=farm_df.empty):
                with st.form("create_farm_form"):
                    farm_col1, farm_col2 = st.columns(2)
                    with farm_col1:
                        farm_client = st.text_input("Cliente da fazenda", value="Cliente AgroGuardian")
                        farm_name = st.text_input("Nome da fazenda", value="Fazenda Principal")
                        farm_municipality = st.text_input("Municipio", value="Guarulhos")
                        farm_state = st.text_input("Estado", value="SP")
                        farm_region = st.text_input("Regiao", value="Guarulhos - SP")
                    with farm_col2:
                        farm_latitude = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=-23.455, format="%.7f")
                        farm_longitude = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=-46.533, format="%.7f")
                        farm_area = st.number_input("Area total (ha)", min_value=0.0, value=0.0, step=1.0)
                        farm_crop = st.text_input("Cultura principal", value="")
                    submit_farm = st.form_submit_button("Salvar fazenda")
                if submit_farm:
                    payload = {
                        "client_name": farm_client,
                        "name": farm_name,
                        "region": farm_region,
                        "latitude": float(farm_latitude),
                        "longitude": float(farm_longitude),
                        "municipality": farm_municipality or None,
                        "state": farm_state or None,
                        "country": "BR",
                        "total_area_ha": float(farm_area) if farm_area > 0 else None,
                        "main_crop": farm_crop or None,
                    }
                    ok_create_farm, farm_result = post_json(ADMIN_FARMS_URL, payload)
                    if ok_create_farm:
                        st.session_state["iot_onboarding_message"] = (
                            f"Fazenda criada com ID {farm_result.get('farm_id')}. Agora cadastre o equipamento."
                        )
                        st.rerun()
                    else:
                        show_api_error("Erro ao criar fazenda", farm_result)

        if has_permission("equipments.create"):
            with st.expander("Cadastrar equipamento", expanded=False):
                farm_options = []
                if not farm_df.empty:
                    farm_options = [
                        f"{int(row['farm_id'])} - {row.get('farm_name', 'Fazenda')}"
                        for _, row in farm_df.iterrows()
                    ]
                with st.form("create_equipment_form"):
                    eq_name = st.text_input("Nome", value="Trator 01")
                    eq_type = st.text_input("Tipo", value="Trator")
                    eq_client = st.text_input("Cliente", value="Cliente AgroGuardian")
                    eq_farm_label = st.selectbox(
                        "Fazenda vinculada",
                        farm_options or ["Cadastre uma fazenda primeiro"],
                    )
                    eq_model = st.text_input("Modelo", value="John Deere 6110J")
                    eq_year = st.number_input("Ano", min_value=1900, max_value=2100, value=2024, step=1)
                    eq_status = st.selectbox("Status", ["active", "inactive", "maintenance"], key="eq_status")
                    submit_eq = st.form_submit_button("Salvar equipamento", disabled=not farm_options)
                if submit_eq:
                    payload = {
                        "name": eq_name,
                        "equipment_type": eq_type,
                        "client_name": eq_client,
                        "farm_id": int(eq_farm_label.split(" - ")[0]),
                        "model": eq_model,
                        "year": int(eq_year),
                        "status": eq_status,
                    }
                    ok_create, create_result = post_json(ADMIN_EQUIPMENTS_URL, payload)
                    if ok_create:
                        st.session_state["iot_onboarding_message"] = (
                            f"Equipamento criado com ID {create_result.get('equipment_id')}. Agora cadastre o ESP32."
                        )
                        st.rerun()
                    else:
                        show_api_error("Erro ao criar equipamento", create_result)

        if has_permission("iot.devices.manage"):
            with st.expander("Cadastrar ESP32", expanded=False):
                equipment_options = []
                if not equipment_df.empty:
                    equipment_options = [
                        f"{int(row['equipment_id'])} - {row.get('equipment_name', row.get('name', 'Equipamento'))}"
                        for _, row in equipment_df.iterrows()
                    ]
                with st.form("create_device_form"):
                    dev_id = st.text_input("Device identifier", value="ESP32-TRATOR-001")
                    dev_name = st.text_input("Nome do dispositivo", value="ESP32 Trator 01")
                    dev_equipment_label = st.selectbox("Equipamento vinculado", equipment_options or ["1 - Equipamento 1"])
                    dev_firmware = st.text_input("Firmware", value="1.0.0")
                    dev_status = st.selectbox("Status inicial", ["offline", "online", "maintenance", "disabled"], key="dev_status")
                    submit_dev = st.form_submit_button("Gerar credencial", disabled=not equipment_options)
                if submit_dev:
                    payload = {
                        "device_identifier": dev_id,
                        "equipment_id": int(dev_equipment_label.split(" - ")[0]),
                        "name": dev_name,
                        "device_type": "ESP32",
                        "firmware_version": dev_firmware,
                        "status": dev_status,
                    }
                    ok_dev, dev_result = post_json(ADMIN_IOT_DEVICES_URL, payload)
                    if ok_dev:
                        st.success("ESP32 cadastrado. A API key aparece apenas agora.")
                        st.json(dev_result)
                        generated_key = dev_result.get("api_key")
                        generated_device_id = dev_result.get("device_id", dev_id)
                        if generated_key:
                            st.caption("Copie estas duas linhas para include/Secrets.h junto com seu Wi-Fi:")
                            st.code(
                                f'#define AGROGUARDIAN_DEVICE_ID "{generated_device_id}"\n'
                                f'#define AGROGUARDIAN_DEVICE_API_KEY "{generated_key}"',
                                language="cpp",
                            )
                    else:
                        show_api_error("Erro ao cadastrar ESP32", dev_result)

            if ok_devices and not devices_df.empty:
                with st.expander("Atualizar ou desativar ESP32", expanded=False):
                    device_options = devices_df["device_id"].astype(str).tolist()
                    selected_device = st.selectbox("Device ID", device_options, key="manage_device_select")
                    new_status = st.selectbox("Novo status", ["online", "offline", "maintenance", "disabled"], key="manage_device_status")
                    rotate_key = st.checkbox("Rotacionar API key", value=False)
                    revoke_key = st.checkbox("Revogar API key atual", value=False)
                    col_update, col_disable = st.columns(2)
                    if col_update.button("Atualizar dispositivo"):
                        ok_update, update_result = put_json(
                            f"{ADMIN_IOT_DEVICES_URL}/{selected_device}",
                            {"status": new_status, "rotate_api_key": rotate_key, "revoke_api_key": revoke_key},
                        )
                        if ok_update:
                            st.success("Dispositivo atualizado.")
                            st.json(update_result)
                        else:
                            show_api_error("Erro ao atualizar dispositivo", update_result)
                    if col_disable.button("Desativar dispositivo"):
                        ok_delete, delete_result = delete_json(f"{ADMIN_IOT_DEVICES_URL}/{selected_device}")
                        if ok_delete:
                            st.success("Dispositivo desativado.")
                            st.json(delete_result)
                        else:
                            show_api_error("Erro ao desativar dispositivo", delete_result)

if active_page == "Alertas e auditoria":
    if active_page == "Alertas e auditoria":
        st.markdown("### Alertas e auditoria")

        col_alerts, col_audit = st.columns(2)

        with col_alerts:
            ok_alerts, alerts_data = get_json(ALERTS_URL)
            st.markdown("#### Alertas recentes")

            if ok_alerts:
                alert_rows = filter_rows_by_farm(alerts_data) if isinstance(alerts_data, list) else alerts_data
                if isinstance(alert_rows, list) and alert_rows:
                    severity_counts: dict[str, int] = {}
                    for alert in alert_rows:
                        key = str(alert.get("severity", "low")).lower() if isinstance(alert, dict) else "low"
                        severity_counts[key] = severity_counts.get(key, 0) + 1
                    render_mini_tiles(
                        [
                            ("Total de alertas", len(alert_rows), ""),
                            ("Alta gravidade", severity_counts.get("high", 0), "bad" if severity_counts.get("high") else "ok"),
                            ("Media", severity_counts.get("medium", 0), "warn" if severity_counts.get("medium") else ""),
                            ("Baixa", severity_counts.get("low", 0), ""),
                        ]
                    )
                    if len(alert_rows) > 5:
                        with st.container(height=480):
                            render_alert_cards(alert_rows, limit=30)
                    else:
                        render_alert_cards(alert_rows, limit=5)
                else:
                    st.info("Nenhum alerta retornado.")
                df_alerts = any_to_dataframe(alert_rows)
                with st.expander(f"Todos os alertas registrados ({len(df_alerts)})", expanded=False):
                    if df_alerts.empty:
                        st.info("Nenhum alerta registrado.")
                    else:
                        st.dataframe(df_alerts, use_container_width=True, hide_index=True)
                        st.download_button(
                            "Baixar CSV dos alertas",
                            df_alerts.to_csv(index=False).encode("utf-8-sig"),
                            file_name="alertas.csv",
                            mime="text/csv",
                            key="alerts_download",
                        )
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

if active_page == "Políticas de alerta":
    if active_page == "Políticas de alerta":
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

if active_page == "Administracao":
    if active_page == "Administracao":
        st.markdown("### Administracao de usuarios")

        ok_roles, roles_data = get_json(ADMIN_ROLES_URL)
        ok_permissions, permissions_data = get_json(ADMIN_PERMISSIONS_URL)
        role_options = [row.get("name") for row in roles_data] if ok_roles and isinstance(roles_data, list) else []
        permission_options = [row.get("code") for row in permissions_data] if ok_permissions and isinstance(permissions_data, list) else []
        permission_descriptions = (
            {row.get("code"): row.get("description") or "" for row in permissions_data}
            if ok_permissions and isinstance(permissions_data, list)
            else {}
        )

        filter_cols = st.columns(4)
        user_q = filter_cols[0].text_input("Busca", key="admin_user_q")
        user_role_filter = filter_cols[1].selectbox("Role", [""] + role_options, key="admin_role_filter")
        user_status_filter = filter_cols[2].selectbox("Status", ["", "active", "inactive", "deleted"], key="admin_status_filter")
        refresh_users = filter_cols[3].button("Atualizar usuarios")

        query_params = []
        if user_q:
            query_params.append(f"q={user_q}")
        if user_role_filter:
            query_params.append(f"role={user_role_filter}")
        if user_status_filter:
            query_params.append(f"status={user_status_filter}")
        users_url = ADMIN_USERS_URL + (("?" + "&".join(query_params)) if query_params else "")
        ok_users, users_data = get_json(users_url)

        if ok_users:
            users_df = any_to_dataframe(users_data)
            st.dataframe(users_df, use_container_width=True)
        else:
            show_api_error("Erro ao carregar usuarios", users_data)
            users_df = pd.DataFrame()

        # Abas (e nao expanders) porque as listas de permissoes ja sao expanders e o Streamlit nao permite aninhar.
        admin_tab_new, admin_tab_edit = st.tabs(["Novo usuario", "Editar usuario"])

        with admin_tab_new:
            with st.form("admin_create_user_form"):
                c1, c2, c3 = st.columns(3)
                new_name = c1.text_input("Nome", value="Novo Usuario")
                new_username = c2.text_input("Login", value="novo.usuario")
                new_email = c3.text_input("Email", value="novo.usuario@agroguardian.ai")
                new_password = st.text_input("Senha inicial", type="password")
                new_roles = st.multiselect("Roles", role_options, default=["LEITURA"] if "LEITURA" in role_options else role_options[:1])
                add_permissions = render_permission_checklist(
                    "Permissoes adicionais",
                    "new_perm_add",
                    permission_options,
                    permission_descriptions,
                    help_text="Concedidas alem das que o perfil (role) ja inclui.",
                )
                remove_permissions = render_permission_checklist(
                    "Permissoes removidas",
                    "new_perm_remove",
                    permission_options,
                    permission_descriptions,
                    help_text="Retiradas do usuario mesmo que o perfil (role) as inclua.",
                )
                st.markdown("**Restringir acesso a dados (opcional)**")
                st.caption(
                    "Deixe em branco para o usuario ver todos os dados permitidos pelo perfil. "
                    "Preencha para limita-lo a um cliente, fazenda ou equipamento especifico; "
                    "administradores nao sao afetados."
                )
                scope_cols = st.columns(3)
                scope_client = scope_cols[0].text_input(
                    "Limitar ao cliente (nome)", value="", help="Ex.: nome do cliente/empresa dono das fazendas."
                )
                scope_farm = scope_cols[1].number_input(
                    "Limitar a fazenda (ID)", min_value=0, value=0, step=1, help="0 = sem restricao por fazenda."
                )
                scope_equipment = scope_cols[2].number_input(
                    "Limitar ao equipamento (ID)", min_value=0, value=0, step=1, help="0 = sem restricao por equipamento."
                )
                create_user_submit = st.form_submit_button("Criar usuario")
            if create_user_submit:
                scopes = []
                if scope_client or scope_farm or scope_equipment:
                    scopes.append(
                        {
                            "client_name": scope_client or None,
                            "farm_id": int(scope_farm) or None,
                            "equipment_id": int(scope_equipment) or None,
                        }
                    )
                payload = {
                    "name": new_name,
                    "username": new_username,
                    "email": new_email,
                    "password": new_password,
                    "roles": new_roles,
                    "permissions_add": add_permissions,
                    "permissions_remove": remove_permissions,
                    "access_scopes": scopes,
                    "is_active": True,
                    "status": "active",
                }
                ok_create, create_result = post_json(ADMIN_USERS_URL, payload)
                if ok_create:
                    st.success("Usuario criado.")
                    st.json(create_result)
                else:
                    show_api_error("Erro ao criar usuario", create_result)

        with admin_tab_edit:
            if not (ok_users and not users_df.empty):
                st.info("Nenhum usuario carregado para editar.")
            if ok_users and not users_df.empty:
                user_options = [
                    f"{int(row['id'])} - {row.get('username', '-')}"
                    for _, row in users_df.iterrows()
                    if "id" in row
                ]
                selected_user_label = st.selectbox("Usuario", user_options, key="admin_edit_user_select")
                selected_user_id = int(selected_user_label.split(" - ")[0])
                selected_row = users_df[users_df["id"] == selected_user_id].iloc[0].to_dict()
                current_roles = selected_row.get("roles") if isinstance(selected_row.get("roles"), list) else []
                current_permissions = selected_row.get("explicit_permissions_add") if isinstance(selected_row.get("explicit_permissions_add"), list) else []
                current_removed = selected_row.get("explicit_permissions_remove") if isinstance(selected_row.get("explicit_permissions_remove"), list) else []

                with st.form("admin_edit_user_form"):
                    e1, e2, e3 = st.columns(3)
                    edit_name = e1.text_input("Nome", value=str(selected_row.get("name", "")))
                    edit_username = e2.text_input("Login", value=str(selected_row.get("username", "")))
                    edit_email = e3.text_input("Email", value=str(selected_row.get("email", "")))
                    edit_roles = st.multiselect("Roles", role_options, default=current_roles)
                    edit_add_permissions = render_permission_checklist(
                        "Permissoes adicionadas",
                        f"edit_perm_add_{selected_user_id}",
                        permission_options,
                        permission_descriptions,
                        selected=current_permissions,
                        help_text="Concedidas alem das que o perfil (role) ja inclui.",
                    )
                    edit_remove_permissions = render_permission_checklist(
                        "Permissoes removidas",
                        f"edit_perm_remove_{selected_user_id}",
                        permission_options,
                        permission_descriptions,
                        selected=current_removed,
                        help_text="Retiradas do usuario mesmo que o perfil (role) as inclua.",
                    )
                    edit_active = st.checkbox("Ativo", value=bool(selected_row.get("is_active", True)))
                    edit_status = st.selectbox("Status", ["active", "inactive", "deleted"], index=0, key="edit_user_status")
                    edit_password = st.text_input("Nova senha opcional", type="password", key="edit_password_optional")
                    update_user_submit = st.form_submit_button("Salvar alteracoes")
                if update_user_submit:
                    payload = {
                        "name": edit_name,
                        "username": edit_username,
                        "email": edit_email,
                        "roles": edit_roles,
                        "permissions_add": edit_add_permissions,
                        "permissions_remove": edit_remove_permissions,
                        "is_active": edit_active,
                        "status": edit_status,
                    }
                    if edit_password:
                        payload["password"] = edit_password
                    ok_update, update_result = put_json(f"{ADMIN_USERS_URL}/{selected_user_id}", payload)
                    if ok_update:
                        st.success("Usuario atualizado.")
                        st.json(update_result)
                    else:
                        show_api_error("Erro ao atualizar usuario", update_result)

                action_cols = st.columns(2)
                reset_password = action_cols[0].text_input("Resetar senha para", type="password", key="reset_user_password")
                if action_cols[0].button("Resetar senha"):
                    ok_reset, reset_result = post_json(
                        f"{ADMIN_USERS_URL}/{selected_user_id}/reset-password",
                        {"new_password": reset_password},
                    )
                    if ok_reset:
                        st.success("Senha resetada.")
                    else:
                        show_api_error("Erro ao resetar senha", reset_result)

                if action_cols[1].button("Desativar/excluir usuario"):
                    ok_delete, delete_result = delete_json(f"{ADMIN_USERS_URL}/{selected_user_id}")
                    if ok_delete:
                        st.success("Usuario desativado.")
                        st.json(delete_result)
                    else:
                        show_api_error("Erro ao desativar usuario", delete_result)

if active_page == "Simulador de risco":
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
        sim_inclinacao = st.slider("Inclinação", 0, 90, 12, key="sim_inclinacao")
        sim_distancia_agua = st.slider("Distância da água", 0, 1000, 20, key="sim_distancia_agua")
        sim_velocidade = st.slider("Velocidade", 0, 200, 15, key="sim_velocidade")
        sim_historico = st.slider("Histórico de sinistros", 0, 20, 2, key="sim_historico")
        sim_chuva_mm = st.slider("Chuva base (mm)", 0, 100, 0, key="sim_chuva_mm")
        sim_solo_instavel = st.selectbox("Solo instável", [0, 1], key="sim_solo_instavel")
        sim_latitude = st.number_input("Latitude", value=-23.4550000, step=0.000001, format="%.7f", key="sim_latitude")
        sim_longitude = st.number_input("Longitude", value=-46.5330000, step=0.000001, format="%.7f", key="sim_longitude")

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
                step=0.000001,
                format="%.7f",
                key="sim2_latitude",
            )
            sim2_longitude = st.number_input(
                "Longitude simulada",
                value=float(sim_longitude),
                step=0.000001,
                format="%.7f",
                key="sim2_longitude",
            )

        sim2_clima = st.selectbox("Clima simulado", ["sol", "nublado", "chuva"], index=2, key="sim2_clima")
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

if active_page == "IA e ML":
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
