import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime, timedelta

# Configuração da Página
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# Conexão
conn = st.connection("gsheets", type=GSheetsConnection)

def limpar_nan(texto):
    if pd.isna(texto): return ""
    return str(texto).strip()

def formatar_unidade(valor, tipo):
    try:
        v = float(valor)
        if tipo == "KG": return f"{v:.3f}".replace('.', ',') + " kg"
        return str(int(v)) + " un"
    except: return str(valor)

# --- CARREGAR DADOS ---
df_produtos = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
df_pedidos = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
df_produtos.columns = [str(c).lower().strip() for c in df_produtos.columns]
df_pedidos.columns = [str(c).lower().strip() for c in df_pedidos.columns]

# --- ESTILO BOTÃO IMPRIMIR ---
def botao_imprimir(ped, label="🖨️ IMPRIMIR"):
    try:
        nome = limpar_nan(ped.get('cliente', '')).upper()
        total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
        comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {total}\n\n\n\n"
        b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">{label}</div></a>', unsafe_allow_html=True)
    except: pass

# --- NAVEGAÇÃO ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tab1:
    st.header("🛒 Novo Pedido")
    
    # 1. IDENTIFICAÇÃO NO TOPO
    c1, c2 = st.columns(2)
    cli = c1.text_input("NOME DO CLIENTE", key="cli_nome").upper()
    end = c2.text_input("ENDEREÇO DE ENTREGA", key="cli_end").upper()
    obs = st.text_area("OBSERVAÇÕES (Troco, ponto de referência...)", key="cli_obs").upper()
    pago_f = st.checkbox("JÁ ESTÁ PAGO?", key="cli_pago")

    st.divider()
    
    # 2. SELEÇÃO DE ITENS E SOMA EM TEMPO REAL
    st.subheader("Selecione os Produtos")
    itens_sel = []
    v_previo = 0.0
    
    if not df_produtos.empty:
        p_ativos = df_produtos[df_produtos['status'] == 'Ativo']
        # Usamos colunas para não ficar uma lista gigante vertical
        col_prod1, col_prod2 = st.columns(2)
        
        for i, (_, p) in enumerate(p_ativos.iterrows()):
            alvo = col_prod1 if i % 2 == 0 else col_prod2
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"n_{p['id']}")
            if qtd > 0:
                preco_num = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if p['tipo'] == "KG" else (qtd * preco_num)
                itens_sel.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                v_previo += sub
    
    st.markdown(f"### 💰 TOTAL PRÉVIO: R$ {v_previo:.2f}")

    # 3. BOTÃO SALVAR (Com lógica de zerar campos)
    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (cli or end) and itens_sel:
            prox_id = int(df
