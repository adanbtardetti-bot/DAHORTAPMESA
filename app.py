import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS Ajustado para cards visíveis e botões robustos
st.markdown("""
<style>
    div[data-testid="stColumn"] { display: flex; align-items: center; }
    .card-montagem {
        border: 2px solid #2e7d32;
        padding: 15px;
        border-radius: 12px;
        background-color: #1e1e1e; /* Fundo escuro para contrastar no app */
        color: white;
        margin-bottom: 15px;
    }
    .btn-pronto { background-color: #2e7d32 !important; color: white !important; height: 3.5em; width: 100%; border-radius: 10px; font-weight: bold; }
    .btn-whatsapp { background-color: #25d366; color: white; padding: 12px; border-radius: 10px; text-align: center; text-decoration: none; display: block; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_pedidos():
    try:
        df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except: return pd.DataFrame()

tab_venda, tab_colheita, tab_montagem = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

# --- LÓGICA DE VENDA E COLHEITA (RESUMIDAS) ---
with tab_venda:
    st.info("Utilize para novos pedidos.") # Mantém a lógica anterior aqui
with tab_colheita:
    st.info("Resumo para o campo.") # Mantém a lógica anterior aqui

# --- ABA 3: MONTAGEM (FOCO TOTAL AQUI) ---
with tab_montagem:
    st.header("⚖️ Montagem de Pedidos")
    df_m = carregar_pedidos()
    
    # Só mostramos o que está "Pendente"
    pendentes_m = df_m[df_m['status'].str.lower() == 'pendente']

    if not pendentes_m.empty:
        for idx, row in pendentes_m.iterrows():
            # Card de Identificação
            st.markdown(f"""
            <div class="card-montagem">
                <h2 style='margin:0;'>👤 {row['cliente']}</h2>
                <p style='margin:5px 0;'>📍 {row['endereco']}</p>
                <small>📝 {row['obs'] if row['obs'] else 'Sem observações'}</small>
            </div>
            """, unsafe_allow_html=True)
            
            itens_lista = json.loads(row['itens'])
            novo_total = 0.0
            
            # Lista de itens para conferir e pesar
            for i, item in enumerate(itens_lista):
                c1, c2 = st.columns([3, 2])
                
                if str(item.get('tipo')).upper() == "KG":
                    c1.markdown(f"⚖️ **{item['nome']}**")
                    # Campo para digitar o valor que deu na balança
                    v_pesado = c2.number_input(f"Valor R$", min_value=0.0, step=0.1, key=f"v_{row['id']}_{i}")
                    item['subtotal'] = v_pesado
                else:
                    c1.markdown(f"✅ {item['qtd']}x **{item['nome']}**")
                    c2.write(f"R$ {item['subtotal']:.2f}")
                
                novo_total += item['subtotal']

            st.markdown(f"### TOTAL: R$ {novo_total:.2f} ({row['pagamento']})")

            # BOTÕES DE AÇÃO
            col1, col2 = st.columns(2)
            
            # 1. BOTÃO IMPRIMIR
            txt_etiq = f"{row['cliente']}\n{row['endereco']}\n\nVALOR: R$ {novo_total:.2f}\n{row['pagamento']}"
            b64 = base64.b64encode(txt_etiq.encode()).decode()
            link_print = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
            col1.markdown(f'<a href="{link_print}" style="text-decoration:none;"><button style="width:100%; height:3.5em; border-radius:10px; background:#444; color:white; font-weight:bold;">🖨️ Imprimir Etiqueta</button></a>', unsafe_allow_html=True)

            # 2. BOTÃO PEDIDO PRONTO (FINALIZA E TIRA DA TELA)
            if col2.button("📦 PEDIDO PRONTO", key=f"btn_ok_{row['id']}", use_container_width=True):
                # Atualiza os dados na linha correta do DataFrame original
                df_m.at[idx, 'status'] = 'Pronto'
                df_m.at[idx, 'total'] = novo_total
                df_m.at[idx, 'itens'] = json.dumps(itens_lista)
                
                conn.update(worksheet="Pedidos", data=df_m)
                st.success(f"Pedido de {row['cliente']} finalizado!")
                st.rerun()

            # BOTÕES SECUNDÁRIOS
            ca, cb = st.columns([1, 1])
            if ca.button("🗑️ Excluir", key=f"del_{row['id']}"):
                df_m = df_m.drop(idx)
                conn.update(worksheet="Pedidos", data=df_m)
                st.rerun()
                
            if cb.button("💳 Marcar Pago", key=f"pago_{row['id']}"):
                df_m.at[idx, 'pagamento'] = 'PAGO'
                conn.update(worksheet="Pedidos", data=df_m)
                st.rerun()

            st.divider()
    else:
        st.info("Tudo montado! Não há pedidos pendentes.")
