import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS para Otimização Máxima (Botões em linha e sem nan)
st.markdown('''
<style>
    .block-container {padding-top: 1rem;}
    [data-testid="stHorizontalBlock"] {gap: 5px !important;}
    .stButton>button {width: 100% !important; height: 2.8rem !important; padding: 0px !important;}
    .card-pedido {border: 1px solid #2e7d32; padding: 10px; border-radius: 8px; background-color: #0e1117; margin-bottom: 5px;}
    p {margin-bottom: 2px !important;}
</style>
''', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÃO DE CARGA ---
def carregar_pedidos():
    try:
        df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        # Limpa todos os 'nan' do DataFrame inteiro de uma vez
        return df.fillna('')
    except:
        return pd.DataFrame()

# --- MENUS (ABAS) NO TOPO ---
aba1, aba2, aba3 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

with aba1:
    st.info("Focando na aba de Montagem...")

with aba2:
    st.info("Focando na aba de Montagem...")

# --- FOCO TOTAL: ABA 3 MONTAGEM ---
with aba3:
    df_m = carregar_pedidos()
    
    if not df_m.empty and 'status' in df_m.columns:
        # Filtra apenas pendentes
        pendentes = df_m[df_m['status'].str.lower() == 'pendente']
        
        if pendentes.empty:
            st.success("Tudo montado! Nenhum pedido pendente.")
        
        for idx, row in pendentes.iterrows():
            # Pegando os dados limpos (sem nan)
            cliente = str(row['cliente']).upper()
            endereco = str(row['endereco']).upper()
            observacao = str(row.get('obs', ''))
            pagamento = str(row.get('pagamento', 'A PAGAR'))
            id_pedido = str(row['id'])

            with st.container():
                # Card de Identificação
                st.markdown(f'''
                    <div class="card-pedido">
                        <b>👤 {cliente}</b><br>
                        📍 {endereco if endereco else "SEM ENDEREÇO"}
                    </div>
                ''', unsafe_allow_html=True)
                
                if observacao:
                    st.caption(f"💬 {observacao}")

                # Processando Itens
                try:
                    itens = json.loads(row['itens'])
                except:
                    itens = []
                
                total_atualizado = 0.0
                
                for i, item in enumerate(itens):
                    c_nome, c_valor = st.columns([3, 2])
                    
                    if str(item.get('tipo', '')).upper() == "KG":
                        # Campo de pesagem
                        peso_valor = c_valor.number_input("R$", min_value=0.0, step=0.1, key=f"v_{id_pedido}_{i}", label_visibility="collapsed")
                        item['subtotal'] = peso_valor
                        c_nome.write(f"⚖️ **{item['nome']}**")
                    else:
                        # Item fixo
                        c_nome.write(f"✅ {item['qtd']}x {item['nome']}")
                        c_valor.write(f"R$ {item.get('subtotal', 0.0):.2f}")
                    
                    total_atualizado += float(item.get('subtotal', 0.0))

                # Resumo de Valores
                st.write(f"**TOTAL: R$ {total_atualizado:.2f}** | 💳 {pagamento}")

                # --- BOTÕES LADO A LADO (4 COLUNAS) ---
                b1, b2, b3, b4 = st.columns(4)

                # 1. FINALIZAR (Sobe para a planilha e some da tela)
                if b1.button("📦 OK", key=f"ok_{id_pedido}"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = total_atualizado
                    df_m.at[idx, 'itens'] = json.dumps(itens)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # 2. ETIQUETA (RawBT) - Sem "Cliente:" ou "Endereço:", só os dados
                texto_etiq = f"{cliente}\n{endereco}"
                if observacao: texto_etiq += f"\nOBS: {observacao}"
                texto_etiq += f"\n\nVALOR: R$ {total_atualizado:.2f}\n{pagamento}"
                
                b64_etiq = base64.b64encode(texto_etiq.encode()).decode()
                link_print = f"intent:base64,{b64_etiq}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                b2.markdown(f'<a href="{link_print}"><button style="width:100%;height:2.8rem;background:#444;color:white;border:none;border-radius:5px;font-weight:bold;">🖨️</button></a>', unsafe_allow_html=True)

                # 3. MARCAR COMO PAGO
                if b3.button("💳 $", key=f"pg_{id_pedido}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # 4. EXCLUIR
                if b4.button("🗑️", key=f"del_{id_pedido}"):
                    df_m = df_m.drop(idx)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                st.divider()
    else:
        st.info("Nenhum pedido encontrado na planilha.")
