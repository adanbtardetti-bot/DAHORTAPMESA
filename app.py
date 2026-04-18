import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

st.set_page_config(layout="centered")

# Ligação com a folha
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
    df.columns = [str(c).lower().strip() for c in df.columns]
    return df

df_vendas = carregar_dados()

# Interface de Abas igual às suas fotos
tab1, tab2, tab3 = st.tabs(["🛒 Vendas", "⚖️ Montagem", "🕒 Histórico"])

with tab2:
    st.subheader("Pedidos Pendentes")
    # Filtra apenas o que é 'Pendente'
    pendentes = df_vendas[df_vendas['status'].astype(str).str.contains('Pendente', case=False)]
    
    for idx, row in pendentes.iterrows():
        with st.container(border=True):
            st.write(f"👤 **Cliente: {row['cliente']}**")
            
            # Tenta ler os itens com segurança
            try:
                lista_itens = json.loads(row['itens'])
                for item in lista_itens:
                    st.write(f"• {item.get('qtd', 0)}x {item.get('nome', 'Produto')}")
            except:
                st.error("Erro nos dados deste pedido.")
            
            # Botões Lado a Lado (como pediu)
            col1, col2 = st.columns(2)
            if col1.button("🗑️ EXCLUIR", key=f"del_{idx}"):
                df_atualizado = df_vendas.drop(idx)
                conn.update(worksheet="Pedidos", data=df_atualizado)
                st.rerun()
            
            if col2.button("✅ CONCLUIR", key=f"ok_{idx}", type="primary"):
                df_vendas.at[idx, 'status'] = 'Concluído'
                conn.update(worksheet="Pedidos", data=df_vendas)
                st.rerun()
