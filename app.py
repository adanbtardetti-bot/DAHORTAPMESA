import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import json

st.set_page_config(page_title="Horta da Mesa", layout="wide")

# Conexão
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()

df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# --- LÓGICA DE EDIÇÃO (SESSION STATE) ---
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

# --- ETIQUETA ---
def gerar_etiqueta_html(ped):
    status_pg = ped.get('pagamento', 'A Pagar')
    html = f"""
    <div id="etiqueta" style="border: 2px solid #000; border-radius: 10px; padding: 15px; width: 260px; font-family: 'Arial'; background: #fff; color: #000;">
        <div style="display: flex; justify-content: space-between; font-weight: bold;">
            <span>@dahortapmesa</span><span>🌿</span>
        </div>
        <hr style="border: 0.5px solid #000">
        <div style="font-size: 22px; font-weight: bold; margin: 10px 0;">{ped['cliente']}</div>
        <div style="font-size: 16px; margin-bottom: 10px; height: 40px;">{ped['endereco']}</div>
        <div style="display: flex; justify-content: space-between; align-items: center; border-top: 2px solid #000; padding-top: 10px;">
            <span style="font-size: 20px; font-weight: bold;">R$ {float(ped['total']):.2f}</span>
            <span style="font-size: 14px; font-weight: bold;">{status_pg}</span>
        </div>
    </div>
    <br>
    <button onclick="window.print()" style="width: 260px; padding: 12px; background: #000; color: #fff; border: none; border-radius: 5px; font-weight: bold;">🖨️ IMPRIMIR ETIQUETA</button>
    """
    return html

# --- NAVEGAÇÃO ---
menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque", "Financeiro"])

# --- NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Lançar / Editar Pedido")
    
    # Preenche se estiver vindo de uma edição
    edit = st.session_state.edit_data
    with st.form("form_venda", clear_on_submit=True):
        c = st.text_input("Nome do Cliente", value=edit['cliente'] if edit else "")
        e = st.text_input("Endereço", value=edit['endereco'] if edit else "")
        pg = st.selectbox("Pagamento", ["A Pagar", "Pago", "Pix", "Dinheiro"], 
                          index=["A Pagar", "Pago", "Pix", "Dinheiro"].index(edit['pagamento']) if edit else 0)
        
        st.write("---")
        itens_p = []
        for _, p in df_produtos.iterrows():
            # Tenta recuperar a quantidade se for edição
            default_qtd = 0
            if edit:
                old_itens = json.loads(edit['itens'])
                for oi in old_itens:
                    if oi['nome'] == p['nome']: default_qtd = oi['qtd']
            
            qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, value=default_qtd, key=f"p_{p['id']}")
            if qtd > 0:
                sub = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
                itens_p.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
        
        if st.form_submit_button("✅ Finalizar e Enviar"):
            if c and itens_p:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo = pd.DataFrame([{
                    "id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_p),
                    "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), 
                    "total": 0.0, "pagamento": pg
                }])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
                st.session_state.edit_data = None # Limpa edição
                st.cache_data.clear()
                st.success("Pedido salvo com sucesso!")
                st.rerun()

# --- MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Central de Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    
    for idx, ped in pendentes.iterrows():
        with st.container(border=True):
            st.subheader(f"{ped['cliente']}")
            itens = json.loads(ped['itens'])
            t_real = 0.0
            trava_kg = False
            
            for i, it in enumerate(itens):
                if it['tipo'] == "KG":
                    v = st.number_input(f"Balança R$ ({it['nome']})", min_value=0.0, key=f"b_{ped['id']}_{i}")
                    it['subtotal'] = v
                    if v <= 0: trava_kg = True
                t_real += it['subtotal']
            
            st.write(f"**Total Pedido: R$ {t_real:.2f}**")
            
            # Layout de Botões
            c1, c2, c3, c4 = st.columns(4)
            
            if c1.button("✅ Concluir", key=f"f_{ped['id']}", disabled=trava_kg, type="primary"):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_real
                df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

            if c2.button("🖨️ Etiqueta", key=f"t_{ped['id']}"):
                p_copy = ped.to_dict()
                p_copy['total'] = t_real
                st.components.v1.html(gerar_etiqueta_html(p_copy), height=380)

            if c3.button("✏️ Editar", key=f"ed_{ped['id']}"):
                # Lógica: Salva os dados na memória, exclui da planilha e manda pro formulário
                st.session_state.edit_data = ped.to_dict()
                df_pedidos = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.info("Carregando dados no formulário...")
                st.rerun() # O menu vai mudar via lógica se você clicar manualmente em Novo Pedido

            if c4.button("🗑️ Excluir", key=f"x_{ped['id']}"):
                df_pedidos = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

# --- ESTOQUE E FINANCEIRO MANTIDOS ---
elif menu == "Estoque":
    st.header("⚙️ Cadastro de Itens")
    # (Mesmo código de estoque anterior)
    with st.form("estoq"):
        n = st.text_input("Nome")
        p = st.number_input("Preço")
        t = st.selectbox("Tipo", ["Unidade", "KG"])
        if st.form_submit_button("Salvar"):
            prox = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
            df_produtos = pd.concat([df_produtos, pd.DataFrame([{"id":prox,"nome":n,"preco":p,"tipo":t,"ativo":True}])])
            conn.update(worksheet="Produtos", data=df_produtos)
            st.rerun()
    st.dataframe(df_produtos)
