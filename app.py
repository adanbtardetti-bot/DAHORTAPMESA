import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

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

if not df_produtos.empty and 'status' not in df_produtos.columns:
    df_produtos['status'] = 'Ativo'

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque"])

# --- FUNÇÃO DE IMPRESSÃO ---
def disparar_impressao_rawbt(ped):
    nome = str(ped.get('cliente', '')).strip().upper() if pd.notna(ped.get('cliente')) else ""
    endereco = str(ped.get('endereco', '')).strip().upper() if pd.notna(ped.get('endereco')) else ""
    status_raw = str(ped.get('pagamento', '')).strip().upper()
    exibir_pg = "PAGO" if status_raw == "PAGO" else ""
    valor_formatado = f"{float(ped['total']):.2f}".replace('.', ',')

    comandos = "\x1b\x61\x01" 
    if nome: comandos += "\x1b\x21\x38" + nome + "\n"
    if endereco: comandos += "\x1b\x21\x38" + endereco + "\n"
    comandos += "\x1b\x21\x00" + "----------------\n"
    comandos += "TOTAL: RS " + valor_formatado + "\n"
    if exibir_pg: comandos += exibir_pg + "\n"
    comandos += "\n\n\n"
    
    try:
        b64_texto = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url_rawbt = f"intent:base64,{b64_texto}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'<a href="{url_rawbt}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;font-size:20px;">🖨️ IMPRIMIR ETIQUETA</div></a>', unsafe_allow_html=True)
    except: st.error("Erro nos caracteres.")

# --- TELAS DE OPERAÇÃO (IGUAIS) ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    with st.form("form_venda", clear_on_submit=True):
        c = st.text_input("Cliente", value=edit['cliente'] if edit else "")
        e = st.text_input("Endereço", value=edit['endereco'] if edit else "")
        foi_pago = st.checkbox("Marcar como PAGO", value=(edit['pagamento'] == "Pago") if edit else False)
        st.write("---")
        itens_p = []
        produtos_ativos = df_produtos[df_produtos['status'] == 'Ativo'] if not df_produtos.empty else pd.DataFrame()
        if not produtos_ativos.empty:
            for _, p in produtos_ativos.iterrows():
                def_qtd = 0
                if edit:
                    try:
                        for oi in json.loads(edit['itens']):
                            if oi['nome'] == p['nome']: def_qtd = int(oi.get('qtd', 0))
                    except: pass
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, value=def_qtd, key=f"p_{p['id']}")
                if qtd > 0: itens_p.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * p['preco'])})
        if st.form_submit_button("✅ SALVAR PEDIDO"):
            if c and itens_p:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo_df = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_p), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if foi_pago else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_df], ignore_index=True))
                st.session_state.edit_data = None; st.cache_data.clear(); st.rerun()

elif menu == "Montagem/Expedição":
    st.header("📦 Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pendentes.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {ped['cliente']}")
            itens = json.loads(ped['itens']); t_real = 0.0; trava_kg = False
            for i, it in enumerate(itens):
                if it['tipo'] == "KG":
                    st.write(f"⚖️ **{it['nome']}**")
                    v_input = st.text_input(f"Valor R$:", key=f"v_{ped['id']}_{i}")
                    if v_input:
                        try: t_real += float(v_input.replace(',', '.')); it['subtotal'] = float(v_input.replace(',', '.'))
                        except: trava_kg = True
                    else: trava_kg = True
                else: st.write(f"✅ {it['nome']} - {it['qtd']} un"); t_real += it['subtotal']
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("✅ Concluir", key=f"f_{ped['id']}", disabled=trava_kg):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
            with c2: disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})
            if c3.button("✏️ Editar", key=f"e_{ped['id']}"):
                st.session_state.edit_data = ped.to_dict(); conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()
            if c4.button("🗑️ Excluir", key=f"x_{ped['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()

# --- TELA: ESTOQUE (LAYOUT NOVO E LIMPO) ---
elif menu == "Estoque":
    st.title("🥦 Controle de Estoque")
    
    # Busca e Cadastro na mesma linha superior
    col_busca, col_add = st.columns([2, 1])
    busca = col_busca.text_input("🔍 Buscar Produto", "").upper()
    
    with col_add.expander("➕ Novo Item"):
        with st.form("quick_add"):
            n = st.text_input("Nome")
            p = st.number_input("Preço", min_value=0.0)
            t
