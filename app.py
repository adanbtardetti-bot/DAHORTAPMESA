import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS para botões e visual
st.markdown('<style>div[data-testid="stColumn"]{display:flex;align-items:center;} .btn-zap{background-color:#25d366;color:white;padding:15px;border-radius:10px;text-align:center;text-decoration:none;display:block;font-weight:bold;margin-top:10px;}</style>', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna('')
    except:
        return pd.DataFrame()

# 5 ABAS
aba1, aba2, aba3, aba4, aba5 = st.tabs(["🛒 Novo Pedido", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro"])

# --- 1. NOVO PEDIDO ---
with aba1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    st.header("🛒 Novo Pedido")
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("Cliente", key=f"n_{f}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f}").upper()
    pg = st.toggle("Pago?", key=f"p_{f}")
    o_ped = st.text_input("Observação", key=f"o_{f}")
    
    df_p = carregar_dados("Produtos")
    carrinho = []; total_v = 0.0
    if not df_p.empty:
        for i, r in df_p.iterrows():
            col_n, col_p, col_q = st.columns([2.5, 1.2, 1.3])
            p_u = float(str(r.get('preco', 0)).replace(',', '.'))
            tipo = str(r.get('tipo', 'UN')).upper()
            col_n.markdown(f"**{r['nome']}**")
            qtd = col_q.number_input("Q", 0, step=1, key=f"q_{r['id']}_{f}", label_visibility="collapsed")
            if qtd > 0:
                sub = 0.0 if tipo == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": tipo})
    
    if st.button("💾 FINALIZAR PEDIDO", type="primary", key=f"btn_s_{f}"):
        if n_cli and carrinho:
            df_v = carregar_dados("Pedidos")
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pg else "A PAGAR", "obs": o_ped}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.session_state.f_id += 1; st.rerun()

# --- 2. COLHEITA ---
with aba2:
    st.header("🚜 Lista de Colheita")
    df_ped = carregar_dados("Pedidos")
    if not df_ped.empty:
        pend = df_ped[df_ped['status'].str.lower() == 'pendente']
        if not pend.empty:
            resumo = {}
            for _, ped in pend.iterrows():
                try:
                    for it in json.loads(ped['itens']):
                        chave = f"{it['nome']} ({it.get('tipo', 'UN')})"
                        resumo[chave] = resumo.get(chave, 0) + it['qtd']
                except: continue
            for item, qtd in resumo.items(): st.write(f"🟢 **{qtd}x** {item}")
            txt_z = "*COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in resumo.items()])
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_z)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)

# --- 3. MONTAGEM ---
with aba3:
    st.header("⚖️ Montagem")
    df_m = carregar_dados("Pedidos")
    if not df_m.empty:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        for idx, row in pend_m.iterrows():
            with st.expander(f"👤 {row['cliente']}", expanded=True):
                st.write(f"📍 {row['endereco']}")
                itens_m = json.loads(row['itens']); total_m = 0.0
                for i, it in enumerate(itens_m):
                    c_i, c_v = st.columns([3, 2])
                    if str(it.get('tipo', '')).upper() == "KG":
                        val_kg = c_v.number_input("R$", 0.0, step=0.1, key=f"m_{row['id']}_{i}")
                        it['subtotal'] = val_kg
                        c_i.write(f"⚖️ {it['nome']}")
                    else:
                        c_i.write(f"✅ {it['qtd']}x {it['nome']}")
                        c_v.write(f"R$ {it['subtotal']:.2f}")
                    total_m += float(it['subtotal'])
                
                st.write(f"**TOTAL: R$ {total_m:.2f}**")
                col1, col2, col3 = st.columns(3)
                if col1.button("📦 OK", key=f"ok_{row['id']}"):
                    df_m.at[idx, 'status'] = 'Pronto'; df_m.at[idx, 'total'] = total_m; df_m.at[idx, 'itens'] = json.dumps(itens_m)
                    conn.update(worksheet="Pedidos", data=df_m); st.rerun()
                
                # Botão Etiqueta
                txt_e = f"{row['cliente']}\n{row['endereco']}\n\nTOTAL: R$ {total_m:.2f}"
                b64 = base64.b64encode(txt_e.encode()).decode()
                col2.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"><button style="width:100%;height:2.5rem;">🖨️</button></a>', unsafe_allow_html=True)
                
                if col3.button("🗑️", key=f"del_{row['id']}"):
                    df_m = df_m.drop(idx); conn.update(worksheet="Pedidos", data=df_m); st.rerun()

# --- 4. HISTÓRICO ---
with aba4:
    st.header("📜 Histórico")
    df_h = carregar_dados("Pedidos")
    if not df_h.empty:
        finalizados = df_h[df_h['status'].str.lower() == 'pronto']
        st.dataframe(finalizados[["data", "cliente", "total", "pagamento"]])

# --- 5. FINANCEIRO ---
with aba5:
    st.header("💰 Financeiro")
    df_f = carregar_dados("Pedidos")
    if not df_f.empty:
        recebido = pd.to_numeric(df_f[df_f['pagamento'] == 'PAGO']['total']).sum()
        pendente = pd.to_numeric(df_f[df_f['pagamento'] == 'A PAGAR']['total']).sum()
        st.metric("Recebido", f"R$ {recebido:.2f}")
        st.metric("A Receber", f"R$ {pendente:.2f}")
