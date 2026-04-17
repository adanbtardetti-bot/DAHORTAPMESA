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
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])
tab1, tab2, tab3, tab4, tab5, tab6 = tabs

# --- FUNÇÃO DE IMPRESSÃO ---
def disparar_impressao_rawbt(ped, label="IMPRIMIR ETIQUETA"):
    try:
        nome = limpar_nan(ped.get('cliente', '')).upper()
        v_num = float(str(ped.get('total', 0)).replace(',', '.'))
        valor_fmt = f"{v_num:.2f}".replace('.', ',')
        comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {valor_fmt}\n\n\n\n"
        b64_texto = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url_rawbt = f"intent:base64,{b64_texto}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'''<a href="{url_rawbt}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:10px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">🖨️ {label}</div></a>''', unsafe_allow_html=True)
    except: pass

# --- ABAS ANTERIORES (RESUMIDAS PARA O CÓDIGO NÃO FICAR GIGANTE) ---
with tab1:
    st.header("🛒 Novo Pedido")
    with st.form("f_venda", clear_on_submit=True):
        c = st.text_input("CLIENTE").upper()
        e = st.text_input("ENDEREÇO").upper()
        itens_sel = []
        if not df_produtos.empty:
            for _, p in df_produtos[df_produtos['status'] == 'Ativo'].iterrows():
                qtd = st.number_input(f"{p['nome']}", min_value=0, key=f"n_{p['id']}")
                if qtd > 0:
                    itens_sel.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * float(p['preco']))})
        if st.form_submit_button("✅ SALVAR"):
            if c and itens_sel:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_sel), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True)); st.cache_data.clear(); st.rerun()

with tab2:
    st.header("🚜 Colheita")
    # Lógica de colheita... (mantida a anterior)

with tab3:
    st.header("📦 Montagem")
    # Lógica de montagem... (mantida a anterior)

with tab4:
    st.header("📅 Histórico")
    dia_busca = st.date_input("Filtrar Histórico:", datetime.now(), format="DD/MM/YYYY")
    dia_str = dia_busca.strftime("%d/%m/%Y")
    concl = df_pedidos[df_pedidos['status'] == "Concluído"] if not df_pedidos.empty else pd.DataFrame()
    if not concl.empty:
        filtro = concl[concl['data'].astype(str).str.strip() == dia_str]
        for idx, ped in filtro.iterrows():
            with st.expander(f"👤 {ped['cliente']} - R$ {ped['total']}"):
                disparar_impressao_rawbt(ped)

# --- ABA 5: FINANCEIRO (NOVA) ---
with tab5:
    st.header("📊 Financeiro e Relatórios")
    
    tipo_relatorio = st.radio("Selecione o tipo de visão:", ["Visão Diária", "Relatório por Período"], horizontal=True)
    
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"].copy() if not df_pedidos.empty else pd.DataFrame()
    
    if concluidos.empty:
        st.info("Ainda não existem pedidos concluídos para gerar financeiro.")
    else:
        # Converter data para formato datetime para facilitar filtros
        concluidos['dt_obj'] = pd.to_datetime(concluidos['data'], format='%d/%m/%Y', errors='coerce')
        
        if tipo_relatorio == "Visão Diária":
            dia_fin = st.date_input("Selecione o dia para o panorama:", datetime.now(), format="DD/MM/YYYY")
            dia_fin_str = dia_fin.strftime("%d/%m/%Y")
            dados_dia = concluidos[concluidos['data'].astype(str).str.strip() == dia_fin_str]
            
            if dados_dia.empty:
                st.warning(f"Nenhum dado financeiro para o dia {dia_fin_str}")
            else:
                col1, col2, col3 = st.columns(3)
                total_vendas = dados_dia['total'].astype(float).sum()
                qtd_pedidos = len(dados_dia)
                pago = dados_dia[dados_dia['pagamento'].str.upper() == "PAGO"]['total'].astype(float).sum()
                a_receber = total_vendas - pago
                
                col1.metric("Faturamento Total", f"R$ {total_vendas:.2f}")
                col2.metric("Pedidos Concluídos", qtd_pedidos)
                col3.metric("Total Pago", f"R$ {pago:.2f}", delta=f"R$ {a_receber:.2f} a receber", delta_color="inverse")
                
                st.subheader("Resumo de Produtos Vendidos no Dia")
                resumo_itens = {}
                for _, p in dados_dia.iterrows():
                    for it in json.loads(p['itens']):
                        resumo_itens[it['nome']] = resumo_itens.get(it['nome'], 0) + it['qtd']
                
                df_resumo = pd.DataFrame([{"Produto": k, "Quantidade": v} for k, v in resumo_itens.items()])
                st.table(df_resumo)

        else:
            st.subheader("Relatório por Período")
            c_ini, c_fim = st.columns(2)
            d_inicio = c_ini.date_input("Data Início", datetime.now() - timedelta(days=7), format="DD/MM/YYYY")
            d_fim = c_fim.date_input("Data Fim", datetime.now(), format="DD/MM/YYYY")
            
            filtro_periodo = concluidos[(concluidos['dt_obj'].dt.date >= d_inicio) & (concluidos['dt_obj'].dt.date <= d_fim)]
            
            if filtro_periodo.empty:
                st.warning("Nenhum pedido encontrado neste período.")
            else:
                total_periodo = filtro_periodo['total'].astype(float).sum()
                st.markdown(f"### 💰 Total no Período: **R$ {total_periodo:.2f}**")
                
                # Agrupar por dia para ver evolução
                faturamento_diario = filtro_periodo.groupby('data')['total'].sum().reset_index()
                st.line_chart(faturamento_diario.set_index('data'))
                
                st.subheader("Lista Detalhada do Período")
                st.dataframe(filtro_periodo[['data', 'cliente', 'total', 'pagamento']], use_container_width=True)
                
                # Botão para gerar texto de relatório (copiar)
                texto_relatorio = f"RELATÓRIO DE VENDAS ({d_inicio.strftime('%d/%m/%Y')} - {d_fim.strftime('%d/%m/%Y')})\n"
                texto_relatorio += f"TOTAL VENDIDO: R$ {total_periodo:.2f}\n"
                texto_relatorio += f"TOTAL PEDIDOS: {len(filtro_periodo)}"
                
                st.text_area("Relatório pronto para copiar:", texto_relatorio)

with tab6:
    st.header("🥦 Estoque")
    # Lógica de estoque... (mantida a anterior)
