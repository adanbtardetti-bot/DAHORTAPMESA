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

# --- NAVEGAÇÃO ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- ABAS 1 A 4 (MANTIDAS) ---
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
                data_br = datetime.now().strftime("%d/%m/%Y")
                novo = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_sel), "status": "Pendente", "data": data_br, "total": 0.0, "pagamento": "Pago" if fp else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True)); st.cache_data.clear(); st.rerun()

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
                if st.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava, use_container_width=True):
                    df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_lista)
                    conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
            except: pass

with tab4:
    st.header("📅 Histórico")
    dia_busca = st.date_input("Filtrar por data:", datetime.now(), format="DD/MM/YYYY")
    dia_str = dia_busca.strftime("%d/%m/%Y")
    concl = df_pedidos[df_pedidos['status'] == "Concluído"] if not df_pedidos.empty else pd.DataFrame()
    if not concl.empty:
        filtro = concl[concl['data'].astype(str).str.strip() == dia_str]
        for _, ped in filtro.iterrows():
            with st.expander(f"👤 {ped['cliente']} - R$ {ped['total']}"):
                st.write(f"Endereço: {ped['endereco']}")
                st.write(f"Status: {ped['pagamento']}")

# --- ABA 5: FINANCEIRO (ATUALIZADA COM VALOR POR ITEM) ---
with tab5:
    st.header("📊 Financeiro")
    tipo_view = st.radio("Selecione:", ["Visão Diária", "Relatório por Período"], horizontal=True)
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"].copy() if not df_pedidos.empty else pd.DataFrame()
    
    if not concluidos.empty:
        concluidos['dt_obj'] = pd.to_datetime(concluidos['data'], format='%d/%m/%Y', errors='coerce')
        
        if tipo_view == "Visão Diária":
            dia_f = st.date_input("Data do Panorama:", datetime.now(), format="DD/MM/YYYY")
            dia_f_str = dia_f.strftime("%d/%m/%Y")
            df_atual = concluidos[concluidos['data'].astype(str).str.strip() == dia_f_str]
            titulo_rel = f"RELATÓRIO DIÁRIO - {dia_f_str}"
        else:
            c_i, c_f = st.columns(2)
            d_ini = c_i.date_input("Data Inicial:", datetime.now() - timedelta(days=7), format="DD/MM/YYYY")
            d_fim = c_f.date_input("Data Final:", datetime.now(), format="DD/MM/YYYY")
            df_atual = concluidos[(concluidos['dt_obj'].dt.date >= d_ini) & (concluidos['dt_obj'].dt.date <= d_fim)]
            titulo_rel = f"RELATÓRIO PERÍODO: {d_ini.strftime('%d/%m/%Y')} até {d_fim.strftime('%d/%m/%Y')}"

        if not df_atual.empty:
            total_v = df_atual['total'].astype(float).sum()
            pago = df_atual[df_atual['pagamento'].str.upper() == "PAGO"]['total'].astype(float).sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento Total", f"R$ {total_v:.2f}")
            c2.metric("Qtd Pedidos", len(df_atual))
            c3.metric("Total Recebido", f"R$ {pago:.2f}", f"R$ {total_v - pago:.2f} a receber", delta_color="inverse")
            
            # Lógica para somar Qtd e Valores de cada Item
            st.subheader("🥦 Resumo de Itens Vendidos (Qtd e Valor)")
            resumo_i = {} # Formato: {"Nome": {"qtd": 0, "valor": 0}}
            
            for _, r in df_atual.iterrows():
                try:
                    lista_itens = json.loads(r['itens'])
                    for it in lista_itens:
                        nome = it['nome']
                        qtd = float(it['qtd'])
                        sub = float(it['subtotal'])
                        
                        if nome not in resumo_i:
                            resumo_i[nome] = {"qtd": 0.0, "valor": 0.0}
                        
                        resumo_i[nome]["qtd"] += qtd
                        resumo_i[nome]["valor"] += sub
                except: pass
            
            # Criando DataFrame para a tabela
            dados_tabela = []
            for nome, valores in resumo_i.items():
                dados_tabela.append({
                    "Produto": nome,
                    "Qtd Total": valores["qtd"],
                    "Faturamento (R$)": f"{valores['valor']:.2f}"
                })
            
            df_resumo_final = pd.DataFrame(dados_tabela)
            st.table(df_resumo_final)

            # Botão para Gerar Relatório de Texto
            st.divider()
            txt_share = f"*{titulo_rel}*\n\n"
            txt_share += f"💰 Faturamento: R$ {total_v:.2f}\n"
            txt_share += f"📦 Total Pedidos: {len(df_atual)}\n"
            txt_share += f"✅ Total Recebido: R$ {pago:.2f}\n"
            txt_share += f"----------------------------\n"
            txt_share += "*RESUMO POR ITEM:*\n"
            for _, row in df_resumo_final.iterrows():
                txt_share += f"• {row['Produto']}: {row['Qtd Total']} | R$ {row['Faturamento (R$)']}\n"
            
            st.subheader("📱 Compartilhar Relatório")
            st.text_area("Copie o texto abaixo:", txt_share, height=200)
            url_zap_rel = f"https://wa.me/?text={urllib.parse.quote(txt_share)}"
            st.markdown(f'''<a href="{url_zap_rel}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;">📱 ENVIAR RELATÓRIO NO WHATSAPP</div></a>''', unsafe_allow_html=True)
        else:
            st.warning("Nenhum dado encontrado para este critério.")

# --- ABA 6: ESTOQUE (MANTIDA) ---
with tab6:
    st.header("🥦 Estoque")
    if not df_produtos.empty:
        for idx, row in df_produtos.iterrows():
            c1, c2 = st.columns([4,1])
            c1.write(f"**{row['nome']}** - R$ {row['preco']} ({row['tipo']})")
            if c2.button("🗑️", key=f"del_{row['id']}"):
                conn.update(worksheet="Produtos", data=df_produtos.drop(idx)); st.cache_data.clear(); st.rerun()
