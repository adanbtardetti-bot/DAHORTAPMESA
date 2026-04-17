import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime, timedelta

# Configuração da Página
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def limpar_nan(texto):
    if pd.isna(texto): return ""
    t = str(texto).replace('nan', '').replace('NaN', '').strip()
    return t

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        if df is None: return pd.DataFrame()
        df = df.dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame()

# Carga inicial de dados
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Garantir que as colunas existam
colunas_pedidos = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"]
for col in colunas_pedidos:
    if col not in df_pedidos.columns:
        df_pedidos[col] = ""

# --- FUNÇÃO DE IMPRESSÃO (RAWBT) ---
def disparar_impressao_rawbt(ped, label="IMPRIMIR ETIQUETA"):
    try:
        nome = limpar_nan(ped.get('cliente', '')).upper()
        endereco = limpar_nan(ped.get('endereco', '')).upper()
        pgto = limpar_nan(ped.get('pagamento', '')).upper()
        try: v_num = float(str(ped.get('total', 0)).replace(',', '.'))
        except: v_num = 0.0
        valor_fmt = f"{v_num:.2f}".replace('.', ',')
        
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
    except: pass

# --- NAVEGAÇÃO ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- ABA 1: NOVO PEDIDO ---
with tab1:
    st.header("🛒 Novo Pedido")
    with st.form("f_venda", clear_on_submit=True):
        c1, c2 = st.columns(2)
        c = c1.text_input("CLIENTE").upper()
        e = c2.text_input("ENDEREÇO").upper()
        fp = st.checkbox("PAGO")
        itens_sel = []
        if not df_produtos.empty:
            for _, p in df_produtos[df_produtos['status'] == 'Ativo'].iterrows():
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"n_{p['id']}")
                if qtd > 0:
                    itens_sel.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "preco_ref": p['preco'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * float(p['preco']))})
        if st.form_submit_button("✅ SALVAR PEDIDO"):
            if c and itens_sel:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty and pd.to_numeric(df_pedidos['id'], errors='coerce').notnull().any() else 1
                data_br = datetime.now().strftime("%d/%m/%Y")
                novo = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_sel), "status": "Pendente", "data": data_br, "total": 0.0, "pagamento": "Pago" if fp else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
                st.cache_data.clear()
                st.rerun()

# --- ABA 2: COLHEITA ---
with tab2:
    st.header("🚜 Colheita Total")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"] if not df_pedidos.empty else pd.DataFrame()
    if not pendentes.empty:
        soma_colheita = {}
        for _, p in pendentes.iterrows():
            try:
                itens = json.loads(p['itens'])
                for i in itens:
                    soma_colheita[i['nome']] = soma_colheita.get(i['nome'], 0) + i['qtd']
            except: pass
        df_colheita = pd.DataFrame([{"Produto": k, "Qtd Total": v} for k, v in soma_colheita.items()])
        st.table(df_colheita)
    else:
        st.info("Nenhum pedido pendente para colheita.")

# --- ABA 3: MONTAGEM ---
with tab3:
    st.header("📦 Montagem de Pedidos")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"] if not df_pedidos.empty else pd.DataFrame()
    for idx, ped in pendentes.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {limpar_nan(ped['cliente'])}")
            try:
                itens_lista = json.loads(ped['itens'])
                t_real = 0.0
                trava_concluir = False
                
                for i, it in enumerate(itens_lista):
                    if it['tipo'] == "KG":
                        v_in = st.text_input(f"Valor R$ {it['nome']} ({it['qtd']} kg):", key=f"mont_{ped['id']}_{i}")
                        if v_in:
                            val = float(v_in.replace(',', '.'))
                            itens_lista[i]['subtotal'] = val
                            t_real += val
                        else:
                            trava_concluir = True
                    else:
                        st.write(f"✅ {it['nome']} - {it['qtd']} UN (R$ {it['subtotal']:.2f})")
                        t_real += float(it['subtotal'])
                
                st.write(f"**Total do Pedido: R$ {t_real:.2f}**")
                
                disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})
                
                if st.button("✅ CONCLUIR", key=f"btn_concluir_{ped['id']}", disabled=trava_concluir, use_container_width=True):
                    df_pedidos.at[idx, 'status'] = "Concluído"
                    df_pedidos.at[idx, 'total'] = t_real
                    df_pedidos.at[idx, 'itens'] = json.dumps(itens_lista)
                    conn.update(worksheet="Pedidos", data=df_pedidos)
                    st.cache_data.clear()
                    st.rerun()
            except: pass

