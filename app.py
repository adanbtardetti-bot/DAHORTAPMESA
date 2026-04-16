import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import urllib.parse
import json

st.set_page_config(page_title="Gestão Horta - Conectado", layout="wide")

# Conectando à Planilha Google
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES DE DADOS ---
def ler_produtos():
    return conn.read(worksheet="Produtos", ttl=0).dropna(how="all")

def ler_pedidos():
    return conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")

def salvar_produto(df_novo):
    conn.update(worksheet="Produtos", data=df_novo)
    st.cache_data.clear()

def salvar_pedido(df_novo):
    conn.update(worksheet="Pedidos", data=df_novo)
    st.cache_data.clear()

# Carregar dados iniciais
try:
    df_produtos = ler_produtos()
    df_pedidos = ler_pedidos()
except:
    st.error("Erro ao ler a planilha. Verifique se os nomes das abas estão corretos (Produtos e Pedidos).")
    st.stop()

# --- INTERFACE ---
menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Colheita", "Montagem/Expedição", "Estoque", "Financeiro", "Histórico"])

if menu == "Estoque":
    st.header("⚙️ Cadastro de Produtos")
    with st.form("add_prod", clear_on_submit=True):
        n = st.text_input("Nome do Produto")
        p = st.number_input("Preço", min_value=0.0, format="%.2f")
        t = st.selectbox("Tipo", ["Unidade", "KG"])
        if st.form_submit_button("➕ Salvar na Planilha"):
            if n:
                # Gerar ID novo
                prox_id = int(df_produtos['id'].max() + 1) if not df_produtos.empty and 'id' in df_produtos.columns else 1
                novo_p = pd.DataFrame([{"id": prox_id, "nome": n, "preco": p, "tipo": t, "ativo": True}])
                
                # Juntar com os antigos e salvar
                df_atualizado = pd.concat([df_produtos, novo_p], ignore_index=True)
                salvar_produto(df_atualizado)
                st.success(f"Produto {n} salvo com sucesso!")
                st.rerun()
    
    st.subheader("Produtos Cadastrados")
    st.dataframe(df_produtos, use_container_width=True)

# (Mantenha as outras telas conforme o código anterior, elas usarão as mesmas funções de salvar)
