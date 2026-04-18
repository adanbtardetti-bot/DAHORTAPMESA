import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

# Configuração de página
st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS para Otimização Extrema e Botões Lado a Lado
st.markdown('''
<style>
    .block-container {padding-top: 1rem; padding-bottom: 0rem;}
    div[data-testid="stColumn"] {display: flex; align-items: center; justify-content: center;}
    .card {border: 1px solid #2e7d32; padding: 8px; border-radius: 8px; background-color: #0e1117; line-height: 1.2;}
    .stButton>button {width: 100%; height: 2.5rem; padding: 0px;}
</style>
''', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except: return pd.DataFrame()

def carregar_pedidos():
    try:
        df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

aba1, aba2, aba3 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

# --- ABA 1: VENDA ---
with aba1:
    if 'form_id' not in st.session_state: st.session_state.form_id = 0
    f_id = st.session_state.form_id
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("Cliente", key=f"n_{f_id}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f_id}").upper()
    pg = st.toggle("Pago?", key=f"p_{f_id}")
    o_ped = st.text_input("Obs", key=f"o_{f_id}")
    
    df_p = carregar_produtos()
    carrinho = []; total_v = 0.0
    if not df_p.empty:
        for i, r in df_p.iterrows():
            col_n, col_p, col_q = st.columns([2.5, 1.2, 1.3])
            p_u = float(str(r['preco']).replace(',', '.'))
            col_n.write(f"**{r['nome']}**")
            qtd = col_q.number_input("Q", min_value=0, step=1, key=f"q_{r['id']}_{f_id}", label_visibility="collapsed")
            if qtd > 0:
                sub = 0.0 if str(r.get('tipo', 'UN')).upper() == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": str(r.get('tipo', 'UN')).upper()})
    
    if st.button(f"💾 SALVAR R$ {total_v:.2f}", type="primary"):
        if n_cli and carrinho:
            df_v = carregar_pedidos()
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pg else "A PAGAR", "obs": o_ped}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.session_state.form_id += 1
            st.rerun()

# --- ABA 2: COLHEITA ---
with aba2:
    df_pedidos = carregar_pedidos()
    if not df_pedidos.empty:
        pendentes = df_pedidos[df_pedidos['status'].str.lower() == 'pendente']
        if not pendentes.empty:
            resumo = {}
            for _, ped in pendentes.iterrows():
                try:
                    for it in json.loads(ped['itens']):
                        chave = f"{it['nome']} ({it.get('tipo', 'UN')})"
                        resumo[chave] = resumo.get(chave, 0) + it['qtd']
                except: continue
            for item, qtd in resumo.items():
                st.write(f"🟢 **{qtd}x** {item}")
            txt_zap = f"*COLHEITA {datetime.now().strftime('%d/%m/%Y')}*\n" + "\n".join([f"• {qtd}x {it}" for it, qtd in resumo.items()])
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_zap)}" target="_blank" class="btn-whatsapp">🟢 WHATSAPP</a>', unsafe_allow_html=True)

# --- ABA 3: MONTAGEM (SEM NAN E COM BOTÕES LADO A LADO) ---
with aba3:
    df_m = carregar_pedidos()
    if not df_m.empty:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        for idx, row in pend_m.iterrows():
            with st.container():
                # Limpeza de NAN para exibição e etiqueta
                cli = str(row['cliente']).replace('nan', '').strip()
                end = str(row['endereco']).replace('nan', '').strip()
                obs = str(row.get('obs', '')).replace('nan', '').strip()
                
                # Card de Identificação
                header_text = f"<b>{cli}</b>"
                if end: header_text += f" | {end}"
                if obs: header_text += f"<br><small><i>💬 {obs}</i></small>"
                
                st.markdown(f'<div class="card">{header_text}</div>', unsafe_allow_html=True)
                
                try: itens_m = json.loads(row['itens'])
                except: itens_m = []
                
                t_at = 0.0
                for i, it in enumerate(itens_m):
                    c_i, c_v = st.columns([3, 2])
                    if str(it.get('tipo', '')).upper() == "KG":
                        v_kg = c_v.number_input("R$", min_value=0.0, step=0.1, key=f"m_{row['id']}_{i}", label_visibility="collapsed")
                        it['subtotal'] = v_kg
                        c_i.write(f"⚖️ {it['nome']}")
                    else:
                        c_i.write(f"✅ {it.get('qtd',0)}x {it['nome']}")
                        c_v.write(f"R$ {it.get('subtotal',0.0):.2f}")
                    t_at += it.get('subtotal', 0.0)

                st.write(f"**Total: R$ {t_at:.2f}** | {row['pagamento']}")
                
                # Botões Lado a Lado (Otimizado)
                b1, b2, b3, b4 = st.columns(4)
                
                if b1.button("📦 OK", key=f"ok_{row['id']}"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = t_at
                    df_m.at[idx, 'itens'] = json.dumps(itens_m)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # ETIQUETA SEM NAN
                etiq_txt = cli
                if end: etiq_txt += f"\n{end}"
                etiq_txt += f"\n\nTOTAL: R$ {t_at:.2f}\nSTATUS: {row['pagamento']}"
                
                b64_e = base64.b64encode(etiq_txt.encode()).decode()
                b2.markdown(f'<a href="intent:base64,{b64_e}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"><button style="width:100%; height:2.5rem; background:#444; color:white; border:none; border-radius:5px; font-weight:bold;">🖨️</button></a>', unsafe_allow_html=True)

                if b3.button("💳", key=f"p_{row['id']}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                if b4.button("🗑️", key=f"d_{row['id']}"):
                    df_m = df_m.drop(idx)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()
                st.markdown("---")
