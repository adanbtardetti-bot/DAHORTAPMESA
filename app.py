import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except: return pd.DataFrame()

df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Garante que colunas críticas existam para evitar o KeyError do print
colunas_vivas = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]
for col in colunas_vivas:
    if col not in df_pedidos.columns: df_pedidos[col] = ""

# --- ABAS ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 3. MONTAGEM (TELA DO SEU PRINT OTIMIZADA) ---
with tabs[2]:
    st.header("Montagem")
    # Filtro seguro: evita erro se a coluna status falhar
    if not df_pedidos.empty and 'status' in df_pedidos.columns:
        pend = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
        
        for idx, p in pend.iterrows():
            with st.container(border=True):
                st.write(f"**Cliente:** {p['cliente']}")
                
                its, tf, ok = [], 0.0, True
                try:
                    its = json.loads(p['itens'])
                    for i, it in enumerate(its):
                        if str(it.get('tipo', '')).upper() == "KG":
                            val = st.text_input(f"Valor {it['nome']} ({it['qtd']}kg):", key=f"m{p['id']}{i}")
                            if val: 
                                v = float(val.replace(',', '.')); it['subtotal'] = v; tf += v
                            else: ok = False
                        else:
                            st.write(f"• {it['nome']} - {it['qtd']} UN")
                            tf += float(it.get('subtotal', 0))
                except: st.error("Erro nos itens deste pedido.")

                st.subheader(f"Total: R$ {tf:.2f}")
                
                # Lógica da Etiqueta: Sempre sai com valor (atendendo seu pedido)
                status_pg = "PAGO" if p['pagamento'] == "PAGO" else "A PAGAR"
                cmd = f"\x1b\x61\x01\x1b\x21\x10{p['cliente']}\n\x1b\x21\x00{p['endereco']}\n\x1b\x21\x08VALOR: RS {tf:.2f}\n({status_pg})\n\n\n"
                b64 = base64.b64encode(cmd.encode('latin-1')).decode('utf-8')
                url_p = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                
                st.markdown(f'[🖨️ IMPRIMIR ETIQUETA]({url_p})')
                
                # BOTÕES LADO A LADO (Otimização de espaço)
                c1, c2, c3 = st.columns(3)
                if c1.button("✅ PAGO", key=f"pg{idx}", use_container_width=True):
                    df_pedidos.at[idx, 'pagamento'] = "PAGO"; conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
                
                if c2.button("🗑️ EXCLUIR", key=f"ex{idx}", use_container_width=True):
                    df_pedidos = df_pedidos.drop(idx); conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
                
                if c3.button("💾 SALVAR", key=f"sv{idx}", disabled=not ok, type="primary", use_container_width=True):
                    df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = tf; df_pedidos.at[idx, 'itens'] = json.dumps(its)
                    conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
    else:
        st.warning("Nenhum pedido pendente ou erro ao acessar a coluna 'status'.")

# --- 4. HISTÓRICO (COM DETALHES QUE VOCÊ PEDIU) ---
with tabs[3]:
    st.header("Histórico")
    data_sel = st.date_input("Filtrar Data", datetime.now()).strftime("%d/%m/%Y")
    if not df_pedidos.empty and 'status' in df_pedidos.columns:
        h_fil = df_pedidos[(df_pedidos['status'].str.lower() == "concluído") & (df_pedidos['data'] == data_sel)]
        
        for idx, p in h_fil.iterrows():
            with st.expander(f"👤 {p['cliente']} | R$ {float(p['total']):.2f}"):
                st.write(f"📍 {p['endereco']}")
                try:
                    itens_h = json.loads(p['itens'])
                    for it in itens_h:
                        st.write(f"- {it['nome']}: R$ {float(it['subtotal']):.2f}")
                except: pass
                
                # Botões lado a lado no histórico também
                ch1, ch2 = st.columns(2)
                with ch1:
                    # Reimprimir etiqueta rápida
                    st.markdown(f'[🖨️ Etiqueta]({url_p})')
                with ch2:
                    msg = f"RECIBO: {p['cliente']}\nTotal: R$ {p['total']:.2f}"
                    st.markdown(f'[📲 WhatsApp](https://wa.me/?text={urllib.parse.quote(msg)})')

# Manter as outras abas (Novo, Colheita, Financeiro, Estoque) com a mesma lógica de segurança...
