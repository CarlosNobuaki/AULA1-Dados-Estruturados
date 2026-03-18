"""
Regressão Linear — Preço do Milho CEPEA ESALQ/B3
=================================================
Fonte   : cotacao_milho.xlsx  (crawler.py)
Modelos : dois modelos independentes — R$ e US$
Predição: 3 e 6 dias úteis à frente

Estratégia de combinação de dados
----------------------------------
A série é construída em dois níveis:
  1. Médias anuais (aba Media_Anual) → representam uma data de referência
     fixa por ano (01/07 do ano — ponto médio anual), funcionando como
     âncora de tendência de longo prazo.
  2. Cotações diárias (aba Diario) → os 15 dias úteis mais recentes,
     que capturam a tendência de curto prazo.

Ambos os conjuntos são concatenados, ordenados por data e usados para
treinar um único modelo de regressão linear (dias corridos vs. preço).
"""

import matplotlib
matplotlib.use("Agg")   # backend sem janela (não bloqueia o terminal)
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error

# ─────────────────────────────────────────────────────────────
#  1. Carregar dados
# ─────────────────────────────────────────────────────────────
XLSX = "/home/carlos-nobuaki/Synapse/dados_estruturados/cotacao_milho.xlsx"
DIAS_UTEIS_PREVISAO = [3, 6]  # horizontes de predição

df_diario = pd.read_excel(XLSX, sheet_name="Diario",      engine="openpyxl")
df_anual  = pd.read_excel(XLSX, sheet_name="Media_Anual", engine="openpyxl")

df_diario["data"] = pd.to_datetime(df_diario["data"], errors="coerce")

# Médias anuais: data de referência = 1º de julho de cada ano (ponto médio)
df_anual["data"] = pd.to_datetime(
    df_anual["ano"].astype(str) + "-07-01", errors="coerce"
)

# ─────────────────────────────────────────────────────────────
#  2. Construir série combinada (longo prazo + curto prazo)
# ─────────────────────────────────────────────────────────────
serie_rs = pd.concat([
    df_anual [["data", "valor_rs_medio" ]].rename(columns={"valor_rs_medio":  "valor"}),
    df_diario[["data", "valor_rs"       ]].rename(columns={"valor_rs":        "valor"}),
], ignore_index=True).dropna().sort_values("data").reset_index(drop=True)

serie_usd = pd.concat([
    df_anual [["data", "valor_usd_medio"]].rename(columns={"valor_usd_medio": "valor"}),
    df_diario[["data", "valor_usd"      ]].rename(columns={"valor_usd":       "valor"}),
], ignore_index=True).dropna().sort_values("data").reset_index(drop=True)

# ─────────────────────────────────────────────────────────────
#  3. Treinar modelos
# ─────────────────────────────────────────────────────────────
def treinar_modelo(serie: pd.DataFrame):
    """Treina regressão linear com dias corridos como variável independente."""
    data_ref = serie["data"].min()
    serie = serie.copy()
    serie["dias"] = (serie["data"] - data_ref).dt.days
    X = serie["dias"].values.reshape(-1, 1)   # sempre numpy array
    y = serie["valor"].values
    modelo = LinearRegression()
    modelo.fit(X, y)
    return modelo, data_ref, serie

modelo_rs,  data_ref_rs,  serie_rs  = treinar_modelo(serie_rs)
modelo_usd, data_ref_usd, serie_usd = treinar_modelo(serie_usd)

# ─────────────────────────────────────────────────────────────
#  4. Gerar previsões para 3 e 6 dias úteis
# ─────────────────────────────────────────────────────────────
def proximos_dias_uteis(data_base: pd.Timestamp, n: int) -> list[pd.Timestamp]:
    """Retorna as próximas n datas úteis após data_base (seg–sex)."""
    datas = []
    d = data_base
    while len(datas) < n:
        d += pd.Timedelta(days=1)
        if d.weekday() < 5:   # 0=seg … 4=sex
            datas.append(d)
    return datas

ultima_data = df_diario["data"].max()

previsoes = {}
for horizonte in DIAS_UTEIS_PREVISAO:
    datas_futuras = proximos_dias_uteis(ultima_data, horizonte)
    data_alvo = datas_futuras[-1]

    dias_rs  = (data_alvo - data_ref_rs ).days
    dias_usd = (data_alvo - data_ref_usd).days

    prev_rs  = modelo_rs .predict(np.array([[dias_rs ]]))[0]
    prev_usd = modelo_usd.predict(np.array([[dias_usd]]))[0]

    previsoes[horizonte] = {
        "data":     data_alvo,
        "prev_rs":  prev_rs,
        "prev_usd": prev_usd,
    }

# ─────────────────────────────────────────────────────────────
#  5. Métricas
# ─────────────────────────────────────────────────────────────
def metricas(modelo, serie):
    y_real = serie["valor"].values
    y_pred = modelo.predict(serie["dias"].values.reshape(-1, 1))
    return {
        "R²":             round(r2_score(y_real, y_pred),          4),
        "MAE":            round(mean_absolute_error(y_real, y_pred), 4),
        "Coef. angular":  round(float(modelo.coef_[0]),              6),
        "Intercepto":     round(float(modelo.intercept_),            4),
    }

m_rs  = metricas(modelo_rs,  serie_rs)
m_usd = metricas(modelo_usd, serie_usd)

# ─────────────────────────────────────────────────────────────
#  6. Imprimir resultados
# ─────────────────────────────────────────────────────────────
print("=" * 55)
print("  REGRESSÃO LINEAR — MILHO CEPEA ESALQ/B3")
print("=" * 55)

