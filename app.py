import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Vendas", layout="centered")

# CSS para manter tudo alinhado e bonito no celular
st.markdown("""
    <style>
    div[data-testid="stColumn"] { display: flex; align-items: center; justify-content: flex-start; }
    .stNumberInput div { margin-top: 0px; }
    [data-testid="stNumberInput"] { width: 100% !important; }
    .stButton>button { background-color: #2e7d32; color: white; height: 3.5em; font-weight: bold; width: 100%; border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- CONTROLE DE LIMPEZA ---
# Se não existe a chave de reset, criamos a 0. Ao salvar, ela vira 1, 2, 3... e limpa tudo.
if 'form_id' not in st.session_state:
    st.session_state.form_id = 0

def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except:
        return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "status"])

# --- TELA DE VENDAS ---
st.header("🛒 Novo Pedido")

# Criamos um container que depende do form_id para existir. 
# Se o form_id mudar, o container e tudo dentro dele reseta.
f_id = st.session_state.form_id

with st.container():
    # Identificação
    c_nome, c_end = st.columns(2)
    nome_cli = c_nome.text_input("Cliente", key=f"n_{f_id}").upper()
    end_cli = c_end.text_input("Endereço", key=f"e_{f_id}").upper()

    c_pg, c_obs = st.columns([1, 2])
    pago = c_pg.toggle("Pago?", key=f"p_{f_id}")
    obs_ped = c_obs.text_input("Observação", key=f"o_{f_id}")

    st.divider()

    df_p = carregar_produtos()
    carrinho = []
    total_venda = 0.0

    if not df_p.empty:
        for i, row in df_p.iterrows():
            # Peso das colunas para manter alinhado na mesma linha
            col_nome, col_preco, col_qtd = st.columns([2.5, 1.2, 1.3])
            
            p_unit = float(str(row['preco']).replace(',', '.'))
            tipo = str(row.get('tipo', 'UN')).upper()
            
            col_nome.markdown(f"**{row['nome']}**")
            
            if tipo == "KG":
                col_preco.caption("PESAGEM")
            else:
                col_preco.write(f"R$ {p_unit:.2f}")
            
            # Campo de quantidade com chave dinâmica para resetar
            qtd = col_qtd.number_input("Qtd", min_value=0, step=1, key=f"q_{row['id']}_{f_id}", label_visibility="collapsed")
            
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

    # BOTÃO SALVAR
    if st.button("💾 FINALIZAR E LIMPAR TELA", type="primary"):
        if nome_cli and carrinho:
            try:
                # 1. Busca Pedidos
                df_v = conn.read(worksheet="Pedidos", ttl=0)
                
                # 2. Prepara novo pedido
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
                
                # 3. Salva
                conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
                
                # --- O PULO DO GATO ---
                # Aumentamos o ID do formulário. Isso mata todos os campos antigos e cria novos vazios.
                st.session_state.form_id += 1
                st.success("Salvo!")
                st.rerun() # Recarrega com a nova identidade limpa
                
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")
        else:
            st.warning("Preencha o Nome e escolha produtos!")
