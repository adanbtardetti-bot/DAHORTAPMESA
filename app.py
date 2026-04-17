
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS para botões lado a lado e visual de App
st.markdown("""
    <style>
    .stButton>button { border-radius: 8px; width: 100%; height: 3em; }
    [data-testid="stMetric"] { background: #ffffff; padding: 15px; border-radius: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border: 1px solid #eee; }
    div[data-testid="stExpander"] { border-radius: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame()

df_p = carregar_dados("Produtos")
df_v = carregar_dados("Pedidos")

# Garante que colunas essenciais existam
for c in ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"]:
    if c not in df_v.columns: df_v[c] = ""

# --- ABAS ---
tab = st.tabs(["🛒 Vendas", "🚜 Colheita", "⚖️ Montagem", "📦 Estoque", "📊 Financeiro", "🕒 Histórico"])

# --- 1. VENDAS ---
with tab[0]:
    st.subheader("Novo Pedido")
    nome = st.text_input("Cliente").upper()
    ende = st.text_input("Endereço").upper()
    
    venda_list = []
    if not df_p.empty:
        for i, r in df_p[df_p['status'] == 'ativo'].iterrows():
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{r['nome']}**\nR$ {r['preco']}")
            q = c2.number_input("", min_value=0, step=1, key=f"add_{i}")
            if q > 0:
                p_u = float(str(r['preco']).replace(',', '.'))
                sub = 0.0 if str(r['tipo']).upper() == "KG" else (q * p_u)
                venda_list.append({"nome": r['nome'], "qtd": q, "tipo": r['tipo'], "subtotal": sub, "preco": p_u})

    if st.button("SALVAR PEDIDO", type="primary", use_container_width=True):
        if nome and venda_list:
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": nome, "endereco": ende, "itens": json.dumps(venda_list), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.rerun()

# --- 2. MONTAGEM (ORGANIZAÇÃO IGUAL À FOTO) ---
with tab[2]:
    st.subheader("Pedidos Pendentes")
    pendentes = df_v[df_v['status'].astype(str).str.lower() == 'pendente']
    
    for idx, p in pendentes.iterrows():
        with st.container(border=True):
            st.write(f"👤 **{p.get('cliente', 'Sem Nome')}**")
            
            try: itens = json.loads(p['itens'])
            except: itens = []
            
            total_m, pronto = 0.0, True
            for i, it in enumerate(its := itens):
                if str(it.get('tipo', '')).upper() == "KG":
                    val = st.text_input(f"Peso {it['nome']}:", key=f"m_{idx}_{i}")
                    if val:
                        v = float(val.replace(',', '.')); it['subtotal'] = v; total_m += v
                    else: pronto = False
                else:
                    st.write(f"• {it['qtd']}x {it['nome']}")
                    total_m += float(it.get('subtotal', 0))
            
            st.subheader(f"Total: R$ {total_m:.2f}")
            
            # Botões Lado a Lado
            c1, c2, c3 = st.columns(3)
            
            # Etiqueta
            cmd = f"intent:base64,{base64.b64encode(f'CLIENTE: {p.get('cliente')}\nTOTAL: R$ {total_m:.2f}\n'.encode('latin-1')).decode()}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
            c1.markdown(f'<a href="{cmd}" style="text-decoration:none;"><button style="width:100%; border-radius:8px; height:3em;">🖨️ Etiqueta</button></a>', unsafe_allow_html=True)
            
            if c2.button("🗑️", key=f"ex_{idx}"):
                conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                
            if c3.button("💾", key=f"ok_{idx}", disabled=not pronto, type="primary"):
                df_v.at[idx, 'status'] = "Concluído"; df_v.at[idx, 'total'] = total_m; df_v.at[idx, 'itens'] = json.dumps(its)
                conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- 3. HISTÓRICO (RESUMO NO TOPO IGUAL À FOTO) ---
with tab[5]:
    st.subheader("Histórico do Dia")
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_hj = df_v[df_v['data'] == hoje]
    
    # Resumo igual à foto
    m1, m2, m3 = st.columns(3)
    m1.metric("Pedidos", len(df_hj))
    m2.metric("Pagos", len(df_hj[df_hj['pagamento'] == "PAGO"]))
    m3.metric("Total", f"R$ {df_hj['total'].apply(lambda x: float(x) if x else 0).sum():.2f}")
    
    st.divider()
    for idx, p in df_hj.iterrows():
        with st.expander(f"👤 {p['cliente']} | R$ {p['total']}"):
            st.write(f"📍 Endereço: {p['endereco']}")
            if st.button("Marcar Pago", key=f"pg_h_{idx}"):
                df_v.at[idx, 'pagamento'] = "PAGO"
                conn.update(worksheet="Pedidos", data=df_v); st.rerun()