print("\n📊 Métricas do modelo R$:")
for k, v in m_rs.items():
    print(f"   {k:20s}: {v:.4f}")

print("\n📊 Métricas do modelo US$:")
for k, v in m_usd.items():
    print(f"   {k:20s}: {v:.4f}")

print("\n📅 Previsões (saca 60 kg):")
print(f"   {'Horizonte':<12} {'Data alvo':<14} {'R$ (BRL)':<12} {'US$ (USD)'}")
print(f"   {'─'*12} {'─'*13} {'─'*11} {'─'*10}")
for h, p in previsoes.items():
    print(f"   {h} dias úteis  {p['data'].strftime('%d/%m/%Y')}    "
          f"R$ {p['prev_rs']:>7.2f}    US$ {p['prev_usd']:>6.2f}")

# ─────────────────────────────────────────────────────────────
#  7. Gráficos
# ─────────────────────────────────────────────────────────────
CORES = {
    "real_anual":  "#9E9E9E",
    "real_diario": "#1565C0",
    "tendencia":   "#E53935",
    "prev_3":      "#F57C00",
    "prev_6":      "#6A1B9A",
}

def plotar(serie, modelo, data_ref, previsoes, moeda, simbolo, cor_diario):
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    # Separa pontos anuais e diários para plotar com estilos distintos
    corte = df_diario["data"].min()
    anuais  = serie[serie["data"] <  corte]
    diarios = serie[serie["data"] >= corte]

    ax.scatter(anuais["data"],  anuais["valor"],
               color=CORES["real_anual"],  s=80, zorder=3,
               label="Médias anuais (referência)")
    ax.scatter(diarios["data"], diarios["valor"],
               color=cor_diario, s=60, zorder=4,
               label="Cotações diárias")

    # Linha de tendência sobre toda a série
    x_line = np.linspace(serie["dias"].min(), serie["dias"].max(), 300)
    y_line = modelo.predict(x_line.reshape(-1, 1))
    datas_line = [data_ref + pd.Timedelta(days=int(d)) for d in x_line]
    ax.plot(datas_line, y_line,
            color=CORES["tendencia"], linewidth=2, label="Linha de tendência")

    # Pontos de previsão
    mapa_cores_prev = {3: CORES["prev_3"], 6: CORES["prev_6"]}
    for h, p in previsoes.items():
        chave = f"prev_rs" if moeda == "BRL" else "prev_usd"
        val = p[chave]
        ax.scatter(p["data"], val,
                   color=mapa_cores_prev[h], s=140, zorder=5,
                   marker="D")
        ax.annotate(
            f"+{h}d\n{simbolo}{val:.2f}",
            xy=(p["data"], val),
            xytext=(10, 12), textcoords="offset points",
            fontsize=9, color=mapa_cores_prev[h],
            arrowprops=dict(arrowstyle="->", color=mapa_cores_prev[h]),
        )

    # Linha vertical separando histórico de futuro
    ax.axvline(df_diario["data"].max(), color="#757575",
               linestyle="--", linewidth=1, alpha=0.7, label="Hoje")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b/%Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.xticks(rotation=30, ha="right")

    _X_plot = serie["dias"].values.reshape(-1, 1)
    titulo = (f"Milho CEPEA ESALQ/B3 — Previsão em {moeda}\n"
              f"R² = {r2_score(serie['valor'], modelo.predict(_X_plot)):.4f}  |  "
              f"MAE = {mean_absolute_error(serie['valor'], modelo.predict(_X_plot)):.2f}")
    ax.set_title(titulo, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel("Data", fontsize=11)
    ax.set_ylabel(f"Preço ({simbolo} / saca 60 kg)", fontsize=11)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    plt.tight_layout()
    return fig

fig_rs  = plotar(serie_rs,  modelo_rs,  data_ref_rs,  previsoes, "BRL", "R$",  CORES["real_diario"])
fig_usd = plotar(serie_usd, modelo_usd, data_ref_usd, previsoes, "USD", "US$", "#00695C")

FIG_RS  = "/home/carlos-nobuaki/Synapse/dados_estruturados/grafico_brl.png"
FIG_USD = "/home/carlos-nobuaki/Synapse/dados_estruturados/grafico_usd.png"
fig_rs .savefig(FIG_RS,  dpi=150, bbox_inches="tight")
fig_usd.savefig(FIG_USD, dpi=150, bbox_inches="tight")
print(f"\n📈 Gráficos salvos:\n   {FIG_RS}\n   {FIG_USD}")

# ─────────────────────────────────────────────────────────────
#  8. Salvar métricas e previsões no Excel
# ─────────────────────────────────────────────────────────────
df_metricas = pd.DataFrame([
    {"Modelo": "BRL (R$)",  **m_rs},
    {"Modelo": "USD (US$)", **m_usd},
])

df_previsoes = pd.DataFrame([
    {
        "Horizonte (dias úteis)": h,
        "Data alvo":              p["data"].strftime("%d/%m/%Y"),
        "Previsão R$ (BRL)":      round(p["prev_rs"],  2),
        "Previsão US$ (USD)":     round(p["prev_usd"], 2),
    }
    for h, p in previsoes.items()
])

with pd.ExcelWriter(
    XLSX, engine="openpyxl", mode="a", if_sheet_exists="replace"
) as writer:
    df_metricas .to_excel(writer, sheet_name="Metricas",  index=False)
    df_previsoes.to_excel(writer, sheet_name="Previsoes", index=False)

print(f"\n✔  Métricas e previsões salvas em '{XLSX}'")
print("   Abas adicionadas: 'Metricas'  |  'Previsoes'")

plt.close("all")