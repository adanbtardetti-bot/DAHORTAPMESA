import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

# 1. Configuração de Tela
st.set_page_config(page_title="Horta Gestão", layout="centered")

# 2. Estilo para botões em linha e compactos
st.markdown('''
<style>
    .block-container {padding: 0.5rem;}
    [data-testid="stHorizontalBlock"] {gap: 4px !important;}
    .stButton>button {width: 100% !important; height: 3rem !important; padding: 0px !important;}
    .card {border: 1px solid #2e7d32; padding: 8px; border-radius: 8px; background: #0e1117; margin-bottom: 5px;}
</style>
''', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna('')
    except:
        if aba == "Pedidos":
            return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])
        return pd.DataFrame()

# --- AS 5 TELAS ---
t1, t2, t3, t4, t5 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem", "📜 Hist.", "💰 Fin."])

# --- 1. VENDA ---
with t1:
    if 'v_id' not in st.session_state: st.session_state.v_id = 0
    vid = st.session_state.v_id
    st.subheader("Novo Pedido")
    c1, c2 = st.columns(2)
    cli = c1.text_input("Cliente", key=f"c{vid}").upper()
    end = c2.text_input("Endereço", key=f"e{vid}").upper()
    c3, c4 = st.columns(2)
    pago_v = c3.toggle("Pago?", key=f"p{vid}")
    obs_v = c4.text_input("Obs", key=f"o{vid}")
    df_p = carregar_dados("Produtos")
    carrinho = []; total_v = 0.0
    if not df_p.empty:
        for i, r in df_p.iterrows():
            if str(r.get('status','')).lower() == 'oculto': continue
            cn, cp, cq = st.columns([2.5, 1, 1])
            p_u = float(str(r.get('preco', 0)).replace(',', '.'))
            cn.markdown(f"**{r.get('nome', 'Item')}**")
            qtd = cq.number_input("Q", 0, step=1, key=f"q{i}{vid}", label_visibility="collapsed")
            if qtd > 0:
                tipo = str(r.get('tipo','UN')).upper()
                sub = 0.0 if tipo == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r.get('nome'), "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": tipo})
    if st.button(f"💾 SALVAR R$ {total_v:.2f}", type="primary"):
        if cli and carrinho:
            df_v = carregar_dados("Pedidos")
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": cli, "endereco": end, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pago_v else "A PAGAR", "obs": obs_v}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.session_state.v_id += 1; st.rerun()

# --- 2. COLHEITA ---
with t2:
    st.subheader("Lista para Colher")
    df_c = carregar_dados("Pedidos")
    if not df_c.empty:
        pend = df_c[df_c['status'].str.lower() == 'pendente']
        res = {}
        for _, p in pend.iterrows():
            try:
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it.get('tipo','UN')})"
                    res[k] = res.get(k, 0) + it['qtd']
            except: continue
        for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")
        txt_z = f"*COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res.items()])
        st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_z)}" target="_blank" style="background:#25d366;color:white;display:block;text-align:center;padding:10px;border-radius:8px;text-decoration:none;font-weight:bold;">ZAP COLHEITA</a>', unsafe_allow_html=True)

# --- 3. MONTAGEM ---
with t3:
    st.subheader("Montagem")
    df_m = carregar_dados("Pedidos")
    if not df_m.empty:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        for idx, row in pend_m.iterrows():
            c, e = str(row['cliente']).upper(), str(row['endereco']).upper()
            with st.container():
                st.markdown(f'<div class="card"><b>{c}</b><br>{e}</div>', unsafe_allow_html=True)
                its = json.loads(row['itens']) if isinstance(row['itens'], str) else []
                t_at = 0.0
                for i, it in enumerate(its):
                    ci, cv = st.columns([3, 2])
                    if str(it.get('tipo', '')).upper() == "KG":
                        v_kg = cv.number_input("R$", 0.0, step=0.1, key=f"m{row['id']}{i}", label_visibility="collapsed")
                        it['subtotal'] = v_kg
                        ci.write(f"⚖️ {it['nome']}")
                    else:
                        ci.write(f"✅ {it['qtd']}x {it['nome']}")
                        cv.write(f"R$ {it.get('subtotal',0.0):.2f}")
                    t_at += float(it.get('subtotal', 0.0))
                st.write(f"**Total: R$ {t_at:.2f}**")
                b1, b2, b3, b4 = st.columns(4)
                if b1.button("📦", key=f"ok{row['id']}"):
                    df_m.at[idx, 'status'] = 'Pronto'; df_m.at[idx, 'total'] = t_at; df_m.at[idx, 'itens'] = json.dumps(its)
                    conn.update(worksheet="Pedidos", data=df_m); st.rerun()
                etiq = f"{c}\n{e}\n\nVALOR: R$ {t_at:.2f}"
                b64 = base64.b64encode(etiq.encode()).decode()
                b2.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"><button style="width:100%;height:3rem;background:#444;color:white;border:none;border-radius:5px;">🖨️</button></a>', unsafe_allow_html=True)
                if b3.button("💳", key=f"p{row['id']}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'; conn.update(worksheet="Pedidos", data=df_m); st.rerun()
                if b4.button("🗑️", key=f"d{row['id']}"):
                    df_m = df_m.drop(idx); conn.update(worksheet="Pedidos", data=df_m); st.rerun()
                st.divider()

# --- 4. HISTÓRICO ---
with t4:
    st.subheader("Histórico")
    df_h = carregar_dados("Pedidos")
    if not df_h.empty:
        h = df_h[df_h['status'].str.lower() == 'pronto'].sort_index(ascending=False)
        st.dataframe(h[['data', 'cliente', 'total']], hide_index=True)

# --- 5. FINANCEIRO ---
with t5:
    st.subheader("Financeiro")
    df_f = carregar_dados("Pedidos")
    if not df_f.empty:
        df_f['total'] = pd.to_numeric(df_f['total'], errors='coerce').fillna(0)
        rec = df_f[df_f['pagamento'] == 'PAGO']['total'].sum()
        pen = df_f[df_f['pagamento'] == 'A PAGAR']['total'].sum()
        st.metric("💰 RECEBIDO", f"R$ {rec:.2f}")
        st.metric("⏳ A RECEBER", f"R$ {pen:.2f}")
