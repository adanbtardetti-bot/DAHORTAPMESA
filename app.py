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
    /* Estilo para labels menores */
    label { font-size: 14px !important; font-weight: bold !important; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# Função para carregar produtos (com cache para ser rápido)
@st.cache_data(ttl=0)
def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos").dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except:
        return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "status"])

# --- TELA DE VENDAS ---
st.header("🛒 Novo Pedido")

# Campos de entrada com chaves (keys) para facilitar o reset
c_nome, c_end = st.columns(2)
nome_cli = c_nome.text_input("Cliente", key="nome_input").upper()
end_cli = c_end.text_input("Endereço", key="end_input").upper()

c_pg, c_obs = st.columns([1, 2])
pago = c_pg.toggle("Pago?", key="pago_input")
obs_ped = c_obs.text_input("Observação", key="obs_input")

st.divider()

df_p = carregar_produtos()
carrinho = []
total_venda = 0.0

if not df_p.empty:
    # LISTA DIRETA (SEM PESQUISAR)
    for i, row in df_p.iterrows():
        col_nome, col_preco, col_qtd = st.columns([2.5, 1.2, 1.3])
        
        p_unit = float(str(row['preco']).replace(',', '.'))
        tipo = str(row.get('tipo', 'UN')).upper()
        
        col_nome.markdown(f"**{row['nome']}**")
        
        # Lógica de Preço/KG
        if tipo == "KG":
            col_preco.caption("PESAGEM")
        else:
            col_preco.write(f"R$ {p_unit:.2f}")
        
        # Quantidade (Sempre zerada no rerun)
        qtd = col_qtd.number_input("Qtd", min_value=0, step=1, key=f"q_{row['id']}", label_visibility="collapsed")
        
        if qtd > 0:
            # SOMA VALOR: Apenas se NÃO for KG
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

# BOTÃO SALVAR
if st.button("💾 FINALIZAR E LIMPAR TUDO", type="primary"):
    if nome_cli and carrinho:
        try:
            # 1. Busca dados existentes
            df_v = conn.read(worksheet="Pedidos", ttl=0)
            
            # 2. Cria novo registro
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
            
            # 3. Salva na Planilha
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            
            # --- LIMPEZA TOTAL ---
            st.cache_data.clear() # Limpa o cache de leitura
            for key in st.session_state.keys():
                del st.session_state[key] # Apaga todos os inputs da memória
            
            st.success("Pedido Gravado!")
            st.rerun() # Recarrega a página limpa
            
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")
    else:
        st.warning("Preencha o Nome e escolha produtos!")
