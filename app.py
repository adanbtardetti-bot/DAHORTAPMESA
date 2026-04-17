import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import json
import urllib.parse

st.set_page_config(page_title="Horta da Mesa", layout="wide")

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()

df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# --- CONTROLE DE EDIÇÃO ---
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

# --- NAVEGAÇÃO ---
menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque", "Financeiro"])

# --- FUNÇÃO DE IMPRESSÃO RAWBT (DIRETA) ---
def disparar_impressao_rawbt(ped):
    # Criando o texto da etiqueta para a térmica
    status_pg = ped.get('pagamento', 'A Pagar')
    texto_etiqueta = f"""
@dahortapmesa 🌱
--------------------------------
CLIENTE: {ped['cliente']}
END: {ped['endereco']}
--------------------------------
TOTAL: R$ {float(ped['total']):.2f}
PAGTO: {status_pg}
--------------------------------
    """
    # Link especial para chamar o app RawBT no Android
    encoded_text = urllib.parse.quote(texto_etiqueta)
    rawbt_url = f"intent:#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;S.text={encoded_text};end;"
    
    st.markdown(f'<a href="{rawbt_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; padding:15px; background:#000; color:#fff; border-radius:10px; font-weight:bold; border:none;">🖨️ DISPARAR IMPRESSORA (RAWBT)</button></a>', unsafe_allow_html=True)

# --- TELA: NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    
    if edit:
        st.warning(f"Editando Pedido de: {edit['cliente']}")
        if st.button("❌ Cancelar Edição"):
            st.session_state.edit_data = None
            st.rerun()

    with st.form("form_venda"):
        c = st.text_input("Nome do Cliente", value=edit['cliente'] if edit else "")
        e = st.text_input("Endereço", value=edit['endereco'] if edit else "")
        pg = st.selectbox("Pagamento", ["A Pagar", "Pago", "Pix", "Dinheiro"], index=0)
        
        itens_p = []
        for _, p in df_produtos.iterrows():
            # Busca quantidade anterior se for edição
            def_qtd = 0
            if edit:
                for oi in json.loads(edit['itens']):
                    if oi['nome'] == p['nome']: def_qtd = oi.get('qtd', 1)
            
            qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, value=def_qtd, key=f"p_{p['id']}")
            if qtd > 0:
                sub = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
                itens_p.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
        
        if st.form_submit_button("✅ Salvar Pedido"):
            if c and itens_p:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo = pd.DataFrame([{
                    "id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_p),
                    "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), 
                    "total": 0.0, "pagamento": pg
                }])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
                st.session_state.edit_data = None
                st.cache_data.clear()
                st.success("Pedido enviado!")
                st.rerun()

# --- TELA: MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    
    for idx, ped in pendentes.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {ped['cliente']}")
            itens = json.loads(ped['itens'])
            t_real = 0.0
            trava_kg = False
            
            # MOSTRAR TODOS OS PRODUTOS (UNIDADE E KG)
            for i, it in enumerate(itens):
                if it['tipo'] == "KG":
                    v = st.number_input(f"Balança R$ ({it['nome']})", min_value=0.0, key=f"b_{ped['id']}_{i}")
                    it['subtotal'] = v
                    if v <= 0: trava_kg = True
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} un")
                    t_real += it['subtotal']
                
            # Soma os totais de KG após os inputs
            for it in itens:
                if it['tipo'] == "KG": t_real += it.get('subtotal', 0)
            
            st.markdown(f"#### Total: R$ {t_real:.2f}")
            
            # BOTÕES EM LINHA ÚNICA
            col1, col2, col3, col4 = st.columns(4)
            
            if col1.button("✅ Concluir", key=f"f_{ped['id']}", disabled=trava_kg):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_real
                df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

            with col2:
                # O botão de etiqueta agora é um link direto RawBT
                ped_copy = ped.to_dict()
                ped_copy['total'] = t_real
                disparar_impressao_rawbt(ped_copy)

            if col3.button("✏️ Editar", key=f"e_{ped['id']}"):
                st.session_state.edit_data = ped.to_dict()
                df_pedidos = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

            if col4.button("🗑️ Excluir", key=f"x_{ped['id']}"):
                df_pedidos = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()