# --- ABA 4: HISTÓRICO ---
with tab4:
    st.header("📅 Histórico")
    dia_busca = st.date_input("Ver pedidos do dia:", datetime.now(), format="DD/MM/YYYY")
    dia_str = dia_busca.strftime("%d/%m/%Y")
    
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"] if not df_pedidos.empty else pd.DataFrame()
    if not concluidos.empty:
        filtro = concluidos[concluidos['data'].astype(str).str.strip() == dia_str]
        if filtro.empty:
            st.warning("Nenhum pedido concluído nesta data.")
        else:
            for idx, ped in filtro.iterrows():
                with st.expander(f"👤 {ped['cliente']} - R$ {ped['total']}"):
                    st.write(f"Pagamento: {ped['pagamento']}")
                    disparar_impressao_rawbt(ped, "REIMPRIMIR")
                    # Zap Direto
                    txt_zap = f"*DA HORTA PRA MESA*\nCliente: {ped['cliente']}\nTotal: R$ {ped['total']}"
                    url_zap = f"https://wa.me/?text={urllib.parse.quote(txt_zap)}"
                    st.markdown(f'''<a href="{url_zap}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:10px;text-align:center;border-radius:8px;font-weight:bold;">📱 WHATSAPP</div></a>''', unsafe_allow_html=True)

# --- ABA 5: FINANCEIRO ---
with tab5:
    st.header("📊 Financeiro")
    menu_fin = st.radio("Tipo:", ["Diário", "Período"], horizontal=True)
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"].copy() if not df_pedidos.empty else pd.DataFrame()
    
    if not concluidos.empty:
        concluidos['dt_obj'] = pd.to_datetime(concluidos['data'], format='%d/%m/%Y', errors='coerce')
        if menu_fin == "Diário":
            dia_f = st.date_input("Data:", datetime.now(), format="DD/MM/YYYY").strftime("%d/%m/%Y")
            df_dia = concluidos[concluidos['data'] == dia_f]
            if not df_dia.empty:
                v_total = df_dia['total'].astype(float).sum()
                st.metric("Faturamento do Dia", f"R$ {v_total:.2f}")
                st.dataframe(df_dia[['cliente', 'total', 'pagamento']])
        else:
            d1 = st.date_input("Início:", datetime.now() - timedelta(days=7))
            d2 = st.date_input("Fim:", datetime.now())
            df_per = concluidos[(concluidos['dt_obj'].dt.date >= d1) & (concluidos['dt_obj'].dt.date <= d2)]
            st.metric("Total no Período", f"R$ {df_per['total'].astype(float).sum():.2f}")
            st.dataframe(df_per[['data', 'cliente', 'total']])

# --- ABA 6: ESTOQUE ---
with tab6:
    st.header("🥦 Gerenciar Produtos")
    with st.expander("➕ CADASTRAR NOVO PRODUTO"):
        with st.form("add_prod"):
            n = st.text_input("Nome").upper()
            p = st.text_input("Preço (ex: 5.50)")
            t = st.selectbox("Tipo", ["UN", "KG"])
            if st.form_submit_button("SALVAR"):
                prox_p = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
                novo_p = pd.DataFrame([{"id": prox_p, "nome": n, "preco": p, "tipo": t, "status": "Ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, novo_p]))
                st.rerun()
    
    if not df_produtos.empty:
        for idx, row in df_produtos.iterrows():
            c1, c2 = st.columns([4,1])
            c1.write(f"**{row['nome']}** - R$ {row['preco']} ({row['tipo']})")
            if c2.button("🗑️", key=f"del_p_{row['id']}"):
                df_produtos.drop(idx, inplace=True)
                conn.update(worksheet="Produtos", data=df_produtos)
                st.rerun()
