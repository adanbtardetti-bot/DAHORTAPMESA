import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

# --- CONFIGURAÇÕES ORIGINAIS ---
st.set_page_config(page_title="Horta Gestão", page_icon="🥬", layout="wide")

def aplicar_estilos():
    css_path = Path(__file__).with_name("styles.css")
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    else:
        # Mantendo os estilos que você já usava
        st.markdown("""
            <style>
                .hero-banner {background-color: #0f1d12; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px;}
                .hero-title {font-size: 24px; font-weight: bold;}
                .btn-zap {background-color: #25d366; color: white !important; padding: 10px; border-radius: 5px; text-decoration: none; display: block; text-align: center; font-weight: bold;}
                .btn-print {text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; color:black; border:1px solid #ddd;}
                .total-badge {background:#f0f2f6; padding:10px; border-radius:5px; font-weight:bold; margin-bottom:10px; color:black;}
                .m-total {font-size: 20px; font-weight: bold; margin-top: 10px; color: #1e1e1e;}
            </style>
        """, unsafe_allow_html=True)

aplicar_estilos()

conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES TÉCNICAS (CORRIGIDAS PARA EVITAR ERROS) ---
def parse_float(val):
    try: return float(str(val).strip().replace(",", "."))
    except: return 0.0

def ler_aba(aba, ttl=5): # Adicionado TTL de 5s para evitar erro de cota do Google
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty:
            # Garante que as colunas existam mesmo se a planilha estiver vazia (evita KeyError)
            cols = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]
            if aba == "Produtos": cols = ["id", "nome", "preco", "tipo", "status"]
            return pd.DataFrame(columns=cols)
        # Padroniza nomes das colunas para evitar erro de maiúscula/minúscula
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna("")
    except:
        return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    st.cache_data.clear() # Limpa cache para atualizar os dados na tela

# --- CARREGAR DADOS ---
df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

st.markdown('<div class="hero-banner"><div class="hero-title">Horta Gestao</div></div>', unsafe_allow_html=True)

aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro", "📦 Produtos"])

# --- 1. NOVO PEDIDO ---
with aba1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    st.header("🛒 Novo Pedido")
    c1, c2, c3 = st.columns([2, 2, 1])
    n_cli = c1.text_input("Cliente", key=f"n_{f}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f}").upper()
    pg = c3.toggle("Pago?", key=f"p_{f}")
    o_ped = st.text_input("Observação", key=f"o_{f}").upper()
    
    carrinho, total_v = [], 0.0
    if not df_produtos.empty:
        # Filtra apenas produtos ativos
        prods = df_produtos[df_produtos['status'].astype(str).str.lower() != "inativo"]
        for idx, r in prods.iterrows():
            col_n, col_p, col_q = st.columns([3.4, 1.3, 1.1])
            col_n.markdown(f"**{r['nome']}**")
            col_p.caption(f"R$ {r['preco']} / {r['tipo']}")
            qtd = col_q.number_input("Q", 0, step=1, key=f"q_{idx}_{f}", label_visibility="collapsed")
            if qtd > 0:
                p_u = parse_float(r['preco'])
                sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": r['tipo']})
    
    st.markdown(f"<div class='total-badge'>Total parcial: R$ {total_v:.2f}</div>", unsafe_allow_html=True)
    if st.button("💾 SALVAR PEDIDO", type="primary", use_container_width=True):
        if n_cli and carrinho:
            df_at = ler_aba("Pedidos", ttl=0)
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pg else "A PAGAR", "obs": o_ped}])
            salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True))
            st.session_state.f_id += 1
            st.rerun()

# --- 2. COLHEITA ---
with aba2:
    st.header("🚜 Colheita")
    if not df_pedidos.empty and "status" in df_pedidos.columns:
        pend = df_pedidos[df_pedidos["status"].str.lower() == "pendente"]
        res = {}
        for _, p in pend.iterrows():
            try:
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it['tipo']})"
                    res[k] = res.get(k, 0) + it['qtd']
            except: continue
        for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")

# --- 3. MONTAGEM ---
with aba3:
    st.header("⚖️ Montagem")
    if not df_pedidos.empty and "status" in df_pedidos.columns:
        pend_m = df_pedidos[df_pedidos["status"].str.lower() == "pendente"]
        for _, row in pend_m.iterrows():
            with st.expander(f"👤 {row['cliente']}", expanded=True):
                st.write(f"📍 {row['endereco']}")
                itens_m = json.loads(row['itens'])
                total_m = 0.0
                for i, it in enumerate(itens_m):
                    c_i, c_v = st.columns([3.5, 1.4])
                    if str(it['tipo']).upper() == "KG":
                        it['subtotal'] = c_v.number_input("R$", 0.0, key=f"m_{row['id']}_{i}", label_visibility="collapsed")
                        c_i.markdown(f"⚖️ {it['nome']}")
                    else:
                        c_i.markdown(f"✅ {it['qtd']}x {it['nome']}")
                        c_v.markdown(f"R$ {parse_float(it['subtotal']):.2f}")
                    total_m += parse_float(it['subtotal'])
                
                st.markdown(f"<div class='m-total'>TOTAL: R$ {total_m:.2f}</div>", unsafe_allow_html=True)
                if st.button("📦 FINALIZAR", key=f"ok_{row['id']}", use_container_width=True):
                    df_f = ler_aba("Pedidos", ttl=0)
                    idx = df_f.index[df_f["id"].astype(str) == str(row["id"])][0]
                    df_f.at[idx, "status"], df_f.at[idx, "total"], df_f.at[idx, "itens"] = "pronto", total_m, json.dumps(itens_m)
                    salvar_aba("Pedidos", df_f); st.rerun()

# --- 4. HISTÓRICO ---
with aba4:
    st.header("📜 Histórico")
    data_f = st.date_input("Filtrar:", datetime.now()).strftime("%d/%m/%Y")
    if not df_pedidos.empty:
        hist = df_pedidos[(df_pedidos["status"] == "pronto") & (df_pedidos["data"] == data_f)]
        for _, r in hist.iterrows():
            st.write(f"✅ {r['cliente']} - R$ {r['total']}")

# --- 5. FINANCEIRO ---
with aba5:
    st.header("💰 Financeiro")
    if not df_pedidos.empty and "total" in df_pedidos.columns:
        hoje = datetime.now().strftime("%d/%m/%Y")
        df_hoje = df_pedidos[df_pedidos["data"] == hoje]
        v_total = df_hoje['total'].apply(parse_float).sum()
        st.metric("Total do Dia", f"R$ {v_total:.2f}")

# --- 6. PRODUTOS ---
with aba6:
    st.header("📦 Produtos")
    # Adicionar
    with st.expander("Novo Produto"):
        n = st.text_input("Nome").upper()
        p = st.number_input("Preço", 0.0)
        t = st.selectbox("Tipo", ["UN", "KG"])
        if st.button("Salvar"):
            df_p = ler_aba("Produtos", 0)
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "nome": n, "preco": p, "tipo": t, "status": "Ativo"}])
            salvar_aba("Produtos", pd.concat([df_p, novo], ignore_index=True))
            st.rerun()
    
    # Listagem original
    if not df_produtos.empty:
        for idx, r in df_produtos.iterrows():
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            c1.write(r['nome'])
            c2.write(f"R$ {r['preco']}")
            if c4.button("🗑️", key=f"delp_{idx}"):
                salvar_aba("Produtos", df_produtos.drop(idx)); st.rerun()
