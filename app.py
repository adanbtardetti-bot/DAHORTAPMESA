import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

# 1. SETUP E ESTILO COMPACTO (Mata o espaço vazio e ajeita ícones)
st.set_page_config(page_title="Horta Gestão", layout="centered")

st.markdown('''
<style>
    .block-container {padding: 1rem 0.5rem;}
    [data-testid="stExpander"] {border: 1px solid #333; border-radius: 8px; margin-bottom: 5px;}
    .stButton>button {width: 100% !important; padding: 0px !important; height: 2.5rem !important;}
    .item-linha {display: flex; justify-content: space-between; font-size: 0.9rem; margin-bottom: 2px;}
    hr {margin: 0.5rem 0 !important;}
    /* Alinha colunas de botões */
    div[data-testid="column"] {display: flex; align-items: center; justify-content: center;}
</style>
''', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna('') # Remove o 'nan' que aparecia no endereço
    except: return pd.DataFrame()

tabs = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem", "📜 Hist.", "💰 Fin."])

# --- ABA MONTAGEM (Onde o bicho pegava no layout) ---
with tabs[2]:
    st.subheader("⚖️ Montagem")
    df_m = carregar_dados("Pedidos")
    if not df_m.empty:
        # Filtra apenas pendentes
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        for idx, row in pend_m.iterrows():
            cliente = str(row['cliente']).upper()
            end = str(row['endereco']).upper()
            # Card ultra compacto
            with st.expander(f"👤 {cliente} | {end[:15]}...", expanded=True):
                if end: st.caption(f"📍 {end}")
                
                its = json.loads(row['itens']) if row['itens'] else []
                total_atual = 0.0
                
                # Lista de itens simplificada
                for i, it in enumerate(its):
                    c1, c2 = st.columns([3, 2])
                    if str(it.get('tipo', '')).upper() == "KG":
                        v_kg = c2.number_input("R$", 0.0, step=0.1, key=f"v_{row['id']}_{i}", label_visibility="collapsed")
                        it['subtotal'] = v_kg
                        c1.markdown(f"⚖️ **{it['nome']}**")
                    else:
                        c1.markdown(f"✅ {it['qtd']}x {it['nome']}")
                        c2.markdown(f"R$ {it.get('subtotal', 0.0):.2f}")
                    total_atual += float(it.get('subtotal', 0.0))
                
                st.markdown(f"**TOTAL: R$ {total_atual:.2f}**")
                
                # --- BOTÕES EM LINHA ÚNICA (Otimização de espaço) ---
                b1, b2, b3, b4 = st.columns(4)
                
                # Botão OK (Finalizar)
                if b1.button("📦", key=f"ok_{row['id']}", help="Pronto"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = total_atual
                    df_m.at[idx, 'itens'] = json.dumps(its)
                    conn.update(worksheet="Pedidos", data=df_m); st.rerun()
                
                # Botão Etiqueta (RawBT)
                etiq = f"{cliente}\n{end}\nTOTAL: R$ {total_atual:.2f}"
                b64 = base64.b64encode(etiq.encode()).decode()
                b2.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"><button style="width:100%;height:2.5rem;background:#444;color:white;border:none;border-radius:4px;">🖨️</button></a>', unsafe_allow_html=True)
                
                # Botão Pago
                if b3.button("💳", key=f"pg_{row['id']}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'
                    conn.update(worksheet="Pedidos", data=df_m); st.rerun()
                
                # Botão Lixeira
                if b4.button("🗑️", key=f"del_{row['id']}"):
                    df_m = df_m.drop(idx); conn.update(worksheet="Pedidos", data=df_m); st.rerun()

# --- ABA COLHEITA (Visual limpo) ---
with tabs[1]:
    st.subheader("🚜 Colheita Total")
    df_c = carregar_dados("Pedidos")
    if not df_c.empty:
        pend_c = df_c[df_c['status'].str.lower() == 'pendente']
        resumo = {}
        for _, p in pend_c.iterrows():
            try:
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it.get('tipo','UN')})"
                    resumo[k] = resumo.get(k, 0) + it['qtd']
            except: continue
        for k, v in resumo.items():
            st.markdown(f"🟢 **{v}x** {k}")
        
        txt_zap = "*LISTA DE COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in resumo.items()])
        st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_zap)}" target="_blank" class="btn-zap" style="background:#25d366;color:white;display:block;text-align:center;padding:10px;border-radius:8px;text-decoration:none;font-weight:bold;">ZAP COLHEITA</a>', unsafe_allow_html=True)

# --- ABA HISTÓRICO E FINANCEIRO (Simplificados) ---
with tabs[3]:
    df_h = carregar_dados("Pedidos")
    if not df_h.empty:
        hist = df_h
