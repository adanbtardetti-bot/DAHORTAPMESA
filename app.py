import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO ---
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
        if aba == "Produtos":
            return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "status"])
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

df_p = carregar("Produtos")
df_v = carregar("Pedidos")

tab = st.tabs(["🛒 Vendas", "🚜 Colheita", "⚖️ Montagem", "📦 Estoque", "📊 Financeiro", "🕒 Histórico"])

# --- 1. VENDAS (SOMA VALOR) ---
with tab[0]:
    st.subheader("Novo Pedido")
    nome = st.text_input("Nome do Cliente").upper()
    ende = st.text_input("Endereço").upper()
    pago_venda = st.checkbox("MARCAR PAGO?")
    obs_venda = st.text_area("Observação")
    
    st.divider()
    carrinho = []
    total_live = 0.0
    
    if not df_p.empty:
        # Só mostra produtos 'ativos'
        ativos = df_p[df_p['status'].astype(str).str.lower() != 'oculto']
        for i, r in ativos.iterrows():
            with st.container():
                c1, c2 = st.columns([3, 1])
                p_u = float(str(r.get('preco', 0)).replace(',', '.'))
                c1.write(f"**{r['nome']}**\nR$ {p_u:.2f}")
                q = c2.number_input("Qtd", min_value=0, step=1, key=f"v_{i}")
                if q > 0:
                    sub = q * p_u
                    total_live += sub
                    carrinho.append({"nome": r['nome'], "qtd": q, "tipo": r['tipo'], "preco": p_u, "subtotal": sub})

    st.subheader(f"Total: R$ {total_live:.2f}")
    if st.button("SALVAR PEDIDO", type="primary"):
        if nome and carrinho:
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": nome, "endereco": ende, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_live, "pagamento": "PAGO" if pago_venda else "A PAGAR", "obs": obs_venda}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.success("Pedido Gravado!"); st.rerun()

# --- 2. COLHEITA (SOMA ITENS PENDENTES) ---
with tab[1]:
    st.subheader("Lista de Colheita")
    if not df_v.empty:
        pendentes = df_v[df_v['status'].astype(str).str.lower() == 'pendente']
        resumo_colheita = {}
        for _, p in pendentes.iterrows():
            try:
                lista_it = json.loads(p['itens'])
                for it in lista_it:
                    nome_prod = it.get('nome')
                    resumo_colheita[nome_prod] = resumo_colheita.get(nome_prod, 0) + it.get('qtd', 0)
            except: pass
        
        if resumo_colheita:
            for prod, qtd in resumo_colheita.items():
                st.write(f"🟢 **{prod}**: {qtd}")
        else: st.write("Nada para colher hoje.")

# --- 3. MONTAGEM ---
with tab[2]:
    st.subheader("Montagem")
    if not df_v.empty:
        pendentes = df_v[df_v['status'].astype(str).str.lower() == 'pendente']
        for idx, p in pendentes.iterrows():
            with st.container():
                st.write(f"👤 **{p['cliente']}**")
                if p.get('endereco') and str(p['endereco']) != 'nan': st.write(f"📍 {p['endereco']}")
                if p.get('obs') and str(p['obs']) != 'nan' and p['obs'].strip() != "": st.info(f"📝 {p['obs']}")
                
                try: its = json.loads(p['itens'])
                except: its = []
                
                t_m, pronto = 0.0, True
                for i, it in enumerate(its):
                    if str(it.get('tipo', '')).upper() == "KG":
                        peso = st.text_input(f"Peso {it['nome']}:", key=f"m_{idx}_{i}")
                        if peso:
                            v = float(peso.replace(',','.')); it['subtotal'] = v; t_m += v
                        else: pronto = False
                    else:
                        st.write(f"• {it['qtd']}x {it['nome']}")
                        t_m += float(it.get('subtotal', 0))
                
                st.write(f"### Total: R$ {t_m:.2f}")
                c1, c2, c3 = st.columns(3)
                txt = f"CLIENTE: {p['cliente']}\nTOTAL: R$ {t_m:.2f}"
                link = f"intent:base64,{base64.b64encode(txt.encode()).decode()}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                c1.markdown(f'<a href="{link}"><button style="width:100%; border-radius:10px; height:3.5em; background:#444; color:white; border:none;">🖨️</button></a>', unsafe_allow_html=True)
                if c2.button("🗑️", key=f"del_{idx}"):
                    conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                if c3.button("✔️", key=f"ok_{idx}", type="primary", disabled=not pronto):
                    df_v.at[idx, 'status'] = "Concluído"; df_v.at[idx, 'total'] = t_m; df_v.at[idx, 'itens'] = json.dumps(its)
                    conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- 4. ESTOQUE (ADICIONAR, EDITAR, EXCLUIR) ---
with tab[3]:
    st.subheader("Gerenciar Produtos")
    
    with st.expander("➕ ADICIONAR NOVO PRODUTO"):
        n_nome = st.text_input("Nome do Produto")
        n_preco = st.text_input("Preço (ex: 5.50)")
        n_tipo = st.selectbox("Tipo", ["UN", "KG", "MAÇO"])
        if st.button("SALVAR NOVO"):
            novo_prod = pd.DataFrame([{"id": int(datetime.now().timestamp()), "nome": n_nome, "preco": n_preco, "tipo": n_tipo, "status": "Ativo"}])
            conn.update(worksheet="Produtos", data=pd.concat([df_p, novo_prod], ignore_index=True))
            st.rerun()

    st.divider()
    if not df_p.empty:
        for idx, row in df_p.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([2, 1, 1])
                c1.write(f"**{row['nome']}** ({row['status']})")
                if c2.button("OCULTAR/ATIVAR", key=f"st_{idx}"):
                    df_p.at[idx, 'status'] = "Oculto" if row['status'] == "Ativo" else "Ativo"
                    conn.update(worksheet="Produtos", data=df_p); st.rerun()
                if c3.button("EXCLUIR", key=f"ex_p_{idx}"):
                    conn.update(worksheet="Produtos", data=df_p.drop(idx)); st.rerun()

# --- FINANCEIRO E HISTÓRICO (SIMPLIFICADO) ---
with tab[4]:
    st.metric("Saldo Total", f"R$ {df_v['total'].astype(float).sum():.2f}")
    st.dataframe(df_v)

with tab[5]:
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_hj = df_v[df_v['data'] == hoje]
    st.metric("Vendas Hoje", len(df_hj))
    st.dataframe(df_hj)
