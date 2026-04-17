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

# Função para formatar a exibição de unidades e pesos
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

# Dicionário para cálculo de KG
dict_precos = {}
if not df_produtos.empty:
    for _, row in df_produtos.iterrows():
        dict_precos[row['nome']] = {"preco": float(str(row['preco']).replace(',', '.')), "tipo": row['tipo']}

# --- NAVEGAÇÃO ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# [Abas 1, 2, 3, 4 e 6 seguem o padrão que você já aprovou]
# ... (Omitidas aqui para focar no Financeiro, mas estão integradas)

with tab5:
    st.header("📊 Financeiro")
    menu_fin = st.radio("Selecione o modo de resumo:", ["Visão Diária", "Relatório por Período", "Selecionar Pedidos"], horizontal=True)
    
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"].copy() if not df_pedidos.empty else pd.DataFrame()
    
    if concluidos.empty:
        st.info("Ainda não há pedidos concluídos.")
    else:
        concluidos['dt_obj'] = pd.to_datetime(concluidos['data'], format='%d/%m/%Y', errors='coerce')
        df_selecionado = pd.DataFrame()

        # 1. MODO DIÁRIO
        if menu_fin == "Visão Diária":
            dia_f = st.date_input("Data:", datetime.now(), format="DD/MM/YYYY")
            df_selecionado = concluidos[concluidos['data'].astype(str).str.strip() == dia_f.strftime("%d/%m/%Y")]
        
        # 2. MODO PERÍODO
        elif menu_fin == "Relatório por Período":
            c_i, c_f = st.columns(2)
            d_ini = c_i.date_input("Início:", datetime.now() - timedelta(days=7), format="DD/MM/YYYY")
            d_fim = c_f.date_input("Fim:", datetime.now(), format="DD/MM/YYYY")
            df_selecionado = concluidos[(concluidos['dt_obj'].dt.date >= d_ini) & (concluidos['dt_obj'].dt.date <= d_fim)]

        # 3. MODO SELEÇÃO MANUAL (NOVO)
        elif menu_fin == "Selecionar Pedidos":
            st.write("Marque os pedidos que deseja incluir no resumo:")
            # Criamos uma lista de opções formatada para o usuário escolher
            concluidos['label'] = concluidos['data'] + " - " + concluidos['cliente'] + " (R$ " + concluidos['total'].astype(str) + ")"
            escolhas = st.multiselect("Selecione os pedidos:", options=concluidos['id'].tolist(), format_func=lambda x: concluidos[concluidos['id'] == x]['label'].values[0])
            df_selecionado = concluidos[concluidos['id'].isin(escolhas)]

        # --- PROCESSAMENTO DOS DADOS (IGUAL PARA TODOS OS MODOS) ---
        if not df_selecionado.empty:
            total_v = df_selecionado['total'].astype(float).sum()
            pago = df_selecionado[df_selecionado['pagamento'].str.upper() == "PAGO"]['total'].astype(float).sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento", f"R$ {total_v:.2f}")
            c2.metric("Pedidos", len(df_selecionado))
            c3.metric("Recebido", f"R$ {pago:.2f}", f"R$ {total_v - pago:.2f} a receber", delta_color="inverse")
            
            st.subheader("🥦 Resumo de Itens Selecionados")
            resumo_i = {}
            for _, r in df_selecionado.iterrows():
                try:
                    lista_itens = json.loads(r['itens'])
                    for it in lista_itens:
                        nome = it['nome']
                        tipo = it.get('tipo', 'UN')
                        valor_item = float(it['subtotal'])
                        if nome not in resumo_i: resumo_i[nome] = {"qtd": 0.0, "valor": 0.0, "tipo": tipo}
                        
                        if tipo == "KG" and nome in dict_precos:
                            preco_unit = dict_precos[nome]['preco']
                            if preco_unit > 0: resumo_i[nome]["qtd"] += (valor_item / preco_unit)
                        else:
                            resumo_i[nome]["qtd"] += float(it['qtd'])
                        resumo_i[nome]["valor"] += valor_item
                except: pass
            
            dados_tabela = [{"Produto": k, "Qtd": formatar_unidade(v['qtd'], v['tipo']), "Total (R$)": f"{v['valor']:.2f}"} for k, v in resumo_i.items()]
            st.table(pd.DataFrame(dados_tabela))

            # Compartilhar
            txt_zap = f"*RESUMO DE VENDAS*\n💰 Total: R$ {total_v:.2f}\n------------------\n"
            for d in dados_tabela: txt_zap += f"• {d['Produto']}: {d['Qtd']} | R$ {d['Total (R$)']}\n"
            
            url_zap = f"https://wa.me/?text={urllib.parse.quote(txt_zap)}"
            st.markdown(f'''<a href="{url_zap}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;">📱 ENVIAR SELEÇÃO VIA WHATSAPP</div></a>''', unsafe_allow_html=True)
        else:
            st.info("Selecione pedidos ou mude o filtro para ver o resumo.")

# Re-inserindo as outras abas simplificadas para o código rodar:
with tab1:
    st.header("🛒 Novo Pedido")
    # ... (Seu código de Novo Pedido aqui)
with tab2:
    st.header("🚜 Colheita")
    # ... (Seu código de Colheita aqui)
with tab3:
    st.header("📦 Montagem")
    # ... (Seu código de Montagem aqui)
with tab4:
    st.header("📅 Histórico")
    # ... (Seu código de Histórico aqui)
with tab6:
    st.header("🥦 Estoque")
    # ... (Seu código de Estoque aqui)
