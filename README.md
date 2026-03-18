# Milho CEPEA ESALQ/B3 — Coleta, Análise e Dashboard

Projeto de coleta automatizada, análise estatística e visualização das cotações do milho (indicador CEPEA ESALQ/B3).

---

## Estrutura do projeto

```
.
├── crawler.py                  # Coleta dados diários do site CEPEA
├── regressão_linear.py         # Treina modelos de regressão (BRL e USD) e gera previsões
├── dashboard.py                # Dashboard interativo com Streamlit
├── crawler_colab.ipynb         # Versão notebook do crawler (Google Colab)
├── regressao_linear_colab.ipynb# Versão notebook da regressão (Google Colab)
├── dashboard_colab.ipynb       # Versão notebook do dashboard (Google Colab)
└── cepea-consulta-*.xls        # Arquivo histórico de médias anuais (baixado do CEPEA)
```

---

## Fonte dos dados

- **CEPEA ESALQ/B3** — Indicador do Milho
- URL: https://cepea.org.br/br/indicador/milho.aspx
- Unidade: R$ e US$ por saca de 60 kg, à vista (descontado CDI/CETIP)
- Licença: CC BY-NC 4.0

---

## Como usar

### 1. Instalar dependências

```bash
python -m venv venv
source venv/bin/activate
pip install curl_cffi beautifulsoup4 pandas openpyxl xlrd scikit-learn matplotlib plotly streamlit ipywidgets
```

### 2. Coletar dados

```bash
# Primeira execução: cria cotacao_milho.xlsx com histórico + dados recentes
python crawler.py

# Execuções seguintes: adiciona apenas datas novas
python crawler.py

# Recriar do zero reimportando o arquivo base do CEPEA
python crawler.py --reimportar
```

### 3. Executar a regressão linear

```bash
python regressão_linear.py
```

Gera previsões para +3 e +6 dias úteis em R$ e US$, exibe métricas (R², MAE) e salva gráficos e resultados no Excel.

### 4. Executar o dashboard

```bash
streamlit run dashboard.py
```

---

## Google Colab

Os arquivos `.ipynb` são versões adaptadas para execução no Google Colab, com upload/download de arquivos e controles interativos via `ipywidgets`.

| Notebook | Função |
|---|---|
| `crawler_colab.ipynb` | Coleta e atualização de dados |
| `regressao_linear_colab.ipynb` | Regressão, métricas e previsões |
| `dashboard_colab.ipynb` | Gráficos e tabelas interativas |

---

## Modelos de previsão

- **Variável independente:** dias corridos desde a primeira data da série
- **Variável dependente:** preço (R$ ou US$) por saca de 60 kg
- **Horizonte:** +3 e +6 dias úteis a partir da última cotação disponível
- **Série:** combinação de médias anuais (longo prazo) + cotações dos últimos dias úteis (curto prazo)

### Limitações

- Regressão linear assume tendência aproximadamente linear no tempo
- Não captura sazonalidade, volatilidade ou choques de mercado
- Adequada como referência de tendência, não como previsão de preço exata

---

## Agendamento automático (crontab)

Atualização toda segunda-feira às 8h:

```cron
0 8 * * 1 /caminho/venv/bin/python /caminho/crawler.py
```
