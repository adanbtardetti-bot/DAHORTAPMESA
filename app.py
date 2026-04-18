import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Horta Gestão", layout="centered")

# 2. CSS PARA BOTÕES EM LINHA E SEM NAN
st.markdown('''
<style>
    .block-container {padding-top: 1rem;}
    [data-testid="stHorizontalBlock"] {gap: 5px !important;}
    .stButton>button {width: 100% !important; height: 3rem !important; padding: 0px !important;}
    .card {border: 2px solid #2e7d32; padding: 10px; border-radius: 10px; background: #0e1117; margin-bottom: 5px;}
    .btn-zap {background-color:#25d366; color:white; padding:12px; border-radius:8px; text-align:center; text-decoration:none; display:block; font-weight:bold;}
</style>
''', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna('') # Mata o 'nan' aqui
    except:
        if aba == "Pedidos":
            return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])
        return pd.DataFrame()

# --- AS 5 TELAS ---
t1, t2, t3, t4, t5 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro"])

# --- 1. TELA DE VENDA ---
with t1:
    if 'v_id' not in st.session_state: st.session_state.v_id = 0
    vid = st.session_state.v_id
    st.subheader("Novo Pedido")
    c1, c2 = st.columns(2)
    cli = c1.text_input("Cliente", key=f"c{vid}").upper()
    end = c2.text_input("Endereço", key=f"e{vid}").upper()
    c3, c4 = st.columns(2)
    pago_v = c3.toggle("Pago?", key=f"p{vid}")
    obs_v = c4.text_input("Obs", key=f"o{vid}")
    
    df_p = carregar_dados("Produtos")
    carrinho = []; total_v = 0.0
    if not df_p.empty:
        for i, r in df_p.iterrows():
            if str(r.get('status','')).lower() == 'oculto': continue
            cn, cp, cq = st.columns([2.5, 1, 1])
            p_u = float(str(r['preco']).replace(',', '.'))
            cn.markdown(f"**{r['nome']}**")
            qtd = cq.number_input("Q", 0, step=1, key=f"q{r['id']}{vid}", label_visibility="collapsed")
            if qtd > 0:
                tipo = str(r.get('tipo','UN')).upper()
                sub = 0.0 if tipo == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": tipo})
    
    if st.button(f"💾 SALVAR R$ {total_v:.2f}", type="primary"):
        if cli and carrinho:
            df_v = carregar_dados("Pedidos")
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": cli, "endereco": end, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pago_v else
