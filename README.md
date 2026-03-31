# AgroGuardian AI

Plataforma inteligente de prevenção de sinistros agrícolas com:
- **Risk AI**: score de risco de 0 a 100.
- **Smart Alerts**: alertas preventivos para operador e gestor.
- **Safe Route AI**: recomendação de rota mais segura.
- **Risk Map**: mapa de risco por zona da fazenda.
- **Sompo Analytics**: painel executivo com ranking, tendências, auditoria e explicações.

## Por que estas tecnologias
- **FastAPI**: escolhida para a API central porque é rápida, moderna e gera documentação automática em Swagger/ReDoc. Isso deixa o projeto com aparência profissional e facilita a demonstração.
- **Streamlit**: escolhida para o dashboard porque permite criar interface interativa com pouco código, ideal para MVP acadêmico e apresentação executiva.
- **XGBoost + scikit-learn**: XGBoost é forte em dados tabulares; scikit-learn entra como base para treino, métricas, fallback e compatibilidade.
- **OpenWeather**: usado para clima em tempo real quando houver chave de API; sem chave, o sistema usa fallback para continuar funcionando no MVP.
- **OpenStreetMap + Folium**: usados para mapa porque são livres, visuais e baratos para um projeto acadêmico.
- **PostgreSQL**: banco relacional profissional para histórico, auditoria, previsões, alertas e relatórios.
- **Render**: plataforma de deploy escolhida porque conecta o repositório GitHub e faz deploy automático a cada atualização do código.

## Arquitetura
Entrada de dados (telemetria, clima, mapas, histórico) -> API central -> motor de risco -> alertas e explicações -> dashboard Sompo / cliente / operador.

## Como rodar localmente

### 1) Criar ambiente e instalar dependências
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
```

### 2) Configurar variáveis
Copie `.env.example` para `.env` e ajuste, se quiser.

### 3) Subir a API
```bash
uvicorn backend.main:app --reload
```

A documentação automática aparece em:
- `/docs`
- `/redoc`

### 4) Subir o dashboard
Em outro terminal:
```bash
streamlit run dashboard/app.py
```

## Deploy no Render
1. Suba o projeto para o GitHub.
2. Crie dois serviços web no Render usando o mesmo repositório:
   - `agroguardian-api`
   - `agroguardian-dashboard`
3. Configure `DATABASE_URL` no serviço da API.
4. Configure `API_BASE_URL` no serviço do dashboard apontando para a URL pública da API.
5. Conecte o Render ao GitHub e ative deploy automático.

## O que o projeto entrega
- Score de risco por equipamento, fazenda, região e operação.
- Alertas por proximidade de água, chuva, velocidade e terreno inclinado.
- Recomendações práticas.
- Mapa com zonas de atenção.
- Explicação dos fatores de risco.
- Auditoria completa das previsões.
- Ranking executivo para a Sompo.
- Simulador de cenário "e se chover amanhã?".
