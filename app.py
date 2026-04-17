import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
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

# Estrutura básica
if not df_produtos.empty and 'status' not in df_produtos.columns:
    df_produtos['status'] = 'Ativo'
if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

# --- NAVEGAÇÃO POR ABAS (NO TOPO) ---
tab1, tab2, tab3, tab4 = st.tabs(["🛒 NOVO PEDIDO", "🚜 COLHEITA", "📦 MONTAGEM", "🥦 ESTOQUE"])

# --- FUNÇÃO DE IMPRESSÃO ---
def disparar_impressao_rawbt(ped):
    nome = str(ped.get('cliente', '')).strip().upper()
    endereco = str(ped.get('endereco', '')).strip().upper()
    pgto = str(ped.get('pagamento', '')).upper()
    valor_fmt = f"{float(ped['total']):.2f}".replace('.', ',')
    
    comandos = "\x1b\x61\x01" 
    if nome: comandos += "\x1b\x21\x38" + nome + "\n"
    if endereco: comandos += "\x1b\x21\x38" + endereco + "\n"
    comandos += "\x1b\x21\x00" + "----------------\n"
    comandos += "TOTAL: RS " + valor_fmt + "\n"
    if pgto == "PAGO": comandos += "PAGO\n"
    comandos += "\n\n\n\n"
    
    try:
        b64_texto = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url_rawbt = f"intent:base64,{b64_texto}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'''
            <a href="{url_rawbt}" style="text-decoration: none;">
                <div style="background-color: #28a745; color: white; padding: 12px; text-align: center; border-radius: 8px; font-weight: bold; display: flex; align-items: center; justify-content: center; gap: 10px; border: 1px solid #218838;">
                    <span style="font-size: 20px;">🖨️</span> IMPRIMIR ETIQUETA
                </div>
            </a>''', unsafe_allow_html=True)
    except: st.error("Erro na etiqueta.")

# --- ABA 1: NOVO PEDIDO ---
with tab1:
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    with st.form("form_venda", clear_on_submit=True):
        col_c1, col_c2 = st.columns(2)
        c = col_c1.text_input("NOME DO CLIENTE", value=edit['cliente'] if edit else "").upper()
        e = col_c2.text_input("ENDEREÇO", value=edit['endereco'] if edit else "").upper()
        fp = st.checkbox("MARCAR COMO PAGO", value=(edit['pagamento'] == "Pago") if edit else False)
        st.write("---")
        
        itens_selecionados = []
        p_ativos = df_produtos[df_produtos['status'] == 'Ativo'] if not df_produtos.empty else pd.DataFrame()
        
        if not p_ativos.empty:
            cols_p = st.columns(3)
            for i, (_, p) in enumerate(p_ativos.iterrows()):
                with cols_p[i % 3]:
                    qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"n_{p['id']}")
                    if qtd > 0:
                        itens_selecionados.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * p['preco'])})
        
        if st.form_submit_button("✅ SALVAR PEDIDO", use_container_width=True):
            if c and itens_selecionados:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo_p = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_selecionados), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if fp else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_p], ignore_index=True))
                st.session_state.edit_data = None; st.cache_data.clear(); st.rerun()

# --- ABA 2: COLHEITA ---
with tab2:
    st.header("🚜 Lista de Colheita")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    if pendentes.empty:
        st.info("Nenhum pedido pendente.")
    else:
        soma = {}
        for _, ped in pendentes.iterrows():
            its = json.loads(ped['itens'])
            for i in its:
                n = i['nome']
                if n not in soma: soma[n] = {"qtd": 0, "tipo": i['tipo']}
                soma[n]['qtd'] += i['qtd']
        
        dados_tabela = []
        texto_whats = f"*LISTA DE COLHEITA - {datetime.now().strftime('%d/%m')}*\n\n"
        for nome, d in soma.items():
            dados_tabela.append({"Produto": nome, "Quantidade": d['qtd'], "Unidade": d['tipo']})
            texto_whats += f"• {nome}: {d['qtd']} {d['tipo']}\n"
        
        st.table(pd.DataFrame(dados_tabela))
        msg_codificada = urllib.parse.quote(texto_whats)
        st.markdown(f'<a href="https://wa.me/?text={msg_codificada}" target="_blank" style="text-decoration: none;"><div style="background-color: #25D366; color: white; padding: 15px; text-align: center; border-radius: 10px; font-weight: bold;">📱 ENVIAR LISTA POR WHATSAPP</div></a>', unsafe_allow_html=True)

# --- ABA 3: MONTAGEM ---
with tab3:
    st.header("📦 Central de Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pendentes.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {ped['cliente']}")
            st.markdown(f"📍 **Endereço:** {ped['endereco'] if ped['endereco'] else '*Não informado*'}")
            st.divider()
            
            itens_lista = json.loads(ped['itens']); t_real = 0.0; trava_kg = False
            col_i, col_r = st.columns([2, 1])
            
            with col_i:
                for i, it in enumerate(itens_lista):
                    if it['tipo'] == "KG":
                        v_in = st.text_input(f"Valor R$ {it['nome']}:", key=f"mnt_{ped['id']}_{i}")
                        if v_in:
                            try: val = float(v_in.replace(',', '.')); it['subtotal'] = val; t_real += val
                            except: trava_kg = True
                        else: trava_kg = True
                    else:
                        st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += it['subtotal']
            
            with col_r:
                cor_pg = "green" if ped['pagamento'] == "Pago" else "red"
                st.markdown(f"Status: <b style='color:{cor_pg}'>{ped['pagamento'].upper()}</b>", unsafe_allow_html=True)
                st.markdown(f"### Total: R$ {t_real:.2f}")

            st.write("")
            b1, b2, b3, b4 = st.columns(4)
            if b1.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava_kg, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_lista)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
            with b2: disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})
            if b3.button("✏️ EDITAR", key=f"e_{ped['id']}", use_container_width=True):
                st.session_state.edit_data = ped.to_dict(); conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()
            if b4.button("🗑️ EXCLUIR", key=f"x_{ped['id']}", use_container_width=True):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()

# --- ABA 4: ESTOQUE ---
with tab4:
    st.header("🥦 Gerenciar Estoque")
    with st.expander("➕ CADASTRAR NOVO PRODUTO"):
        with st.form("add_p"):
            n = st.text_input("NOME").upper(); p = st.number_input("PREÇO", min_value=0.0); t = st.selectbox("UNIDADE", ["UN", "KG"])
            if st.form_submit_button("SALVAR PRODUTO", use_container_width=True):
                nid = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
                new_it = pd.DataFrame([{"id":nid, "nome":n, "preco":p, "tipo":t, "status":"Ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, new_it], ignore_index=True))
                st.cache_data.clear(); st.rerun()
    
    if not df_produtos.empty:
        cols = st.columns(3)
        for i, (idx, row) in enumerate(df_produtos.iterrows()):
            with cols[i % 3].container(border=True):
                st.write(f"### {row['nome']}")
                st.write(f"R$ {row['preco']} / {row['tipo']}")
                c_b1, c_b2 = st.columns(2)
                if c_b1.button("OCULTAR" if row['status'] == 'Ativo' else "ATIVAR", key=f"st_{row['id']}", use_container_width=True):
                    df_produtos.at[idx, 'status'] =
