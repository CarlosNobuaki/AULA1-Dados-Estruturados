"""
Dashboard — Cotação do Milho CEPEA ESALQ/B3
============================================
Rodar:
    streamlit run dashboard.py
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score

# ─────────────────────────────────────────────────────────────
#  Configuração da página
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Milho CEPEA — Dashboard",
    page_icon="🌽",
    layout="wide",
)
st.title("🌽 Cotação do Milho — CEPEA ESALQ/B3")
st.caption("Fonte: CEPEA · Unidade: R$ / US$ por saca de 60 kg · Licença CC BY-NC 4.0")

XLSX = "cotacao_milho.xlsx"

# ─────────────────────────────────────────────────────────────
#  Carregar dados
# ─────────────────────────────────────────────────────────────
@st.cache_data
def carregar_dados():
    df_d = pd.read_excel(XLSX, sheet_name="Diario",      engine="openpyxl")
    df_a = pd.read_excel(XLSX, sheet_name="Media_Anual", engine="openpyxl")
    df_d["data"] = pd.to_datetime(df_d["data"], errors="coerce")
    df_a["data"] = pd.to_datetime(
        df_a["ano"].astype(str) + "-07-01", errors="coerce"
    )
    return df_d, df_a

df_diario, df_anual = carregar_dados()

# ─────────────────────────────────────────────────────────────
#  Sidebar — filtros e opções
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configurações")

    moeda = st.selectbox("Moeda", ["Ambas", "R$ (BRL)", "US$ (USD)"])

    horizonte = st.multiselect(
        "Horizonte de previsão (dias úteis)",
        options=[1, 2, 3, 4, 5, 6, 7, 10],
        default=[3, 6],
    )

    st.divider()
    st.subheader("Dados exibidos")
    exibir_anuais  = st.toggle("Médias anuais",    value=True)
    exibir_diarios = st.toggle("Cotações diárias", value=True)
    exibir_tendencia = st.toggle("Linha de tendência", value=True)
    exibir_previsoes = st.toggle("Previsões",       value=True)

    st.divider()
    if st.button("🔄 Recarregar dados"):
        st.cache_data.clear()
        st.rerun()

# ─────────────────────────────────────────────────────────────
#  Construir séries combinadas
# ─────────────────────────────────────────────────────────────
def construir_serie(col_anual, col_diario):
    return pd.concat([
        df_anual [["data", col_anual ]].rename(columns={col_anual:  "valor"}),
        df_diario[["data", col_diario]].rename(columns={col_diario: "valor"}),
    ], ignore_index=True).dropna().sort_values("data").reset_index(drop=True)

serie_rs  = construir_serie("valor_rs_medio",  "valor_rs")
serie_usd = construir_serie("valor_usd_medio", "valor_usd")

# ─────────────────────────────────────────────────────────────
#  Treinar modelos
# ─────────────────────────────────────────────────────────────
def treinar(serie):
    data_ref = serie["data"].min()
    s = serie.copy()
    s["dias"] = (s["data"] - data_ref).dt.days
    X = s["dias"].values.reshape(-1, 1)
    y = s["valor"].values
    m = LinearRegression().fit(X, y)
    return m, data_ref, s

modelo_rs,  ref_rs,  serie_rs  = treinar(serie_rs)
modelo_usd, ref_usd, serie_usd = treinar(serie_usd)

# ─────────────────────────────────────────────────────────────
#  Previsões
# ─────────────────────────────────────────────────────────────
def proximos_uteis(base, n):
    datas, d = [], base
    while len(datas) < n:
        d += pd.Timedelta(days=1)
        if d.weekday() < 5:
            datas.append(d)
    return datas

ultima = df_diario["data"].max()
previsoes = {}
for h in sorted(set(horizonte)):
    data_alvo = proximos_uteis(ultima, h)[-1]
    previsoes[h] = {
        "data":     data_alvo,
        "prev_rs":  modelo_rs .predict([[( data_alvo - ref_rs ).days]])[0],
        "prev_usd": modelo_usd.predict([[(data_alvo - ref_usd).days]])[0],
    }

# ─────────────────────────────────────────────────────────────
#  Métricas dos modelos
# ─────────────────────────────────────────────────────────────
def calc_metricas(modelo, serie):
    X = serie["dias"].values.reshape(-1, 1)
    y = serie["valor"].values
    yp = modelo.predict(X)
    return {
        "R²":            round(r2_score(y, yp),             4),
        "MAE":           round(mean_absolute_error(y, yp),   4),
        "Coef. angular": round(float(modelo.coef_[0]),        6),
        "Intercepto":    round(float(modelo.intercept_),      4),
    }

m_rs  = calc_metricas(modelo_rs,  serie_rs)
m_usd = calc_metricas(modelo_usd, serie_usd)

# ─────────────────────────────────────────────────────────────
#  KPIs — topo
# ─────────────────────────────────────────────────────────────
ultimo_rs  = df_diario["valor_rs"].iloc[-1]
ultimo_usd = df_diario["valor_usd"].iloc[-1]
delta_rs   = df_diario["var_dia_pct"].iloc[-1]
delta_usd  = (df_diario["valor_usd"].iloc[-1] - df_diario["valor_usd"].iloc[-2]) / df_diario["valor_usd"].iloc[-2] * 100

col1, col2, col3, col4 = st.columns(4)
col1.metric("Última cotação — R$",  f"R$ {ultimo_rs:.2f}",  f"{delta_rs:+.2f}% dia")
col2.metric("Última cotação — US$", f"US$ {ultimo_usd:.2f}", f"{delta_usd:+.2f}% dia")
col3.metric("R² modelo R$",  f"{m_rs['R²']:.4f}",  help="1.0 = ajuste perfeito")
col4.metric("R² modelo US$", f"{m_usd['R²']:.4f}", help="1.0 = ajuste perfeito")

st.divider()

# ─────────────────────────────────────────────────────────────
#  Função de gráfico Plotly
# ─────────────────────────────────────────────────────────────
def fazer_grafico(serie, modelo, data_ref, prev, simbolo, cor_diario, titulo):
    corte   = df_diario["data"].min()
    anuais  = serie[serie["data"] <  corte]
    diarios = serie[serie["data"] >= corte]

    fig = go.Figure()

    if exibir_anuais:
        fig.add_trace(go.Scatter(
            x=anuais["data"], y=anuais["valor"],
            mode="markers",
            marker=dict(color="#9E9E9E", size=12, symbol="diamond"),
            name="Médias anuais",
            hovertemplate="%{x|%d/%m/%Y}<br>" + simbolo + " %{y:.2f}<extra>Média anual</extra>",
        ))

    if exibir_diarios:
        fig.add_trace(go.Scatter(
            x=diarios["data"], y=diarios["valor"],
            mode="lines+markers",
            line=dict(color=cor_diario, width=2),
            marker=dict(size=7),
            name="Cotação diária",
            hovertemplate="%{x|%d/%m/%Y}<br>" + simbolo + " %{y:.2f}<extra>Diário</extra>",
        ))

    if exibir_tendencia:
        x_num = np.linspace(serie["dias"].min(), serie["dias"].max() + 15, 300)
        y_ten = modelo.predict(x_num.reshape(-1, 1))
        d_ten = [data_ref + pd.Timedelta(days=int(d)) for d in x_num]
        fig.add_trace(go.Scatter(
            x=d_ten, y=y_ten,
            mode="lines",
            line=dict(color="#E53935", width=2, dash="dot"),
            name="Tendência",
            hoverinfo="skip",
        ))

    if exibir_previsoes:
        cores_prev = ["#F57C00", "#6A1B9A", "#0288D1",
                      "#2E7D32", "#AD1457", "#00695C", "#4527A0", "#558B2F"]
        for idx, (h, p) in enumerate(prev.items()):
            val = p["prev_rs"] if simbolo == "R$" else p["prev_usd"]
            cor = cores_prev[idx % len(cores_prev)]
            fig.add_trace(go.Scatter(
                x=[p["data"]], y=[val],
                mode="markers+text",
                marker=dict(color=cor, size=14, symbol="diamond"),
                text=[f"+{h}d: {simbolo}{val:.2f}"],
                textposition="top right",
                name=f"Prev. +{h} dias úteis",
                hovertemplate=(
                    f"%{{x|%d/%m/%Y}}<br>{simbolo} %{{y:.2f}}"
                    f"<extra>Previsão +{h} dias úteis</extra>"
                ),
            ))

    # Linha vertical "hoje"
    fig.add_vline(
        x=ultima.timestamp() * 1000,
        line_dash="dash", line_color="#757575", line_width=1,
        annotation_text="Hoje", annotation_position="top",
    )

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=15)),
        xaxis_title="Data",
        yaxis_title=f"Preço ({simbolo} / saca 60 kg)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=450,
        template="plotly_white",
    )
    return fig

# ─────────────────────────────────────────────────────────────
#  Plotar gráficos conforme moeda selecionada
# ─────────────────────────────────────────────────────────────
mostrar_rs  = moeda in ("Ambas", "R$ (BRL)")
mostrar_usd = moeda in ("Ambas", "US$ (USD)")

if mostrar_rs and mostrar_usd:
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            fazer_grafico(serie_rs, modelo_rs, ref_rs, previsoes,
                          "R$", "#1565C0", "Preço em R$ (BRL)"),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            fazer_grafico(serie_usd, modelo_usd, ref_usd, previsoes,
                          "US$", "#00695C", "Preço em US$ (USD)"),
            use_container_width=True,
        )
elif mostrar_rs:
    st.plotly_chart(
        fazer_grafico(serie_rs, modelo_rs, ref_rs, previsoes,
                      "R$", "#1565C0", "Preço em R$ (BRL)"),
        use_container_width=True,
    )
elif mostrar_usd:
    st.plotly_chart(
        fazer_grafico(serie_usd, modelo_usd, ref_usd, previsoes,
                      "US$", "#00695C", "Preço em US$ (USD)"),
        use_container_width=True,
    )

st.divider()

# ─────────────────────────────────────────────────────────────
#  Tabela: Previsões
# ─────────────────────────────────────────────────────────────
st.subheader("📅 Tabela de Previsões")

df_prev = pd.DataFrame([
    {
        "Horizonte (dias úteis)": h,
        "Data alvo":              p["data"].strftime("%d/%m/%Y"),
        "Previsão R$ (BRL)":      round(p["prev_rs"],  2),
        "Previsão US$ (USD)":     round(p["prev_usd"], 2),
    }
    for h, p in previsoes.items()
])

col_filtro = st.columns([1, 1, 2])
with col_filtro[0]:
    min_h = int(df_prev["Horizonte (dias úteis)"].min()) if not df_prev.empty else 1
    max_h = int(df_prev["Horizonte (dias úteis)"].max()) if not df_prev.empty else 10
    filt_h = st.slider("Filtrar horizonte", min_h, max_h, (min_h, max_h)) if min_h < max_h else (min_h, max_h)

df_prev_filt = df_prev[
    df_prev["Horizonte (dias úteis)"].between(filt_h[0], filt_h[1])
]

st.dataframe(
    df_prev_filt,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Previsão R$ (BRL)":  st.column_config.NumberColumn(format="R$ %.2f"),
        "Previsão US$ (USD)": st.column_config.NumberColumn(format="US$ %.2f"),
    },
)

# ─────────────────────────────────────────────────────────────
#  Tabela: Métricas dos modelos
# ─────────────────────────────────────────────────────────────
st.subheader("📊 Métricas dos Modelos")

df_met = pd.DataFrame([
    {"Modelo": "BRL (R$)",  **m_rs},
    {"Modelo": "USD (US$)", **m_usd},
])

modelos_sel = st.multiselect(
    "Selecionar modelos",
    options=df_met["Modelo"].tolist(),
    default=df_met["Modelo"].tolist(),
)
metricas_sel = st.multiselect(
    "Selecionar métricas",
    options=["R²", "MAE", "Coef. angular", "Intercepto"],
    default=["R²", "MAE", "Coef. angular", "Intercepto"],
)

colunas = ["Modelo"] + [c for c in metricas_sel if c in df_met.columns]
df_met_filt = df_met[df_met["Modelo"].isin(modelos_sel)][colunas]

st.dataframe(
    df_met_filt,
    use_container_width=True,
    hide_index=True,
    column_config={
        "R²":            st.column_config.NumberColumn(format="%.4f"),
        "MAE":           st.column_config.NumberColumn(format="%.4f"),
        "Coef. angular": st.column_config.NumberColumn(format="%.6f"),
        "Intercepto":    st.column_config.NumberColumn(format="%.4f"),
    },
)

# ─────────────────────────────────────────────────────────────
#  Tabela: Histórico diário (com filtros)
# ─────────────────────────────────────────────────────────────
st.subheader("📋 Histórico Diário")

c_data1, c_data2, c_colunas = st.columns([1, 1, 2])
with c_data1:
    d_ini = st.date_input("De",  value=df_diario["data"].min().date())
with c_data2:
    d_fim = st.date_input("Até", value=df_diario["data"].max().date())
with c_colunas:
    colunas_disp = ["data", "valor_rs", "var_dia_pct", "var_mes_pct", "valor_usd"]
    cols_sel = st.multiselect("Colunas", colunas_disp, default=colunas_disp)

df_hist = df_diario[
    (df_diario["data"].dt.date >= d_ini) &
    (df_diario["data"].dt.date <= d_fim)
][cols_sel].sort_values("data", ascending=False)

st.dataframe(
    df_hist,
    use_container_width=True,
    hide_index=True,
    column_config={
        "data":        st.column_config.DateColumn("Data",         format="DD/MM/YYYY"),
        "valor_rs":    st.column_config.NumberColumn("Valor R$",   format="R$ %.2f"),
        "var_dia_pct": st.column_config.NumberColumn("Var. Dia %", format="%.2f%%"),
        "var_mes_pct": st.column_config.NumberColumn("Var. Mês %", format="%.2f%%"),
        "valor_usd":   st.column_config.NumberColumn("Valor US$",  format="US$ %.2f"),
    },
)

# ─────────────────────────────────────────────────────────────
#  Tabela: Médias anuais
# ─────────────────────────────────────────────────────────────
st.subheader("📆 Médias Anuais")

anos_disp = sorted(df_anual["ano"].tolist())
anos_sel  = st.multiselect("Selecionar anos", anos_disp, default=anos_disp)

df_anual_filt = df_anual[df_anual["ano"].isin(anos_sel)][
    ["ano", "valor_rs_medio", "valor_usd_medio"]
]
st.dataframe(
    df_anual_filt,
    use_container_width=True,
    hide_index=True,
    column_config={
        "ano":             st.column_config.NumberColumn("Ano",           format="%d"),
        "valor_rs_medio":  st.column_config.NumberColumn("Média R$",      format="R$ %.2f"),
        "valor_usd_medio": st.column_config.NumberColumn("Média US$",     format="US$ %.2f"),
    },
)

# ─────────────────────────────────────────────────────────────
#  Rodapé
# ─────────────────────────────────────────────────────────────
st.divider()
st.caption(
    f"Última atualização dos dados: {ultima.strftime('%d/%m/%Y')}  · "
    "Atualização automática: toda segunda-feira às 8h (crontab)  · "
    "Para atualizar agora: `python crawler.py`"
)
