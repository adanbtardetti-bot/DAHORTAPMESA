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

def limpar_nan(texto):
    t = str(texto).replace('nan', '').replace('NaN', '').strip()
    return t if t else ""

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

tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "🥦 ESTOQUE"])

# --- FUNÇÃO DE IMPRESSÃO SEM NAN ---
def disparar_impressao_rawbt(ped, label="IMPRIMIR ETIQUETA"):
    try:
        nome = limpar_nan(ped.get('cliente')).upper()
        endereco = limpar_nan(ped.get('endereco')).upper()
        pgto = limpar_nan(ped.get('pagamento')).upper()
        valor_total = ped.get('total', 0)
        valor_fmt = f"{float(valor_total):.2f}".replace('.', ',')
        
        comandos = "\x1b\x61\x01" 
        if nome: comandos += "\x1b\x21\x38" + nome + "\n"
        if endereco: comandos += "\x1b\x21\x38" + endereco + "\n"
        comandos += "\x1b\x21\x00" + "----------------\n"
        comandos += "TOTAL: RS " + valor_fmt + "\n"
        if pgto == "PAGO": comandos += "PAGO\n"
        comandos += "\n\n\n\n"
        
        b64_texto = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url_rawbt = f"intent:base64,{b64_texto}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'''<a href="{url_rawbt}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">🖨️ {label}</div></a>''', unsafe_allow_html=True)
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
        if not df_produtos.empty:
            p_ativos = df_produtos[df_produtos['status'] == 'Ativo']
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
    if not df_pedidos.empty:
        pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
        if pendentes.empty: st.info("Nenhum pedido pendente.")
        else:
            soma = {}
            for _, ped in pendentes.iterrows():
                try:
                    its = json.loads(ped['itens'])
                    for i in its:
                        n = i['nome']; soma[n] = soma.get(n, 0) + i['qtd']
                except: pass
            st.table(pd.DataFrame([{"Produto": k, "Qtd": v} for k, v in soma.items()]))
            txt_w = urllib.parse.quote(f"*COLHEITA {datetime.now().strftime('%d/%m')}*\n" + "\n".join([f"• {k}: {v}" for k, v in soma.items()]))
            st.markdown(f'<a href="https://wa.me/?text={txt_w}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;">📱 ENVIAR LISTA WHATSAPP</div></a>', unsafe_allow_html=True)

# --- ABA 3: MONTAGEM ---
with tab3:
    st.header("📦 Central de Montagem")
    if not df_pedidos.empty:
        pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
        for idx, ped in pendentes.iterrows():
            with st.container(border=True):
                st.subheader(f"👤 {limpar_nan(ped['cliente'])}")
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
                disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})
                if st.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava_kg, use_container_width=True):
                    df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_lista)
                    conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()

# --- ABA 4: HISTÓRICO COM RECIBO VISUAL ---
with tab4:
    st.header("📅 Histórico")
    if not df_pedidos.empty:
        concluidos = df_pedidos[df_pedidos['status'] == "Concluído"].copy()
        if concluidos.empty: st.info("Nenhum pedido concluído.")
        else:
            concluidos['data'] = concluidos['data'].fillna(datetime.now().strftime("%d/%m/%Y"))
            for data, grupo in concluidos.groupby('data', sort=False):
                st.markdown(f"#### 📅 {data}")
                for idx, ped in grupo.iterrows():
                    nome_c = limpar_nan(ped['cliente'])
                    valor_c = float(ped['total'])
                    with st.expander(f"👤 {nome_c} - R$ {valor_c:.2f}"):
                        # --- MINI RECIBO VISUAL ---
                        st.markdown(f"""
                        <div style="border: 2px dashed #ccc; padding: 20px; background-color: #fff; color: #333; font-family: 'Courier New', Courier, monospace; border-radius: 5px;">
                            <center><h3 style="margin:0;">HORTA DA MESA</h3><p style="margin:0;">Recibo de Venda</p></center>
                            <hr>
                            <b>CLIENTE:</b> {nome_c}<br>
                            <b>ENDEREÇO:</b> {limpar_nan(ped['endereco'])}<br>
                            <b>DATA:</b> {ped['data']}<br>
                            <hr>
                            <table style="width:100%">
                        """, unsafe_allow_html=True)
                        itens = json.loads(ped['itens'])
                        recibo_txt = f"*HORTA DA MESA - RECIBO*\n\n*Cliente:* {nome_c}\n"
                        for it in itens:
                            st.markdown(f"<tr><td>{it['nome']}</td><td style='text-align:right'>R$ {float(it['subtotal']):.2f}</td></tr>", unsafe_allow_html=True)
                            recibo_txt += f"• {it['nome']}: R$ {float(it['subtotal']):.2f}\n"
                        st.markdown(f"""
                            </table>
                            <hr>
                            <h3 style="text-align:right; margin:0;">TOTAL: R$ {valor_c:.2f}</h3>
                            <p style="text-align:center; margin-top:10px;"><b>STATUS: {ped['pagamento'].upper()}</b></p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.write("")
                        disparar_impressao_rawbt(ped, "REIMPRIMIR ETIQUETA")
                        c1, c2 = st.columns(2)
                        if c1.button("💳 ALTERAR PGTO", key=f"pg_{ped['id']}", use_container_width=True):
                            df_pedidos.at[idx, 'pagamento'] = "A Pagar" if ped['pagamento'] == "Pago" else "Pago"
                            conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
                        
                        recibo_txt += f"\n*TOTAL: R$ {valor_c:.2f}*\n*Status:* {ped['pagamento'].upper()}"
                        if c2.button("📱 ENVIAR WHATSAPP", key=f"rec_{ped['id']}", use_container_width=True):
                            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(recibo_txt)}" target="_blank">Clique para abrir WhatsApp</a>', unsafe_allow_html=True)

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
