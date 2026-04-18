import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Vendas", layout="centered")

st.markdown("""
    <style>
    /* Alinhamento vertical das colunas */
    div[data-testid="stColumn"] { display: flex; align-items: center; justify-content: flex-start; }
    .stNumberInput div { margin-top: 0px; }
    .stButton>button { background-color: #2e7d32; color: white; height: 3.5em; font-weight: bold; border-radius: 10px; }
    /* Ajuste para o seletor de quantidade não quebrar linha */
    [data-testid="stNumberInput"] { width: 100% !important; }
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

# Bloco Superior
c_nome, c_end = st.columns(2)
nome_cli = c_nome.text_input("Cliente").upper()
end_cli = c_end.text_input("Endereço").upper()

c_pg, c_obs = st.columns([1, 2])
pago = c_pg.toggle("Pago?")
obs_ped = c_obs.text_input("Observação")

st.divider()

# Busca e Lista
busca = st.text_input("🔍 Pesquisar produto...", "").lower()
df_p = carregar_produtos()
carrinho = []
total_venda = 0.0

if not df_p.empty:
    df_exibir = df_p[df_p['nome'].str.lower().str.contains(busca)] if busca else df_p
    
    for i, row in df_exibir.iterrows():
        col_nome, col_preco, col_qtd = st.columns([2.5, 1.2, 1.3])
        
        p_unit = float(str(row['preco']).replace(',', '.'))
        tipo = str(row.get('tipo', 'UN')).upper()
        
        col_nome.markdown(f"**{row['nome']}**")
        
        # Se for KG, avisa que o preço é na pesagem
        if tipo == "KG":
            col_preco.caption("PESAGEM")
        else:
            col_preco.write(f"R$ {p_unit:.2f}")
        
        # Input de Quantidade (o label oculto mantém o alinhamento)
        qtd = col_qtd.number_input("Qtd", min_value=0, step=1, key=f"q_{i}", label_visibility="collapsed")
        
        if qtd > 0:
            # Só soma ao total se NÃO for KG (itens de KG somam na Montagem)
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
st.subheader(f"💰 TOTAL ATUAL: R$ {total_venda:.2f}")
if any(item['tipo'] == 'KG' for item in carrinho):
    st.info("💡 Itens de **KG** serão somados após a pesagem na tela de Montagem.")

if st.button("💾 FINALIZAR E LIMPAR", type="primary"):
    if nome_cli and carrinho:
        try:
            # Salvar
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
            
            st.success("Pedido Salvo com Sucesso!")
            # O SEGREDO PARA ZERAR TUDO:
            st.rerun() 
            
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")
    else:
        st.warning("Preencha o nome e escolha os produtos!")
