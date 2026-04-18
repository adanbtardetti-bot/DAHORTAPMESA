import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

# Configuração de página
st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS para fixar abas e compactar botões (lado a lado)
st.markdown('''
<style>
    .block-container {padding-top: 1rem;}
    .card {border: 1px solid #2e7d32; padding: 8px; border-radius: 8px; background-color: #0e1117; margin-bottom: 5px;}
    div[data-testid="stHorizontalBlock"] {gap: 5px;}
    .stButton>button {width: 100% !important; height: 2.8rem !important; padding: 0px !important;}
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

# CRIAÇÃO DAS ABAS - Isso garante que os menus apareçam
aba1, aba2, aba3 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

# --- ABA 1: VENDA ---
with aba1:
    if 'form_id' not in st.session_state: st.session_state.form_id = 0
    f_id = st.session_state.form_id
    n_cli = st.text_input("Cliente", key=f"n_{f_id}").upper()
    e_cli = st.text_input("Endereço", key=f"e_{f_id}").upper()
    c_aux = st.columns(2)
    pg = c_aux[0].toggle("Pago?", key=f"p_{f_id}")
    o_ped = c_aux[1].text_input("Obs", key=f"o_{f_id}")
    
    df_p = carregar_produtos()
    carrinho = []; total_v = 0.0
    if not df_p.empty:
        for i, r in df_p.iterrows():
            col_n, col_q = st.columns([3, 2])
            p_u = float(str(r['preco']).replace(',', '.'))
            col_n.write(f"**{r['nome']}**")
            qtd = col_q.number_input("Qtd", min_value=0, step=1, key=f"q_{r['id']}_{f_id}", label_visibility="collapsed")
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
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_zap)}" target="_blank" style="background:#25d366;color:white;padding:10px;display:block;text-align:center;border-radius:8px;text-decoration:none;">🟢 ENVIAR WHATSAPP</a>', unsafe_allow_html=True)

# --- ABA 3: MONTAGEM ---
with aba3:
    df_m = carregar_pedidos()
    if not df_m.empty:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        for idx, row in pend_m.iterrows():
            # Limpeza de campos vazios (tira o 'nan')
            cli = str(row['cliente']).replace('nan', '').strip()
            end = str(row['endereco']).replace('nan', '').strip()
            obs = str(row.get('obs', '')).replace('nan', '').strip()
            
            with st.container():
                st.markdown(f'<div class="card"><b>👤 {cli}</b><br>📍 {end if end else "S/ Endereço"}</div>', unsafe_allow_html=True)
                if obs: st.caption(f"💬 {obs}")
                
                itens_m = json.loads(row['itens']) if isinstance(row['itens'], str) else []
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
                
                # BOTÕES LADO A LADO (4 colunas)
                b_col1, b_col2, b_col3, b_col4 = st.columns(4)
                
                if b_col1.button("📦", key=f"ok_{row['id']}", help="Finalizar"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = t_at
                    df_m.at[idx, 'itens'] = json.dumps(itens_m)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # ETIQUETA SEM TÍTULOS INÚTEIS
                etiq = f"{cli}\n{end}"
                if obs: etiq += f"\nObs: {obs}"
                etiq += f"\n\nVALOR: R$ {t_at:.2f}\n{row['pagamento']}"
                b64 = base64.b64encode(etiq.encode()).decode()
                b_col2.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"><button style="width:100%;height:2.8rem;background:#444;color:white;border:none;border-radius:5px;">🖨️</button></a>', unsafe_allow_html=True)

                if b_col3.button("💳", key=f"p_{row['id']}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                if b_col4.button("🗑️", key=f"d_{row['id']}"):
                    df_m = df_m.drop(idx)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()
                st.divider()
