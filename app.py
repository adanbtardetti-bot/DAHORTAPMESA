import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# 1. Configuração da Página
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# 2. Conexão (TTL de 10 segundos para não estourar a cota do Google)
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÃO DE CARREGAMENTO ---
def carregar_dados():
    try:
        df_p = conn.read(worksheet="Produtos", ttl=10).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=10).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except Exception as e:
        if "429" in str(e):
            st.error("⏳ Muita pressa! O Google limitou o acesso. Aguarde 30 segundos.")
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- FUNÇÃO PARA LIMPAR CAMPOS ---
def limpar_campos():
    for key in st.session_state.keys():
        if key.startswith("v_") or key in ["c_nome", "c_end", "c_obs", "c_pago"]:
            st.session_state[key] = "" if isinstance(st.session_state[key], str) else 0 if isinstance(st.session_state[key], int) else False

# --- NAVEGAÇÃO ---
# Aqui definimos as variáveis tab1, tab2... para evitar o NameError
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tab1:
    st.header("🛒 Novo Pedido")
    
    # Identificação no Topo
    col1, col2 = st.columns(2)
    nome = col1.text_input("NOME DO CLIENTE", key="c_nome").upper()
    endereco = col2.text_input("ENDEREÇO", key="c_end").upper()
    observacao = st.text_area("OBSERVAÇÕES", key="c_obs").upper()
    pago_ja = st.checkbox("PAGO ANTECIPADO", key="c_pago")

    st.divider()
    
    # Itens e Cálculo
    st.subheader("Itens")
    itens_venda = []
    total_preview = 0.0
    
    if not df_produtos.empty:
        p_ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        cp1, cp2 = st.columns(2)
        for i, (_, p) in enumerate(p_ativos.iterrows()):
            alvo = cp1 if i % 2 == 0 else cp2
            # Key dinâmica para resetar depois
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"v_{p['id']}")
            if qtd > 0:
                preco_f = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if p['tipo'] == "KG" else (qtd * preco_f)
                itens_venda.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                total_preview += sub
    
    st.markdown(f"## 💰 TOTAL: R$ {total_preview:.2f}")

    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (nome or endereco) and itens_venda:
            try:
                prox_id = int(df_pedidos['id'].max()) + 1 if not df_pedidos.empty else 1
                novo_p = pd.DataFrame([{
                    "id": prox_id, "cliente": nome, "endereco": endereco, "obs": observacao,
                    "itens": json.dumps(itens_venda), "status": "Pendente",
                    "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0,
                    "pagamento": "Pago" if pago_ja else "A Pagar"
                }])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_p], ignore_index=True))
                st.success("Pedido Salvo!")
                st.cache_data.clear()
                # O rerun limpa tudo porque os inputs estão vinculados ao session_state
                st.rerun()
            except: st.error("Erro ao salvar. Tente novamente.")
        else: st.warning("Preencha o Nome/Endereço e escolha produtos.")

# --- 3. MONTAGEM (Correção Endereço/Excluir/Imprimir) ---
with tab3:
    st.header("📦 Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, p in pendentes.iterrows():
        with st.container(border=True):
            m1, m2 = st.columns([3, 1])
            m1.subheader(f"👤 {p['cliente']}")
            m1.write(f"📍 {p['endereco']}")
            if p['obs']: m1.warning(f"📝 {p['obs']}")
            
            if m2.button("🗑️ EXCLUIR", key=f"del_{p['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx))
                st.cache_data.clear(); st.rerun()

            # Lógica de KG e Finalizar...
            # (Aqui continuam as outras funções que já tínhamos)
