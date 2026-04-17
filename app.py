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

# --- FUNÇÃO DE IMPRESSÃO (BOTÃO MELHORADO) ---
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
        
        # HTML do Botão Estilizado
        st.markdown(f"""
            <a href="{url_rawbt}" style="text-decoration: none;">
                <div style="
                    background-color: #28a745; 
                    color: white; 
                    padding: 12px 5px; 
                    text-align: center; 
                    border-radius: 8px; 
                    font-weight: bold; 
                    font-size: 16px; 
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    border: 1px solid #218838;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 10px;
                    text-transform: uppercase;">
                    <span style="font-size: 22px;">🖨️</span> IMPRIMIR
                </div>
            </a>
            """, unsafe_allow_html=True)
    except: 
        st.error("Erro nos caracteres.")

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

elif menu == "Montagem/Expedição":
    st.title("📦 Central de Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pendentes.iterrows():
        with st.container(border=True):
            st.markdown(f"## 👤 {ped['cliente']}")
            st.markdown(f"📍 **Endereço:** {ped['endereco'] if ped['endereco'] else '*Não informado*'}")
            st.divider()
            itens = json.loads(ped['itens']); t_real = 0.0; trava_kg = False
            
            c_it, c_res = st.columns([2, 1])
            with c_it:
                for i, it in enumerate(itens):
                    if it['tipo'] == "KG":
                        v_input = st.text_input(f"Valor R$ {it['nome']}:", key=f"v_{ped['id']}_{i}")
                        if v_input:
                            try:
                                v = float(v_input.replace(',', '.'))
                                t_real += v; it['subtotal'] = v
                            except: trava_kg = True
                        else: trava_kg = True
                    else:
                        st.markdown(f"✅ {it['nome']} — **{it['qtd']} UN**")
                        t_real += it['subtotal']
            
            with c_res:
                st.markdown(f"Pagto: **{ped['pagamento'].upper()}**")
                st.markdown(f"### Total: R$ {t_real:.2f}")

            # BOTÕES DE AÇÃO
            st.write("")
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava_kg, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
            
            with b2: # O BOTÃO NOVO AQUI
                disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})
            
            if b3.button("✏️ EDITAR", key=f"e_{ped['id']}", use_container_width=True):
                st.session_state.edit_data = ped.to_dict()
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()
            if b4.button("🗑️ EXCLUIR", key=f"x_{ped['id']}", use_container_width=True):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()

elif menu == "Estoque":
    st.title("🥦 Estoque")
    # ... (Mantenha a lógica do estoque que já funciona)
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
    if not df_produtos.empty:
        df_f = df_produtos[df_produtos['nome'].str.contains(busca)] if busca else df_produtos
        cols = st.columns(3)
        for i, (idx, row) in enumerate(df_f.iterrows()):
            with cols[i % 3].container(border=True):
                st.markdown(f"### {'🟢' if row['status'] == 'Ativo' else '⚪'} {row['nome']}")
                st.markdown(f"**R$ {row['preco']:.2f}**")
                b_c1, b_c2 = st.columns(2)
                if b_c1.button("Ocultar" if row['status'] == 'Ativo' else "Ativar", key=f"st_{row['id']}", use_container_width=True):
                    df_produtos.at[idx, 'status'] = 'Inativo' if row['status'] == 'Ativo' else 'Ativo'
                    conn.update(worksheet="Produtos", data=df_produtos); st.cache_data.clear(); st.rerun()
                if b_c2.button("🗑️", key=f"del_{row['id']}", use_container_width=True):
                    df_produtos = df_produtos.drop(idx); conn.update(worksheet="Produtos", data=df_produtos); st.cache_data.clear(); st.rerun()
