import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# Configuração da Página
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()

# Carga inicial dos dados
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Garante coluna status no estoque
if not df_produtos.empty and 'status' not in df_produtos.columns:
    df_produtos['status'] = 'Ativo'

# Estado da sessão para edição
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

# Menu Lateral
menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Lista de Colheita", "Montagem/Expedição", "Estoque"])

# --- FUNÇÃO DE IMPRESSÃO (ESTILIZADA) ---
def disparar_impressao_rawbt(ped):
    nome = str(ped.get('cliente', '')).strip().upper() if pd.notna(ped.get('cliente')) else ""
    endereco = str(ped.get('endereco', '')).strip().upper() if pd.notna(ped.get('endereco')) else ""
    status_raw = str(ped.get('pagamento', '')).strip().upper()
    exibir_pg = "PAGO" if status_raw == "PAGO" else ""
    valor_formatado = f"{float(ped['total']):.2f}".replace('.', ',')

    comandos = "\x1b\x61\x01" # Centralizar
    if nome: comandos += "\x1b\x21\x38" + nome + "\n"
    if endereco: comandos += "\x1b\x21\x38" + endereco + "\n"
    comandos += "\x1b\x21\x00" + "----------------\n"
    comandos += "TOTAL: RS " + valor_formatado + "\n"
    if exibir_pg: comandos += exibir_pg + "\n"
    comandos += "\n\n\n"
    
    try:
        b64_texto = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url_rawbt = f"intent:base64,{b64_texto}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'''
            <a href="{url_rawbt}" style="text-decoration: none;">
                <div style="background-color: #28a745; color: white; padding: 12px; text-align: center; border-radius: 8px; font-weight: bold; display: flex; align-items: center; justify-content: center; gap: 10px;">
                    <span style="font-size: 20px;">🖨️</span> IMPRIMIR
                </div>
            </a>''', unsafe_allow_html=True)
    except: st.error("Erro na etiqueta.")

# --- TELA: NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    with st.form("form_venda", clear_on_submit=True):
        c = st.text_input("Cliente", value=edit['cliente'] if edit else "")
        e = st.text_input("Endereço", value=edit['endereco'] if edit else "")
        fp = st.checkbox("Marcar como PAGO", value=(edit['pagamento'] == "Pago") if edit else False)
        st.write("---")
        
        itens_selecionados = []
        p_ativos = df_produtos[df_produtos['status'] == 'Ativo'] if not df_produtos.empty else pd.DataFrame()
        
        if not p_ativos.empty:
            for _, p in p_ativos.iterrows():
                def_val = 0
                if edit:
                    try:
                        for it in json.loads(edit['itens']):
                            if it['nome'] == p['nome']: def_val = int(it['qtd'])
                    except: pass
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, value=def_val, key=f"new_{p['id']}")
                if qtd > 0:
                    itens_selecionados.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * p['preco'])})
        
        if st.form_submit_button("✅ SALVAR PEDIDO"):
            if c and itens_selecionados:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo_p = pd.DataFrame([{
                    "id": prox_id, "cliente": c.upper(), "endereco": e.upper(), "itens": json.dumps(itens_selecionados),
                    "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if fp else "A Pagar"
                }])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_p], ignore_index=True))
                st.session_state.edit_data = None
                st.cache_data.clear()
                st.success("Salvo!")
                st.rerun()

# --- TELA: LISTA DE COLHEITA ---
elif menu == "Lista de Colheita":
    st.header("🚜 Resumo para Colheita")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    if pendentes.empty:
        st.info("Nen
