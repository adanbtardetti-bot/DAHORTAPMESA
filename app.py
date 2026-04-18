import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO E ESTILO (IGUAL AOS SEUS PRINTS) ---
st.set_page_config(page_title="Horta Gestão", layout="centered")

st.markdown("""
    <style>
    .stButton>button { border-radius: 10px; height: 3.5em; width: 100%; font-weight: bold; }
    [data-testid="stMetric"] { background: white; padding: 15px; border-radius: 15px; border: 1px solid #eee; }
    .card { background: white; padding: 20px; border-radius: 15px; border: 1px solid #eee; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO DIRETA ---
conn = st.connection("gsheets", type=GSheetsConnection)

def ler(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame()

df_p = ler("Produtos")
df_v = ler("Pedidos")

# --- NAVEGAÇÃO ---
tab = st.tabs(["🛒 Vendas", "⚖️ Montagem", "🕒 Histórico"])

# --- 1. VENDAS ---
with tab[0]:
    st.subheader("Novo Pedido")
    nome = st.text_input("Cliente").upper()
    ende = st.text_input("Endereço").upper()
    
    carrinho = []
    if not df_p.empty:
        for i, r in df_p.iterrows():
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                col1.write(f"**{r.get('nome', '---')}**\nR$ {r.get('preco', '0')}")
                qtd = col2.number_input("Qtd", min_value=0, step=1, key=f"v_{i}")
                if qtd > 0:
                    carrinho.append({"nome": r['nome'], "qtd": qtd, "tipo": r.get('tipo', 'UN'), "preco": float(str(r['preco']).replace(',','.'))})

    if st.button("SALVAR PEDIDO", type="primary"):
        if nome and carrinho:
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": nome, "endereco": ende, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0, "pagamento": "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.rerun()

# --- 2. MONTAGEM (IGUAL AO SEU PRINT 1000381881) ---
with tab[1]:
    st.subheader("Montagem")
    if not df_v.empty and 'status' in df_v.columns:
        pendentes = df_v[df_v['status'].astype(str).str.upper() == "PENDENTE"]
        for idx, p in pendentes.iterrows():
            with st.container(border=True):
                st.write(f"👤 **{p.get('cliente', '---')}**")
                
                try: itens = json.loads(p['itens'])
                except: itens = []
                
                t_final, ok = 0.0, True
                for i, it in enumerate(itens):
                    if str(it.get('tipo', '')).upper() == "KG":
                        # Campo de peso igual ao seu print da Cristiane
                        v_peso = st.text_input(f"Peso {it['nome']}:", key=f"m_{idx}_{i}")
                        if v_peso:
                            try:
                                v = float(v_peso.replace(',','.')); it['subtotal'] = v; t_final += v
                            except: ok = False
                        else: ok = False
                    else:
                        st.write(f"• {it['qtd']}x {it['nome']}")
                        sub = float(it['qtd']) * float(it['preco']); it['subtotal'] = sub; t_final += sub
                
                st.write(f"### Total: R$ {t_final:.2f}")
                
                # BOTÕES LADO A LADO
                c1, c2, c3 = st.columns(3)
                
                # Impressão RawBT
                txt_etiq = f"CLIENTE: {p['cliente']}\nTOTAL: R$ {t_final:.2f}"
                b64 = base64.b64encode(txt_etiq.encode()).decode()
                link = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                c1.markdown(f'<a href="{link}"><button style="width:100%; border-radius:10px; height:3.5em;">🖨️ Etiq.</button></a>', unsafe_allow_html=True)
                
                if c2.button("🗑️", key=f"del_{idx}"):
                    conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                
                if c3.button("✅", key=f"ok_{idx}", type="primary", disabled=not ok):
                    df_v.at[idx, 'status'] = "Concluído"; df_v.at[idx, 'total'] = t_final; df_v.at[idx, 'itens'] = json.dumps(itens)
                    conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- 3. HISTÓRICO (IGUAL AO SEU PRINT 1000381887) ---
with tab[2]:
    st.subheader("Histórico")
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_hj = df_v[df_v['data'] == hoje] if not df_v.empty else pd.DataFrame()
    
    # MÉTRICAS NO TOPO (IGUAL AO PRINT VERDE)
    m1, m2, m3 = st.columns(3)
    m1.metric("Pedidos", len(df_hj))
    m2.metric("Pagos", len(df_hj[df_hj['pagamento'] == "PAGO"]) if not df_hj.empty else 0)
    v_total = df_hj['total'].astype(float).sum() if not df_hj.empty else 0
    m3.metric("Total", f"R$ {v_total:.2f}")
    
    st.divider()
    for idx, p in df_hj.iterrows():
        with st.expander(f"{p.get('cliente')} - R$ {p.get('total')}"):
            if st.button("PAGO", key=f"h_{idx}", type="primary" if p.get('pagamento')=="PAGO" else "secondary"):
                df_v.at[idx, 'pagamento'] = "PAGO"; conn.update(worksheet="Pedidos", data=df_v); st.rerun()
