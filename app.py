import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="Horta", layout="centered")

# CSS Minimalista para economizar cada pixel da tela
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] { gap: 0px; }
    .stTabs [data-baseweb="tab"] { padding: 8px; font-size: 12px; }
    .card-horta {
        border: 1px solid #2e7d32;
        padding: 5px 10px;
        border-radius: 5px;
        background-color: #0e1117;
        margin-bottom: 5px;
        line-height: 1.2;
    }
    button { height: 2.2rem !important; padding: 0px 5px !important; font-size: 12px !important; }
    p, span, div { font-size: 13px !important; }
    .stNumberInput div div input { height: 2rem !important; }
</style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES DE CARREGAMENTO SEGURO ---
def safe_read(worksheet_name):
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame()

# --- ABAS ---
tab1, tab2, tab3 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

# --- 1. VENDA (SIMPLIFICADA E RÁPIDA) ---
with tab1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    fid = st.session_state.f_id
    
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("Cliente", key=f"n_{fid}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{fid}").upper()
    
    df_prod = safe_read("Produtos")
    carrinho = []
    total_venda = 0.0
    
    if not df_prod.empty:
        for i, r in df_prod.iterrows():
            if str(r.get('status', '')).lower() == 'oculto': continue
            col_n, col_q = st.columns([3, 1])
            nome = r.get('nome', 'Sem Nome')
            preco = float(str(r.get('preco', 0)).replace(',', '.'))
            tipo = str(r.get('tipo', 'UN')).upper()
            
            col_n.write(f"**{nome}** ({tipo})")
            qtd = col_q.number_input("Q", min_value=0, step=1, key=f"q_{i}_{fid}", label_visibility="collapsed")
            
            if qtd > 0:
                sub = 0.0 if tipo == "KG" else (qtd * preco)
                total_venda += sub
                carrinho.append({"nome": nome, "qtd": qtd, "preco": preco, "subtotal": sub, "tipo": tipo})
    
    st.write(f"**TOTAL: R$ {total_venda:.2f}**")
    if st.button("💾 SALVAR PEDIDO", use_container_width=True):
        if n_cli and carrinho:
            df_ped = safe_read("Pedidos")
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_venda, "pagamento": "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_ped, novo], ignore_index=True))
            st.session_state.f_id += 1
            st.rerun()

# --- 2. COLHEITA (SOMA AUTOMÁTICA) ---
with tab2:
    df_c = safe_read("Pedidos")
    if not df_c.empty and 'status' in df_c.columns:
        pend = df_c[df_c['status'].str.lower() == 'pendente']
        resumo = {}
        for _, p in pend.iterrows():
            try:
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it.get('tipo', 'UN')})"
                    resumo[k] = resumo.get(k, 0) + it['qtd']
            except: continue
        
        for k, v in resumo.items(): st.write(f"🟢 **{v}x** {k}")
    else: st.info("Nada pendente.")

# --- 3. MONTAGEM (SUPER OTIMIZADA) ---
with tab3:
    df_m = safe_read("Pedidos")
    if not df_m.empty and 'status' in df_m.columns:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        
        for idx, row in pend_m.iterrows():
            st.markdown(f'<div class="card-horta"><b>{row.get("cliente", "S/N")}</b> | {row.get("endereco", "")}</div>', unsafe_allow_html=True)
            
            try: itens = json.loads(row['itens'])
            except: itens = []
            
            t_ped = 0.0
            for i, item in enumerate(itens):
                c_it, c_v = st.columns([3, 2])
                if str(item.get('tipo', '')).upper() == "KG":
                    val_kg = c_v.number_input("R$", min_value=0.0, step=0.1, key=f"v_{row['id']}_{i}", label_visibility="collapsed")
                    item['subtotal'] = val_kg
                    c_it.write(f"⚖️ {item['nome']}")
                else:
                    c_it.write(f"✅ {item['qtd']}x {item['nome']}")
                    c_v.write(f"R$ {item.get('subtotal', 0.0):.2f}")
                t_ped += item.get('subtotal', 0.0)

            # Botões em linha única para economizar espaço
            st.write(f"**Total: R$ {t_ped:.2f}**")
            b1, b2, b3, b4 = st.columns([1, 1, 1, 0.6])
            
            # Botão OK (Tira da tela)
            if b1.button("📦 OK", key=f"ok_{row['id']}"):
                df_m.at[idx, 'status'] = 'Pronto'
                df_m.at[idx, 'total'] = t_ped
                df_m.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_m)
                st.rerun()

            # Botão Impressão (RawBT)
            txt = f"{row.get('cliente')}\n{row.get('endereco')}\n\nR$ {t_ped:.2f}"
            b64 = base64.b64encode(txt.encode()).decode()
            l_print = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
            b2.markdown(f'<a href="{l_print}"><button style="width:100%; background:#444; color:white; border:none; border-radius:5px;">🖨️ Etiq</button></a>', unsafe_allow_html=True)

            if b3.button("💳 $", key=f"p_{row['id']}"):
                df_m.at[idx, 'pagamento'] = 'PAGO'
                conn.update(worksheet="Pedidos", data=df_m)
                st.rerun()

            if b4.button("🗑️", key=f"d_{row['id']}"):
                df_m = df_m.drop(idx)
                conn.update(worksheet="Pedidos", data=df_m)
                st.rerun()
            st.divider()
    else: st.info("Sem pedidos.")
