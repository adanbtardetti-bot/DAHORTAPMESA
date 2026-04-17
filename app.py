import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- BLOCO 1: CONFIGURAÇÃO E DADOS ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        df_p = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except:
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- BLOCO 2: FUNÇÃO DE IMPRESSÃO ---
def botao_imprimir(ped, valor_real):
    def limpar(txt):
        if pd.isna(txt) or str(txt).lower() == 'nan': return ""
        return str(txt).strip().upper()
    nome = limpar(ped.get('cliente', ''))
    end = limpar(ped.get('endereco', ''))
    pag = limpar(ped.get('pagamento', ''))
    txt_pg = f"\n*** {pag} ***\n" if "PAGO" in pag else "\n"
    v_f = f"{float(valor_real):.2f}".replace('.', ',')
    cmds = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{end}{txt_pg}\n\x1b\x61\x01\x1b\x21\x10TOTAL: RS {v_f}\n\n\n\n"
    b64 = base64.b64encode(cmds.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;">🖨️ REIMPRIMIR ETIQUETA</div></a>', unsafe_allow_html=True)

# --- BLOCO 3: ABAS ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# (MANTIVE AS ABAS NOVO, COLHEITA E MONTAGEM COMO ESTAVAM...)
with tabs[0]: # NOVO
    st.write("Crie novos pedidos aqui.") # O teu código anterior de Novo Pedido entra aqui
    # ... código do novo pedido ...

with tabs[1]: # COLHEITA
    st.write("Resumo para colheita.") # O teu código anterior de Colheita entra aqui
    # ... código da colheita ...

with tabs[2]: # MONTAGEM
    st.write("Finalize os pesos aqui.") # O teu código anterior de Montagem entra aqui
    # ... código da montagem ...

# --- NOVO BLOCO 4: HISTÓRICO (REFORMULADO) ---
with tabs[3]:
    st.header("📅 Histórico de Pedidos")
    
    # 1. Filtro por Calendário
    data_sel = st.date_input("Filtrar por data", datetime.now())
    data_str = data_sel.strftime("%d/%m/%Y")
    
    # 2. Filtro de Pedidos Concluídos do dia
    df_dia = df_pedidos[(df_pedidos['status'] == "Concluído") & (df_pedidos['data'] == data_str)]
    
    if df_dia.empty:
        st.info(f"Sem pedidos concluídos em {data_str}")
    else:
        for idx, p in df_dia.iterrows():
            with st.container(border=True):
                col_c1, col_c2, col_c3 = st.columns([3, 2, 1])
                
                with col_c1:
                    st.markdown(f"**👤 {p['cliente']}**")
                    st.caption(f"📍 {p['endereco']}")
                
                with col_c2:
                    valor = float(str(p['total']).replace(',', '.'))
                    st.markdown(f"**💰 R$ {valor:.2f}**")
                    st.caption(f"💳 {p['pagamento']}")
                
                with col_c3:
                    # Usamos um expander para ver detalhes
                    with st.popover("🔍 Detalhes"):
                        st.write("### Itens do Pedido")
                        itens = json.loads(p['itens'])
                        for it in itens:
                            st.write(f"- {it['nome']}: {it['qtd']} {it['tipo']} (R$ {it['subtotal']:.2f})")
                        
                        st.divider()
                        # Botão de Reimprimir
                        botao_imprimir(p, valor)
                        
                        st.divider()
                        # Mudar Pagamento
                        novo_pg = "A PAGAR" if p['pagamento'] == "PAGO" else "PAGO"
                        if st.button(f"Mudar para {novo_pg}", key=f"pg_{p['id']}"):
                            df_pedidos.at[idx, 'pagamento'] = novo_pg
                            conn.update(worksheet="Pedidos", data=df_pedidos)
                            st.rerun()

# --- NOVO BLOCO 5: FINANCEIRO ---
with tabs[4]:
    st.header("📊 Resumo Financeiro")
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"]
    
    if not concluidos.empty:
        c_f1, c_f2 = st.columns(2)
        v_pago = concluidos[concluidos['pagamento'] == "PAGO"]['total'].astype(float).sum()
        v_pend = concluidos[concluidos['pagamento'] == "A PAGAR"]['total'].astype(float).sum()
        
        c_f1.metric("Total Recebido (PAGO)", f"R$ {v_pago:.2f}")
        c_f2.metric("A Receber (PENDENTE)", f"R$ {v_pend:.2f}")
        
        st.divider()
        st.write("Tabela completa de vendas:")
        st.dataframe(concluidos, use_container_width=True)
    else:
        st.write("Sem dados financeiros para exibir.")

with tabs[5]: # ESTOQUE
    # ... o teu código anterior do estoque ...
    st.write("Gerencie o estoque aqui.")
