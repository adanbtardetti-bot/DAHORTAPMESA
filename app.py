import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# Configuração focada em Mobile (ocupar a tela toda)
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# Estilo para botões gigantes e leitura clara
st.markdown("""
    <style>
    .stButton>button { width: 100%; height: 3em; font-size: 18px !important; font-weight: bold; }
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    h2 { font-size: 28px !important; color: #1e3d59; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except: return pd.DataFrame()

df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Garante estrutura básica
if not df_produtos.empty and 'status' not in df_produtos.columns: df_produtos['status'] = 'Ativo'
if 'edit_data' not in st.session_state: st.session_state.edit_data = None

# --- NAVEGAÇÃO POR TABS (Mais funcional que menu lateral) ---
tab1, tab2, tab3, tab4 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "🥦 ESTOQUE"])

# --- FUNÇÃO DE IMPRESSÃO ---
def imprimir_bt(ped):
    v_fmt = f"{float(ped['total']):.2f}".replace('.', ',')
    cmd = f"\x1b\x61\x01\x1b\x21\x38{ped['cliente']}\n\x1b\x21\x00{ped['endereco']}\n----------------\nTOTAL: RS {v_fmt}\n\n\n\n"
    b64 = base64.b64encode(cmd.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;margin-bottom:10px;">🖨️ IMPRIMIR ETIQUETA</div></a>', unsafe_allow_html=True)

# --- ABA 1: NOVO PEDIDO ---
with tab1:
    edit = st.session_state.edit_data
    with st.form("f_venda", clear_on_submit=True):
        st.subheader("Dados do Cliente")
        c = st.text_input("NOME DO CLIENTE", value=edit['cliente'] if edit else "").upper()
        e = st.text_input("ENDEREÇO", value=edit['endereco'] if edit else "").upper()
        fp = st.checkbox("JÁ ESTÁ PAGO?", value=(edit['pagamento'] == "Pago") if edit else False)
        
        st.divider()
        st.subheader("Produtos")
        itens_selecionados = []
        p_ativos = df_produtos[df_produtos['status'] == 'Ativo'] if not df_produtos.empty else pd.DataFrame()
        
        if not p_ativos.empty:
            for _, p in p_ativos.iterrows():
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"n_{p['id']}")
                if qtd > 0:
                    itens_selecionados.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * p['preco'])})
        
        if st.form_submit_button("✅ SALVAR PEDIDO"):
            if c and itens_selecionados:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo_p = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_selecionados), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if fp else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_p], ignore_index=True))
                st.session_state.edit_data = None; st.cache_data.clear(); st.rerun()

# --- ABA 2: COLHEITA ---
with tab2:
    st.subheader("Total para Colher Agora")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"]
    if pend.empty: st.info("Nada pendente.")
    else:
        resumo = {}
        for _, ped in pend.iterrows():
            for it in json.loads(ped['itens']):
                resumo[it['nome']] = resumo.get(it['nome'], 0) + it['qtd']
        
        for nome, qtd in resumo.items():
            st.markdown(f"**{nome}**: {qtd}")
            st.divider()
        
        txt_w = f"*COLHEITA {datetime.now().strftime('%d/%m')}*\n" + "\n".join([f"- {n}: {q}" for n, q in resumo.items()])
        st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_w)}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;">📱 ENVIAR LISTA WHATSAPP</div></a>', unsafe_allow_html=True)

# --- ABA 3: MONTAGEM ---
with tab3:
    pend = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pend.iterrows():
        with st.container(border=True):
            st.write(f"### {ped['cliente']}")
            st.write(f"📍 {ped['endereco']}")
            
            itens = json.loads(ped['itens']); t_real = 0.0; trava = False
            for i, it in enumerate(itens):
                if it['tipo'] == "KG":
                    v = st.text_input(f"Valor R$ {it['nome']}:", key=f"m_{ped['id']}_{i}")
                    if v:
                        try: val = float(v.replace(',','.')); it['subtotal'] = val; t_real += val
                        except: trava = True
                    else: trava = True
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += it['subtotal']
            
            st.write(f"**Total: R$ {t_real:.2f}** | Pgto: {ped['pagamento']}")
            
            imprimir_bt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real})
            if st.button("✅ CONCLUIR PEDIDO", key=f"ok_{ped['id']}", disabled=trava):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
            if st.button("🗑️ EXCLUIR", key=f"del_{ped['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()

# --- ABA 4: ESTOQUE ---
with tab4:
    with st.expander("➕ CADASTRAR PRODUTO"):
        with st.form("add"):
            n = st.text_input("Nome").upper(); p = st.number_input("Preço", min_value=0.0); t = st.selectbox("Unidade", ["UN", "KG"])
            if st.form_submit_button("SALVAR"):
                nid = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
                new = pd.DataFrame([{"id":nid, "nome":n, "preco":p, "tipo":t, "status":"Ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, new], ignore_index=True)); st.cache_data.clear(); st.rerun()
    
    for idx, row in df_produtos.iterrows():
        col1, col2 = st.columns([3, 1])
        col1.write(f"**{row['nome']}** - R$ {row['preco']}")
        if col2.button("🗑️", key=f"d_{row['id']}"):
            conn.update(worksheet="Produtos", data=df_produtos.drop(idx)); st.cache_data.clear(); st.rerun()
