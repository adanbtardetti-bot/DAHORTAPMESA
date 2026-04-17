import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# Configuração da Página
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def limpar_nan(texto):
    t = str(texto).replace('nan', '').replace('NaN', '').strip()
    return t if t != "" else "N/A"

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.dropna(how="all")
    except:
        return pd.DataFrame()

# Carga inicial com verificação de colunas
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Garante que as colunas existam para não dar erro de "Key"
if df_pedidos.empty:
    df_pedidos = pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"])

if not df_produtos.empty and 'status' not in df_produtos.columns:
    df_produtos['status'] = 'Ativo'

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

# --- NAVEGAÇÃO POR ABAS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "🥦 ESTOQUE"])

# --- FUNÇÃO DE IMPRESSÃO ---
def disparar_impressao_rawbt(ped, label="IMPRIMIR ETIQUETA"):
    try:
        nome = limpar_nan(ped.get('cliente')).upper()
        endereco = limpar_nan(ped.get('endereco')).upper()
        pgto = limpar_nan(ped.get('pagamento')).upper()
        valor = ped.get('total', 0)
        valor_fmt = f"{float(valor):.2f}".replace('.', ',')
        
        comandos = "\x1b\x61\x01" 
        if nome != "N/A": comandos += "\x1b\x21\x38" + nome + "\n"
        if endereco != "N/A": comandos += "\x1b\x21\x38" + endereco + "\n"
        comandos += "\x1b\x21\x00" + "----------------\n"
        comandos += "TOTAL: RS " + valor_fmt + "\n"
        if pgto == "PAGO": comandos += "PAGO\n"
        comandos += "\n\n\n\n"
        
        b64_texto = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url_rawbt = f"intent:base64,{b64_texto}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'''<a href="{url_rawbt}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">🖨️ {label}</div></a>''', unsafe_allow_html=True)
    except: st.error("Erro ao gerar etiqueta.")

# --- ABA 1: NOVO PEDIDO ---
with tab1:
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    with st.form("form_venda", clear_on_submit=True):
        col_c1, col_c2 = st.columns(2)
        c = col_c1.text_input("NOME DO CLIENTE", value=edit['cliente'] if edit else "").upper()
        e = col_c2.text_input("ENDEREÇO", value=edit['endereco'] if edit else "").upper()
        fp = st.checkbox("MARCAR COMO PAGO", value=(edit['pagamento'] == "Pago") if edit else False)
        st.write("---")
        itens_selecionados = []
        if not df_produtos.empty:
            p_ativos = df_produtos[df_produtos['status'] == 'Ativo']
            cols_p = st.columns(3)
            for i, (_, p) in enumerate(p_ativos.iterrows()):
                with cols_p[i % 3]:
                    qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"n_{p['id']}")
                    if qtd > 0:
                        itens_selecionados.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * p['preco'])})
        if st.form_submit_button("✅ SALVAR PEDIDO", use_container_width=True):
            if c and itens_selecionados:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo_p = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_selecionados), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if fp else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_p], ignore_index=True))
                st.session_state.edit_data = None; st.cache_data.clear(); st.rerun()

# --- ABA 2: COLHEITA ---
with tab2:
    st.header("🚜 Lista de Colheita")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"] if not df_pedidos.empty else pd.DataFrame()
    if pendentes.empty: st.info("N
