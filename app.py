import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS para botões lado a lado e remover o 'nan' visual
st.markdown('''
<style>
    .block-container {padding-top: 1rem;}
    [data-testid="stHorizontalBlock"] {gap: 4px !important;}
    .stButton>button {width: 100% !important; height: 2.8rem !important; padding: 0px !important;}
    .card-horta {border: 1px solid #2e7d32; padding: 8px; border-radius: 8px; background-color: #0e1117; margin-bottom: 5px;}
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

# --- AS ABAS (MENUS) ---
aba1, aba2, aba3 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

# --- ABA 1: VENDA ---
with aba1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    cli = st.text_input("Cliente", key=f"c{f}").upper()
    end = st.text_input("Endereço", key=f"e{f}").upper()
    col_p, col_o = st.columns(2)
    pago = col_p.toggle("Pago?", key=f"p{f}")
    obs = col_o.text_input("Obs", key=f"o{f}")
    
    try:
        df_prod = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df_prod.columns = [str(c).lower().strip() for c in df_prod.columns]
        carrinho = []; tot = 0.0
        for i, r in df_prod.iterrows():
            if str(r.get('status','')).lower() == 'oculto': continue
            c_n, c_q = st.columns([3, 2])
            c_n.write(f"**{r['nome']}**")
            qtd = c_q.number_input("Q", 0, step=1, key=f"q{r['id']}{f}", label_visibility="collapsed")
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
                st.session_state.f_id += 1
                st.rerun()
    except: st.write("Carregando...")

# --- ABA 2: COLHEITA ---
with aba2:
    df_ped = carregar_pedidos()
    if not df_ped.empty:
        pend = df_ped[df_ped['status'].str.lower() == 'pendente']
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
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(zap)}" target="_blank" style="background:#25d366;color:white;padding:10px;display:block;text-align:center;border-radius:8px;text-decoration:none;">WHATSAPP</a>', unsafe_allow_html=True)

# --- ABA 3: MONTAGEM ---
with aba3:
    df_m = carregar_pedidos()
    if not df_m.empty:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        for idx, row in pend_m.iterrows():
            # Limpeza de NAN (Não mostra se estiver vazio)
            c = str(row['cliente']).replace('nan', '').strip()
            e = str(row['endereco']).replace('nan', '').strip()
            o = str(row.get('obs', '')).replace('nan', '').strip()
            
            with st.container():
                st.markdown(f'<div class="card-horta"><b>👤 {c}</b><br>📍 {e if e else "---"}</div>', unsafe_allow_html=True)
                if o: st.caption(f"💬 {o}")
                
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
                
                # BOTÕES LADO A LADO
                b_col1, b_col2, b_col3, b_col4 = st.columns(4)
                
                if b_col1.button("📦", key=f"ok{row['id']}"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = t_at
                    df_m.at[idx, 'itens'] = json.dumps(its)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # ETIQUETA LIMPA (Só imprime o que tem valor)
                etiq = f"{c}\n{e}"
                if o: etiq += f"\nObs: {o}"
                etiq += f"\n\nVALOR: R$ {t_at:.2f}\n{row['pagamento']}"
                b64 = base64.b64encode(etiq.encode()).decode()
                b_col2.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"><button style="width:100%;height:2.8rem;background:#444;color:white;border:none;border-radius:5px;">🖨️</button></a>', unsafe_allow_html=True)

                if b_col3.button("💳", key=f"p{row['id']}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                if b_col4.button("🗑️", key=f"d{row['id']}"):
                    df_m = df_m.drop(idx)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()
                st.divider()
