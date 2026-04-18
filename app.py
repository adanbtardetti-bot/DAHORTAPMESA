import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

# 1. CONFIGURAÇÃO E ESTILO (Botões lado a lado e compactos)
st.set_page_config(page_title="Horta Gestão", layout="centered")
st.markdown('''
<style>
    .block-container {padding-top: 0.5rem;}
    [data-testid="stHorizontalBlock"] {gap: 4px !important;}
    .stButton>button {width: 100% !important; height: 3rem !important; padding: 0px !important;}
    .card-horta {border: 2px solid #2e7d32; padding: 10px; border-radius: 10px; background: #0e1117; margin-bottom: 5px;}
    p {margin-bottom: 2px !important;}
</style>
''', unsafe_allow_html=True)

# 2. CONEXÃO E LIMPEZA DE DADOS
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(folha):
    try:
        df = conn.read(worksheet=folha, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna('') # LIMPA O 'nan' AQUI PARA TODAS AS TELAS
    except:
        return pd.DataFrame()

# --- 3. AS TRÊS TELAS (MENUS) ---
aba1, aba2, aba3 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

# --- TELA DE VENDA ---
with aba1:
    if 'venda_id' not in st.session_state: st.session_state.venda_id = 0
    v_id = st.session_state.venda_id
    
    st.subheader("Novo Pedido")
    c1, c2 = st.columns(2)
    cliente = c1.text_input("Cliente", key=f"cli_{v_id}").upper()
    endereco = c2.text_input("Endereço", key=f"end_{v_id}").upper()
    
    c3, c4 = st.columns(2)
    pago_v = c3.toggle("Já está pago?", key=f"pgv_{v_id}")
    obs_v = c4.text_input("Observação", key=f"obs_{v_id}")
    
    df_p = carregar_dados("Produtos")
    carrinho = []; total_v = 0.0
    
    if not df_p.empty:
        for i, r in df_p.iterrows():
            if str(r.get('status','')).lower() == 'oculto': continue
            col_n, col_q = st.columns([3, 1])
            col_n.write(f"**{r['nome']}** (R$ {r['preco']})")
            qtd = col_q.number_input("Qtd", 0, step=1, key=f"q_{r['id']}_{v_id}", label_visibility="collapsed")
            if qtd > 0:
                p_u = float(str(r['preco']).replace(',', '.'))
                sub = 0.0 if str(r.get('tipo','')).upper() == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome":r['nome'], "qtd":qtd, "preco":p_u, "subtotal":sub, "tipo":str(r.get('tipo','UN')).upper()})
    
    if st.button(f"💾 SALVAR PEDIDO - R$ {total_v:.2f}", type="primary"):
        if cliente and carrinho:
            df_v = carregar_dados("Pedidos")
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": cliente, "endereco": endereco, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pago_v else "A PAGAR", "obs": obs_v}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.session_state.venda_id += 1
            st.rerun()

# --- TELA DE COLHEITA ---
with aba2:
    st.subheader("Lista para Colher")
    df_c = carregar_dados("Pedidos")
    if not df_c.empty:
        pend_c = df_c[df_c['status'].astype(str).str.lower() == 'pendente']
        res_c = {}
        for _, p in pend_c.iterrows():
            try:
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it.get('tipo','UN')})"
                    res_c[k] = res_c.get(k, 0) + it['qtd']
            except: continue
        for k, v in res_c.items(): st.write(f"🥦 **{v}x** {k}")
        
        texto_zap = "*LISTA DE COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res_c.items()])
        st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(texto_zap)}" target="_blank" style="background:#25d366;color:white;padding:10px;display:block;text-align:center;border-radius:8px;text-decoration:none;font-weight:bold;">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)

# --- TELA DE MONTAGEM (O SEU FOCO) ---
with aba3:
    st.subheader("Montagem e Pesagem")
    df_m = carregar_dados("Pedidos")
    if not df_m.empty:
        pend_m = df_m[df_m['status'].astype(str).str.lower() == 'pendente']
        for idx, row in pend_m.iterrows():
            # Dados já vêm sem 'nan' por causa do fillna('') lá em cima
            cli_m = str(row['cliente']).upper()
            end_m = str(row['endereco']).upper()
            obs_m = str(row.get('obs', ''))
            id_m = str(row['id'])

            with st.container():
                st.markdown(f'<div class="card-horta"><b>👤 {cli_m}</b><br>📍 {end_m if end_m else "S/ ENDEREÇO"}</div>', unsafe_allow_html=True)
                if obs_m: st.caption(f"💬 {obs_m}")
                
                try: its_m = json.loads(row['itens'])
                except: its_m = []
                
                total_m = 0.0
                for i, it in enumerate(its_m):
                    c_n, c_v = st.columns([3, 2])
                    if str(it.get('tipo', '')).upper() == "KG":
                        v_kg = c_v.number_input("R$", 0.0, step=0.1, key=f"m_{id_m}_{i}", label_visibility="collapsed")
                        it['subtotal'] = v_kg
                        c_n.write(f"⚖️ **{it['nome']}**")
                    else:
                        c_n.write(f"✅ {it['qtd']}x {it['nome']}")
                        c_v.write(f"R$ {it.get('subtotal', 0.0):.2f}")
                    total_m += float(it.get('subtotal', 0.0))

                st.write(f"**TOTAL: R$ {total_m:.2f}** | {row.get('pagamento', 'A PAGAR')}")

                # OS 4 BOTÕES LADO A LADO
                b1, b2, b3, b4 = st.columns(4)
                
                if b1.button("📦", key=f"ok_{id_m}"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = total_m
                    df_m.at[idx, 'itens'] = json.dumps(its_m)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # Etiqueta RawBT
                txt_e = f"{cli_m}\n{end_m}" + (f"\n{obs_m}" if obs_m else "") + f"\n\nVALOR: R$ {total_m:.2f}"
                b64 = base64.b64encode(txt_e.encode()).decode()
                b2.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"><button style="width:100%;height:3rem;background:#444;color:white;border:none;border-radius:5px;">🖨️</button></a>', unsafe_allow_html=True)

                if b3.button("💳", key=f"pg_{id_m}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                if b4.button("🗑️", key=f"del_{id_m}"):
                    df_m = df_m.drop(idx); conn.update(worksheet="Pedidos", data=df_m); st.rerun()
                st.divider()
