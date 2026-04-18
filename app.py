import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Gestão", layout="centered")

st.markdown("""
    <style>
    div[data-testid="stColumn"] { display: flex; align-items: center; justify-content: flex-start; }
    .stNumberInput div { margin-top: 0px; }
    .btn-whatsapp { background-color: #25d366; color: white; padding: 12px; border-radius: 10px; text-align: center; text-decoration: none; display: block; font-weight: bold; margin-bottom: 10px; }
    .card-montagem { border: 1px solid #2e7d32; padding: 10px; border-radius: 8px; background-color: #0e1117; margin-bottom: 10px; }
    .info-cliente { font-size: 16px; font-weight: bold; color: #4CAF50; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES DE DADOS ---
def carregar_pedidos():
    try:
        df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except: return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except: return pd.DataFrame()

# --- ABAS ---
tab1, tab2, tab3 = st.tabs(["🛒 Novo Pedido", "🚜 Colheita", "⚖️ Montagem"])

# --- 1. NOVO PEDIDO ---
with tab1:
    if 'form_id' not in st.session_state: st.session_state.form_id = 0
    f_id = st.session_state.form_id
    
    st.header("🛒 Novo Pedido")
    c_n, c_e = st.columns(2)
    nome_cli = c_n.text_input("Cliente", key=f"n_{f_id}").upper()
    end_cli = c_e.text_input("Endereço", key=f"e_{f_id}").upper()
    
    c_p, c_o = st.columns([1, 2])
    pago_v = c_p.toggle("Já está Pago?", key=f"p_{f_id}")
    obs_v = c_o.text_input("Observação (Ex: Deixar no portão)", key=f"o_{f_id}")
    
    st.divider()
    df_p = carregar_produtos()
    carrinho = []; total_v = 0.0
    
    if not df_p.empty:
        for i, row in df_p.iterrows():
            if str(row.get('status', '')).lower() == 'oculto': continue
            col_nome, col_preco, col_qtd = st.columns([2.5, 1.2, 1.3])
            
            p_unit = float(str(row['preco']).replace(',', '.'))
            tipo = str(row.get('tipo', 'UN')).upper()
            
            col_nome.markdown(f"**{row['nome']}**")
            if tipo == "KG": col_preco.caption("PESAGEM")
            else: col_preco.write(f"R$ {p_unit:.2f}")
            
            qtd = col_qtd.number_input("Qtd", min_value=0, step=1, key=f"q_{row['id']}_{f_id}", label_visibility="collapsed")
            
            if qtd > 0:
                sub = 0.0 if tipo == "KG" else (qtd * p_unit)
                total_v += sub
                carrinho.append({"nome": row['nome'], "qtd": qtd, "preco": p_unit, "subtotal": sub, "tipo": tipo})
                
    st.divider()
    st.subheader(f"💰 TOTAL: R$ {total_v:.2f}")
    if st.button("💾 FINALIZAR PEDIDO", type="primary", use_container_width=True):
        if nome_cli and carrinho:
            df_v = carregar_pedidos()
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": nome_cli, "endereco": end_cli, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pago_v else "A PAGAR", "obs": obs_v}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.session_state.form_id += 1
            st.rerun()

# --- 2. COLHEITA ---
with tab2:
    st.header("🚜 Lista de Colheita")
    df_ped = carregar_pedidos()
    if not df_ped.empty and 'status' in df_ped.columns:
        pend = df_ped[df_ped['status'].str.lower() == 'pendente']
        if not pend.empty:
            resumo = {}
            for _, p in pend.iterrows():
                try:
                    for it in json.loads(p['itens']):
                        k = f"{it['nome']} ({it.get('tipo', 'UN')})"
                        resumo[k] = resumo.get(k, 0) + it['qtd']
                except: continue
            
            for k, v in resumo.items():
                st.write(f"🟢 **{v}x** {k}")
            
            st.divider()
            # Botão WhatsApp da Colheita
            txt_zap = f"*COLHEITA DO DIA - {datetime.now().strftime('%d/%m/%Y')}*\n\n" + "\n".join([f"• {v}x {k}" for k, v in resumo.items()])
            link_z = f"https://wa.me/?text={urllib.parse.quote(txt_zap)}"
            st.markdown(f'<a href="{link_z}" target="_blank" class="btn-whatsapp">🟢 ENVIAR LISTA PRO WHATSAPP</a>', unsafe_allow_html=True)
        else: st.info("Nada para colher no momento.")

# --- 3. MONTAGEM ---
with tab3:
    st.header("⚖️ Montagem e Pesagem")
    df_m = carregar_pedidos()
    if not df_m.empty and 'status' in df_m.columns:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        
        for idx, row in pend_m.iterrows():
            with st.container():
                # Card de Identificação com Obs
                st.markdown(f"""
                <div class="card-montagem">
                    <span class="info-cliente">👤 {row['cliente']}</span><br>
                    📍 {row['endereco']}<br>
                    <small>💬 OBS: {row.get('obs', 'Nenhuma')}</small>
                </div>
                """, unsafe_allow_html=True)
                
                itens_m = json.loads(row['itens'])
                t_atual = 0.0
                
                for i, item in enumerate(itens_m):
                    c_it, c_v = st.columns([3, 2])
                    if str(item.get('tipo', '')).upper() == "KG":
                        v_kg = c_v.number_input(f"Valor R$ {item['nome']}", min_value=0.0, step=0.1, key=f"m_{row['id']}_{i}", label_visibility="collapsed")
                        item['subtotal'] = v_kg
                        c_it.write(f"⚖️ **{item['nome']}** (Pesar)")
                    else:
                        c_it.write(f"✅ {item['qtd']}x {item['nome']}")
                        c_v.write(f"R$ {item.get('subtotal', 0.0):.2f}")
                    t_atual += item.get('subtotal', 0.0)

                st.write(f"**Total: R$ {t_atual:.2f}** | Status: **{row.get('pagamento', 'A PAGAR')}**")
                
                # Botões de Ação
                b_ok, b_print, b_pago, b_del = st.columns([1, 1, 0.8, 0.6])
                
                # Botão OK: Salva e Tira da tela
                if b_ok.button("📦 OK", key=f"ok_{row['id']}", help="Finaliza e remove da tela"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = t_atual
                    df_m.at[idx, 'itens'] = json.dumps(itens_m)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # Botão Etiqueta (RawBT)
                txt_e = f"{row['cliente']}\n{row['endereco']}\n\nTOTAL: R$ {t_atual:.2f}\n{row.get('pagamento')}"
                b64_e = base64.b64encode(txt_e.encode()).decode()
                l_p = f"intent:base64,{b64_e}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                b_print.markdown(f'<a href="{l_p}"><button style="width:100%; height:2.2rem; background:#444; color:white; border:none; border-radius:5px;">🖨️ Etiq.</button></a>', unsafe_allow_html=True)

                # Marcar como Pago rápido
                if b_pago.button("💳 $", key=f"pg_{row['id']}", help="Marcar como Pago"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # Excluir
                if b_del.button("🗑️", key=f"del_{row['id']}"):
                    df_m = df_m.drop(idx)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()
                st.divider()
