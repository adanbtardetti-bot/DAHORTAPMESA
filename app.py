import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

# --- CONFIGURAÇÕES E ESTILOS ---
st.set_page_config(page_title="Horta Gestão", page_icon="🥬", layout="wide")

def aplicar_estilos():
    # CSS para forçar ícones lado a lado no celular e estilização geral
    st.markdown("""
        <style>
            .hero-banner {background-color: #0f1d12; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px;}
            .btn-zap {background-color: #25d366; color: white !important; padding: 10px; border-radius: 5px; text-decoration: none; display: block; text-align: center; font-weight: bold;}
            .btn-print {text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; color:black; border:1px solid #ddd;}
            .total-badge {background:#f0f2f6; padding:10px; border-radius:5px; font-weight:bold; margin-bottom:10px; color:black;}
            /* Força colunas a não quebrarem no mobile para os botões */
            [data-testid="column"] { min-width: 0px !important; flex-basis: auto !important; }
        </style>
    """, unsafe_allow_html=True)

aplicar_estilos()

# --- CONEXÃO COM CACHE PARA EVITAR QUOTA EXCEEDED ---
conn = st.connection("gsheets", type=GSheetsConnection)

def ler_aba(aba, ttl=10): # TTL de 10s evita requisições em excesso
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty:
            return pd.DataFrame()
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna("")
    except Exception:
        return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    st.cache_data.clear() # Limpa o cache após salvar

# --- FUNÇÕES DE UTILIDADE ---
def parse_float(val):
    try: return float(str(val).strip().replace(",", "."))
    except: return 0.0

# --- CARREGAR DADOS ---
df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

st.markdown('<div class="hero-banner"><h2>Horta Gestao</h2></div>', unsafe_allow_html=True)
tabs = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro", "📦 Produtos"])

# --- 1. NOVO PEDIDO ---
with tabs[0]:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("Cliente", key=f"n_{f}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f}").upper()
    
    carrinho, total_v = [], 0.0
    if not df_produtos.empty:
        for idx, r in df_produtos.iterrows():
            if str(r.get('status', '')).lower() == "inativo": continue
            col_n, col_q = st.columns([3, 1])
            qtd = col_q.number_input("Q", 0, step=1, key=f"q_{idx}_{f}", label_visibility="collapsed")
            col_n.write(f"**{r['nome']}** (R$ {r['preco']})")
            if qtd > 0:
                p_u = parse_float(r['preco'])
                sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": r['tipo']})
    
    if st.button("💾 SALVAR PEDIDO", use_container_width=True, type="primary"):
        if n_cli and carrinho:
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "A PAGAR"}])
            salvar_aba("Pedidos", pd.concat([df_pedidos, novo], ignore_index=True))
            st.session_state.f_id += 1
            st.rerun()

# --- 3. MONTAGEM ---
with tabs[2]:
    if not df_pedidos.empty:
        pend = df_pedidos[df_pedidos["status"] == "pendente"]
        for _, row in pend.iterrows():
            with st.expander(f"👤 {row['cliente']}"):
                itens = json.loads(row['itens'])
                total_m = 0.0
                for i, it in enumerate(itens):
                    c_i, c_v = st.columns([3, 1])
                    if str(it['tipo']).upper() == "KG":
                        it['subtotal'] = c_v.number_input("R$", 0.0, key=f"v_{row['id']}_{i}")
                        c_i.write(f"⚖️ {it['nome']}")
                    else:
                        c_i.write(f"✅ {it['qtd']}x {it['nome']}")
                        c_v.write(f"R$ {it['subtotal']:.2f}")
                    total_m += parse_float(it['subtotal'])
                
                c_ok, c_del = st.columns(2)
                if c_ok.button("📦 Finalizar", key=f"f_{row['id']}"):
                    df_pedidos.loc[df_pedidos["id"] == row["id"], ["status", "total", "itens"]] = ["pronto", total_m, json.dumps(itens)]
                    salvar_aba("Pedidos", df_pedidos); st.rerun()

# --- 5. FINANCEIRO ---
with tabs[4]:
    st.header("💰 Financeiro")
    if not df_pedidos.empty:
        # Correção do KeyError: Garante que a coluna 'data' existe e está filtrada corretamente
        hoje = datetime.now().strftime("%d/%m/%Y")
        df_hoje = df_pedidos[df_pedidos["data"] == hoje]
        v_total = df_hoje['total'].apply(parse_float).sum()
        st.metric("Faturamento Hoje", f"R$ {v_total:.2f}")
        
        res = {}
        for _, r in df_hoje.iterrows():
            for it in json.loads(r['itens']):
                n = it['nome'].upper()
                res[n] = res.get(n, 0) + parse_float(it.get('subtotal', 0))
        if res:
            st.table(pd.DataFrame([{"Produto": k, "Valor": f"R$ {v:.2f}"} for k, v in res.items()]))

# --- 6. PRODUTOS (LAYOUT IGUAL MONTAGEM) ---
with tabs[5]:
    st.header("📦 Produtos")
    with st.expander("➕ Adicionar Novo Produto"):
        c1, c2, c3 = st.columns([2, 1, 1])
        n_p = c1.text_input("Nome")
        p_p = c2.number_input("Preço", 0.0)
        t_p = c3.selectbox("Tipo", ["UN", "KG"])
        if st.button("SALVAR NOVO"):
            if n_p:
                novo_p = pd.DataFrame([{"nome": n_p.upper(), "preco": p_p, "tipo": t_p, "status": "Ativo"}])
                salvar_aba("Produtos", pd.concat([df_produtos, novo_p], ignore_index=True))
                st.rerun()

    if not df_produtos.empty:
        for idx, r in df_produtos.iterrows():
            with st.container():
                st.write(f"**{r['nome']}**")
                col_p, col_t = st.columns(2)
                np = col_p.number_input("R$", parse_float(r['preco']), key=f"p_{idx}")
                nt = col_t.selectbox("T", ["UN", "KG"], index=0 if r['tipo']=="UN" else 1, key=f"t_{idx}")
                
                c_at, c_sv, c_del, _ = st.columns([1.5, 0.6, 0.6, 2])
                est = c_at.toggle("Ativo", value=(str(r['status']).lower() == "ativo"), key=f"s_{idx}")
                if c_sv.button("💾", key=f"sv_{idx}"):
                    df_produtos.loc[idx, ["preco", "tipo", "status"]] = [np, nt, ("Ativo" if est else "Inativo")]
                    salvar_aba("Produtos", df_produtos); st.rerun()
                if c_del.button("🗑️", key=f"dl_{idx}"):
                    salvar_aba("Produtos", df_produtos.drop(idx)); st.rerun()
                st.divider()
