import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

# --- CONFIGURAÇÕES E ESTILOS ---
st.set_page_config(page_title="Horta Gestão", page_icon="🥬", layout="wide")

def aplicar_estilos():
    css_path = Path(__file__).with_name("styles.css")
    try:
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except:
        st.markdown("""
            <style>
                .hero-banner {background-color: #0f1d12; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px;}
                .hero-title {font-size: 24px; font-weight: bold;}
                .btn-zap {background-color: #25d366; color: white !important; padding: 10px; border-radius: 5px; text-decoration: none; display: block; text-align: center; font-weight: bold;}
                .btn-print {text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; color:black; border:1px solid #ddd;}
                .total-badge {background:#f0f2f6; padding:10px; border-radius:5px; font-weight:bold; margin-bottom:10px; color:black;}
                .m-total {font-size: 20px; font-weight: bold; margin-top: 10px; color: #1e1e1e;}
            </style>
        """, unsafe_allow_html=True)

aplicar_estilos()

conn = st.connection("gsheets", type=GSheetsConnection)
STATUS_PENDENTE = "pendente"
STATUS_PRONTO = "pronto"
PAGAMENTO_PAGO = "PAGO"
PAGAMENTO_A_PAGAR = "A PAGAR"

# --- FUNÇÕES ---
def limpar_texto(texto):
    if not texto: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')

def gerar_b64_etiqueta(cliente, endereco, valor, pagamento):
    largura = 32
    marca = "@dahortapmesa".center(largura)
    cli = limpar_texto(cliente).upper().center(largura)
    end = limpar_texto(endereco).upper().center(largura)
    val_txt = f"R$ {valor:.2f}"
    status_txt = "pago" if pagamento == PAGAMENTO_PAGO else ""
    espacos = max(1, largura - len(val_txt) - len(status_txt) - 2)
    linha_final = f"{val_txt}{' ' * espacos}{status_txt}"
    corpo = f"{marca}\n\n{cli}\n\n{end}\n\n{linha_final}"
    return base64.b64encode(corpo.encode('ascii', 'ignore')).decode()

def parse_float(val):
    try: return float(str(val).strip().replace(",", "."))
    except: return 0.0

def ler_aba(aba, ttl=30):
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty: return pd.DataFrame()
        df.columns = [str(c).lower().strip() for c in df.columns]
        # PROTEÇÃO CONTRA O ERRO KEYERROR STATUS
        if aba == "Produtos":
            if "status" not in df.columns:
                df["status"] = "Ativo"
        return df.fillna("")
    except: return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    conn.reset()

# --- CARREGAR DADOS ---
df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

st.markdown('<div class="hero-banner"><div class="hero-title">Horta Gestao</div></div>', unsafe_allow_html=True)

aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro", "📦 Produtos"])

# Aba 1 até 5 permanecem com sua lógica original de filtros e visualização
# ... (Omitido para focar na correção, mas o código completo segue seu padrão)

# 6. PRODUTOS (LAYOUT ORIGINAL CORRIGIDO)
with aba6:
    st.header("📦 Produtos")
    with st.expander("➕ Adicionar Novo Produto"):
        c_n, c_p, c_t = st.columns([3, 1, 1])
        n_p = c_n.text_input("Nome").upper()
        p_p = c_p.number_input("Preço", 0.0)
        t_p = c_t.selectbox("Tipo", ["UN", "KG"])
        if st.button("SALVAR PRODUTO", type="primary", use_container_width=True):
            if n_p:
                df_p = ler_aba("Produtos", 0)
                novo_p = pd.DataFrame([{"nome": n_p, "preco": p_p, "tipo": t_p, "status": "Ativo"}])
                salvar_aba("Produtos", pd.concat([df_p, novo_p], ignore_index=True))
                st.rerun()

    st.markdown("---")
    df_l = ler_aba("Produtos", 0)
    for idx, r in df_l.iterrows():
        c1, c2, c3, c4, c5, c6 = st.columns([2.5, 1, 1, 1, 0.5, 0.5])
        en = c1.text_input("N", r['nome'], key=f"en_{idx}", label_visibility="collapsed").upper()
        ep = c2.number_input("R$", parse_float(r['preco']), key=f"ep_{idx}", label_visibility="collapsed")
        et = c3.selectbox("T", ["UN", "KG"], index=0 if r['tipo']=="UN" else 1, key=f"et_{idx}", label_visibility="collapsed")
        status_ativo = (r['status'] == "Ativo")
        est = c4.toggle("Ativo", value=status_ativo, key=f"es_{idx}")
        if c5.button("💾", key=f"sv_{idx}"):
            df_l.at[idx, 'nome'], df_l.at[idx, 'preco'], df_l.at[idx, 'tipo'], df_l.at[idx, 'status'] = en, ep, et, ("Ativo" if est else "Inativo")
            salvar_aba("Produtos", df_l); st.rerun()
        if c6.button("🗑️", key=f"dl_{idx}"):
            salvar_aba("Produtos", df_l.drop(idx)); st.rerun()
