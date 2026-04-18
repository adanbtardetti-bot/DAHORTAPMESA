import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Gestão", layout="centered")

st.markdown("""
    <style>
    div[data-testid="stColumn"] { display: flex; align-items: center; }
    .stNumberInput div { margin-top: 0px; }
    [data-testid="stNumberInput"] { width: 100% !important; }
    .stButton>button { border-radius: 10px; font-weight: bold; }
    .btn-venda { background-color: #2e7d32; color: white; height: 3.5em; width: 100%; }
    /* Cor oficial do WhatsApp */
    .btn-whatsapp { 
        background-color: #25d366; 
        color: white; 
        padding: 15px; 
        border-radius: 10px; 
        text-align: center; 
        text-decoration: none; 
        display: block; 
        font-weight: bold;
        margin-top: 10px;
    }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES DE DADOS ---
def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except:
        return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "status"])

def carregar_pedidos():
    try:
        df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

# --- CONTROLE DE ABAS ---
aba1, aba2 = st.tabs(["🛒 Novo Pedido", "🚜 Colheita"])

# --- TELA 1: VENDAS ---
with aba1:
    if 'form_id' not in st.session_state: st.session_state.form_id = 0
    f_id = st.session_state.form_id
    
    st.header("🛒 Novo Pedido")
    with st.container():
        c1, c2 = st.columns(2)
        n_cli = c1.text_input("Cliente", key=f"n_{f_id}").upper()
        e_cli = c2.text_input("Endereço", key=f"e_{f_id}").upper()
        
        c3, c4 = st.columns([1, 2])
        pg = c3.toggle("Pago?", key=f"p_{f_id}")
        o_ped = c4.text_input("Observação", key=f"o_{f_id}")
        
        st.divider()
        
        df_p = carregar_produtos()
        carrinho = []
        total_v = 0.0
        
        if not df_p.empty:
            for i, r in df_p
