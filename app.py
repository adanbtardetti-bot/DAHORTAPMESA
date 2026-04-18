import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Vendas", layout="centered")

# CSS para forçar o alinhamento e remover espaços
st.markdown("""
    <style>
    .stNumberInput div { margin-top: -10px; }
    div[data-testid="stColumn"] { display: flex; align-items: center; }
    .stButton>button { background-color: #2e7d32; color: white; height: 3em; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except:
        return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "status"])

# --- TELA DE VENDAS ---
st.header("🛒 Novo Pedido")

# Bloco de Identificação mais compacto
c_nome, c_end = st.columns(2)
nome_cli = c_nome.text_input("Cliente").upper()
end_cli = c_end.text_input("Endereço").upper()

c_pg, c_obs = st.columns([1, 2])
pago = c_pg.toggle("Pago?")
obs_ped = c_obs.text_input("Obs")

st.divider()

# Busca
busca = st.text_input("🔍 Pesquisar produto...", "").lower()

df_p = carregar_produtos()
carrinho = []
total = 0.0

if not df_p.empty:
    df_exibir = df_p[df_p['nome'].str.lower().str.contains(busca)] if busca else df_p
    
    for i, row in df_exibir.iterrows():
        # --- AQUI ESTÁ O SEGREDO DO ALINHAMENTO ---
        # Criamos 3 colunas: Nome (grande), Preço (médio), Quantidade (pequeno)
        col_nome, col_preco, col_qtd = st.columns([2.5, 1.2, 1.3])
        
        p_unit = float(str(row['preco']).replace(',', '.'))
        
        # Alinhando tudo na mesma linha
        col_nome.markdown(f"**{row['nome']}**")
        col_preco.write(f"R$ {p_unit:.2f}")
        
        # Campo de Qtd sem o label "Qtd" para economizar espaço vertical
        qtd = col_qtd.number_input("n", min_value=0, step=1, key=f"q_{i}", label_visibility="collapsed")
        
        if qtd > 0:
            sub = qtd * p_unit
            total += sub
            carrinho.append({"nome": row['nome'], "qtd": qtd, "preco": p_unit, "subtotal": sub})

st.divider()
st.subheader(f"💰 TOTAL: R$ {total:.2f}")

if st.button("💾 SALVAR PEDIDO", type="primary"):
    if nome_cli and carrinho:
        try:
            df_v = conn.read(worksheet="Pedidos", ttl=0)
            novo = pd.DataFrame([{
                "id": int(datetime.now().timestamp()),
                "cliente": nome_cli,
                "endereco": end_cli,
                "itens": json.dumps(carrinho),
                "status": "Pendente",
                "data": datetime.now().strftime("%d/%m/%Y"),
                "total": total,
                "pagamento": "PAGO" if pago else "A PAGAR",
                "obs": obs_ped
            }])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.success("Salvo!"); st.rerun()
        except Exception as e:
            st.error(f"Erro: {e}")
    else:
        st.warning("Falta nome ou produtos!")
