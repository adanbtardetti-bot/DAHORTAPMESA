import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Vendas", layout="centered")

st.markdown("""
    <style>
    /* Ajuste para alinhar Nome, Preço e Qtd na mesma linha */
    div[data-testid="stColumn"] { display: flex; align-items: center; justify-content: flex-start; }
    .stNumberInput div { margin-top: 0px; }
    [data-testid="stNumberInput"] { width: 100% !important; }
    /* Estilo do botão de salvar */
    .stButton>button { background-color: #2e7d32; color: white; height: 3.5em; font-weight: bold; width: 100%; border-radius: 10px; }
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

st.header("🛒 Novo Pedido")

# --- O SEGREDO: FORMULÁRIO COM LIMPEZA AUTOMÁTICA ---
with st.form("meu_formulario", clear_on_submit=True):
    
    # Bloco Superior
    c_nome, c_end = st.columns(2)
    nome_cli = c_nome.text_input("Cliente").upper()
    end_cli = c_end.text_input("Endereço").upper()

    c_pg, c_obs = st.columns([1, 2])
    pago = c_pg.toggle("Pago?")
    obs_ped = c_obs.text_input("Observação")

    st.divider()

    df_p = carregar_produtos()
    # Dicionário temporário para guardar as quantidades antes de salvar
    dict_qtds = {}

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
            
            # Input de quantidade dentro do formulário
            qtd = col_qtd.number_input("Qtd", min_value=0, step=1, key=f"q_{row['id']}", label_visibility="collapsed")
            dict_qtds[row['id']] = {"qtd": qtd, "nome": row['nome'], "preco": p_unit, "tipo": tipo}

    st.divider()
    
    # Botão de envio do formulário
    botao_salvar = st.form_submit_button("💾 FINALIZAR E LIMPAR TELA")

# --- LÓGICA DE PROCESSAMENTO (FORA DO FORM) ---
if botao_salvar:
    carrinho = []
    total_venda = 0.0
    
    # Processa o que foi preenchido
    for id_p, dados in dict_qtds.items():
        if dados['qtd'] > 0:
            sub = 0.0 if dados['tipo'] == "KG" else (dados['qtd'] * dados['preco'])
            total_venda += sub
            carrinho.append({
                "nome": dados['nome'], 
                "qtd": dados['qtd'], 
                "preco": dados['preco'], 
                "subtotal": sub, 
                "tipo": dados['tipo']
            })

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
            st.success(f"Pedido de {nome_cli} salvo! A tela foi limpa.")
            # Não precisa de rerun, o clear_on_submit já zerou os campos.
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")
    else:
        st.warning("Preencha o Nome e escolha ao menos um produto para salvar!")
