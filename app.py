import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import urllib.parse
import json

st.set_page_config(page_title="Horta Gestão", layout="wide")

# Conexão Direta
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        # Tenta ler a aba; se falhar, cria um DataFrame vazio com as colunas certas
        df = conn.read(worksheet=aba, ttl=0)
        return df.dropna(how="all")
    except:
        if aba == "Produtos":
            return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "ativo"])
        else:
            return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "obs", "data", "total"])

# Carregamento Inicial
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque", "Financeiro"])

# --- TELA ESTOQUE ---
if menu == "Estoque":
    st.header("⚙️ Cadastro de Produtos")
    with st.form("novo_prod", clear_on_submit=True):
        nome = st.text_input("Nome do Produto")
        preco = st.number_input("Preço", min_value=0.0)
        tipo = st.selectbox("Tipo", ["Unidade", "KG"])
        if st.form_submit_button("💾 Salvar na Planilha"):
            if nome:
                novo_id = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
                novo_p = pd.DataFrame([{"id": novo_id, "nome": nome, "preco": preco, "tipo": tipo, "ativo": True}])
                df_final = pd.concat([df_produtos, novo_p], ignore_index=True)
                conn.update(worksheet="Produtos", data=df_final)
                st.cache_data.clear()
                st.success("Produto salvo! Verifique sua planilha agora.")
                st.rerun()
    
    st.subheader("Produtos na Nuvem")
    st.write(df_produtos)

# --- TELA NOVO PEDIDO ---
elif menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    c_nome = st.text_input("Cliente")
    c_end = st.text_input("Endereço")
    
    itens_venda = []
    total_parcial = 0.0
    
    if not df_produtos.empty:
        for _, p in df_produtos.iterrows():
            qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"v_{p['id']}")
            if qtd > 0:
                sub = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
                total_parcial += sub
                itens_venda.append({"id": p['id'], "nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
        
        st.markdown(f"### Total: R$ {total_parcial:.2f}")
        
        if st.button("💾 Finalizar Pedido", use_container_width=True):
            p_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
            novo_ped = pd.DataFrame([{
                "id": p_id, "cliente": c_nome, "endereco": c_end, 
                "itens": json.dumps(itens_venda), "status": "Pendente", 
                "data": datetime.now().strftime("%d/%m/%Y"), "total": total_parcial
            }])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_ped], ignore_index=True))
            st.cache_data.clear()
            st.success("Pedido enviado para a nuvem!")
            st.rerun()
    else:
        st.info("Cadastre produtos no estoque primeiro.")

# --- TELA MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Montagem")
    pends = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pends.iterrows():
        with st.expander(f"Pedido #{ped['id']} - {ped['cliente']}"):
            itens = json.loads(ped['itens'])
            t_final = 0.0
            for it in itens:
                if it['tipo'] == "KG":
                    v_kg = st.number_input(f"Valor Balança: {it['nome']}", value=0.0, key=f"m_{ped['id']}_{it['id']}")
                    it['subtotal'] = v_kg
                t_final += it['subtotal']
            
            st.write(f"**Total Real: R$ {t_final:.2f}**")
            
            if st.button(f"Concluir e Salvar #{ped['id']}"):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_final
                df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

# --- TELA FINANCEIRO ---
elif menu == "Financeiro":
    st.header("💰 Resumo Financeiro")
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"]
    st.metric("Total Vendido (Nuvem)", f"R$ {concluidos['total'].sum():.2f}")
    st.dataframe(concluidos[['cliente', 'data', 'total']])
