"""
sheets_utils.py — Camada de acesso ao Google Sheets para o Controle de Piso.

Responsabilidades:
- Autenticação via Service Account (credentials.json).
- Abertura/criação da planilha "controle_piso" e abas "Estoque" e "Historico".
- Leitura tipada em DataFrame e escritas (append, registrar saída).
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_NAME = "controle_piso"
ESTOQUE_TAB = "Estoque"
HISTORICO_TAB = "Historico"

HEADERS: list[str] = [
    "NF",
    "Praça",
    "Toneladas",
    "Qtd_Volume",
    "Qtd_Palet",
    "Data_Entrada",
    "Data_Saída",
    "DPE",
]

CREDENTIALS_PATH = os.environ.get("CONTROLE_PISO_CREDENTIALS", "credentials.json")


# ---------------------------------------------------------------------------
# Erros de domínio
# ---------------------------------------------------------------------------
class CredentialsError(FileNotFoundError):
    """Levantada quando credentials.json não está acessível."""


class SheetsConnectionError(RuntimeError):
    """Levantada quando a conexão com o Google Sheets falha."""


# ---------------------------------------------------------------------------
# Cliente / Spreadsheet
# ---------------------------------------------------------------------------
_client_cache: gspread.Client | None = None


def get_client() -> gspread.Client:
    """Devolve um cliente gspread autenticado (cacheado em memória).

    Prioriza st.secrets (deploy) e cai para credentials.json (local).
    """
    global _client_cache
    if _client_cache is not None:
        return _client_cache

    creds = None
    try:
        # Deploy: tenta ler dos secrets do Streamlit
        try:
            import streamlit as st
            if "gcp_service_account" in st.secrets:
                creds = Credentials.from_service_account_info(
                    dict(st.secrets["gcp_service_account"]),
                    scopes=SCOPES,
                )
        except Exception:
            pass

        # Local: cai para o arquivo
        if creds is None:
            if not os.path.exists(CREDENTIALS_PATH):
                raise CredentialsError(
                    f"Credenciais não encontradas (nem em st.secrets, nem em {CREDENTIALS_PATH})."
                )
            creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)

        _client_cache = gspread.authorize(creds)
        return _client_cache
    except CredentialsError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsConnectionError(f"Falha ao autenticar no Google Sheets: {exc}") from exc

def get_spreadsheet() -> gspread.Spreadsheet:
    """Abre a planilha controle_piso. Cria se não existir."""
    client = get_client()
    try:
        sh = client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        sh = client.create(SPREADSHEET_NAME)
        # Remove a aba default criada pelo Google
        try:
            default = sh.worksheet("Sheet1")
            sh.del_worksheet(default)
        except gspread.WorksheetNotFound:
            pass
    except Exception as exc:  # noqa: BLE001
        raise SheetsConnectionError(f"Não foi possível abrir a planilha: {exc}") from exc

    # Garantir abas e cabeçalhos
    _ensure_worksheet(sh, ESTOQUE_TAB)
    _ensure_worksheet(sh, HISTORICO_TAB)
    return sh


def _ensure_worksheet(sh: gspread.Spreadsheet, name: str) -> gspread.Worksheet:
    """Garante que a aba exista com os cabeçalhos corretos."""
    try:
        ws = sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=1000, cols=len(HEADERS))

    first_row = ws.row_values(1)
    if first_row != HEADERS:
        # Reescreve apenas a linha 1 com os cabeçalhos definidos.
        ws.update(values=[HEADERS], range_name="A1")
    return ws


def get_worksheet(name: str) -> gspread.Worksheet:
    """Atalho público para obter uma aba já garantida."""
    return _ensure_worksheet(get_spreadsheet(), name)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def _ws_to_df(ws: gspread.Worksheet) -> pd.DataFrame:
    """Lê todos os valores formatados da aba e devolve um DataFrame tipado."""
    values = ws.get_all_values()
    if len(values) <= 1:
        return pd.DataFrame(columns=HEADERS)

    headers = values[0]
    df = pd.DataFrame(values[1:], columns=headers)

    # Garante todas as colunas esperadas, mesmo que faltem na planilha
    for col in HEADERS:
        if col not in df.columns:
            df[col] = ""
    df = df[HEADERS].copy()

    # Conversões de tipo
    df["NF"] = df["NF"].astype(str).str.strip()
    df["Praça"] = df["Praça"].astype(str).str.strip()
    df["Toneladas"] = (
        df["Toneladas"].astype(str).str.replace(",", ".", regex=False)
    )
    df["Toneladas"] = pd.to_numeric(df["Toneladas"], errors="coerce").fillna(0.0)
    df["Qtd_Volume"] = pd.to_numeric(df["Qtd_Volume"], errors="coerce").fillna(0).astype(int)
    df["Qtd_Palet"] = pd.to_numeric(df["Qtd_Palet"], errors="coerce").fillna(0).astype(int)

    # Remove linhas totalmente vazias (NF em branco)
    df = df[df["NF"].astype(str).str.strip() != ""].reset_index(drop=True)
    return df


def carregar_estoque() -> pd.DataFrame:
    return _ws_to_df(get_worksheet(ESTOQUE_TAB))


def carregar_historico() -> pd.DataFrame:
    return _ws_to_df(get_worksheet(HISTORICO_TAB))


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
def adicionar_entrada(row: dict[str, Any]) -> None:
    """Faz append de um registro na aba Estoque."""
    ws = get_worksheet(ESTOQUE_TAB)
    payload = [_serialize(row.get(col, "")) for col in HEADERS]
    ws.append_row(payload, value_input_option="USER_ENTERED")


def registrar_saida(nf: str, data_saida_str: str) -> None:
    """Move um NF do Estoque para o Histórico com Data_Saída preenchida."""
    estoque_ws = get_worksheet(ESTOQUE_TAB)
    historico_ws = get_worksheet(HISTORICO_TAB)

    df = _ws_to_df(estoque_ws)
    nf = str(nf).strip()
    mask = df["NF"] == nf
    if not mask.any():
        raise ValueError(f"NF {nf} não encontrada no estoque.")

    row = df[mask].iloc[0].to_dict()
    row["Data_Saída"] = data_saida_str

    payload = [_serialize(row.get(col, "")) for col in HEADERS]
    historico_ws.append_row(payload, value_input_option="USER_ENTERED")

    # Remove a linha original: idx 0 -> linha 2 (linha 1 é cabeçalho)
    idx = int(df[mask].index[0])
    estoque_ws.delete_rows(idx + 2)


def _serialize(v: Any) -> Any:
    """Normaliza valores para escrita no Sheets."""
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return format_date_br(v)
    return v


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------
def parse_date_br(s: Any) -> date | None:
    """Converte string DD/MM/AAAA em date. Devolve None se inválido/vazio."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    text = str(s).strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def format_date_br(d: Any) -> str:
    """Formata uma date/datetime como DD/MM/AAAA."""
    if d is None:
        return ""
    if isinstance(d, str):
        return d
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return str(d)
