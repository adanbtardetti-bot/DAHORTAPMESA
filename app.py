import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# Configuração da Página
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()

# Carga inicial dos dados
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Garante coluna status no estoque
if not df_produtos.empty and 'status' not in df_produtos.columns:
    df_produtos['status'] = 'Ativo'

# Estado da sessão para edição
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

# Menu Lateral
menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Lista de Colheita", "Montagem/Expedição", "Estoque"])

# --- FUNÇÃO DE IMPRESSÃO ---
def disparar_impressao_rawbt(ped):
    nome = str(ped.get('cliente', '')).strip().upper() if pd.notna(ped.get('cliente')) else ""
    endereco = str(ped.get('endereco', '')).strip().upper() if pd.notna(ped.get('endereco')) else ""
    status_raw = str(ped.get('pagamento', '')).strip().upper()
    exibir_pg = "PAGO" if status_raw == "PAGO" else ""
    valor_formatado = f"{float(ped['total']):.2f}".replace('.', ',')

    comandos = "\x1b\x61\x01" # Centralizar
    if nome: comandos += "\x1b\x21\x38" + nome + "\n"
    if endereco: comandos += "\x1b\x21\x38" + endereco + "\n"
    comandos += "\x1b\x21\x00" + "----------------\n"
    comandos += "TOTAL: RS " + valor_formatado + "\n"
    if exibir_pg: comandos += exibir_pg + "\n"
    comandos += "\n\n\n"
    
    try:
        b64_texto = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url_rawbt = f"intent:base64,{b64_texto}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'''
            <a href="{url_rawbt}" style="text-decoration: none;">
                <div style="background-color: #28a745; color: white; padding: 12px; text-align: center; border-radius: 8px; font-weight: bold; display: flex; align-items: center; justify-content: center; gap: 10px;">
                    <span style="font-size: 20px;">🖨️</span> IMPRIMIR
                </div>
            </a>''', unsafe_allow_html=True)
    except: st.error("Erro na etiqueta.")

# --- TELA: NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    with st.form("form_venda", clear_on_submit=True):
        c = st.text_input("Cliente", value=edit['cliente'] if edit else "")
        e = st.text_input("Endereço", value=edit['endereco'] if edit else "")
        fp = st.checkbox("Marcar como PAGO", value=(edit['pagamento'] == "Pago") if edit else False)
        st.write("---")
        itens_selecionados = []
        p_ativos = df_produtos[df_produtos['status'] == 'Ativo'] if not df_produtos.empty else pd.DataFrame()
        if not p_ativos.empty:
            for _, p in p_ativos.iterrows():
                def_val = 0
                if edit:
                    try:
                        for it in json.loads(edit['itens']):
                            if it['nome'] == p['nome']: def_val = int(it['qtd'])
                    except: pass
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, value=def_val, key=f"new_{p['id']}")
                if qtd > 0:
                    itens_selecionados.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * p['preco'])})
        
        if st.form_submit_button("✅ SALVAR PEDIDO"):
            if c and itens_selecionados:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo_p = pd.DataFrame([{
                    "id": prox_id, "cliente": c.upper(), "endereco": e.upper(), "itens": json.dumps(itens_selecionados),
                    "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if fp else "A Pagar"
                }])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_p], ignore_index=True))
                st.session_state.edit_data = None
                st.cache_data.clear()
                st.rerun()

# --- TELA: LISTA DE COLHEITA ---
elif menu == "Lista de Colheita":
    st.header("🚜 Resumo para Colheita")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    if pendentes.empty:
        st.info("Nenhum pedido pendente para colher.")
    else:
        soma = {}
        for _, ped in pendentes.iterrows():
            its = json.loads(ped['itens'])
            for i in its:
                n = i['nome']
                if n not in soma: soma[n] = {"qtd": 0, "tipo": i['tipo']}
                soma[n]['qtd'] += i['qtd']
        
        for nome, d in soma.items():
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                col1.subheader(nome)
                col2.metric(d['tipo'], f"{d['qtd']}")

# --- TELA: MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pendentes.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {ped['cliente']}")
            st.caption(f"📍 {ped['endereco']}")
            itens_lista = json.loads(ped['itens'])
            t_real = 0.0
            trava_kg = False
            c_itens, c_res = st.columns([2, 1])
            with c_itens:
                for i, it in enumerate(itens_lista):
                    if it['tipo'] == "KG":
                        v_in = st.text_input(f"Valor {it['nome']}:", key=f"mnt_{ped['id']}_{i}")
                        if v_in:
                            try:
                                val = float(v_in.replace(',', '.')); it['subtotal'] = val; t_real += val
                            except: trava_kg = True
                        else: trava_kg = True
                    else:
                        st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += it['subtotal']
            with c_res:
                st.write(f"Pgto: **{ped['pagamento']}**")
                st.markdown(f"### Total: R$ {t_real:.2f}")
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava_kg):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real
                df_pedidos.at[idx, 'itens'] = json.dumps(itens_lista)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
            with b2: disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})
            if b3.button("✏️", key=f"e_{ped['id']}"):
                st.session_state.edit_data = ped.to_dict()
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()
            if b4.button("🗑️", key=f"x_{ped['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()

# --- TELA: ESTOQUE ---
elif menu == "Estoque":
    st.header("🥦 Estoque")
    with st.expander("➕ Novo Produto"):
        with st.form("add_p"):
            n = st.text_input("Nome"); p = st.number_input("Preço", min_value=0.0); t = st.selectbox("Tipo", ["UN", "KG"])
            if st.form_submit_button("Salvar"):
                nid = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
                new_it = pd.DataFrame([{"id":nid, "nome":n.upper(), "preco":p, "tipo":t, "status":"Ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, new_it], ignore_index=True))
                st.cache_data.clear(); st.rerun()
    if not df_produtos.empty:
        cols = st.columns(3)
        for i, (idx, row) in enumerate(df_produtos.iterrows()):
            with cols[i % 3].container(border=True):
                st.write(f"**{row['nome']}**")
                st.write(f"R$ {row['preco']} ({row['status']})")
                c_b1, c_b2 = st.columns(2)
                if c_b1.button("Ocultar" if row['status'] == 'Ativo' else "Ativar", key=f"st_{row['id']}"):
                    df_produtos.at[idx, 'status'] = 'Inativo' if row['status'] == 'Ativo' else 'Ativo'
                    conn.update(worksheet="Produtos", data=df_produtos); st.cache_data.clear(); st.rerun()
                if c_b2.button("🗑️", key=f"del_{row['id']}"):
                    conn.update(worksheet="Produtos", data=df_produtos.drop(idx)); st.cache_data.clear(); st.rerun()
