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
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()

df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

if not df_produtos.empty and 'status' not in df_produtos.columns:
    df_produtos['status'] = 'Ativo'

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque"])

# --- FUNÇÃO DE IMPRESSÃO (SÓ PAGO + LAYOUT SEU) ---
def disparar_impressao_rawbt(ped):
    nome = str(ped.get('cliente', '')).strip().upper() if pd.notna(ped.get('cliente')) else ""
    endereco = str(ped.get('endereco', '')).strip().upper() if pd.notna(ped.get('endereco')) else ""
    status_raw = str(ped.get('pagamento', '')).strip().upper()
    exibir_pg = "PAGO" if status_raw == "PAGO" else ""
    valor_formatado = f"{float(ped['total']):.2f}".replace('.', ',')

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

# --- TELA: NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    with st.form("form_venda", clear_on_submit=True):
        c = st.text_input("Cliente", value=edit['cliente'] if edit else "")
        e = st.text_input("Endereço", value=edit['endereco'] if edit else "")
        foi_pago = st.checkbox("Marcar como PAGO", value=(edit['pagamento'] == "Pago") if edit else False)
        st.write("---")
        itens_p = []
        produtos_ativos = df_produtos[df_produtos['status'] == 'Ativo'] if not df_produtos.empty else pd.DataFrame()
        if not produtos_ativos.empty:
            for _, p in produtos_ativos.iterrows():
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
                novo_df = pd.DataFrame([{"id": prox_id, "cliente": c.upper(), "endereco": e.upper(), "itens": json.dumps(itens_p), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if foi_pago else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_df], ignore_index=True))
                st.session_state.edit_data = None; st.cache_data.clear(); st.rerun()

# --- TELA: MONTAGEM (LAYOUT MELHORADO) ---
elif menu == "Montagem/Expedição":
    st.title("📦 Central de Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    
    if pendentes.empty:
        st.info("Todos os pedidos já foram montados! 🎉")
    
    for idx, ped in pendentes.iterrows():
        # Card de Pedido com borda destacada
        with st.container(border=True):
            # Cabeçalho do Card: Cliente e Endereço com Destaque
            st.markdown(f"## 👤 {ped['cliente']}")
            if ped['endereco']:
                st.markdown(f"📍 **Endereço:** {ped['endereco']}")
            else:
                st.markdown("📍 *Endereço não informado*")
            
            st.divider()
            
            # Lista de Itens
            itens = json.loads(ped['itens'])
            t_real = 0.0
            trava_kg = False
            
            col_itens_1, col_itens_2 = st.columns([2, 1])
            
            with col_itens_1:
                st.write("**Lista de Itens:**")
                for i, it in enumerate(itens):
                    if it['tipo'] == "KG":
                        # Campo de entrada para peso/valor destacado
                        st.markdown(f"⚖️ **{it['nome']} (KG)**")
                        v_input = st.text_input(f"Valor R$ {it['nome']}:", key=f"v_{ped['id']}_{i}", placeholder="0,00")
                        if v_input:
                            try:
                                valor_item = float(v_input.replace(',', '.'))
                                t_real += valor_item
                                it['subtotal'] = valor_item
                            except: trava_kg = True
                        else: trava_kg = True
                    else:
                        st.markdown(f"✅ {it['nome']} — **{it['qtd']} UN**")
                        t_real += it['subtotal']
            
            with col_itens_2:
                # Painel de Status de Pagamento e Total
                st.write("**Resumo Financeiro:**")
                cor_pg = "green" if ped['pagamento'] == "Pago" else "red"
                st.markdown(f"Pagamento: <span style='color:{cor_pg}; font-weight:bold;'>{ped['pagamento'].upper()}</span>", unsafe_allow_html=True)
                st.markdown(f"### Total: R$ {t_real:.2f}")

            st.write("") # Espaço

            # Botões de Ação na Base do Card
            b1, b2, b3, b4 = st.columns(4)
            
            if b1.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava_kg, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_real
                df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear(); st.rerun()

            with b2:
                # Envia dados atualizados para a função de impressão
                disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})

            if b3.button("✏️ EDITAR", key=f"e_{ped['id']}", use_container_width=True):
                st.session_state.edit_data = ped.to_dict()
                df_pedidos_restantes = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos_restantes)
                st.cache_data.clear(); st.rerun()

            if b4.button("🗑️ EXCLUIR", key=f"x_{ped['id']}", use_container_width=True):
                df_pedidos_restantes = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos_restantes)
                st.cache_data.clear(); st.rerun()

# --- TELA: ESTOQUE (LAYOUT GRID 3 COLUNAS) ---
elif menu == "Estoque":
    st.title("🥦 Controle de Estoque")
    col_busca, col_add = st.columns([2, 1])
    busca = col_busca.text_input("🔍 Buscar Produto", "").upper()
    with col_add.expander("➕ Novo Item"):
        with st.form("quick_add"):
            n = st.text_input("Nome"); p = st.number_input("Preço", min_value=0.0); t = st.selectbox("Unidade", ["UN", "KG"])
            if st.form_submit_button("Adicionar"):
                nid = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
                new = pd.DataFrame([{"id":nid, "nome":n.upper(), "preco":p, "tipo":t, "status":"Ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, new], ignore_index=True))
                st.cache_data.clear(); st.rerun()
    st.write("---")
    if not df_produtos.empty:
        df_f = df_produtos[df_produtos['nome'].str.contains(busca)] if busca else df
