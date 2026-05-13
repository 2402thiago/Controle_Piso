# 📦 Controle de Piso

Aplicativo Streamlit para gerenciamento de estoque de piso integrado ao
Google Sheets via Service Account.

## Estrutura

```
controle_piso/
├── app.py                  # Aplicação Streamlit (4 telas)
├── sheets_utils.py         # Camada Google Sheets (gspread + pandas)
├── credentials.json        # Service Account — NÃO versionar
├── .streamlit/
│   └── config.toml         # Tema dark
└── requirements.txt
```

## Setup

1. **Criar Service Account no Google Cloud**
   - Console → IAM & Admin → Service Accounts → *Create*.
   - Habilitar as APIs **Google Sheets API** e **Google Drive API**.
   - Gerar uma chave JSON e salvar como `credentials.json` na raiz do projeto.

2. **Compartilhar a planilha (opcional)**
   - Se a planilha `controle_piso` já existir, compartilhe-a com o e-mail
     da Service Account (`client_email` dentro do JSON) com permissão de
     editor. Se não existir, será criada automaticamente na conta da
     Service Account no primeiro acesso.

3. **Instalar dependências**
   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Rodar**
   ```bash
   streamlit run app.py
   ```

## Planilha

Arquivo: **controle_piso** (criado automaticamente se não existir).

**Aba `Estoque`** — registros ativos.
**Aba `Historico`** — registros finalizados (com `Data_Saída`).

Ambas com as colunas:

| Coluna        | Tipo                 |
|---------------|----------------------|
| NF            | str                  |
| Praça         | str (MAO/BVB/Interior/Retenção) |
| Toneladas     | float                |
| Qtd_Volume    | int                  |
| Qtd_Palet     | int                  |
| Data_Entrada  | date (DD/MM/AAAA)    |
| Data_Saída    | date (DD/MM/AAAA)    |
| DPE           | date (DD/MM/AAAA)    |

## Colunas calculadas (em memória)

**Armazenagem** — derivada de `Data_Entrada` vs. hoje:

| Condição              | Valor                       |
|-----------------------|-----------------------------|
| > 7 dias              | ⚠️ Armazenagem Vencida      |
| = 7 dias              | 🔴 Armazenagem Vence Hoje   |
| < 7 dias              | ✅ Armazenagem em Dia       |

**Status DPE** — derivado de `DPE` vs. hoje:

| Condição              | Valor                |
|-----------------------|----------------------|
| DPE < hoje            | ⚠️ DPE Vencido       |
| DPE = hoje            | 🔴 DPE Vence Hoje    |
| DPE = hoje + 1 dia    | 🟡 DPE a Vencer      |
| DPE > hoje + 1 dia    | ✅ DPE em Dia        |

## Telas

- **🏠 Home** — Estoque ativo com busca por NF, atualizar e registrar saída.
- **📋 Nova Entrada** — Formulário de cadastro (valida NF duplicada).
- **📊 Métricas** — Cards + gráficos Plotly do estoque ativo.
- **📁 Histórico** — Tabela, busca e gráficos dos registros finalizados.

## Notas

- O cliente gspread é cacheado em memória (singleton) para evitar
  reautenticação a cada interação.
- Toda escrita re-sincroniza `st.session_state` com o Sheets.
- O Sheets é lido **apenas** na inicialização, ao clicar *Atualizar* ou
  após uma escrita.
- O caminho do `credentials.json` pode ser sobrescrito via variável de
  ambiente `CONTROLE_PISO_CREDENTIALS`.

## .gitignore sugerido

```
credentials.json
.venv/
__pycache__/
.streamlit/secrets.toml
```
