import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
import unicodedata
import pytz
from datetime import datetime, timedelta
from pathlib import Path

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Horta Gestão", page_icon="🥬", layout="wide")
fuso_br = pytz.timezone('America/Sao_Paulo')

def aplicar_estilos():
    css_path = Path(__file__).with_name("styles.css")
    try:
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except OSError:
        pass

aplicar_estilos()

conn = st.connection("gsheets", type=GSheetsConnection)
STATUS_PRONTO = "pronto"
STATUS_PENDENTE = "pendente"
PAGAMENTO_PAGO = "PAGO"
PAGAMENTO_A_PAGAR = "A PAGAR"

# --- FUNÇÕES DE APOIO ---
def limpar_texto(texto):
    if not texto: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texto))
                   if unicodedata.category(c) != 'Mn')

def parse_float(val):
    try: return float(str(val).strip().replace(",", "."))
    except: return 0.0

def ler_aba(aba, ttl=30):
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty: return pd.DataFrame()
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    conn.reset()

# --- CARREGAR DADOS ---
df_pedidos = ler_aba("Pedidos")

# --- TELA FINANCEIRO (ATUALIZADA) ---
def render_tab_financeiro(tab):
    with tab:
        st.header("💰 Gestão Financeira")
        
        menu = st.radio("Selecione o Relatório:", 
                        ["Panorama do Dia", "Resumo por Período", "Grupo de Pedidos (Relatório Customizado)"], 
                        horizontal=True)

        # 1. PANORAMA DO DIA
        if menu == "Panorama do Dia":
            hoje = datetime.now(fuso_br).strftime("%d/%m/%Y")
            st.subheader(f"📅 Resumo de Hoje ({hoje})")
            
            df_hoje = df_pedidos[df_pedidos["data"] == hoje]
            
            if df_hoje.empty:
                st.info("Nenhum pedido registrado hoje.")
            else:
                # Processar itens vendidos hoje
                vendas = {}
                total_geral = 0.0
                for _, row in df_hoje.iterrows():
                    total_geral += parse_float(row["total"])
                    itens = json.loads(row["itens"])
                    for it in itens:
                        nome = it["nome"]
                        vendas[nome] = vendas.get(nome, {"qtd": 0, "valor": 0.0})
                        vendas[nome]["qtd"] += it["qtd"]
                        vendas[nome]["valor"] += parse_float(it["subtotal"])

                # Exibir métricas
                c1, c2 = st.columns(2)
                c1.metric("Pedidos Hoje", len(df_hoje))
                c2.metric("Total Arrecadado", f"R$ {total_geral:.2f}")

                # Tabela de itens
                st.markdown("**Itens vendidos hoje:**")
                df_resumo = pd.DataFrame([
                    {"Item": k, "Qtd": v["qtd"], "Total": f"R$ {v['valor']:.2f}"} 
                    for k, v in vendas.items()
                ])
                st.table(df_resumo)

        # 2. RESUMO POR PERÍODO
        elif menu == "Resumo por Período":
            st.subheader("🔍 Vendas por Período")
            c1, c2 = st.columns(2)
            data_ini = c1.date_input("Início", datetime.now(fuso_br) - timedelta(days=7))
            data_fim = c2.date_input("Fim", datetime.now(fuso_br))
            
            if st.button("Gerar Resumo do Período"):
                # Converter datas da planilha para objeto datetime para comparar
                df_periodo = df_pedidos.copy()
                df_periodo["dt_obj"] = pd.to_datetime(df_periodo["data"], format="%d/%m/%Y").dt.date
                mask = (df_periodo["dt_obj"] >= data_ini) & (df_periodo["dt_obj"] <= data_fim)
                df_filtrado = df_periodo[mask]
                
                if df_filtrado.empty:
                    st.warning("Nenhuma venda neste período.")
                else:
                    resumo_p = {}
                    total_p = 0.0
                    for _, row in df_filtrado.iterrows():
                        total_p += parse_float(row["total"])
                        for it in json.loads(row["itens"]):
                            n = it["nome"]
                            resumo_p[n] = resumo_p.get(n, {"qtd": 0, "valor": 0.0})
                            resumo_p[n]["qtd"] += it["qtd"]
                            resumo_p[n]["valor"] += parse_float(it["subtotal"])
                    
                    st.success(f"Período: {data_ini.strftime('%d/%m')} a {data_fim.strftime('%d/%m')}")
                    st.metric("Volume Total", f"R$ {total_p:.2f}")
                    
                    df_res_p = pd.DataFrame([
                        {"Produto": k, "Qtd Total": v["qtd"], "Faturamento": f"R$ {v['valor']:.2f}"}
                        for k, v in resumo_p.items()
                    ])
                    st.dataframe(df_res_p, use_container_width=True)

        # 3. GRUPO ESPECÍFICO DE PEDIDOS (CUSTOMIZADO)
        elif menu == "Grupo de Pedidos (Relatório Customizado)":
            st.subheader("📋 Relatório por Seleção")
            st.write("Marque os pedidos que deseja incluir no relatório:")
            
            # Filtro rápido para ajudar a achar os pedidos
            hoje_str = datetime.now(fuso_br).strftime("%d/%m/%Y")
            pedidos_alvo = df_pedidos[df_pedidos["status"] != "Excluido"].tail(20) # Últimos 20 pedidos
            
            selecionados = []
            for i, row in pedidos_alvo.iterrows():
                col_sel, col_info = st.columns([0.5, 9.5])
                if col_sel.checkbox("", key=f"sel_{row['id']}"):
                    selecionados.append(row)
                col_info.write(f"👤 {row['cliente']} | 📅 {row['data']} | 💰 R$ {parse_float(row['total']):.2f}")
            
            if selecionados:
                st.markdown("---")
                st.markdown("### 📊 Relatório do Grupo Selecionado")
                df_sel = pd.DataFrame(selecionados)
                total_sel = df_sel["total"].apply(parse_float).sum()
                
                # Resumo de itens do grupo
                resumo_g = {}
                for _, r in df_sel.iterrows():
                    for it in json.loads(r["itens"]):
                        resumo_g[it["nome"]] = resumo_g.get(it["nome"], 0) + it["qtd"]
                
                col1, col2 = st.columns(2)
                col1.metric("Qtd Pedidos", len(df_sel))
                col2.metric("Valor Total do Grupo", f"R$ {total_sel:.2f}")
                
                st.write("**Itens somados no grupo:**")
                for k, v in resumo_g.items():
                    st.write(f"• {v}x {k}")
                
                # Botão para WhatsApp do Grupo
                txt_zap = f"*RELATÓRIO DE GRUPO*\n"
                txt_zap += f"Total de Pedidos: {len(df_sel)}\n"
                txt_zap += f"Valor Total: R$ {total_sel:.2f}\n\n"
                txt_zap += "\n".join([f"- {v}x {k}" for k, v in resumo_g.items()])
                
                st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_zap)}" target="_blank" class="btn-zap">ENVIAR RELATÓRIO DO GRUPO</a>', unsafe_allow_html=True)

# --- EXECUÇÃO ---
# (Mantendo a estrutura das outras abas conforme seu código anterior)
# ... render_tab_novo_pedido, render_tab_colheita, etc ...

aba1, aba2, aba3, aba4, aba5 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro"])
# Chamada da nova função na aba 5
render_tab_financeiro(aba5)
