"""
app.py — Controle de Piso (Streamlit + Google Sheets).

Execução local:
    streamlit run app.py
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import sheets_utils as su

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Controle de Piso",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Plotly: tema dark consistente
PLOTLY_TEMPLATE = "plotly_dark"
ACCENT = "#00C9A7"


# ---------------------------------------------------------------------------
# Colunas calculadas (Armazenagem e Status DPE)
# ---------------------------------------------------------------------------
def calc_armazenagem(entrada: str | None) -> str:
    d = su.parse_date_br(entrada)
    if d is None:
        return ""
    dias = (date.today() - d).days
    if dias > 7:
        return "⚠️ Armazenagem Vencida"
    if dias == 7:
        return "🔴 Armazenagem Vence Hoje"
    return "✅ Armazenagem em Dia"


def calc_status_dpe(dpe: str | None) -> str:
    d = su.parse_date_br(dpe)
    if d is None:
        return ""
    hoje = date.today()
    if d < hoje:
        return "⚠️ DPE Vencido"
    if d == hoje:
        return "🔴 DPE Vence Hoje"
    if d == hoje + timedelta(days=1):
        return "🟡 DPE a Vencer"
    return "✅ DPE em Dia"


def add_calc_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        out = df.copy() if df is not None else pd.DataFrame()
        out["Armazenagem"] = []
        out["Status DPE"] = []
        return out
    out = df.copy()
    out["Armazenagem"] = out["Data_Entrada"].apply(calc_armazenagem)
    out["Status DPE"] = out["DPE"].apply(calc_status_dpe)
    return out


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------
def _safe_load_estoque() -> pd.DataFrame | None:
    try:
        return su.carregar_estoque()
    except su.CredentialsError:
        st.error("Credenciais não encontradas.")
    except su.SheetsConnectionError:
        st.error("Não foi possível conectar ao Google Sheets.")
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
    return None


def _safe_load_historico() -> pd.DataFrame | None:
    try:
        return su.carregar_historico()
    except su.CredentialsError:
        st.error("Credenciais não encontradas.")
    except su.SheetsConnectionError:
        st.error("Não foi possível conectar ao Google Sheets.")
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
    return None


def init_state() -> None:
    if "df_estoque" not in st.session_state:
        df = _safe_load_estoque()
        if df is None:
            st.stop()
        st.session_state.df_estoque = df

    if "df_historico" not in st.session_state:
        df = _safe_load_historico()
        if df is None:
            st.stop()
        st.session_state.df_historico = df


def refresh_state() -> None:
    df_e = _safe_load_estoque()
    df_h = _safe_load_historico()
    if df_e is not None:
        st.session_state.df_estoque = df_e
    if df_h is not None:
        st.session_state.df_historico = df_h


init_state()


# ---------------------------------------------------------------------------
# Sidebar / Navegação
# ---------------------------------------------------------------------------
st.sidebar.title("📦 Controle de Piso")
menu = st.sidebar.radio(
    "Navegação",
    ["🏠 Home", "📋 Nova Entrada", "📊 Métricas", "📁 Histórico"],
    label_visibility="collapsed",
)

# JS para recolher a sidebar no mobile após seleção
st.markdown(
    """
    <script>
    (function(){
        try {
            if (window.innerWidth < 768) {
                const doc = window.parent.document;
                const btn = doc.querySelector('[data-testid="stSidebarCollapseButton"]')
                         || doc.querySelector('[data-testid="baseButton-header"]');
                if (btn) { setTimeout(() => btn.click(), 50); }
            }
        } catch (e) {}
    })();
    </script>
    """,
    unsafe_allow_html=True,
)

DISPLAY_COLS_ESTOQUE = [
    "NF", "Praça", "Toneladas", "Qtd_Volume", "Qtd_Palet",
    "Data_Entrada", "DPE", "Armazenagem", "Status DPE",
]

DISPLAY_COLS_HISTORICO = [
    "NF", "Praça", "Toneladas", "Qtd_Volume", "Qtd_Palet",
    "Data_Entrada", "Data_Saída", "DPE", "Armazenagem", "Status DPE",
]


def filter_by_nf(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query:
        return df
    return df[df["NF"].astype(str).str.contains(query.strip(), case=False, na=False)]


def bar_status(df: pd.DataFrame, col: str, title: str):
    counts = df[col].value_counts().reset_index()
    counts.columns = ["Status", "Contagem"]
    fig = px.bar(
        counts, x="Status", y="Contagem",
        template=PLOTLY_TEMPLATE, color="Status",
        title=title,
    )
    fig.update_layout(showlegend=False, margin=dict(t=40, b=20, l=10, r=10))
    return fig


# ===========================================================================
# 🏠 HOME
# ===========================================================================
if menu == "🏠 Home":
    st.title("🏠 Estoque Ativo")

    c1, c2 = st.columns([3, 1])
    with c1:
        busca = st.text_input("🔍 Pesquisar por NF", "", key="busca_home")
    with c2:
        st.write("")
        if st.button("🔄 Atualizar", use_container_width=True, key="btn_refresh_home"):
            refresh_state()
            st.rerun()

    df = add_calc_cols(st.session_state.df_estoque)
    df = filter_by_nf(df, busca)

    if df.empty:
        st.info("Nenhum registro no estoque ativo.")
    else:
        st.dataframe(
            df[DISPLAY_COLS_ESTOQUE],
            use_container_width=True,
            hide_index=True,
        )

        st.divider()
        st.subheader("Registrar Saída")
        st.caption("Expanda um NF para informar a data de saída e confirmar.")

        for _, row in df.iterrows():
            label = (
                f"NF {row['NF']} • {row['Praça']} • "
                f"{row['Toneladas']:.2f} t • {row['Status DPE']}"
            )
            with st.expander(label):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    saida = st.date_input(
                        "Data_Saída",
                        value=date.today(),
                        format="DD/MM/YYYY",
                        key=f"saida_{row['NF']}",
                    )
                with col_b:
                    st.write("")
                    if st.button(
                        "✅ Confirmar saída",
                        use_container_width=True,
                        key=f"btn_saida_{row['NF']}",
                    ):
                        try:
                            su.registrar_saida(row["NF"], su.format_date_br(saida))
                            refresh_state()
                            st.success("Saída registrada com sucesso!")
                            st.rerun()
                        except Exception as exc:  # noqa: BLE001
                            st.error(str(exc))


# ===========================================================================
# 📋 NOVA ENTRADA
# ===========================================================================
elif menu == "📋 Nova Entrada":
    st.title("📋 Nova Entrada")

    with st.form("nova_entrada", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            nf = st.text_input("NF *", max_chars=50)
            praca = st.selectbox("Praça *", ["MAO", "BVB", "Interior", "Retenção"])
            toneladas = st.number_input(
                "Toneladas *", min_value=0.0, step=0.1, format="%.2f"
            )
            qtd_volume = st.number_input("Qtd_Volume *", min_value=0, step=1)
        with c2:
            qtd_palet = st.number_input("Qtd_Palet *", min_value=0, step=1)
            data_entrada = st.date_input(
                "Data_Entrada *",
                value=date.today(),
                format="DD/MM/YYYY",
            )
            dpe = st.date_input(
                "DPE — Data Prevista de Entrega *",
                value=date.today() + timedelta(days=7),
                format="DD/MM/YYYY",
            )

        submitted = st.form_submit_button("💾 Salvar", use_container_width=True)

    if submitted:
        nf_clean = (nf or "").strip()
        if not nf_clean:
            st.warning("Preencha todos os campos obrigatórios.")
        else:
            existing = st.session_state.df_estoque
            duplicada = (
                not existing.empty
                and (existing["NF"].astype(str).str.strip() == nf_clean).any()
            )
            if duplicada:
                st.warning("Esta NF já existe no estoque.")
            else:
                try:
                    su.adicionar_entrada({
                        "NF": nf_clean,
                        "Praça": praca,
                        "Toneladas": float(toneladas),
                        "Qtd_Volume": int(qtd_volume),
                        "Qtd_Palet": int(qtd_palet),
                        "Data_Entrada": su.format_date_br(data_entrada),
                        "Data_Saída": "",
                        "DPE": su.format_date_br(dpe),
                    })
                    refresh_state()
                    st.success("Entrada registrada!")
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))


# ===========================================================================
# 📊 MÉTRICAS
# ===========================================================================
elif menu == "📊 Métricas":
    st.title("📊 Métricas — Estoque Ativo")

    df = add_calc_cols(st.session_state.df_estoque)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total de NFs Ativos", len(df))
    c2.metric("Total de Toneladas", f"{df['Toneladas'].sum():.2f}" if not df.empty else "0.00")
    c3.metric("Total de Paletes", int(df["Qtd_Palet"].sum()) if not df.empty else 0)

    if df.empty:
        st.info("Sem dados para exibir.")
    else:
        st.subheader("Toneladas por NF")
        fig1 = px.bar(
            df.sort_values("Toneladas", ascending=False),
            x="NF", y="Toneladas",
            template=PLOTLY_TEMPLATE,
            color="Toneladas",
            color_continuous_scale="Teal",
        )
        fig1.update_layout(margin=dict(t=30, b=20, l=10, r=10))
        st.plotly_chart(fig1, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(
                bar_status(df, "Armazenagem", "Status de Armazenagem"),
                use_container_width=True,
            )
        with c2:
            st.plotly_chart(
                bar_status(df, "Status DPE", "Status DPE"),
                use_container_width=True,
            )

        st.subheader("Resumo")
        st.dataframe(
            df[["NF", "Praça", "Toneladas", "Qtd_Palet",
                "Data_Entrada", "DPE", "Armazenagem", "Status DPE"]],
            use_container_width=True,
            hide_index=True,
        )


# ===========================================================================
# 📁 HISTÓRICO
# ===========================================================================
elif menu == "📁 Histórico":
    st.title("📁 Histórico")

    df = add_calc_cols(st.session_state.df_historico)

    c1, c2 = st.columns([3, 1])
    with c1:
        busca = st.text_input("🔍 Pesquisar por NF", "", key="busca_hist")
    with c2:
        st.write("")
        if st.button("🔄 Atualizar", use_container_width=True, key="btn_refresh_hist"):
            refresh_state()
            st.rerun()

    df = filter_by_nf(df, busca)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total de NFs Finalizadas", len(df))
    c2.metric(
        "Total de Toneladas (Histórico)",
        f"{df['Toneladas'].sum():.2f}" if not df.empty else "0.00",
    )
    c3.metric(
        "Total de Paletes (Histórico)",
        int(df["Qtd_Palet"].sum()) if not df.empty else 0,
    )

    if df.empty:
        st.info("Nenhum registro no histórico.")
    else:
        st.dataframe(
            df[DISPLAY_COLS_HISTORICO],
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Toneladas por NF (Histórico)")
        fig1 = px.bar(
            df.sort_values("Toneladas", ascending=False),
            x="NF", y="Toneladas",
            template=PLOTLY_TEMPLATE,
            color="Toneladas",
            color_continuous_scale="Teal",
        )
        fig1.update_layout(margin=dict(t=30, b=20, l=10, r=10))
        st.plotly_chart(fig1, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(
                bar_status(df, "Armazenagem", "Status de Armazenagem"),
                use_container_width=True,
            )
        with c2:
            st.plotly_chart(
                bar_status(df, "Status DPE", "Status DPE"),
                use_container_width=True,
            )
