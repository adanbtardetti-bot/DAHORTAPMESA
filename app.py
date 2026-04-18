import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

st.set_page_config(page_title="Horta Vendas", layout="centered")

conn = st.connection("gsheets", type=GSheetsConnection)

# -------- MENU --------
menu = st.sidebar.radio("Menu", [
    "🛒 Novo Pedido",
    "🚜 Colheita",
    "📦 Montagem",
    "📅 Histórico",
    "📊 Financeiro",
    "📦 Estoque"
])

# -------- FUNÇÕES --------
def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except:
        return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "status"])

def carregar_pedidos():
    try:
        return conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
    except:
        return pd.DataFrame()

# -------- NOVO PEDIDO --------
if menu == "🛒 Novo Pedido":
    st.header("🛒 Novo Pedido")

    if 'form_id' not in st.session_state:
        st.session_state.form_id = 0

    f_id = st.session_state.form_id

    nome = st.text_input("Cliente", key=f"n_{f_id}")
    endereco = st.text_input("Endereço", key=f"e_{f_id}")
    pago = st.toggle("Pago?", key=f"p_{f_id}")
    obs = st.text_area("Observações", key=f"o_{f_id}")

    st.divider()

    df_p = carregar_produtos()
    carrinho = []
    total = 0.0

    for _, row in df_p.iterrows():
        col1, col2, col3 = st.columns([2,1,1])

        col1.write(row["nome"])

        tipo = str(row["tipo"]).upper()
        preco = float(str(row["preco"]).replace(",", "."))

        if tipo == "KG":
            col2.caption("PESAGEM")
        else:
            col2.write(f"R$ {preco:.2f}")

        qtd = col3.number_input("qtd", 0, key=f"{row['id']}_{f_id}")

        if qtd > 0:
            sub = 0 if tipo == "KG" else qtd * preco
            total += sub

            carrinho.append({
                "id": row["id"],
                "nome": row["nome"],
                "qtd": qtd,
                "