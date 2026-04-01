import streamlit as st
import requests
import pandas as pd
import os

st.set_page_config(page_title="AgroGuardian AI", layout="wide")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_URL = f"{API_BASE_URL}/api/v1/risk/predict"

st.title("🌱 AgroGuardian AI")
st.subheader("Plataforma Inteligente de Prevenção de Sinistros Agrícolas")

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

# Valores-base; a API pode enriquecer com clima real
clima_base = st.sidebar.selectbox("Clima base", ["sol", "nublado", "chuva"], index=0)
chuva_mm_base = st.sidebar.slider("Chuva base (mm)", 0, 100, 0)

if st.button("Calcular risco"):
    dados = {
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
        "longitude": float(longitude)
    }

    try:
        response = requests.post(API_URL, json=dados, timeout=30)

        if response.status_code == 200:
            resultado = response.json()

            st.success("Predição realizada com sucesso")

            col1, col2, col3 = st.columns(3)
            col1.metric("Risk Score", resultado.get("risk_score", "-"))
            col2.metric("Nível de risco", resultado.get("risk_label", "-"))
            col3.metric("Alerta", resultado.get("alert_level", "-"))

            risk_score = float(resultado.get("risk_score", 0))

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
                st.warning(f"Clima externo indisponível. Fallback aplicado: {weather.get('error')}")

            st.subheader("Alertas")
            alertas = resultado.get("alerts", [])
            if alertas:
                for alerta in alertas:
                    severidade = str(alerta.get("severity", "")).lower()
                    mensagem = alerta.get("message", "-")

                    if severidade == "high":
                        st.error(mensagem)
                    elif severidade == "medium":
                        st.warning(mensagem)
                    else:
                        st.info(mensagem)
            else:
                st.info("Nenhum alerta retornado.")

            st.subheader("Recomendação")
            st.info(resultado.get("recommendation", "Sem recomendação"))

            st.subheader("Mapa da operação")
            mapa_df = pd.DataFrame(
                [{"lat": float(latitude), "lon": float(longitude)}]
            )
            st.map(mapa_df)

            st.subheader("Gráfico de fatores de risco")
            explicacao = resultado.get("explanation", {})
            if explicacao and isinstance(explicacao, dict):
                grafico_df = pd.DataFrame(
                    {
                        "Fator": list(explicacao.keys()),
                        "Impacto": list(explicacao.values())
                    }
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
            st.error(f"Erro na API: {response.status_code}")

            content_type = response.headers.get("content-type", "")

            if "text/html" in content_type:
                st.warning(
                    "A API pode estar indisponível temporariamente ou acordando no plano gratuito do Render. "
                    "Espere alguns segundos e tente novamente."
                )
            else:
                try:
                    st.json(response.json())
                except Exception:
                    st.write(response.text)

    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão com a API: {e}")