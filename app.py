import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

st.set_page_config(page_title="Horta", layout="centered")

# CSS Super Otimizado para Celular
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 1.2rem !important; }
    .card-mini {
        border: 1px solid #2e7d32;
        padding: 8px;
        border-radius: 8px;
        background-color: #0e1117;
        margin-bottom: 5px;
    }
    .stButton>button { width: 100% !important; height: 2.5em !important; padding: 0px !important; }
    p, span { margin: 0px !important; padding: 0px !important; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except: return pd.DataFrame()

tab1, tab2, tab3 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

# --- ABA 3: MONTAGEM (FOCO EM OTIMIZAÇÃO) ---
with tab3:
    df_m = carregar_dados("Pedidos")
    
    if not df_m.empty and 'status' in df_m.columns:
        pendentes = df_m[df_m['status'].str.lower() == 'pendente']
        
        for idx, row in pendentes.iterrows():
            with st.container():
                # Card Compacto
                st.markdown(f"""
                <div class="card-mini">
                    <b>👤 {row['cliente']}</b> | 📍 {row['endereco']}
                </div>
                """, unsafe_allow_html=True)
                
                itens_lista = json.loads(row['itens'])
                total_atual = 0.0
                
                # Itens em linha única
                for i, item in enumerate(itens_lista):
                    col_it, col_val = st.columns([3, 2])
                    
                    if str(item.get('tipo')).upper() == "KG":
                        # Input pequeno para valor do KG
                        valor_kg = col_val.number_input("R$", min_value=0.0, step=0.1, key=f"v_{row['id']}_{i}", label_visibility="collapsed")
                        item['subtotal'] = valor_kg
                        col_it.write(f"⚖️ {item['nome']}")
                    else:
                        col_it.write(f"✅ {item['qtd']}x {item['nome']}")
                        col_val.write(f"R$ {item['subtotal']:.2f}")
                    
                    total_atual += item['subtotal']

                # Linha de Ações Otimizada
                st.write(f"**Total: R$ {total_atual:.2f}** | {row.get('pagamento', '')}")
                
                c1, c2, c3, c4 = st.columns([1, 1.2, 0.8, 0.5])
                
                # Pronto (Soma e tira da tela)
                if c1.button("📦 OK", key=f"ok_{row['id']}"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = total_atual
                    df_m.at[idx, 'itens'] = json.dumps(itens_lista)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()
                
                # Imprimir (RawBT)
                txt = f"{row['cliente']}\n{row['endereco']}\n\nR$ {total_atual:.2f}\n{row.get('pagamento', '')}"
                b64 = base64.b64encode(txt.encode()).decode()
                link = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                c2.markdown(f'<a href="{link}"><button style="width:100%; background:#444; color:white; border-radius:5px; border:none; height:2.5em;">🖨️ Etiq.</button></a>', unsafe_allow_html=True)
                
                # Pago rápido
                if c3.button("💳 $", key=f"pg_{row['id']}"):
                    df_m.at[idx, 'pagamento'] = 'PAGO'
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()
                
                # Excluir
                if c4.button("🗑️", key=f"del_{row['id']}"):
                    df_m = df_m.drop(idx)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()
                
                st.divider()
    else:
        st.info("Nenhum pedido pendente.")
