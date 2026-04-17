import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta da Mesa", layout="centered")
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except: return pd.DataFrame()

df_p = carregar("Produtos")
df_v = carregar("Pedidos")

# Blindagem de Colunas
for c in ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]:
    if c not in df_v.columns: df_v[c] = ""

# --- NAVEGAÇÃO ---
menu = st.tabs(["🛒 VENDAS", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. VENDAS (NOVO PEDIDO) ---
with menu[0]:
    f_id = st.session_state.get("f_id", 0)
    nome = st.text_input("Cliente", key=f"n{f_id}").upper()
    ende = st.text_input("Endereço", key=f"e{f_id}").upper()
    pago_v = st.checkbox("Pago", key=f"p{f_id}")
    
    st.write("---")
    venda_it, t_est = [], 0.0
    for _, r in df_p[df_p['status'] == 'ativo'].iterrows():
        c1, c2 = st.columns([3, 1])
        qtd = c2.number_input(f"{r['nome']}", min_value=0, step=1, key=f"p{r['id']}{f_id}")
        if qtd > 0:
            p_u = float(str(r['preco']).replace(',', '.'))
            sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
            venda_it.append({"nome": r['nome'], "qtd": qtd, "tipo": r['tipo'], "subtotal": sub, "preco": p_u})
            t_est += sub
    
    st.write(f"### Estimado: R$ {t_est:.2f}")
    if st.button("SALVAR PEDIDO", use_container_width=True, type="primary"):
        if nome and venda_it:
            nid = int(pd.to_numeric(df_v['id'], errors='coerce').max() + 1) if not df_v.empty else 1
            novo = pd.DataFrame([{"id": nid, "cliente": nome, "endereco": ende, "itens": json.dumps(venda_it), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if pago_v else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.session_state["f_id"] = f_id + 1
            st.rerun()

# --- 2. COLHEITA ---
with menu[1]:
    pend = df_v[df_v['status'].str.lower() == "pendente"]
    if not pend.empty:
        soma = {}
        for _, p in pend.iterrows():
            for it in json.loads(p['itens']): soma[it['nome']] = soma.get(it['nome'], 0) + it['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Total": v} for k, v in soma.items()]))
        txt_w = "COLHEITA:\n" + "\n".join([f"{k}: {v}" for k, v in soma.items()])
        st.markdown(f'[📲 WhatsApp](https://wa.me/?text={urllib.parse.quote(txt_w)})')

# --- 3. MONTAGEM ---
with menu[2]:
    p_montar = df_v[df_v['status'].str.lower() == "pendente"]
    for idx, p in p_montar.iterrows():
        with st.container(border=True):
            st.write(f"**{p['cliente']}**")
            its, tf, ok = json.loads(p['itens']), 0.0, True
            for i, it in enumerate(its):
                if str(it.get('tipo')).upper() == "KG":
                    val = st.text_input(f"Valor {it['nome']} ({it['qtd']}kg):", key=f"m{p['id']}{i}")
                    if val: v = float(val.replace(',', '.')); it['subtotal'] = v; tf += v
                    else: ok = False
                else:
                    st.write(f"• {it['nome']} - {it['qtd']} UN"); tf += float(it['subtotal'])
            
            # Etiqueta com Valor Sempre
            cmd = f"\x1b\x61\x01\x1b\x21\x10{p['cliente']}\n\x1b\x21\x00{p['endereco']}\n\x1b\x21\x08VALOR: RS {tf:.2f}\n\n\n"
            b64 = base64.b64encode(cmd.encode('latin-1')).decode('utf-8')
            url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
            st.markdown(f'[🖨️ ETIQUETA]({url})')
            
            c1, c2, c3 = st.columns(3)
            # Botão Pago fica verde (primary) se clicado
            cor_pago = "primary" if p['pagamento'] == "PAGO" else "secondary"
            if c1.button("✅ PAGO", key=f"pg{idx}", type=cor_pago, use_container_width=True):
                df_v.at[idx, 'pagamento'] = "PAGO"; conn.update(worksheet="Pedidos", data=df_v); st.rerun()
            if c2.button("🗑️", key=f"ex{idx}", use_container_width=True):
                conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
            if c3.button("SALVAR", key=f"sv{idx}", disabled=not ok, use_container_width=True):
                df_v.at[idx, 'status'] = "Concluído"; df_v.at[idx, 'total'] = tf; df_v.at[idx, 'itens'] = json.dumps(its)
                conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- 4. HISTÓRICO ---
with menu[3]:
    hoje = datetime.now().strftime("%d/%m/%Y")
    data_h = st.date_input("Data", datetime.now()).strftime("%d/%m/%Y")
    h_fil = df_v[(df_v['status'].str.lower() == "concluído") & (df_v['data'] == data_h)]
    
    # Resumo igual à foto
    res1, res2, res3 = st.columns(3)
    res1.metric("Pedidos", len(h_fil))
    res2.metric("Pagos", len(h_fil[h_fil['pagamento'] == "PAGO"]))
    res3.metric("Total", f"R$ {h_fil['total'].astype(float).sum():.2f}")
    
    for idx, p in h_fil.iterrows():
        with st.expander(f"👤 {p['cliente']} | R$ {float(p['total']):.2f}"):
            st.write(f"📍 {p['endereco']}")
            for it in json.loads(p['itens']):
                st.write(f"- {it['nome']}: R$ {float(it['subtotal']):.2f}")
            
            c1, c2 = st.columns(2)
            c1.markdown(f'[🖨️ Re-Imprimir]({url})')
            if c2.button("MARCAR PAGO", key=f"hpg{idx}"):
                df_v.at[idx, 'pagamento'] = "PAGO"; conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- 5. FINANCEIRO ---
with tabs[4]:
    # Lógica de seleção de períodos e grupos de pedidos
    df_con = df_v[df_v['status'].str.lower() == "concluído"]
    sel = st.multiselect("Grupo de Pedidos (Relatório)", df_con['cliente'].unique())
    if sel:
        df_g = df_con[df_con['cliente'].isin(sel)]
        st.write(f"Total Grupo: R$ {df_g['total'].astype(float).sum():.2f}")
        st.dataframe(df_g[['cliente', 'total', 'pagamento']])

# --- 6. ESTOQUE ---
with menu[5]:
    st.subheader("Produtos")
    for i, r in df_p.iterrows():
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.write(f"**{r['nome']}** - R$ {r['preco']}")
        if c2.button("🚫" if r['status'] == "ativo" else "✅", key=f"at{i}"):
            df_p.at[i, 'status'] = "inativo" if r['status'] == "ativo" else "ativo"
            conn.update(worksheet="Produtos", data=df_p); st.rerun()
        if c3.button("🗑️", key=f"exc{i}"):
            conn.update(worksheet="Produtos", data=df_p.drop(i)); st.rerun()
