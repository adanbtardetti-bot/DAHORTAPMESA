import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS para botões em linha, sem nan e otimização de celular
st.markdown('''
<style>
    .block-container {padding-top: 1rem;}
    [data-testid="stHorizontalBlock"] {gap: 5px !important;}
    .stButton>button {width: 100% !important; height: 2.8rem !important; padding: 0px !important;}
    .card {border: 2px solid #2e7d32; padding: 10px; border-radius: 10px; background: #0e1117; margin-bottom: 5px;}
    .btn-whatsapp{background-color:#25d366;color:white;padding:12px;border-radius:8px;text-align:center;text-decoration:none;display:block;font-weight:bold;}
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

# MENUS
abas = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro"])

# --- 1. VENDA (Seu código original otimizado) ---
with abas[0]:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("Cliente", key=f"n{f}").upper()
    e_cli = c2.text_input("Endereço", key=f"e{f}").upper()
    col_a, col_b = st.columns(2)
    pg = col_a.toggle("Pago?", key=f"p{f}")
    o_ped = col_b.text_input("Obs", key=f"o{f}")
    
    df_p = carregar_dados("Produtos")
    carrinho = []; total_v = 0.0
    if not df_p.empty:
        for i, r in df_p.iterrows():
            if str(r.get('status','')).lower() == 'oculto': continue
            cn, cp, cq = st.columns([2.5, 1, 1])
            p_u = float(str(r['preco']).replace(',', '.'))
            cn.markdown(f"**{r['nome']}**")
            qtd = cq.number_input("Q", 0, step=1, key=f"q{r['id']}{f}", label_visibility="collapsed")
            if qtd > 0:
                sub = 0.0 if str(r.get('tipo','')).upper() == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": str(r.get('tipo','UN')).upper()})
    
    if st.button(f"💾 SALVAR R$ {total_v:.2f}", type="primary"):
        if n_cli and carrinho:
            df_v = carregar_dados("Pedidos")
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pg else "A PAGAR", "obs": o_ped}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.session_state.f_id += 1; st.rerun()

# --- 2. COLHEITA (Seu código original) ---
with abas[1]:
    df_c = carregar_dados("Pedidos")
    if not df_c.empty:
        pend = df_c[df_c['status'].str.lower() == 'pendente']
        if not pend.empty:
            res = {}
            for _, p in pend.iterrows():
                try:
                    for it in json.loads(p['itens']):
                        k = f"{it['nome']} ({it.get('tipo','UN')})"
                        res[k] = res.get(k, 0) + it['qtd']
                except: continue
            for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")
            zap = f"*COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res.items()])
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(zap)}" target="_blank" class="btn-whatsapp">ZAP COLHEITA</a>', unsafe_allow_html=True)

# --- 3. MONTAGEM (O que você pediu) ---
with abas[2]:
    df_m = carregar_dados("Pedidos")
    if not df_m.empty:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        for idx, row in pend_m.iterrows():
            c, e, o = str(row['cliente']).upper(), str(row['endereco']).upper(), str(row.get('obs',''))
            with st.container():
                st.markdown(f'<div class="card"><b>{c}</b><br>{e}</div>', unsafe_allow_html=True)
                its = json.loads(row['itens']); t_at = 0.0
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
                
                st.write(f"**Total: R$ {t_at:.2f}** | {row['pagamento']}")
                b1, b2, b3, b4 = st.columns(4)
                if b1.button("📦", key=f"ok{row['id']}"):
                    df_m.at[idx, 'status'] = 'Pronto'; df_m.at[idx, 'total'] = t_at; df_m.at[idx, 'itens'] = json.dumps(its)
                    conn.update(worksheet="Pedidos", data=df_m); st.rerun()
                
                etiq = f"{c}\n{e}\n\nVALOR: R$ {t_at:.2f}\n{row['pagamento']}"
                b64 = base64.b64encode(etiq.encode()).decode()
                b2.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"><button style="width:100%;height:3rem;background:#444;color:white;border:none;border-radius:5px;">🖨️</button></a>', unsafe_allow_html=True)
                
                if b3.button("💳", key=f"p{row['id']}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'; conn.update(worksheet="Pedidos", data=df_m); st.rerun()
                if b4.button("🗑️", key=f"d{row['id']}"):
                    df_m = df_m.drop(idx); conn.update(worksheet="Pedidos", data=df_m); st.rerun()
                st.divider()

# --- 4. HISTÓRICO ---
with abas[3]:
    df_h = carregar_dados("Pedidos")
    if not df_h.empty:
        prontos = df_h[df_h['status'].str.lower() == 'pronto'].sort_index(ascending=False)
        for idx, row in prontos.iterrows():
            st.write(f"✅ **{row['cliente']}** - {row['data']} - R$ {row['total']}")
            if st.button("↩️ Reabrir", key=f"rev_{row['id']}"):
                df_h.at[idx, 'status'] = 'Pendente'; conn.update(worksheet="Pedidos", data=df_h); st.rerun()

# --- 5. FINANCEIRO ---
with abas[4]:
    df_f = carregar_dados("Pedidos")
    if not df_f.empty:
        df_f['total'] = pd.to_numeric(df_f['total'], errors='coerce').fillna(0)
        recebido = df_f[df_f['pagamento'] == 'PAGO']['total'].sum()
        a_receber =
