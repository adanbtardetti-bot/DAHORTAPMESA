import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

# 1. Configuração inicial (Sempre no topo)
st.set_page_config(page_title="Horta Gestão", layout="centered")

# 2. CSS para organizar botões lado a lado e compactar tudo
st.markdown('''
<style>
    .block-container {padding-top: 1rem; padding-bottom: 0rem;}
    [data-testid="stHorizontalBlock"] {gap: 5px !important;}
    .stButton>button {width: 100% !important; height: 2.8rem !important; padding: 0px !important;}
    .card-info {border: 1px solid #2e7d32; padding: 8px; border-radius: 8px; background-color: #0e1117; margin-bottom: 5px;}
    p {margin-bottom: 0px !important;}
</style>
''', unsafe_allow_html=True)

# 3. Conexão e Funções
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_pedidos():
    try:
        df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

# --- MENU PRINCIPAL (ESTA LINHA CRIA AS ABAS) ---
aba1, aba2, aba3 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

# --- ABA 1: VENDA ---
with aba1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    
    cli = st.text_input("Cliente", key=f"c{f}").upper()
    end = st.text_input("Endereço", key=f"e{f}").upper()
    col_p, col_o = st.columns(2)
    pago = col_p.toggle("Pago?", key=f"p{f}")
    obs = col_o.text_input("Obs", key=f"o{f}")
    
    try:
        df_prod = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df_prod.columns = [str(c).lower().strip() for c in df_prod.columns]
        carrinho = []; tot = 0.0
        for i, r in df_prod.iterrows():
            if str(r.get('status','')).lower() == 'oculto': continue
            c_n, c_q = st.columns([3, 2])
            c_n.write(f"**{r['nome']}**")
            qtd = c_q.number_input("Q", 0, step=1, key=f"q{r['id']}{f}", label
