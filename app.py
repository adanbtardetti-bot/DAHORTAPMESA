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

# --- FUNÇÕES DE APOIO ---
def limpar_nan(texto):
    if pd.isna(texto): return ""
    return str(texto).strip()

def formatar_unidade(valor, tipo):
    try:
        v = float(valor)
        if tipo == "KG": return f"{v:.3f}".replace('.', ',') + " kg"
        return str(int(v)) + " un"
    except: return str(valor)

# --- CARREGAR E TRATAR DADOS ---
def carregar_tudo():
    df_p = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
    df_v = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
    df_p.columns = [str(c).lower().strip() for c in df_p.columns]
    df_v.columns = [str(c).lower().strip() for c in df_v.columns]
    
    # Blindagem contra Script Exception (Garante que as colunas existam)
    for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
        if col not in df_v.columns:
            df_v[col] = ""
    return df_p, df_v

df_produtos, df_pedidos = carregar_tudo()

# --- ESTILO BOTÃO IMPRIMIR ---
def botao_imprimir(ped, label="🖨️ IMPRIMIR"):
    try:
        nome = limpar_nan(ped.get('cliente', '')).upper()
        total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
        comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {total}\n\n\n\n"
        b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border:1px solid white;">{label}</div></a>', unsafe_allow_html=True)
    except: pass

# --- ABAS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tab1:
    st.header("🛒 Novo Pedido")
    
    # CLIENTE NO TOPO
    c1, c2 = st.columns(2)
    cli_nome = c1.text_input("NOME DO CLIENTE", key="input_nome").upper()
    cli_end = c2.text_input("ENDEREÇO", key="input_end").upper()
    cli_obs = st.text_area("OBSERVAÇÕES", key="input_obs").upper()
    cli_pago = st.checkbox("PAGO ANTECIPADO", key="input_pago")

    st.divider()
    
    # PRODUTOS COM SOMA REAL-TIME
    st.subheader("Itens")
    itens_selecionados = []
    total_previo = 0.0
    
    if not df_produtos.empty:
        p_ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        col1, col2 = st.columns(2)
        
        for i, (_, p) in enumerate(p_ativos.iterrows()):
            col_alvo = col1 if i % 2 == 0 else col2
            qtd = col_alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"q_{p['id']}")
            if qtd > 0:
                preco_f = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if p['tipo'] == "KG" else (qtd * preco_f)
                itens_selecionados.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                total_previo += sub
    
    st.markdown(f"### 💰 TOTAL ESTIMADO: R$ {total_previo:.2f}")

    if st.button("✅ SALVAR E ZERAR", use_container_width=True):
        if (cli_nome or cli_end) and itens_selecionados:
            prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty and str(df_pedidos['id'].max()).isdigit() else 1
            
            novo_ped = pd.DataFrame([{
                "id": prox_id, "cliente": cli_nome, "endereco": cli_end, "obs": cli_obs,
                "itens": json.dumps(itens_selecionados), "status": "Pendente",
                "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0
