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

# --- NAVEGAÇÃO POR ABAS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "🥦 ESTOQUE"])

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
        st.markdown(f'''<a href="{url_rawbt}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:10px;text-align:center;border-radius:8px;font-weight:bold;">🖨️ REIMPRIMIR ETIQUETA</div></a>''', unsafe_allow_html=True)
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
    if pendentes.empty: st.info("Nenhum pedido pendente.")
    else:
        soma = {}
        for _, ped in pendentes.iterrows():
            its = json.loads(ped['itens'])
            for i in its:
                n = i['nome']; soma[n] = soma.get(n, 0) + i['qtd']
        dados_col = [{"Produto": k, "Qtd": v} for k, v in soma.items()]
        st.table(pd.DataFrame(dados_col))
        txt_w = urllib.parse.quote(f"*COLHEITA {datetime.now().strftime('%d/%m')}*\n" + "\n".join([f"• {k}: {v}" for k, v in soma.items()]))
        st.markdown(f'<a href="https://wa.me/?text={txt_w}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;">📱 ENVIAR LISTA WHATSAPP</div></a>', unsafe_allow_html=True)

# --- ABA 3: MONTAGEM ---
with tab3:
    st.header("📦 Central de Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pendentes.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {ped['cliente']}")
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
                    else: st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += it['subtotal']
            with col_r:
                st.write(f"Pgto: **{ped['pagamento']}**")
                st.markdown(f"### Total: R$ {t_real:.2f}")
            b1, b2 = st.columns(2)
            if b1.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava_kg, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_lista)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
            with b2: disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})

# --- ABA 4: HISTÓRICO ---
with tab4:
    st.header("📅 Histórico de Pedidos")
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"]
    if concluidos.empty:
        st.info("Nenhum pedido finalizado ainda.")
    else:
        # Ordenar por data (assumindo formato DD/MM/YYYY)
        concluidos['dt_obj'] = pd.to_datetime(concluidos['data'], format='%d/%m/%Y')
        concluidos = concluidos.sort_values(by='dt_obj', ascending=False)
        
        for data, grupo in concluidos.groupby('data', sort=False):
            st.markdown(f"#### 📅 {data}")
            for idx, ped in grupo.iterrows():
                cor_txt = "#28a745" if ped['pagamento'] == "Pago" else "#dc3545"
                with st.expander(f"👤 {ped['cliente']} | R$ {ped['total']:.2f} | {ped['pagamento'].upper()}"):
                    st.write(f"📍 **Endereço:** {ped['endereco']}")
                    itens = json.loads(ped['itens'])
                    for it in itens:
                        st.write(f"- {it['nome']}: R$ {it['subtotal']:.2f}")
                    
                    st.divider()
                    col_h1, col_h2, col_h3 = st.columns(3)
                    
                    if col_h1.button("💳 ALTERAR PGTO", key=f"pg_{ped['id']}"):
                        novo_status = "A Pagar" if ped['pagamento'] == "Pago" else "Pago"
                        df_pedidos.at[idx, 'pagamento'] = novo_status
                        conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
                    
                    with col_h2:
                        disparar_impressao_rawbt(ped)
                    
                    if col_h3.button("📝 GERAR RECIBO", key=f"rec_{ped['id']}"):
                        resumo_rec = f"*RECIBO - HORTA DA MESA*\n\nCliente: {ped['cliente']}\nData: {ped['data']}\n"
                        for it in itens: resumo_rec += f"- {it['nome']}: R$ {it['subtotal']:.2f}\n"
                        resumo_rec += f"\n*TOTAL: R$ {ped['total']:.2f}*\nStatus: {ped['pagamento'].upper()}"
                        st.code(resumo_rec) # Exibe para copiar
                        st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(resumo_rec)}" target="_blank" style="text-decoration:none;color:white;background-color:#25D366;padding:5px;border-radius:5px;">Enviar Recibo via WhatsApp 📱</a>', unsafe_allow_html=True)

# --- ABA 5: ESTOQUE ---
with tab5:
    st.header("🥦 Estoque")
    with st.expander("➕ NOVO PRODUTO"):
        with st.form("add_p"):
            n = st.text_input("NOME").upper(); p = st.number_input("PREÇO", min_value=0.0); t = st.selectbox("UNIDADE", ["UN", "KG"])
            if st.form_submit_button("SALVAR"):
                nid = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
                new_it = pd.DataFrame([{"id":nid, "nome":n, "preco":p, "tipo":t, "status":"Ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, new_it], ignore_index=True)); st.cache_data.clear(); st.rerun()
    if not df_produtos.empty:
        cols = st.columns(3)
        for i, (idx, row) in enumerate(df_produtos.iterrows()):
            with cols[i % 3].container(border=True):
                st.write(f"**{row['nome']}** - R$ {row['preco']}")
                if st.button("🗑️", key=f"del_{row['id']}", use_container_width=True):
                    conn.update(worksheet="Produtos", data=df_produtos.drop(idx)); st.cache_data.clear(); st.rerun()
