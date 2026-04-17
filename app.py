import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS para botões lado a lado e visual limpo
st.markdown("""
    <style>
    .stButton>button { border-radius: 8px; width: 100%; }
    [data-testid="stMetric"] { background: #f8f9fa; padding: 10px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_seguro(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        # Força os nomes das colunas para minúsculas e sem espaços para evitar o erro do teu print
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except Exception:
        return pd.DataFrame()

df_p = carregar_seguro("Produtos")
df_v = carregar_seguro("Pedidos")

# Garante que as colunas existem na memória para não dar erro
for col in ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"]:
    if col not in df_v.columns: df_v[col] = ""

# --- NAVEGAÇÃO ---
tab = st.tabs(["🛒 Vendas", "🚜 Colheita", "⚖️ Montagem", "📦 Estoque", "📊 Financeiro", "🕒 Histórico"])

# --- MONTAGEM (ORGANIZAÇÃO IGUAL À FOTO) ---
with tab[2]:
    st.subheader("Pedidos Pendentes")
    pendentes = df_v[df_v['status'].astype(str).str.lower() == 'pendente']
    
    for idx, p in pendentes.iterrows():
        with st.container(border=True):
            st.write(f"👤 **{p.get('cliente', 'Sem Nome')}**")
            
            # Processar itens do JSON de forma segura
            try:
                itens = json.loads(p['itens']) if p['itens'] else []
            except:
                itens = []
                
            total_pedido = 0.0
            pronto = True
            
            for i, it in enumerate(itens):
                if str(it.get('tipo', '')).upper() == "KG":
                    val = st.text_input(f"Peso {it['nome']}:", key=f"m_{idx}_{i}")
                    if val:
                        v = float(val.replace(',', '.'))
                        it['subtotal'] = v
                        total_pedido += v
                    else:
                        pronto = False
                else:
                    st.write(f"• {it.get('qtd')}x {it.get('nome')}")
                    total_pedido += float(it.get('subtotal', 0))
            
            st.write(f"**Total: R$ {total_pedido:.2f}**")
            
            # BOTÕES LADO A LADO (Igual ao exemplo)
            c1, c2, c3 = st.columns(3)
            
            # Botão Pago: Fica Azul (Primary) se clicado
            is_pago = p.get('pagamento') == "PAGO"
            if c1.button("✅ PAGO" if is_pago else "MARCAR PAGO", key=f"pg_{idx}", type="primary" if is_pago else "secondary", use_container_width=True):
                df_v.at[idx, 'pagamento'] = "PAGO"
                conn.update(worksheet="Pedidos", data=df_v); st.rerun()
                
            if c2.button("🗑️ EXCLUIR", key=f"del_{idx}", use_container_width=True):
                conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                
            if c3.button("💾 SALVAR", key=f"ok_{idx}", disabled=not pronto, type="primary" if pronto else "secondary", use_container_width=True):
                df_v.at[idx, 'status'] = "Concluído"
                df_v.at[idx, 'total'] = total_pedido
                df_v.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- HISTÓRICO (ORGANIZAÇÃO COM RESUMO NO TOPO) ---
with tab[5]:
    st.subheader("Histórico do Dia")
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_hj = df_v[df_v['data'] == hoje]
    
    # RESUMO IGUAL À FOTO VERDE
    m1, m2, m3 = st.columns(3)
    m1.metric("Pedidos", len(df_hj))
    m2.metric("Pagos", len(df_hj[df_hj['pagamento'] == "PAGO"]))
    m3.metric("Total", f"R$ {df_hj['total'].apply(lambda x: float(x) if x else 0).sum():.2f}")
    
    st.divider()
    
    for idx, p in df_hj.iterrows():
        with st.expander(f"{p['cliente']} - R$ {p['total']}"):
            st.write(f"📍 Endereço: {p['endereco']}")
            if st.button("Reimprimir Etiqueta", key=f"print_{idx}"):
                # Gerar link RawBT aqui
                pass
