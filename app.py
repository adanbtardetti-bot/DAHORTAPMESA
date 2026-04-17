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

# Carga inicial
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

colunas_pedidos = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"]
for col in colunas_pedidos:
    if col not in df_pedidos.columns:
        df_pedidos[col] = ""

# --- FUNÇÃO DE IMPRESSÃO ---
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

# --- ABA 1: NOVO ---
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
                    itens_sel.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * float(p['preco']))})
        if st.form_submit_button("✅ SALVAR"):
            if c and itens_sel:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty and pd.to_numeric(df_pedidos['id'], errors='coerce').notnull().any() else 1
                data_br = datetime.now().strftime("%d/%m/%Y")
                novo = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_sel), "status": "Pendente", "data": data_br, "total": 0.0, "pagamento": "Pago" if fp else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True)); st.cache_data.clear(); st.rerun()

# --- ABA 2: COLHEITA ---
with tab2:
    st.header("🚜 Colheita")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"] if not df_pedidos.empty else pd.DataFrame()
    if not pend.empty:
        soma = {}
        for _, p in pend.iterrows():
            try:
                for i in json.loads(p['itens']): soma[i['nome']] = soma.get(i['nome'], 0) + i['qtd']
            except: pass
        st.table(pd.DataFrame([{"Produto": k, "Qtd": v} for k, v in soma.items()]))

# --- ABA 3: MONTAGEM ---
with tab3:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"] if not df_pedidos.empty else pd.DataFrame()
    for idx, ped in pend.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {limpar_nan(ped['cliente'])}")
            try:
                itens_lista = json.loads(ped['itens']); t_real = 0.0; trava = False
                for i, it in enumerate(itens_lista):
                    if it['tipo'] == "KG":
                        v_in = st.text_input(f"Valor R$ {it['nome']}:", key=f"m_{ped['id']}_{i}")
                        if v_in:
                            val = float(v_in.replace(',', '.')); it['subtotal'] = val; t_real += val
                        else: trava = True
                    else:
                        st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += float(it['subtotal'])
                st.write(f"**Total: R$ {t_real:.2f}**")
                disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})
                if st.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava, use_container_width=True):
                    df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_lista)
                    conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
            except: pass

# --- ABA 4: HISTÓRICO ---
with tab4:
    st.header("📅 Histórico")
    dia_busca = st.date_input("Filtrar por data:", datetime.now(), format="DD/MM/YYYY")
    dia_str = dia_busca.strftime("%d/%m/%Y")
    concl = df_pedidos[df_pedidos['status'] == "Concluído"] if not df_pedidos.empty else pd.DataFrame()
    if not concl.empty:
        filtro = concl[concl['data'].astype(str).str.strip() == dia_str]
        for idx, ped in filtro.iterrows():
            cliente_nome = limpar_nan(ped['cliente'])
            with st.expander(f"👤 {cliente_nome} - R$ {ped['total']}"):
                st.write(f"📍 Endereço: {limpar_nan(ped['endereco'])}")
                lista_itens = json.loads(ped['itens'])
                txt_recibo = f"*DA HORTA PRA MESA - RECIBO*\n\n*Data:* {dia_str}\n*Cliente:* {cliente_nome}\n"
                for it in lista_itens:
                    st.write(f"- {it['nome']}: R$ {float(it['subtotal']):.2f}")
                    txt_recibo += f"• {it['nome']}: R$ {float(it['subtotal']):.2f}\n"
                txt_recibo += f"\n*TOTAL: R$ {float(ped['total']):.2f}*\n*Status:* {limpar_nan(ped['pagamento']).upper()}"
                st.divider()
                disparar_impressao_rawbt(ped, "REIMPRIMIR ETIQUETA")
                url_zap = f"https://wa.me/?text={urllib.parse.quote(txt_recibo)}"
                st.markdown(f'''<a href="{url_zap}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">📱 ENVIAR RECIBO WHATSAPP</div></a>''', unsafe_allow_html=True)
                if st.button("💳 ALTERAR STATUS PAGAMENTO", key=f"alt_{ped['id']}", use_container_width=True):
                    df_pedidos.at[idx, 'pagamento'] = "A Pagar" if ped['pagamento'].upper() == "PAGO" else "Pago"
                    conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()

# --- ABA 5: FINANCEIRO (RESTAURADO COMPLETO) ---
with tab5:
    st.header("📊 Financeiro")
    tipo_view = st.radio("Selecione:", ["Visão Diária", "Relatório por Período"], horizontal=True)
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"].copy() if not df_pedidos.empty else pd.DataFrame()
    
    if not concluidos.empty:
        concluidos['dt_obj'] = pd.to_datetime(concluidos['data'], format='%d/%m/%Y', errors='coerce')
        if tipo_view == "Visão Diária":
            dia_f = st.date_input("Data do Panorama:", datetime.now(), format="DD/MM/YYYY")
            dia_f_str = dia_f.strftime("%d/%m/%Y")
            df_dia = concluidos[concluidos['data'].astype(str).str.strip() == dia_f_str]
            if not df_dia.empty:
                c1, c2, c3 = st.columns(3)
                total_v = df_dia['total'].astype(float).sum()
                pago = df_dia[df_dia['pagamento'].str.upper() == "PAGO"]['total'].astype(float).sum()
                c1.metric("Faturamento", f"R$ {total_v:.2f}")
                c2.metric("Pedidos", len(df_dia))
                c3.metric("Recebido", f"R$ {pago:.2f}", f"R$ {total_v - pago:.2f} faltante")
                
                st.subheader("Produtos Vendidos no Dia")
                resumo_i = {}
                for _, r in df_dia.iterrows():
                    for it in json.loads(r['itens']): resumo_i[it['nome']] = resumo_i.get(it['nome'], 0) + it['qtd']
                st.table(pd.DataFrame([{"Produto": k, "Qtd": v} for k, v in resumo_i.items()]))
        else:
            c_i, c_f = st.columns(2)
            d_ini = c_i.date_input("De:", datetime.now() - timedelta(days=7), format="DD/MM/YYYY")
            d_fim = c_f.date_input("Até:", datetime.now(), format="DD/MM/YYYY")
            df_per = concluidos[(concluidos['dt_obj'].dt.date >= d_ini) & (concluidos['dt_obj'].dt.date <= d_fim)]
            if not df_per.empty:
                st.metric("Total no Período", f"R$ {df_per['total'].astype(float).sum():.2f}")
                fat_diario = df_per.groupby('data')['total'].sum().reset_index()
                st.line_chart(fat_diario.set_index('data'))
                st.dataframe(df_per[['data', 'cliente', 'total', 'pagamento']], use_container_width=True)

# --- ABA 6: ESTOQUE ---
with tab6:
    st.header("🥦 Estoque")
    if not df_produtos.empty:
        for idx, row in df_produtos.iterrows():
            c1, c2 = st.columns([4,1])
            c1.write(f"**{row['nome']}** - R$ {row['preco']} ({row['tipo']})")
            if c2.button("🗑️", key=f"del_{row['id']}"):
                conn.update(worksheet="Produtos", data=df_produtos.drop(idx)); st.cache_data.clear(); st.rerun()
