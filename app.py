import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import json

# Configuração da Página
st.set_page_config(page_title="Horta da Mesa - Gestão", layout="wide")

# Conexão com Google Sheets usando as Secrets (JSON)
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        if df is None or df.empty:
            if aba == "Produtos":
                return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "ativo"])
            return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total"])
        return df.dropna(how="all")
    except:
        if aba == "Produtos":
            return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "ativo"])
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total"])

# Carregar dados globais
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Menu Lateral
st.sidebar.title("🌿 Horta da Mesa")
menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque", "Financeiro"])

# --- TELA: ESTOQUE ---
if menu == "Estoque":
    st.header("⚙️ Gestão de Produtos")
    with st.form("add_prod", clear_on_submit=True):
        col1, col2, col3 = st.columns([3, 1, 1])
        nome = col1.text_input("Nome do Produto")
        preco = col2.number_input("Preço (R$)", min_value=0.0)
        tipo = col3.selectbox("Tipo", ["Unidade", "KG"])
        if st.form_submit_button("💾 Salvar Produto"):
            if nome:
                prox_id = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
                novo = pd.DataFrame([{"id": prox_id, "nome": nome, "preco": preco, "tipo": tipo, "ativo": True}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, novo], ignore_index=True))
                st.cache_data.clear()
                st.success("Produto salvo!")
                st.rerun()

    st.subheader("Lista de Itens")
    st.dataframe(df_produtos, use_container_width=True)

# --- TELA: NOVO PEDIDO ---
elif menu == "Novo Pedido":
    st.header("🛒 Lançar Pedido")
    with st.form("venda"):
        cliente = st.text_input("Cliente")
        endereco = st.text_input("Endereço")
        st.divider()
        itens_selecionados = []
        total_previsto = 0.0
        
        for _, p in df_produtos.iterrows():
            qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"v_{p['id']}")
            if qtd > 0:
                sub = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
                total_previsto += sub
                itens_selecionados.append({"id": int(p['id']), "nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "preco": p['preco'], "subtotal": sub})
        
        if st.form_submit_button("✅ Finalizar Pedido"):
            if cliente and itens_selecionados:
                p_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo_ped = pd.DataFrame([{
                    "id": p_id, "cliente": cliente, "endereco": endereco,
                    "itens": json.dumps(itens_selecionados), "status": "Pendente",
                    "data": datetime.now().strftime("%d/%m/%Y"), "total": total_previsto
                }])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_ped], ignore_index=True))
                st.cache_data.clear()
                st.success("Pedido enviado para montagem!")
                st.rerun()

# --- TELA: MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Montagem e Pesagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pendentes.iterrows():
        with st.expander(f"Pedido #{ped['id']} - {ped['cliente']}"):
            itens = json.loads(ped['itens'])
            t_real = 0.0
            for it in itens:
                if it['tipo'] == "KG":
                    it['subtotal'] = st.number_input(f"Peso Final (R$): {it['nome']}", value=0.0, key=f"m_{ped['id']}_{it['id']}")
                else:
                    st.write(f"✅ {it['nome']}: {it['qtd']} un")
                t_real += it['subtotal']
            
            st.write(f"**Total Real: R$ {t_real:.2f}**")
            if st.button(f"Concluir Pedido #{ped['id']}"):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_real
                df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

# --- TELA: FINANCEIRO ---
elif menu == "Financeiro":
    st.header("💰 Financeiro")
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"]
    if not concluidos.empty:
        st.metric("Faturamento Total", f"R$ {concluidos['total'].sum():.2f}")
        vendas_resumo = {}
        for _, p in concluidos.iterrows():
            its = json.loads(p['itens'])
            for i in its:
                vendas_resumo[i['nome']] = vendas_resumo.get(i['nome'], 0.0) + i['subtotal']
        df_fin = pd.DataFrame(list(vendas_resumo.items()), columns=["Produto", "Total Faturado"])
        st.table(df_fin.sort_values(by="Total Faturado", ascending=False))
    else:
        st.info("Nenhuma venda concluída.")
