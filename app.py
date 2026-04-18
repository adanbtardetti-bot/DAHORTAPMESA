import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO E ESTILO ---
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
        cols = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"]
        return pd.DataFrame(columns=cols)

df_p = carregar("Produtos")
df_v = carregar("Pedidos")

# --- TODAS AS ABAS (COLHEITA VOLTOU) ---
tab = st.tabs(["🛒 Vendas", "🚜 Colheita", "⚖️ Montagem", "📊 Financeiro", "🕒 Histórico"])

# --- 1. VENDAS ---
with tab[0]:
    st.subheader("Novo Pedido")
    nome = st.text_input("Cliente").upper()
    carrinho = []
    if not df_p.empty:
        for i, r in df_p.iterrows():
            with st.container():
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{r.get('nome', '---')}**\nR$ {r.get('preco', '0')}")
                q = c2.number_input("Qtd", min_value=0, step=1, key=f"v_{i}")
                if q > 0:
                    carrinho.append({"nome": r['nome'], "qtd": q, "tipo": r.get('tipo', 'un'), "preco": float(str(r['preco']).replace(',','.'))})
    
    if st.button("SALVAR PEDIDO", type="primary"):
        if nome and carrinho:
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": nome, "status": "Pendente", "itens": json.dumps(carrinho), "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.rerun()

# --- 2. COLHEITA (RESTAURADA) ---
with tab[1]:
    st.subheader("Lista de Colheita")
    if not df_v.empty:
        pendentes = df_v[df_v['status'].astype(str).str.upper() == "PENDENTE"]
        colheita_total = {}
        for _, p in pendentes.iterrows():
            try: its = json.loads(p['itens'])
            except: its = []
            for it in its:
                nome_it = it.get('nome')
                colheita_total[nome_it] = colheita_total.get(nome_it, 0) + it.get('qtd', 0)
        
        for prod, qtd in colheita_total.items():
            st.write(f"🥦 **{prod}**: {qtd}")

# --- 3. MONTAGEM (COM BOTÃO IMPRIMIR E PAGO) ---
with tab[2]:
    st.subheader("Montagem")
    if not df_v.empty:
        pendentes = df_v[df_v['status'].astype(str).str.upper() == "PENDENTE"]
        for idx, p in pendentes.iterrows():
            with st.container():
                # BOTÃO PAGO NO TOPO DO CARD
                pago = p.get('pagamento') == "PAGO"
                if st.button("✅ PAGO" if pago else "💵 MARCAR PAGO", key=f"pg_{idx}", type="primary" if pago else "secondary"):
                    df_v.at[idx, 'pagamento'] = "PAGO"
                    conn.update(worksheet="Pedidos", data=df_v); st.rerun()

                st.write(f"👤 **{p.get('cliente')}**")
                try: its = json.loads(p['itens'])
                except: its = []
                
                t_calc, ok = 0.0, True
                for i, it in enumerate(its):
                    if str(it.get('tipo', '')).upper() == "KG":
                        peso = st.text_input(f"Peso {it['nome']}:", key=f"m_{idx}_{i}")
                        if peso:
                            v = float(peso.replace(',','.')); it['subtotal'] = v; t_calc += v
                        else: ok = False
                    else:
                        st.write(f"• {it['qtd']}x {it['nome']}")
                        t_calc += (float(it['qtd']) * float(it.get('preco', 0)))
                
                st.write(f"### Total: R$ {t_calc:.2f}")
                
                # BOTÕES LADO A LADO: [IMPRIMIR | EXCLUIR | CONCLUIR]
                c1, c2, c3 = st.columns(3)
                
                # Botão Imprimir (RawBT)
                txt_etiq = f"CLIENTE: {p['cliente']}\nTOTAL: R$ {t_calc:.2f}"
                link = f"intent:base64,{base64.b64encode(txt_etiq.encode()).decode()}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                c1.markdown(f'<a href="{link}"><button style="width:100%; border-radius:10px; height:3.5em; background:#444; color:white; border:none;">🖨️</button></a>', unsafe_allow_html=True)
                
                if c2.button("🗑️", key=f"d_{idx}"):
                    conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                
                if c3.button("✔️", key=f"s_{idx}", type="primary", disabled=not ok):
                    df_v.at[idx, 'status'] = "Concluído"; df_v.at[idx, 'total'] = t_calc
                    conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- 4. FINANCEIRO E 5. HISTÓRICO ---
with tab[3]:
    st.subheader("Financeiro")
    st.metric("Total em Vendas", f"R$ {df_v['total'].astype(float).sum():.2f}")
    st.dataframe(df_v)

with tab[4]:
    st.subheader("Histórico do Dia")
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_hj = df_v[df_v['data'] == hoje]
    for idx, p in df_hj.iterrows():
        st.write(f"✅ {p['cliente']} - R$ {p['total']} ({p['pagamento']})")
