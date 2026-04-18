import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Horta Gestão - Vendas", layout="centered")

st.markdown("""
    <style>
    /* Deixa os botões e inputs mais robustos para celular */
    .stButton>button { border-radius: 10px; height: 3.5em; width: 100%; font-weight: bold; background-color: #2e7d32; color: white; }
    .stTextInput>div>div>input { font-size: 16px; }
    /* Caixa do Total */
    .total-container {
        position: sticky;
        top: 0;
        z-index: 999;
        background-color: #ffffff;
        padding: 10px;
        border-bottom: 2px solid #2e7d32;
        margin-bottom: 20px;
    }
    /* Cards de Produtos mais finos */
    .prod-card {
        padding: 10px;
        border-bottom: 1px solid #eee;
    }
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO ---
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        # Mostra apenas produtos que não estão ocultos
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except:
        return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "status"])

# --- INTERFACE ---
st.header("🛒 Novo Pedido")

# 1. DADOS DO CLIENTE
with st.container():
    col1, col2 = st.columns(2)
    nome_cli = col1.text_input("Nome do Cliente").upper()
    end_cli = col2.text_input("Endereço").upper()
    
    col3, col4 = st.columns([1, 2])
    pago = col3.toggle("Já está pago?")
    obs_ped = col4.text_input("Observação ou recado")

st.divider()

# 2. LISTA DE PRODUTOS COM BUSCA
busca = st.text_input("🔍 Procurar produto (Ex: Alface, Tomate...)", "").lower()

df_p = carregar_produtos()
carrinho = []
valor_total = 0.0

if not df_p.empty:
    # Filtro de busca
    if busca:
        df_exibir = df_p[df_p['nome'].str.lower().str.contains(busca)]
    else:
        df_exibir = df_p

    # Cabeçalho da Lista
    st.write(f"Exibindo {len(df_exibir)} produtos:")
    
    for i, row in df_exibir.iterrows():
        # Layout em colunas para cada linha de produto
        c_nome, c_preco, c_qtd = st.columns([2, 1, 1])
        
        preco_unit = float(str(row['preco']).replace(',', '.'))
        c_nome.write(f"**{row['nome']}**")
        c_preco.write(f"R$ {preco_unit:.2f}")
        
        # Campo de quantidade
        qtd = c_qtd.number_input("Qtd", min_value=0, step=1, key=f"p_{row['id']}_{i}")
        
        if qtd > 0:
            subtotal = qtd * preco_unit
            valor_total += subtotal
            carrinho.append({
                "nome": row['nome'],
                "qtd": qtd,
                "preco": preco_unit,
                "subtotal": subtotal,
                "tipo": row.get('tipo', 'un')
            })

# 3. RESUMO E SALVAMENTO
st.markdown("---")
st.markdown(f"### 💰 TOTAL DO PEDIDO: R$ {valor_total:.2f}")

if st.button("💾 CONFIRMAR E SALVAR PEDIDO"):
    if not nome_cli:
        st.error("Por favor, coloque o NOME do cliente.")
    elif not carrinho:
        st.error("O pedido está vazio! Adicione algum produto.")
    else:
        try:
            # Tenta ler pedidos existentes
            df_v = conn.read(worksheet="Pedidos", ttl=0)
            
            novo_item = pd.DataFrame([{
                "id": int(datetime.now().timestamp()),
                "cliente": nome_cli,
                "endereco": end_cli,
                "itens": json.dumps(carrinho),
                "status": "Pendente",
                "data": datetime.now().strftime("%d/%m/%Y"),
                "total": valor_total,
                "pagamento": "PAGO" if pago else "A PAGAR",
                "obs": obs_ped
            }])
            
            # Atualiza a planilha
            df_final = pd.concat([df_v, novo_item], ignore_index=True)
            conn.update(worksheet="Pedidos", data=df_final)
            
            st.success(f"Pedido de {nome_cli} salvo com sucesso!")
            st.balloons()
            # Opcional: st.rerun() para limpar a tela para o próximo
        except Exception as e:
            st.error(f"Erro ao salvar na planilha: {e}")
