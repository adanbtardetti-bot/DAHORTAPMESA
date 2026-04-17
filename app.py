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

def formatar_unidade(valor, tipo):
    try:
        v = float(valor)
        if tipo == "KG":
            return f"{v:.3f}".replace('.', ',') + " kg"
        else:
            return str(int(v)) + " un"
    except:
        return str(valor)

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

# Dicionário de preços para KG
dict_precos = {}
if not df_produtos.empty:
    for _, row in df_produtos.iterrows():
        dict_precos[row['nome']] = {"preco": float(str(row['preco']).replace(',', '.')), "tipo": row['tipo']}

# --- FUNÇÃO DE IMPRESSÃO ---
def disparar_impressao_rawbt(ped, label="🖨️ IMPRIMIR ETIQUETA"):
    try:
        nome = limpar_nan(ped.get('cliente', '')).upper()
        total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
        comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {total}\n\n\n\n"
        b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:10px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">{label}</div></a>', unsafe_allow_html=True)
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
                    itens_sel.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * float(p['preco']))})
        if st.form_submit_button("✅ SALVAR"):
            if c and itens_sel:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_sel), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if fp else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
                st.cache_data.clear(); st.rerun()

# --- ABA 2: COLHEITA ---
with tab2:
    st.header("🚜 Colheita Total")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"] if not df_pedidos.empty else pd.DataFrame()
    if not pend.empty:
        soma = {}
        for _, p in pend.iterrows():
            for i in json.loads(p['itens']): soma[i['nome']] = soma.get(i['nome'], 0) + i['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Qtd Total": formatar_unidade(v, "UN" if "un" in k.lower() else "UN")} for k, v in soma.items()]))
    else: st.info("Sem pedidos pendentes.")

# --- ABA 3: MONTAGEM ---
with tab3:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"] if not df_pedidos.empty else pd.DataFrame()
    for idx, ped in pend.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {ped['cliente']}")
            itens_lista = json.loads(ped['itens']); t_real = 0.0; trava = False
            for i, it in enumerate(itens_lista):
                if it['tipo'] == "KG":
                    v_in = st.text_input(f"Valor R$ {it['nome']} ({it['qtd']} kg):", key=f"m_{ped['id']}_{i}")
                    if v_in:
                        val = float(v_in.replace(',', '.')); it['subtotal'] = val; t_real += val
                    else: trava = True
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += float(it['subtotal'])
            st.write(f"**Total: R$ {t_real:.2f}**")
            disparar_impressao_rawbt({"cliente":ped['cliente'], "total":t_real})
            if st.button("✅ CONCLUIR", key=f"btn_c_{ped['id']}", disabled=trava, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_lista)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()

# --- ABA 4: HISTÓRICO ---
with tab4:
    st.header("📅 Histórico")
    dia_h = st.date_input("Data:", datetime.now(), format="DD/MM/YYYY", key="hist_date")
    concl = df_pedidos[df_pedidos['status'] == "Concluído"] if not df_pedidos.empty else pd.DataFrame()
    if not concl.empty:
        filtro = concl[concl['data'] == dia_h.strftime("%d/%m/%Y")]
        for _, p in filtro.iterrows():
            with st.expander(f"{p['cliente']} - R$ {p['total']}"):
                st.write(f"Pagamento: {p['pagamento']}")
                disparar_impressao_rawbt(p, "REIMPRIMIR")

# --- ABA 5: FINANCEIRO ---
with tab5:
    st.header("📊 Financeiro")
    menu_fin = st.radio("Modo:", ["Visão Diária", "Relatório por Período", "Selecionar Pedidos"], horizontal=True)
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"].copy() if not df_pedidos.empty else pd.DataFrame()
    
    if not concluidos.empty:
        concluidos['dt_obj'] = pd.to_datetime(concluidos['data'], format='%d/%m/%Y', errors='coerce')
        df_atual = pd.DataFrame(); mostrar = False

        if menu_fin == "Visão Diária":
            dia_f = st.date_input("Ver dia:", datetime.now(), format="DD/MM/YYYY")
            df_atual = concluidos[concluidos['data'] == dia_f.strftime("%d/%m/%Y")]
            mostrar = True
        
        elif menu_fin == "Relatório por Período":
            c1, c2 = st.columns(2)
            d1 = c1.date_input("De:", datetime.now() - timedelta(days=7))
            d2 = c2.date_input("Até:", datetime.now())
            df_atual = concluidos[(concluidos['dt_obj'].dt.date >= d1) & (concluidos['dt_obj'].dt.date <= d2)]
            mostrar = True

        elif menu_fin == "Selecionar Pedidos":
            dia_sel = st.date_input("Puxar pedidos do dia:", datetime.now(), format="DD/MM/YYYY")
            pedidos_dia = concluidos[concluidos['data'] == dia_sel.strftime("%d/%m/%Y")]
            if not pedidos_dia.empty:
                with st.form("f_sel"):
                    selecionados = []
                    for _, r in pedidos_dia.iterrows():
                        if st.checkbox(f"{r['cliente']} (R$ {r['total']})", key=f"s_{r['id']}"): selecionados.append(r['id'])
                    if st.form_submit_button("📊 GERAR RELATÓRIO DA SELEÇÃO"):
                        df_atual = pedidos_dia[pedidos_dia['id'].isin(selecionados)]
                        mostrar = True
            else: st.warning("Nenhum pedido concluído neste dia.")

        if mostrar and not df_atual.empty:
            t_v = df_atual['total'].astype(float).sum()
            st.divider()
            st.metric("Faturamento", f"R$ {t_v:.2f}")
            res_i = {}
            for _, r in df_atual.iterrows():
                for it in json.loads(r['itens']):
                    n = it['nome']; tipo = it.get('tipo', 'UN'); val = float(it['subtotal'])
                    if n not in res_i: res_i[n] = {"qtd": 0.0, "v": 0.0, "t": tipo}
                    if tipo == "KG" and n in dict_precos:
                        p_u = dict_precos[n]['preco']
                        if p_u > 0: res_i[n]["qtd"] += (val / p_u)
                    else: res_i[n]["qtd"] += float(it['qtd'])
                    res_i[n]["v"] += val
            
            dados = [{"Produto": k, "Qtd": formatar_unidade(v['qtd'], v['t']), "Total (R$)": f"{v['v']:.2f}"} for k, v in res_i.items()]
            st.table(pd.DataFrame(dados))
            txt = f"*FINANCEIRO*\nTotal: R$ {t_v:.2f}\n" + "\n".join([f"• {d['Produto']}: {d['Qtd']}" for d in dados])
            st.markdown(f'''<a href="https://wa.me/?text={urllib.parse.quote(txt)}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;">📱 WHATSAPP</div></a>''', unsafe_allow_html=True)

# --- ABA 6: ESTOQUE ---
with tab6:
    st.header("🥦 Estoque")
    with st.expander("➕ NOVO PRODUTO"):
        with st.form("add"):
            n = st.text_input("Nome").upper()
            p = st.text_input("Preço")
            t = st.selectbox("Tipo", ["UN", "KG"])
            if st.form_submit_button("SALVAR"):
                prox = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
                new = pd.DataFrame([{"id": prox, "nome": n, "preco": p, "tipo": t, "status": "Ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, new])); st.rerun()
    if not df_produtos.empty:
        for idx, r in df_produtos.iterrows():
            c1, c2 = st.columns([4,1])
            c1.write(f"**{r['nome']}** - R$ {r['preco']} ({r['tipo']})")
            if c2.button("🗑️", key=f"d_{r['id']}"):
                conn.update(worksheet="Produtos", data=df_produtos.drop(idx)); st.rerun()
