import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import json
import urllib.parse

# Configuração da Página
st.set_page_config(page_title="Horta da Mesa - Gestão", layout="wide", initial_sidebar_state="expanded")

# --- CONEXÃO COM GOOGLE SHEETS ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Erro na conexão! Verifique se as 'Secrets' no Streamlit Cloud estão configuradas corretamente.")

# --- FUNÇÕES DE DADOS ---
def carregar_dados(aba):
    try:
        # Tenta ler a aba; se falhar ou estiver vazia, cria estrutura padrão
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

def salvar_dados(aba, df):
    try:
        conn.update(worksheet=aba, data=df)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar no Google Sheets: {e}")
        st.info("Verifique se a planilha está compartilhada como 'EDITOR' para 'Qualquer pessoa com o link'.")
        return False

# --- CARREGAMENTO INICIAL ---
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# --- MENU LATERAL ---
st.sidebar.title("🌿 Horta da Mesa")
menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque", "Financeiro", "Histórico"])

# --- TELA: ESTOQUE ---
if menu == "Estoque":
    st.header("⚙️ Gestão de Produtos")
    with st.form("cad_produto", clear_on_submit=True):
        col1, col2 = st.columns(2)
        nome = col1.text_input("Nome do Produto (Ex: Alface Crespa)")
        preco = col2.number_input("Preço Base (R$)", min_value=0.0, format="%.2f")
        tipo = st.selectbox("Tipo de Venda", ["Unidade", "KG"])
        
        if st.form_submit_button("💾 Salvar Produto"):
            if nome:
                novo_id = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
                novo_p = pd.DataFrame([{"id": novo_id, "nome": nome, "preco": preco, "tipo": tipo, "ativo": True}])
                df_final = pd.concat([df_produtos, novo_p], ignore_index=True)
                if salvar_dados("Produtos", df_final):
                    st.success(f"Produto '{nome}' salvo na nuvem!")
                    st.rerun()
            else:
                st.warning("O nome do produto é obrigatório.")

    st.subheader("Produtos Cadastrados")
    st.dataframe(df_produtos, use_container_width=True)

# --- TELA: NOVO PEDIDO ---
elif menu == "Novo Pedido":
    st.header("🛒 Lançar Novo Pedido")
    if df_produtos.empty:
        st.warning("Vá em 'Estoque' e cadastre seus produtos primeiro!")
    else:
        with st.form("form_pedido"):
            c1, c2 = st.columns(2)
            cliente = c1.text_input("Nome do Cliente")
            endereco = c2.text_input("Endereço/Ponto de Entrega")
            
            st.write("---")
            st.subheader("Escolha os Itens")
            itens_selecionados = []
            total_estimado = 0.0
            
            # Lista produtos ativos
            for _, p in df_produtos.iterrows():
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']}/{p['tipo']})", min_value=0, key=f"p_{p['id']}")
                if qtd > 0:
                    sub = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
                    total_estimado += sub
                    itens_selecionados.append({
                        "id": int(p['id']), "nome": p['nome'], "qtd": qtd, 
                        "tipo": p['tipo'], "preco": p['preco'], "subtotal": sub
                    })
            
            st.write(f"### Total Estimado: R$ {total_estimado:.2f}")
            
            if st.form_submit_button("✅ Gravar Pedido"):
                if cliente and itens_selecionados:
                    novo_id_ped = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                    novo_ped = pd.DataFrame([{
                        "id": novo_id_ped, "cliente": cliente, "endereco": endereco,
                        "itens": json.dumps(itens_selecionados), "status": "Pendente",
                        "data": datetime.now().strftime("%d/%m/%Y"), "total": total_estimado
                    }])
                    if salvar_dados("Pedidos", pd.concat([df_pedidos, novo_ped], ignore_index=True)):
                        st.success("Pedido registrado com sucesso!")
                        st.rerun()
                else:
                    st.error("Preencha o nome do cliente e escolha pelo menos um item.")

# --- TELA: MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Montagem e Pesagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    
    if pendentes.empty:
        st.info("Não há pedidos pendentes para montagem.")
    else:
        for idx, ped in pendentes.iterrows():
            with st.expander(f"Pedido #{ped['id']} - {ped['cliente']}"):
                itens = json.loads(ped['itens'])
                total_real = 0.0
                st.write(f"📍 **Entrega:** {ped['endereco']}")
                
                for it in itens:
                    if it['tipo'] == "KG":
                        v_balanca = st.number_input(f"Peso/Valor Balança: {it['nome']}", value=float(it['subtotal']), key=f"m_{ped['id']}_{it['id']}")
                        it['subtotal'] = v_balanca
                    else:
                        st.write(f"✅ {it['nome']}: {it['qtd']} un (R$ {it['subtotal']:.2f})")
                    total_real += it['subtotal']
                
                st.write(f"**Total Real: R$ {total_real:.2f}**")
                
                if st.button(f"Finalizar e Salvar #{ped['id']}"):
                    df_pedidos.at[idx, 'status'] = "Concluído"
                    df_pedidos.at[idx, 'total'] = total_real
                    df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                    if salvar_dados("Pedidos", df_pedidos):
                        st.success("Pedido concluído!")
                        st.rerun()

# --- TELA: FINANCEIRO ---
elif menu == "Financeiro":
    st.header("💰 Resumo Financeiro")
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"]
    
    if concluidos.empty:
        st.info("Nenhuma venda concluída para gerar relatório.")
    else:
        col1, col2 = st.columns(2)
        total_geral = concluidos['total'].sum()
        col1.metric("Faturamento Total", f"R$ {total_geral:.2f}")
        col2.metric("Pedidos Entregues", len(concluidos))
        
        # Resumo por Produto
        st.subheader("Vendas por Produto")
        vendas_prod = {}
        for _, p in concluidos.iterrows():
            its = json.loads(p['itens'])
            for i in its:
                vendas_prod[i['nome']] = vendas_prod.get(i['nome'], 0) + i['subtotal']
        
        df_f = pd.DataFrame(list(vendas_prod.items()), columns=['Produto', 'Faturamento (R$)'])
        st.table(df_f.sort_values(by='Faturamento (R$)', ascending=False))

# --- TELA: HISTÓRICO ---
elif menu == "Histórico":
    st.header("📜 Histórico de Pedidos")
    st.dataframe(df_pedidos, use_container_width=True)
