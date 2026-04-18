import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS para garantir o alinhamento que você gosta (Venda e Botões)
st.markdown("""
    <style>
    div[data-testid="stColumn"] { display: flex; align-items: center; justify-content: flex-start; }
    .stNumberInput div { margin-top: 0px; }
    .btn-whatsapp { background-color: #25d366; color: white; padding: 10px; border-radius: 10px; text-align: center; text-decoration: none; display: block; font-weight: bold; }
    .card-montagem { border: 1px solid #2e7d32; padding: 10px; border-radius: 10px; background-color: #0e1117; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES DE APOIO ---
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

# --- 1. NOVO PEDIDO (VOLTOU AO ORIGINAL) ---
with tab1:
    if 'form_id' not in st.session_state: st.session_state.form_id = 0
    f_id = st.session_state.form_id
    
    st.header("🛒 Novo Pedido")
    c_n, c_e = st.columns(2)
    nome_cli = c_n.text_input("Cliente", key=f"n_{f_id}").upper()
    end_cli = c_e.text_input("Endereço", key=f"e_{f_id}").upper()
    
    c_p, c_o = st.columns([1, 2])
    pago_v = c_p.toggle("Pago?", key=f"p_{f_id}")
    obs_v = c_o.text_input("Observação", key=f"o_{f_id}")
    
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
    if st.button("💾 FINALIZAR E LIMPAR", type="primary", use_container_width=True):
        if nome_cli and carrinho:
            df_v = carregar_pedidos()
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": nome_cli, "endereco": end_cli, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pago_v else "A PAGAR", "obs": obs_v}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.session_state.form_id += 1
            st.rerun()

# --- 2. COLHEITA (VOLTOU AO ORIGINAL) ---
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
            
            txt_zap = f"*LISTA DE COLHEITA - {datetime.now().strftime('%d/%m/%Y')}*\n\n"
            for k, v in resumo.items():
                st.write(f"🟢 **{v}x** {k}")
                txt_zap += f"• {v}x {k}\n"
            
            st.divider()
            link_z = f"https://wa.me/?text={urllib.parse.quote(txt_zap)}"
            st.markdown(f'<a href="{link_z}" target="_blank" class="btn-whatsapp">🟢 COMPARTILHAR NO WHATSAPP</a>', unsafe_allow_html=True)
        else: st.info("Nada pendente.")

# --- 3. MONTAGEM (OTIMIZADA E SEM ERROS) ---
with tab3:
    st.header("⚖️ Montagem")
    df_m = carregar_pedidos()
    if not df_m.empty and 'status' in df_m.columns:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        
        for idx, row in pend_m.iterrows():
            with st.container():
                # Título do Card
                st.markdown(f'<div class="card-montagem"><b>👤 {row["cliente"]}</b> | 📍 {row["endereco"]}</div>', unsafe_allow_html=True)
                
                itens_m = json.loads(row['itens'])
                t_atual = 0.0
                
                for i, item in enumerate(itens_m):
                    c_it, c_v = st.columns([3, 2])
                    if str(item.get('tipo', '')).upper() == "KG":
                        # Campo para o valor pesado
                        v_kg = c_v.number_input("Valor R$", min_value=0.0, step=0.1, key=f"m_{row['id']}_{i}", label_visibility="collapsed")
                        item['subtotal'] = v_kg
                        c_it.write(f"⚖️ {item['nome']}")
                    else:
                        c_it.write(f"✅ {item['qtd']}x {item['nome']}")
                        # Busca o subtotal com segurança para não dar KeyError
                        c_v.write(f"R$ {item.get('subtotal', 0.0):.2f}")
                    
                    t_atual += item.get('subtotal', 0.0)

                st.write(f"**Total: R$ {t_atual:.2f}** | {row.get('pagamento', 'A PAGAR')}")
                
                # BOTÕES
                b1, b2, b3, b4 = st.columns([1, 1, 0.8, 0.6])
                
                if b1.button("📦 OK", key=f"ok_{row['id']}"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = t_atual
                    df_m.at[idx, 'itens'] = json.dumps(itens_m)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # Impressão RawBT
                txt_e = f"{row['cliente']}\n{row['endereco']}\n\nR$ {t_atual:.2f}"
                b64_e = base64.b64encode(txt_e.encode()).decode()
                l_p = f"intent:base64,{b64_e}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                b2.markdown(f'<a href="{l_p}"><button style="width:100%; height:2.2rem; background:#444; color:white; border:none; border-radius:5px;">🖨️ Etiq</button></a>', unsafe_allow_html=True)

                if b3.button("💳 $", key=f"pg_{row['id']}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                if b4.button("🗑️", key=f"del_{row['id']}"):
                    df_m = df_m.drop(idx)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()
                st.divider()
