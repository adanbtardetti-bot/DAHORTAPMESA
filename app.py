import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# Estilo para imitar seus prints verdes
st.set_page_config(page_title="Horta Gestão", layout="centered")
st.markdown("<style>.stButton>button {border-radius:10px; height:3.5em; width:100%; font-weight:bold;}</style>", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        # Cria colunas certas se a planilha estiver vazia (Evita o KeyError)
        cols = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"]
        return pd.DataFrame(columns=cols)

df_p = carregar("Produtos")
df_v = carregar("Pedidos")

# Garante que as abas existam sempre
tab = st.tabs(["🛒 Vendas", "⚖️ Montagem", "📊 Financeiro", "🕒 Histórico"])

with tab[0]: # VENDAS
    st.subheader("Novo Pedido")
    nome = st.text_input("Nome do Cliente").upper()
    ende = st.text_input("Endereço").upper()
    carrinho = []
    if not df_p.empty:
        for i, r in df_p.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{r.get('nome', '---')}**\nR$ {r.get('preco', '0')}")
                qtd = c2.number_input("Qtd", min_value=0, step=1, key=f"v_{i}")
                if qtd > 0:
                    carrinho.append({"nome": r['nome'], "qtd": qtd, "tipo": r.get('tipo', 'un'), "preco": float(str(r['preco']).replace(',','.'))})
    
    if st.button("SALVAR PEDIDO", type="primary"):
        if nome and carrinho:
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": nome, "endereco": ende, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.success("Salvo com sucesso!"); st.rerun()

with tab[1]: # MONTAGEM
    st.subheader("Montagem")
    if not df_v.empty:
        pendentes = df_v[df_v['status'].astype(str).str.upper() == "PENDENTE"]
        for idx, p in pendentes.iterrows():
            with st.container(border=True):
                st.write(f"👤 **{p.get('cliente')}**")
                try: its = json.loads(p['itens'])
                except: its = []
                total_m, ok = 0.0, True
                for i, it in enumerate(its):
                    if str(it.get('tipo')).upper() == "KG":
                        peso = st.text_input(f"Peso {it['nome']}:", key=f"m_{idx}_{i}")
                        if peso:
                            v = float(peso.replace(',','.')); it['subtotal'] = v; total_m += v
                        else: ok = False
                    else:
                        st.write(f"• {it['qtd']}x {it['nome']}")
                        total_m += (float(it['qtd']) * float(it['preco']))
                
                st.write(f"### Total: R$ {total_m:.2f}")
                col1, col2, col3 = st.columns(3)
                if col2.button("🗑️", key=f"d_{idx}"):
                    conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                if col3.button("✅", key=f"s_{idx}", type="primary", disabled=not ok):
                    df_v.at[idx, 'status'] = "Concluído"; df_v.at[idx, 'total'] = total_m
                    conn.update(worksheet="Pedidos", data=df_v); st.rerun()

with tab[3]: # HISTÓRICO
    st.subheader("Resumo do Dia")
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_hj = df_v[df_v['data'] == hoje] if not df_v.empty else pd.DataFrame()
    m1, m2, m3 = st.columns(3)
    m1.metric("Pedidos", len(df_hj))
    m2.metric("Pagos", len(df_hj[df_hj['pagamento'] == "PAGO"]) if not df_hj.empty else 0)
    v_total = df_hj['total'].astype(float).sum() if not df_hj.empty else 0
    m3.metric("Total", f"R$ {v_total:.2f}")
