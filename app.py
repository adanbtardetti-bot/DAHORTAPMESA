import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        df_p = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        # Padroniza colunas para evitar o KeyError
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        
        colunas_necessarias = ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']
        for col in colunas_necessarias:
            if col not in df_v.columns:
                df_v[col] = ""
        return df_p, df_v
    except Exception as e:
        st.error(f"Erro ao conectar com a planilha: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- 2. MOTOR DE IMPRESSÃO (CORRIGIDO) ---
def imprimir_comando(ped, valor_real, tipo="ETIQUETA"):
    def limpar(txt):
        if pd.isna(txt) or str(txt).lower() == 'nan': return ""
        return str(txt).strip().upper()
    
    nome = limpar(ped.get('cliente', ''))
    end = limpar(ped.get('endereco', ''))
    pag = limpar(ped.get('pagamento', ''))
    v_f = f"{float(valor_real):.2f}".replace('.', ',')
    
    if tipo == "ETIQUETA":
        txt_pg = f"\\n*** {pag} ***\\n" if "PAGO" in pag else "\\n"
        cmds = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{end}{txt_pg}\n\x1b\x61\x01\x1b\x21\x10TOTAL: RS {v_f}\n\n\n\n"
        label, cor = "🖨️ ETIQUETA", "#28a745"
    else:
        detalhes = ""
        try:
            for it in json.loads(ped['itens']):
                detalhes += f"{it['nome'][:15]} {it['qtd']}{it['tipo']} -> RS {float(it['subtotal']):.2f}\n"
        except: detalhes = "Erro nos itens"
        cmds = f"\x1b\x61\x01\x1b\x21\x10HORTA DA MESA\n\x1b\x21\x00\n--------------------------------\nCLIENTE: {nome}\nDATA: {ped['data']}\n--------------------------------\n{detalhes}--------------------------------\nTOTAL: RS {v_f}\nPGTO: {pag}\n\n\n\n"
        label, cor = "📄 RECIBO", "#007bff"

    b64 = base64.b64encode(cmds.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    # AQUI ESTAVA O ERRO DE SINTAXE - AGORA FECHADO CORRETAMENTE
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:{cor};color:white;padding:8px;text-align:center;border-radius:5px;font-weight:bold;font-size:12px;margin:2px 0px;">{label}</div></a>', unsafe_allow_html=True)

# --- 3. ABAS ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# NOVO PEDIDO
with tabs[0]:
    if "f_id" not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    c1, c2 = st.columns(2)
    n = c1.text_input("NOME DO CLIENTE", key=f"n{f}").upper()
    e = c2.text_input("ENDEREÇO", key=f"e{f}").upper()
    o = st.text_area("OBSERVAÇÕES", key=f"o{f}", height=80).upper()
    p_check = st.checkbox("PAGO ANTECIPADO", key=f"p{f}")
    
    st.markdown("### 🥦 Itens")
    itens_venda, total_estimado = [], 0.0
    if not df_produtos.empty and 'status' in df_produtos.columns:
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for _, row in ativos.iterrows():
            col_a, col_b = st.columns([4, 1])
            qtd = col_b
