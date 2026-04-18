import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Gestão", layout="centered")

st.markdown("""
    <style>
    .stButton>button { border-radius: 10px; height: 3.5em; width: 100%; font-weight: bold; }
    [data-testid="stMetric"] { background: white; padding: 15px; border-radius: 15px; border: 1px solid #eee; }
    div[data-testid="stContainer"] { background: white; padding: 15px; border-radius: 15px; border: 1px solid #eee; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        cols = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]
        return pd.DataFrame(columns=cols)

df_p = carregar("Produtos")
df_v = carregar("Pedidos")

# --- ABAS ---
tab = st.tabs(["🛒 Vendas", "🚜 Colheita", "⚖️ Montagem", "📊 Financeiro", "🕒 Histórico"])

# --- 1. TELA DE VENDAS (COMO VOCÊ PEDIU) ---
with tab[0]:
    st.subheader("Novo Pedido")
    
    # Nome e Endereço
    nome = st.text_input("Nome do Cliente").upper()
    ende = st.text_input("Endereço de Entrega").upper()
    
    # Botão Pago (Embaixo do nome/endereço)
    pago_venda = st.checkbox("MARCAR COMO PAGO AGORA?")
    status_pg = "PAGO" if pago_venda else "A PAGAR"
    
    # Campo de Observação
    observacao = st.text_area("Observações do Pedido")
    
    st.divider()
    st.write("**Selecione os Produtos:**")
    
    carrinho = []
    if not df_p.empty:
        for i, r in df_p.iterrows():
            with st.container():
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{r.get('nome', '---')}**\nR$ {r.get('preco', '0')}")
                q = c2.number_input("Qtd", min_value=0, step=1, key=f"v_{i}")
                if q > 0:
                    preco_unit = float(str(r.get('preco', '0')).replace(',', '.'))
                    carrinho.append({
                        "nome": r.get('nome'), 
                        "qtd": q, 
                        "tipo": r.get('tipo', 'un'), 
                        "preco": preco_unit,
                        "subtotal": 0.0 if str(r.get('tipo')).upper() == "KG" else (q * preco_unit)
                    })

    # Botão Salvar no final de tudo
    if st.button("SALVAR PEDIDO", type="primary", use_container_width=True):
        if nome and carrinho:
            novo_pedido = pd.DataFrame([{
                "id": int(datetime.now().timestamp()),
                "cliente": nome,
                "endereco": ende,
                "itens": json.dumps(carrinho),
                "status": "Pendente",
                "data": datetime.now().strftime("%d/%m/%Y"),
                "total": sum(i['subtotal'] for i in carrinho),
                "pagamento": status_pg,
                "obs": observacao
            }])
            df
