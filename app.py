import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Vendas", layout="centered")

st.markdown("""
    <style>
    div[data-testid="stColumn"] { display: flex; align-items: center; justify-content: flex-start; }
    .stNumberInput div { margin-top: 0px; }
    .stButton>button { background-color: #2e7d32; color: white; height: 3.5em; font-weight: bold; border-radius: 10px; }
    [data-testid="stNumberInput"] { width: 100% !important; }
    label { font-size: 14px !important; font-weight: bold !important; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- LÓGICA DE LIMPEZA (RESET) ---
# Se não existe um 'contador de reset', a gente cria um
if 'reset_key' not in st.session_state:
    st.session_state.reset_key = 0

def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except:
        return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "status"])

# --- TELA DE VENDAS ---
st.header("🛒 Novo Pedido")

# A mágica acontece aqui: toda vez que st.session_state.reset_key muda, 
# tudo dentro deste 'container' é destruído e recriado vazio.
with st.container():
    # Identificação - Usando o reset_key no sufixo da chave
    rk = st.session_state.reset_key
    
    c_nome, c_end = st.columns(2)
    nome_cli = c_nome.text_input("Cliente", key=f"nome_{rk}").upper()
    end_cli = c_end.text_input("Endereço", key=f"end_{rk}").upper()

    c_pg, c_obs = st.columns([1, 2])
    pago = c_pg.toggle("Pago?", key=f"pago_{rk}")
    obs_ped = c_obs.text_input("Observação", key=f"obs_{rk}")

    st.divider()

    df_p = carregar_produtos()
    carrinho = []
    total_venda = 0.0

    if not df_p.empty:
        for i, row in df_p.iterrows():
            col_nome, col_preco, col_qtd = st.columns([2.5, 1.2, 1.3])
            
            p_unit = float(str(row['preco']).replace(',', '.'))
            tipo = str(row.get('tipo', 'UN')).upper()
            
            col_nome.markdown(f"**{row['nome']}**")
            
            if tipo == "KG":
                col_preco.caption("PESAGEM")
            else:
                col_preco.write(f"R$ {p_unit:.2f}")
            
            # Quantidade também com a chave de reset
            qtd = col_qtd.number_input("Qtd", min_value=0, step=1, key=f"q_{row['id']}_{rk}", label_visibility="collapsed")
            
            if qtd > 0:
                sub = 0.0 if tipo == "KG" else (qtd * p_unit)
                total_venda += sub
                carrinho.append({
                    "nome": row['nome'], 
                    "qtd": qtd, 
                    "preco": p_unit, 
                    "subtotal": sub, 
                    "tipo": tipo
                })

    st.divider()
    st.subheader(f"💰 TOTAL: R$ {total_venda:.2f}")

    if st.button("💾 FINALIZAR PEDIDO", type="primary"):
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
                    "total": total_venda,
                    "pagamento": "PAGO" if pago else "A PAGAR",
                    "obs": obs_ped
                }])
                
                conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
                
                # --- AQUI É O RESET ---
                st.session_state.reset_key += 1 # Muda a chave de todos os campos
                st.success("Pedido Gravado!")
                st.rerun() # Reinicia com a nova chave (tudo vazio)
                
            except Exception as e:
                st.error(f"Erro: {e}")
        else:
            st.warning("Preencha o Nome e escolha produtos!")
