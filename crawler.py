"""
Cotação do Milho — Indicador CEPEA ESALQ/B3
============================================
Fonte     : https://cepea.org.br/br/indicador/milho.aspx
Unidade   : R$ por saca de 60 kg, à vista (descontado CDI/CETIP)
Licença   : CEPEA (CC BY-NC 4.0)
Saída     : cotacao_milho.xlsx  (abas: Diario | Media_Anual)

Estratégia
----------
  • curl_cffi impersona o TLS do Chrome → passa pelo Cloudflare sem browser
  • Primeira execução: importa o XLS histórico baixado manualmente do CEPEA
    e scrapa a tabela da página para preencher os dias recentes.
  • Execuções seguintes: acrescenta apenas datas ainda não presentes no Excel.

Uso
---
    python crawler.py                  # atualiza (ou cria) cotacao_milho.xlsx
    python crawler.py --reimportar     # reimporta o XLS base + atualiza

Agendamento semanal (crontab — toda segunda às 8h)
---------------------------------------------------
    0 8 * * 1 /caminho/venv/bin/python /caminho/crawler.py
"""

import argparse
import os

import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests as cf

# ─────────────────────────────────────────────────────────────
#  Configurações
# ─────────────────────────────────────────────────────────────
CEPEA_URL = "https://cepea.org.br/br/indicador/milho.aspx"

# XLS baixado manualmente do CEPEA (médias anuais — base histórica)
XLS_BASE  = "cepea-consulta-20260315134332.xls"

# Arquivo de saída Excel (gerado/atualizado pelo crawler)
XLS_SAIDA = "cotacao_milho.xlsx"

# ─────────────────────────────────────────────────────────────
#  Funções auxiliares
# ─────────────────────────────────────────────────────────────

def _limpar_numero(serie: pd.Series) -> pd.Series:
    """Remove formatação brasileira (1.234,56 / 0,59%) e converte para float."""
    return pd.to_numeric(
        serie.astype(str)
             .str.replace(r"\s", "", regex=True)
             .str.replace("%", "", regex=False)
             .str.replace(".", "", regex=False)
             .str.replace(",", ".", regex=False)
             .str.replace(r"[^\d.\-]", "", regex=True),
        errors="coerce",
    )


def _scrape_tabela() -> pd.DataFrame:
    """
    Scrapa a tabela diária da página principal do CEPEA usando curl_cffi
    (impersona TLS do Chrome para passar pelo Cloudflare).

    Retorna DataFrame com colunas:
        data | valor_rs | var_dia_pct | var_mes_pct | valor_usd
    """
    print(f"  Conectando: {CEPEA_URL}")
    resp = cf.get(CEPEA_URL, impersonate="chrome120", timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    tabela = soup.find("table")
    if tabela is None:
        raise RuntimeError("Tabela não encontrada na página do CEPEA.")

    linhas = []
    for tr in tabela.find_all("tr"):
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cols) == 5 and cols[0]:
            linhas.append(cols)

    if not linhas:
        raise RuntimeError("Nenhuma linha de dados encontrada na tabela.")

    df = pd.DataFrame(linhas, columns=[
        "data_str", "valor_rs_str", "var_dia_str", "var_mes_str", "valor_usd_str"
    ])

    resultado = pd.DataFrame()
    resultado["data"]        = pd.to_datetime(df["data_str"],    dayfirst=True, errors="coerce")
    resultado["valor_rs"]    = _limpar_numero(df["valor_rs_str"])
    resultado["var_dia_pct"] = _limpar_numero(df["var_dia_str"])
    resultado["var_mes_pct"] = _limpar_numero(df["var_mes_str"])
    resultado["valor_usd"]   = _limpar_numero(df["valor_usd_str"])

    return (
        resultado
        .dropna(subset=["data", "valor_rs"])
        .sort_values("data")
        .reset_index(drop=True)
    )


def _importar_base_xls() -> pd.DataFrame:
    """
    Lê o XLS de médias anuais baixado manualmente do CEPEA.
    Retorna DataFrame com colunas: ano | valor_rs_medio | valor_usd_medio
    """
    if not os.path.exists(XLS_BASE):
        print(f"  [AVISO] '{XLS_BASE}' não encontrado. Pulando importação.")
        return pd.DataFrame(columns=["ano", "valor_rs_medio", "valor_usd_medio"])

    raw = pd.read_excel(XLS_BASE, header=None, engine="xlrd")

    # Localiza a linha do cabeçalho (contém "Data" ou "Ano")
    header_row = 3
    for i, row in raw.iterrows():
        if any("data" in str(c).lower() for c in row.values):
            header_row = int(i)
            break

    df = pd.read_excel(XLS_BASE, header=header_row, engine="xlrd")
    df.columns = [str(c).strip() for c in df.columns]

    def _achar(palavras):
        for p in palavras:
            for col in df.columns:
                if p.lower() in col.lower():
                    return col
        return None

    col_ano = _achar(["data", "ano"])
    col_rs  = _achar(["r$", "vista r", "reais"])
    col_usd = _achar(["us$", "dólar", "dollar"])

    resultado = pd.DataFrame()
    resultado["ano"]            = df[col_ano].astype(str).str.strip() if col_ano else "?"
    resultado["valor_rs_medio"] = _limpar_numero(df[col_rs])   if col_rs  else float("nan")
    resultado["valor_usd_medio"]= _limpar_numero(df[col_usd])  if col_usd else float("nan")

    return (
        resultado
        .dropna(subset=["valor_rs_medio"])
        .reset_index(drop=True)
    )


