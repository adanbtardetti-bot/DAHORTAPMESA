import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import json

# Configuração da página
st.set_page_config(page_title="Gestão Horta", layout="wide")

# Conexão com a planilha
conn = st.connection("gsheets", type=GSheetsConnection)

# Função segura para carregar dados
def carregar_aba(nome_aba):
    try:
        # Tenta ler a aba da planilha
        df = conn.read(worksheet=nome_aba, ttl=0)
        if df is None or df.empty:
            raise ValueError
        return df.dropna(how="all")
    except:
        # Se falhar ou estiver vazio, cria o formato correto
        if nome_aba == "Produtos":
            return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "ativo"])
        else:
            return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total"])

# Carregar dados
df_produtos = carregar_aba("Produtos")
df_pedidos = carregar_aba("Pedidos")

menu = st.sidebar.radio("Navegação", ["Estoque", "Novo Pedido", "Montagem", "Financeiro"])

# --- TELA: ESTOQUE ---
if menu == "Estoque":
    st.header("⚙️ Cadastro de Produtos")
    with st.form("form_estoque", clear_on_submit=True):
        nome = st.text_input("Nome do Produto")
        preco = st.number_input("Preço Base (R$)", min_value=0.0, format="%.2f")
        tipo = st.selectbox("Tipo", ["Unidade", "KG"])
        
        if st.form_submit_button("💾 Salvar na Planilha"):
            if nome:
                # Gerar ID novo com segurança
                try:
                    novo_id = int(df_produtos['id'].max() + 1)
                except:
                    novo_id = 1
                
                novo_p = pd.DataFrame([{"id": novo_id, "nome": nome, "preco": preco, "tipo": tipo, "ativo": True}])
                df_atualizado = pd.concat([df_produtos, novo_p], ignore_index=True)
                
                # Salvar
                conn.update(worksheet="Produtos", data=df_atualizado)
                st.cache_data.clear()
                st.success(f"✅ {nome} salvo com sucesso!")
                st.rerun()
            else:
                st.error("Preencha o nome do produto!")

    st.subheader("Lista Atual")
    st.dataframe(df_produtos, use_container_width=True)

# --- TELA: NOVO PEDIDO ---
elif menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    if df_produtos.empty:
        st.warning("⚠️ Cadastre produtos no Estoque primeiro!")
    else:
        with st.form("form_venda"):
            c_nome = st.text_input("Nome do Cliente")
            c_end = st.text_input("Endereço de Entrega")
            st.divider()
            
            venda_itens = []
            total_venda = 0.0
            
            for _, p in df_produtos.iterrows():
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"v_{p['id']}")
                if qtd > 0:
                    sub = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
                    total_venda += sub
                    venda_itens.append({"id": p['id'], "nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
            
            if st.form_submit_button("✅ Finalizar Lançamento"):
                try:
                    novo_id_ped = int(df_pedidos['id'].max() + 1)
                except:
                    novo_id_ped = 1
                
                novo_ped = pd.DataFrame([{
                    "id": novo_id_ped, "cliente": c_nome, "endereco": c_end, 
                    "itens": json.dumps(venda_itens), "status": "Pendente", 
                    "data": datetime.now().strftime("%d/%m/%Y"), "total": total_venda
                }])
                
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_ped], ignore_index=True))
                st.cache_data.clear()
                st.success("Pedido gravado na nuvem!")
                st.rerun()
