import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

st.set_page_config(page_title="Horta da Mesa", layout="wide")

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        if df is None:
            return pd.DataFrame()
        return df.dropna(how="all")
    except Exception as e:
        st.error(f"Erro na aba {aba}: {e}")
        return pd.DataFrame()

# Carregar Dados
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# --- CORREÇÃO AUTOMÁTICA DA COLUNA STATUS ---
if not df_produtos.empty:
    if 'status' not in df_produtos.columns:
        df_produtos['status'] = 'Ativo'
        # Salva na planilha para criar a coluna de vez
        conn.update(worksheet="Produtos", data=df_produtos)
        st.cache_data.clear()

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque"])

# --- FUNÇÃO DE IMPRESSÃO ---
def disparar_impressao_rawbt(ped):
    nome = str(ped.get('cliente', '')).strip().upper() if pd.notna(ped.get('cliente')) else ""
    endereco = str(ped.get('endereco', '')).strip().upper() if pd.notna(ped.get('endereco')) else ""
    status_raw = str(ped.get('pagamento', '')).strip().upper()
    exibir_pg = "PAGO" if status_raw == "PAGO" else ""
    
    try:
        valor_float = float(ped['total'])
    except:
        valor_float = 0.0
        
    valor_formatado = f"{valor_float:.2f}".replace('.', ',')

    comandos = "\x1b\x61\x01" 
    if nome: comandos += "\x1b\x21\x38" + nome + "\n"
    if endereco: comandos += "\x1b\x21\x38" + endereco + "\n"
    comandos += "\x1b\x21\x00" + "----------------\n"
    comandos += "TOTAL: RS " + valor_formatado + "\n"
    if exibir_pg: comandos += exibir_pg + "\n"
    comandos += "\n\n\n"
    
    try:
        b64_texto = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url_rawbt = f"intent:base64,{b64_texto}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'<a href="{url_rawbt}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;font-size:20px;">🖨️ IMPRIMIR ETIQUETA</div></a>', unsafe_allow_html=True)
    except: st.error("Erro nos caracteres.")

# --- TELAS DE OPERAÇÃO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    with st.form("form_venda", clear_on_submit=True):
        c = st.text_input("Cliente", value=edit['cliente'] if edit else "")
        e = st.text_input("Endereço", value=edit['endereco'] if edit else "")
        foi_pago = st.checkbox("Marcar como PAGO", value=(edit['pagamento'] == "Pago") if edit else False)
        st.write("---")
        itens_p = []
        if not df_produtos.empty:
            # Filtra apenas Ativos para o pedido
            prods_ativos = df_produtos[df_produtos['status'] == 'Ativo']
            for _, p in prods_ativos.iterrows():
                def_qtd = 0
                if edit:
                    try:
                        for oi in json.loads(edit['itens']):
                            if oi['nome'] == p['nome']: def_qtd = int(oi.get('qtd', 0))
                    except: pass
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, value=def_qtd, key=f"p_{p['id']}")
                if qtd > 0: itens_p.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * p['preco'])})
        
        if st.form_submit_button("✅ SALVAR PEDIDO"):
            if c and itens_p:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo_df = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_p), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if foi_pago else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_df], ignore_index=True))
                st.session_state.edit_data = None; st.cache_data.clear(); st.rerun()

elif menu == "Montagem/Expedição":
    st.header("📦 Montagem")
    if not df_pedidos.empty:
        pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
        for idx, ped in pendentes.iterrows():
            with st.container(border=True):
                st.subheader(f"👤 {ped['cliente']}")
                try:
                    itens = json.loads(ped['itens'])
                    t_real = 0.0; trava_kg = False
                    for i, it in enumerate(itens):
                        if it['tipo'] == "KG":
                            st.write(f"⚖️ **{it['nome']}**")
                            v_input = st.text_input(f"Valor R$:", key=f"v_{ped['id']}_{i}")
                            if v_input:
                                try: t_real += float(v_input.replace(',', '.')); it['subtotal'] = float(v_input.replace(',', '.'))
                                except: trava_kg = True
                            else: trava_kg = True
                        else: st.write(f"✅ {it['nome']} - {it['qtd']} un"); t_real += it['subtotal']
                    
                    c1, c2, c3, c4 = st.columns(4)
                    if c1.button("✅ Concluir", key=f"f_{ped['id']}", disabled=trava_kg):
                        df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                        conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
                    with c2: disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})
                    if c3.button("✏️ Editar", key=f"e_{ped['id']}"):
                        st.session_state.edit_data = ped.to_dict(); conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()
                    if c4.button("🗑️ Excluir", key=f"x_{ped['id']}"):
                        conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()
                except: st.error("Erro nos dados deste pedido.")

# --- TELA: ESTOQUE (GRID MODERNO) ---
elif menu == "Estoque":
    st.title("🥦 Controle de Estoque")
    
    col_busca, col_add = st.columns([2, 1])
    busca = col_busca.text_input("🔍 Buscar Produto", "").upper()
    
    with col_add.expander("➕ Novo Item"):
        with st.form("quick_add"):
            n = st.text_input("Nome")
            p = st.number_input("Preço", min_value=0.0)
            t = st.selectbox("Unidade", ["UN", "KG"])
            if st.form_submit_button("Adicionar"):
                if n:
                    nid = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
                    new = pd.DataFrame([{"id":nid, "nome":n.upper(), "preco":p, "tipo":t, "status":"Ativo"}])
                    conn.update(worksheet="Produtos", data=pd.concat([df_produtos, new], ignore_index=True))
                    st.cache_data.clear(); st.rerun()

    st.write("---")

    if not df_produtos.empty:
        df_f = df_produtos[df_produtos['nome'].str.contains(busca)] if busca else df_produtos
        df_f = df_f.sort_values(by="status")

        cols = st.columns(3)
        for i, (idx, row) in enumerate(df_f.iterrows()):
            with cols[i % 3].container(border=True):
                status_simbolo = "🟢" if row['status'] == 'Ativo' else "⚪"
                st.markdown(f"### {status_simbolo} {row['nome']}")
                st.markdown(f"**Preço:** R$ {row['preco']:.2f} / {row['tipo']}")
                
                btn_col1, btn_col2 = st.columns(2)
                label_vis = "Ocultar" if row['status'] == 'Ativo' else "Ativar"
                if btn_col1.button(label_vis, key=f"st_{row['id']}", use_container_width=True):
                    df_produtos.at[idx, 'status'] = 'Inativo' if row['status'] == 'Ativo' else 'Ativo'
                    conn.update(worksheet="Produtos", data=df_produtos)
                    st.cache_data.clear(); st.rerun()
                
                if btn_col2.button("🗑️", key=f"del_{row['id']}", use_container_width=True):
                    df_produtos = df_produtos.drop(idx)
                    conn.update(worksheet="Produtos", data=df_produtos)
                    st.cache_data.clear(); st.rerun()
    else:
        st.info("Estoque vazio.")