def _ler_diario_existente() -> pd.DataFrame:
    """Lê a aba 'Diario' do XLS de saída, ou retorna DataFrame vazio."""
    colunas_padrao = ["data", "valor_rs", "var_dia_pct", "var_mes_pct", "valor_usd"]
    if not os.path.exists(XLS_SAIDA):
        return pd.DataFrame(columns=colunas_padrao)
    try:
        df = pd.read_excel(XLS_SAIDA, sheet_name="Diario", engine="openpyxl")
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame(columns=colunas_padrao)


def _salvar_xls(df_diario: pd.DataFrame, df_anual: pd.DataFrame) -> None:
    """Salva os dois DataFrames em abas separadas do XLS de saída."""
    with pd.ExcelWriter(
        XLS_SAIDA, engine="openpyxl",
        date_format="DD/MM/YYYY",
        datetime_format="DD/MM/YYYY",
    ) as writer:
        df_diario.to_excel(writer, sheet_name="Diario",      index=False)
        df_anual.to_excel( writer, sheet_name="Media_Anual", index=False)


# ─────────────────────────────────────────────────────────────
#  Funções principais
# ─────────────────────────────────────────────────────────────

def inicializar():
    """
    Criação inicial do XLS de saída:
      1. Importa médias anuais do XLS base (histórico manual do CEPEA)
      2. Scrapa a tabela diária da página principal do CEPEA
      3. Salva em cotacao_milho.xlsx (abas Diario + Media_Anual)
    """
    print(f"\n{'─'*55}")
    print("Inicializando cotacao_milho.xlsx ...")
    print(f"{'─'*55}")

    print("\n[1/3] Importando médias anuais do XLS base ...")
    df_anual = _importar_base_xls()
    print(f"      {len(df_anual)} ano(s) importado(s): {list(df_anual['ano'])}")

    print("\n[2/3] Scraping da tabela diária do CEPEA ...")
    df_diario = _scrape_tabela()
    print(f"      {len(df_diario)} linhas capturadas  "
          f"({df_diario['data'].min().date()} → {df_diario['data'].max().date()})")

    print(f"\n[3/3] Salvando '{XLS_SAIDA}' ...")
    _salvar_xls(df_diario, df_anual)

    print(f"\n✔  Arquivo criado: '{XLS_SAIDA}'")
    print(f"   Aba 'Diario'      : {len(df_diario)} linhas")
    print(f"   Aba 'Media_Anual' : {len(df_anual)} linhas")
    print("\n   Últimas linhas diárias:")
    print(df_diario[["data", "valor_rs", "var_dia_pct", "valor_usd"]].tail(5).to_string(index=False))


def atualizar():
    """
    Atualização semanal:
      1. Lê os dados diários já salvos no XLS
      2. Scrapa a tabela da página do CEPEA
      3. Acrescenta apenas as datas ainda não presentes
      4. Salva o XLS atualizado
    Se o arquivo não existir, chama inicializar() automaticamente.
    """
    if not os.path.exists(XLS_SAIDA):
        print("[INFO] Arquivo de saída não encontrado. Inicializando ...")
        inicializar()
        return

    print(f"\n{'─'*55}")
    print("Atualizando cotacao_milho.xlsx ...")
    print(f"{'─'*55}")

    print("\n[1/3] Lendo dados existentes ...")
    df_existente = _ler_diario_existente()
    datas_existentes = set(df_existente["data"].dt.normalize())
    ultima = df_existente["data"].max()
    print(f"      {len(df_existente)} linhas. Última data: {ultima.date()}")

    print("\n[2/3] Scraping da tabela diária do CEPEA ...")
    df_novo = _scrape_tabela()

    df_novo_filtrado = df_novo[
        ~df_novo["data"].dt.normalize().isin(datas_existentes)
    ].copy()

    if df_novo_filtrado.empty:
        print("      Nenhuma data nova encontrada. Arquivo já está atualizado.")
        return

    print(f"      {len(df_novo_filtrado)} nova(s) data(s) encontrada(s).")

    print(f"\n[3/3] Salvando '{XLS_SAIDA}' ...")
    df_anual = pd.read_excel(XLS_SAIDA, sheet_name="Media_Anual", engine="openpyxl")
    df_combinado = (
        pd.concat([df_existente, df_novo_filtrado], ignore_index=True)
        .drop_duplicates(subset=["data"])
        .sort_values("data")
        .reset_index(drop=True)
    )
    _salvar_xls(df_combinado, df_anual)

    print(f"\n✔  +{len(df_novo_filtrado)} linha(s) adicionada(s).")
    print(f"   Total: {len(df_combinado)} linhas diárias em '{XLS_SAIDA}'")
    print("\n   Últimas linhas:")
    print(df_combinado[["data", "valor_rs", "var_dia_pct", "valor_usd"]].tail(5).to_string(index=False))


# ─────────────────────────────────────────────────────────────
#  Entry-point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Baixa/atualiza cotações diárias do milho CEPEA ESALQ/B3."
    )
    parser.add_argument(
        "--reimportar",
        action="store_true",
        help="Recria o XLS de saída reimportando o arquivo base + scraping.",
    )
    args = parser.parse_args()

    if args.reimportar:
        inicializar()
    else:
        atualizar()
