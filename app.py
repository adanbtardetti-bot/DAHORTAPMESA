import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# Configuração igual aos teus prints
st.set_page_config(page_title="Horta Gestão", layout="centered")

st.markdown("""
    <style>
    .stButton>button { border-radius: 10px; height: 3.5em; width: 100%; font-weight: bold; }
    [data-testid="stMetric"] { background: white; padding: 15px; border-radius: 15px; border: 1px solid #eee; }
    div[data-testid="stContainer"] { background: white; padding: 15px; border-radius: 15px; border: 1px solid #eee; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        # Se der erro ou estiver vazia, cria estrutura básica para não travar o app
        cols = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"]
        return pd.DataFrame(columns=cols)

df_p = carregar_dados("Produtos")
df_v = carregar_dados("Pedidos")

# Garante que as abas apareçam mesmo se o DF estiver vazio
tabs = st.tabs(["🛒 Vendas", "⚖️ Montagem", "📊 Financeiro", "🕒 Histórico"])

# --- ABA VENDAS ---
with tabs[0]:
    st.subheader("Novo Pedido")
    nome = st.text_input("Cliente").upper()
    ende = st.text_input("Endereço").upper()
    
    itens_selecionados = []
    if not df_p.empty:
        for i, r in df_p.iterrows():
            with st.container():
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{r.get('nome', 'Produto')}**\nR$ {r.get('preco', '0')}")
                qtd = c2.number_input("Qtd", min_value=0, step=1, key=f"v_{i}")
                if qtd > 0:
                    itens_selecionados.append({
                        "nome": r.get('nome'), 
                        "qtd": qtd, 
                        "tipo": r.get('tipo', 'un'), 
                        "preco": float(str(r.get('preco')).replace(',','.'))
                    })

    if st.button("SALVAR PEDIDO", type="primary"):
        if nome and itens_selecionados:
            novo_p = pd.DataFrame([{
                "id": int(datetime.now().timestamp()), 
                "cliente": nome, 
                "endereco": ende, 
                "itens": json.dumps(itens_selecionados), 
                "status": "Pendente", 
                "data": datetime.now().strftime("%d/%m/%Y"), 
                "total": 0.0, 
                "pagamento": "A PAGAR"
            }])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo_p], ignore_index=True))
            st.rerun()

# --- ABA MONTAGEM ---
with tabs[1]:
    st.subheader("Pedidos Pendentes")
    if not df_v.empty and 'status' in df_v.columns:
        pendentes = df_v[df_v['status'].astype(str).str.upper() == "PENDENTE"]
        for idx, p in pendentes.iterrows():
            with st.container():
                st.write(f"👤 **{p.get('cliente', '---')}**")
                try: 
                    lista = json.loads(p['itens'])
                except: 
                    lista = []
                
                total_m, ok_montagem = 0.0, True
                for i, it in enumerate(lista):
                    if str(it.get('tipo')).upper() == "KG":
                        peso = st.text_input(f"Peso {it.get('nome')}:", key=f"m_{idx}_{i}")
                        if peso:
                            try:
                                v = float(peso.replace(',','.')); it['subtotal'] = v; total_m += v
                            except: ok_montagem = False
                        else: ok_montagem = False
                    else:
                        st.write(f"• {it.get('qtd')}x {it.get('nome')}")
                        sub = float(it.get('qtd', 0)) * float(it.get('preco', 0))
                        total_m += sub
                
                st.write(f"### Total: R$ {total_m:.2f}")
                
                c1, c2, c3 = st.columns(3)
                if c2.button("🗑️", key=f"del_{idx}"):
                    conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                if c3.button("✅", key=f"ok_{idx}", type="primary", disabled=not ok_montagem):
                    df_v.at[idx, 'status'] = "Concluído"; df_v.at[idx, 'total'] = total_m
                    conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- ABA HISTÓRICO ---
with tabs[3]:
    st.subheader("Resumo do Dia")
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_hj = df_v[df_v['data'] == hoje] if not df_v.empty else pd.DataFrame()
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Pedidos", len(df_hj))
    m2.metric("Pagos", len(df_hj[df_hj['pagamento'] == "PAGO"]) if not df_hj.empty else 0)
    total_dia = df_hj['total'].astype(float).sum() if not df_hj.empty else 0
    m3.metric("Total", f"R$ {total_dia:.2f}")
