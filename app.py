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

# --- NAVEGAÇÃO ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- ABA 5: FINANCEIRO (RESTAURADA E AMPLIADA) ---
with tab5:
    st.header("📊 Financeiro")
    menu_fin = st.radio("Modo de exibição:", ["Visão Diária", "Relatório por Período", "Selecionar Pedidos"], horizontal=True)
    
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"].copy() if not df_pedidos.empty else pd.DataFrame()
    
    if not concluidos.empty:
        concluidos['dt_obj'] = pd.to_datetime(concluidos['data'], format='%d/%m/%Y', errors='coerce')
        df_atual = pd.DataFrame()
        mostrar_relatorio = False

        # --- OPÇÃO 1: DIÁRIA ---
        if menu_fin == "Visão Diária":
            dia_f = st.date_input("Data do Panorama:", datetime.now(), format="DD/MM/YYYY")
            df_atual = concluidos[concluidos['data'].astype(str).str.strip() == dia_f.strftime("%d/%m/%Y")]
            mostrar_relatorio = True
        
        # --- OPÇÃO 2: PERÍODO ---
        elif menu_fin == "Relatório por Período":
            c_i, c_f = st.columns(2)
            d_ini = c_i.date_input("Início:", datetime.now() - timedelta(days=7), format="DD/MM/YYYY")
            d_fim = c_f.date_input("Fim:", datetime.now(), format="DD/MM/YYYY")
            df_atual = concluidos[(concluidos['dt_obj'].dt.date >= d_ini) & (concluidos['dt_obj'].dt.date <= d_fim)]
            mostrar_relatorio = True

        # --- OPÇÃO 3: SELEÇÃO MANUAL (COM BOTÃO) ---
        elif menu_fin == "Selecionar Pedidos":
            st.subheader("Escolha os pedidos na lista abaixo:")
            with st.form("f_selecao_manual"):
                ids_selecionados = []
                # Filtra apenas os últimos 50 pedidos para não pesar a tela
                ultimos_pedidos = concluidos.sort_values('dt_obj', ascending=False).head(50)
                for idx, row in ultimos_pedidos.iterrows():
                    label = f"{row['data']} - {row['cliente']} (R$ {row['total']})"
                    if st.checkbox(label, key=f"chk_{row['id']}"):
                        ids_selecionados.append(row['id'])
                
                if st.form_submit_button("📊 GERAR RELATÓRIO DA SELEÇÃO"):
                    if ids_selecionados:
                        df_atual = concluidos[concluidos['id'].isin(ids_selecionados)]
                        mostrar_relatorio = True
                    else:
                        st.warning("Selecione ao menos um pedido.")

        # --- RENDERIZAÇÃO DO RELATÓRIO (PADRÃO PARA TODOS) ---
        if mostrar_relatorio and not df_atual.empty:
            st.divider()
            total_v = df_atual['total'].astype(float).sum()
            pago = df_atual[df_atual['pagamento'].str.upper() == "PAGO"]['total'].astype(float).sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento Total", f"R$ {total_v:.2f}")
            c2.metric("Qtd Pedidos", len(df_atual))
            c3.metric("Recebido", f"R$ {pago:.2f}", f"R$ {total_v - pago:.2f} faltante", delta_color="inverse")
            
            # Resumo de Itens
            resumo_i = {}
            for _, r in df_atual.iterrows():
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
            
            dados_tab = [{"Produto": k, "Qtd Total": formatar_unidade(v['qtd'], v['tipo']), "Faturamento (R$)": f"{v['valor']:.2f}"} for k, v in resumo_i.items()]
            st.table(pd.DataFrame(dados_tab))

            # WhatsApp
            txt_zap = f"*RELATÓRIO FINANCEIRO*\n💰 Total: R$ {total_v:.2f}\n------------------\n"
            for d in dados_tab:
                txt_zap += f"• {d['Produto']}: {d['Qtd Total']} | R$ {d['Faturamento (R$)']}\n"
            
            url_zap = f"https://wa.me/?text={urllib.parse.quote(txt_zap)}"
            st.markdown(f'''<a href="{url_zap}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;">📱 COMPARTILHAR NO WHATSAPP</div></a>''', unsafe_allow_html=True)
        elif mostrar_relatorio:
            st.warning("Nenhum pedido encontrado para os critérios selecionados.")
    else:
        st.info("Nenhum pedido concluído.")

# [As outras abas 1, 2, 3, 4 e 6 permanecem com o código original para manter o funcionamento completo]
