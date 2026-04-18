import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS - FORÇANDO BOTÕES LADO A LADO E REMOVENDO ESPAÇOS
st.markdown('''
<style>
    .block-container {padding-top: 0.5rem;}
    [data-testid="stHorizontalBlock"] {gap: 2px !important;}
    .stButton>button {width: 100% !important; padding: 0px !important; height: 2.5rem !important;}
    .card-info {border: 1px solid #2e7d32; padding: 6px; border-radius: 8px; background-color: #0e1117; margin-bottom: 5px;}
    p {margin-bottom: 0px !important;}
</style>
''', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_pedidos():
    try:
        df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

# AS 3 ABAS SÃO CRIADAS AQUI NO TOPO
aba1, aba2, aba3 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

with aba1:
    st.subheader("Novo Pedido")
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    cli = st.text_input("Cliente", key=f"c{f}").upper()
    end = st.text_input("Endereço", key=f"e{f}").upper()
    col_p, col_o = st.columns(2)
    pago = col_p.toggle("Pago?", key=f"p{f}")
    obs = col_o.text_input("Obs", key=f"o{f}")
    
    # Lista de Produtos (Simplificada para carregar rápido)
    try:
        df_prod = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df_prod.columns = [str(c).lower().strip() for c in df_prod.columns]
        carrinho = []; tot = 0.0
        for i, r in df_prod.iterrows():
            if str(r.get('status','')).lower() == 'oculto': continue
            c_n, c_q = st.columns([3, 2])
            c_n.write(f"**{r['nome']}**")
            qtd = c_q.number_input("Q", min_value=0, step=1, key=f"q{r['id']}{f}", label_visibility="collapsed")
            if qtd > 0:
                p_u = float(str(r['preco']).replace(',', '.'))
                sub = 0.0 if str(r.get('tipo','')).upper() == "KG" else (qtd * p_u)
                tot += sub
                carrinho.append({"nome":r['nome'], "qtd":qtd, "preco":p_u, "subtotal":sub, "tipo":str(r.get('tipo','UN')).upper()})
        
        if st.button(f"💾 SALVAR R$ {tot:.2f}", type="primary"):
            if cli and carrinho:
                df_v = carregar_pedidos()
                novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": cli, "endereco": end, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": tot, "pagamento": "PAGO" if pago else "A PAGAR", "obs": obs}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
                st.session_state.f_id += 1; st.rerun()
    except: st.error("Erro ao carregar produtos")

with aba2:
    st.subheader("Colheita")
    df_ped = carregar_pedidos()
    if not df_ped.empty:
        pend = df_ped[df_ped['status'].str.lower() == 'pendente']
        res = {}
        for _, p in pend.iterrows():
            try:
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it.get('tipo','UN')})"
                    res[k] = res.get(k, 0) + it['qtd']
            except: continue
        for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")
        zap = f"*COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res.items()])
        st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(zap)}" target="_blank" style="background:#25d366;color:white;padding:10px;display:block;text-align:center;border-radius:8px;text-decoration:none;">WHATSAPP</a>', unsafe_allow_html=True)

with aba3:
    st.subheader("Montagem")
    df_m = carregar_pedidos()
    if not df_m.empty:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        for idx, row in pend_m.iterrows():
            # LIMPEZA DE NAN
            c = str(row['cliente']).replace('nan', '').strip()
            e = str(row['endereco']).replace('nan', '').strip()
            o = str(row.get('obs', '')).replace('nan', '').strip()
            
            # CARD COMPACTO
            st.markdown(f'<div class="card-info"><b>{c}</b> | {e}<br><small>{o}</small></div>', unsafe_allow_html=True)
            
            its = json.loads(row['itens']) if isinstance(row['itens'], str) else []
            t_at = 0.0
            for i, it in enumerate(its):
                c_i, c_v = st.columns([3, 2])
                if str(it.get('tipo', '')).upper() == "KG":
                    v_kg = c_v.number_input("R$", 0.0, step=0.1, key=f"m{row['id']}{i}", label_visibility="collapsed")
                    it['subtotal'] = v_kg
                    c_i.write(f"⚖️ {it['nome']}")
                else:
                    c_i.write(f"✅ {it['qtd']}x {it['nome']}")
                    c_v.write(f"R$ {it.get('subtotal',0.0):.2f}")
                t_at += it.get('subtotal', 0.0)

            st.write(f"**Total: R$ {t_at:.2f}** | {row['pagamento']}")
            
            # BOTÕES EM UMA LINHA SÓ (4 COLUNAS)
            b1, b2, b3, b4 = st.columns(4)
            
            if b1.button("📦 OK", key=f"ok{row['id']}"):
                df_m.at[idx, 'status'] = 'Pronto'
                df_m.at[idx, 'total'] = t_at
                df_m.at[idx, 'itens'] = json.dumps(its)
                conn.update(worksheet="Pedidos", data=df_m)
                st.rerun()

            # ETIQUETA SEM TÍTULOS E SEM NAN
            txt_etiq = f"{c}\n{e}" + (f"\nObs: {o}" if o else "") + f"\n\nVALOR: R$ {t_at:.2f}\n{row['pagamento']}"
            b64 = base64.b64encode(txt_etiq.encode()).decode()
            b2.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"><button style="width:100%;height:2.5rem;background:#444;color:white;border:none;border-radius:5px;font-weight:bold;">🖨️</button></a>', unsafe_allow_html=True)

            if b3.button("💳", key=f"p{row['id']}"):
                df_m.at[idx, 'pagamento'] = 'PAGO'
                conn.update(worksheet="Pedidos", data=df_m)
                st.rerun()

            if b4.button("🗑️", key=f"d{row['id']}"):
                df_m = df_m.drop(idx); conn.update(worksheet="Pedidos", data=df_m); st.rerun()
            st.divider()
