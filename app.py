import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# 1. Configuração e Conexão
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# Controle de limpeza
if "form_id" not in st.session_state:
    st.session_state.form_id = 0

# Função de leitura robusta
def carregar_dados():
    try:
        df_p = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except: return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- ETIQUETA ---
def botao_imprimir(ped, valor_real, label="🖨️ IMPRIMIR"):
    def limpar(txt):
        if pd.isna(txt) or str(txt).lower() == 'nan': return ""
        return str(txt).strip().upper()
    nome = limpar(ped.get('cliente', ''))
    endereco = limpar(ped.get('endereco', ''))
    pagamento = limpar(ped.get('pagamento', ''))
    txt_status = f"\n*** {pagamento} ***\n" if "PAGO" in pagamento else "\n"
    valor_formatado = f"{float(valor_real):.2f}".replace('.', ',')
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{endereco}\n{txt_status}\n\x1b\x61\x01\x1b\x21\x10TOTAL: RS {valor_formatado}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div
