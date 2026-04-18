import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="Horta Gestão", layout="centered")

# Estilo para botões lado a lado na Montagem e visual limpo
st.markdown('''
<style>
    .block-container {padding-top: 1rem;}
    [data-testid="stHorizontalBlock"] {gap: 5px !important;}
    .stButton>button {width: 100% !important; height: 3rem !important; padding: 0px !important;}
    .card-pedido {border: 2px solid #2e7d32; padding: 10px; border-radius: 10px; background: #0e1117; margin-bottom: 5px;}
</style>
''', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna('') # Remove o 'nan' de vez
    except:
        return pd.DataFrame()

# Criação das Abas
aba_venda, aba_colheita, aba_montagem = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

# --- 1. TELA DE VENDA ---
with aba_venda:
    st.subheader("Novo Pedido")
    if 'v_id' not in st.session_state: st.session_state.v_id = 0
    v = st.session_state.v_id
    
    cli = st.text_input("Cliente", key=f"c_{v}").upper()
    end = st.text_input("Endereço", key=f"e_{v}").upper()
    c1, c2 = st.columns(2)
    pago_v = c1.toggle("Já está pago?", key=f"p_{v}")
    obs_v = c2.text_input("Observação", key=f"o_{v}")
    
    df_p = carregar_dados("Produtos")
    carrinho = []; total_v = 0.0
    if not df_p.empty:
        for i, r in df_p.iterrows():
            if str(r.get('status','')).lower() == 'oculto': continue
            col_n, col_q = st.columns([3, 1])
            col_n.write(f"**{r['nome']}** (R$ {r['preco']})")
            qtd = col_q.number_input("Qtd", 0, step=1, key=f"q_{r['id']}_{v}", label_visibility="collapsed")
            if qtd > 0:
                p_u = float(str(r['preco']).replace(',', '.'))
                sub = 0.0 if str(r.get('tipo','')).upper() == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome":r['nome'], "qtd":qtd, "preco":p_u, "subtotal":sub, "tipo":str(r.get('tipo','UN')).upper()})
    
    if st.button(f"💾 SALVAR PEDIDO - R$ {total_v:.2f}", type="primary", key="btn_save"):
        if cli and carrinho:
            df_ped = carregar_dados("Pedidos")
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": cli, "endereco": end, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pago_v else "A PAGAR", "obs": obs_v}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_ped, novo], ignore_index=True))
            st.session_state.v_id += 1
            st.rerun()

# --- 2. TELA DE COLHEITA ---
with aba_colheita:
    st.subheader("Lista para Colher")
    df_c = carregar_dados("Pedidos")
    if not df_c.empty:
        pend_c = df_c[df_c['status'].str.lower() == 'pendente']
        res_c = {}
        for _, p in pend_c.iterrows():
            try:
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it.get('tipo','UN')})"
                    res_c[k] = res_c.get(k, 0) + it['qtd']
            except: continue
        for k, v in res_c.items(): st.write(f"🥦 **{v}x** {k}")
        
        txt_zap = "*LISTA DE COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res_c.items()])
        st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_zap)}" target="_blank" style="background:#25d366;color:white;padding:10px;display:block;text-align:center;border-radius:8px;text-decoration:none;font-weight:bold;">ZAP COLHEITA</a>', unsafe_allow_html=True)

# --- 3. TELA DE MONTAGEM ---
with aba_montagem:
    st.subheader("Pedidos para Montar")
    df_m = carregar_dados("Pedidos")
    if not df_m.empty:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        for idx, row in pend_m.iterrows():
            c_nome = str(row['cliente']).upper()
            c_end = str(row['endereco']).upper()
            c_obs = str(row.get('obs', ''))
            
            with st.container():
                st.markdown(f'<div class="card-pedido"><b>👤 {c_nome}</b><br>📍 {c_end if c_end else "---"}</div>', unsafe_allow_html=True)
                if c_obs: st.caption(f"💬 {c_obs}")
                
                itens_m = json.loads(row['itens']) if isinstance(row['itens'], str) else []
                total_m = 0.0
                for i, it in enumerate(itens_m):
                    col_i, col_v = st.columns([3, 2])
                    if str(it.get('tipo', '')).upper() == "KG":
                        val_kg = col_v.number_input("R$", 0.0, step=0.1, key=f"m_{row['id']}_{i}", label_visibility="collapsed")
                        it['subtotal'] = val_kg
                        col_i.write(f"⚖️ **{it['nome']}**")
                    else:
                        col_i.write(f"✅ {it['qtd']}x {it['nome']}")
                        col_v.write(f"R$ {it.get('subtotal', 0.0):.2f}")
                    total_m += float(it.get('subtotal', 0.0))

                st.write(f"**TOTAL: R$ {total_m:.2f}** | {row.get('pagamento', 'A PAGAR')}")

                # Botões em linha
                b1, b2, b3, b4 = st.columns(4)
                if b1.button("📦", key=f"ok_{row['id']}"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = total_m
                    df_m.at[idx, 'itens'] = json.dumps(itens_m)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # Etiqueta (Correção do SyntaxError aqui)
                txt_etiq = f"{c_nome}\n{c_end}" + (f"\nObs: {c_obs}" if c_obs else "") + f"\n\nTOTAL: R$ {total_m:.2f}"
                b64 = base64.b64encode(txt_etiq.encode()).decode()
                b2.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"><button style="width:100%;height:3rem;background:#444;color:white;border:none;border-radius:5px;font-weight:bold;">🖨️</button></a>', unsafe_allow_html=True)

                if b3.button("💳", key=f"pay_{row['id']}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                if b4.button("🗑️", key=f"del_{row['id']}"):
                    df_m = df_m.drop(idx)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()
                st.divider()
