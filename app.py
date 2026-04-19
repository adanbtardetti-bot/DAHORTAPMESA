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
    st.markdown("""
        <style>
            .hero-banner {background-color: #0f1d12; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px;}
            .hero-title {font-size: 24px; font-weight: bold;}
            .btn-zap {background-color: #25d366; color: white !important; padding: 10px; border-radius: 5px; text-decoration: none; display: block; text-align: center; font-weight: bold;}
            .btn-print {text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; color:black; border:1px solid #ddd;}
            .total-badge {background:#f0f2f6; padding:10px; border-radius:5px; font-weight:bold; margin-bottom:10px; color:black;}
            .card-prod {background-color:white; border-radius:10px; padding:12px; color:black; margin-bottom:5px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);}
        </style>
    """, unsafe_allow_html=True)

aplicar_estilos()

conn = st.connection("gsheets", type=GSheetsConnection)
STATUS_PENDENTE = "pendente"
STATUS_PRONTO = "pronto"
PAGAMENTO_PAGO = "PAGO"
PAGAMENTO_A_PAGAR = "A PAGAR"

# --- FUNÇÕES ---
def limpar_texto(texto):
    if not texto: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')

def gerar_b64_etiqueta(cliente, endereco, valor, pagamento):
    largura = 32
    marca = "@dahortapmesa".center(largura)
    cli = limpar_texto(cliente).upper().center(largura)
    end = limpar_texto(endereco).upper().center(largura)
    val_txt = f"R$ {valor:.2f}"
    status_txt = "pago" if pagamento == PAGAMENTO_PAGO else ""
    espacos = largura - len(val_txt) - len(status_txt) - 2
    linha_final = f"{val_txt}{' ' * espacos}{status_txt}"
    corpo = f"{marca}\n\n{cli}\n\n{end}\n\n{linha_final}"
    return base64.b64encode(corpo.encode('ascii', 'ignore')).decode()

def parse_float(val):
    try: return float(str(val).strip().replace(",", "."))
    except: return 0.0

def ler_aba(aba, ttl=30):
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty: return pd.DataFrame()
        df.columns = [str(c).lower().strip() for c in df.columns]
        # CORREÇÃO DO ERRO: Garante que a coluna 'status' existe
        if aba == "Produtos":
            if "status" not in df.columns:
                df["status"] = "Ativo"
        return df.fillna("")
    except: return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    conn.reset()

# --- DADOS ---
df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

st.markdown('<div class="hero-banner"><div class="hero-title">Horta Gestao</div></div>', unsafe_allow_html=True)

aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro", "📦 Produtos"])

# 1. NOVO
with aba1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    st.header("🛒 Novo Pedido")
    c1, c2, c3 = st.columns([2, 2, 1])
    n_cli = c1.text_input("Cliente", key=f"n_{f}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f}").upper()
    pg = c3.toggle("Pago?", key=f"p_{f}")
    
    carrinho, total_v = [], 0.0
    # Filtra apenas produtos ativos para venda
    prods_venda = df_produtos[df_produtos['status'] == "Ativo"]
    for idx, r in prods_venda.iterrows():
        col_n, col_p, col_q = st.columns([3.4, 1.3, 1.1])
        col_n.markdown(f"**{r['nome']}**")
        col_p.caption(f"R$ {r['preco']}")
        qtd = col_q.number_input("Q", 0, step=1, key=f"q_{idx}_{f}", label_visibility="collapsed")
        if qtd > 0:
            p_u = parse_float(r['preco'])
            sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
            total_v += sub
            carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": r['tipo']})
    
    if st.button("💾 SALVAR PEDIDO", type="primary", use_container_width=True):
        if n_cli and carrinho:
            df_at = ler_aba("Pedidos", 0)
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": STATUS_PENDENTE, "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR}])
            salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True))
            st.session_state.f_id += 1; st.rerun()

# 2, 3, 4, 5 (Mantidos conforme seu original...)
# ... (Código omitido para brevidade, mas deve ser mantido)

# 6. PRODUTOS (LAYOUT ESTILO HISTÓRICO)
with aba6:
    st.header("📦 Gerenciar Produtos")
    with st.expander("➕ Adicionar Novo"):
        cn = st.text_input("Nome").upper()
        cp = st.number_input("Preço", 0.0)
        ct = st.selectbox("Tipo", ["UN", "KG"])
        if st.button("Salvar Produto"):
            df_p = ler_aba("Produtos", 0)
            novo_p = pd.DataFrame([{"nome": cn, "preco": cp, "tipo": ct, "status": "Ativo"}])
            salvar_aba("Produtos", pd.concat([df_p, novo_p], ignore_index=True)); st.rerun()

    st.markdown("---")
    for idx, r in df_produtos.iterrows():
        ativo = r['status'] == "Ativo"
        cor = "#28a745" if ativo else "#6c757d"
        st.markdown(f"""
            <div class="card-prod" style="border-left:8px solid {cor};">
                <b>{r['nome']}</b> | R$ {parse_float(r['preco']):.2f} ({r['tipo']})<br>
                <small>Status: {r['status']}</small>
            </div>
        """, unsafe_allow_html=True)
        
        with st.expander(f"Editar {r['nome']}"):
            c1, c2, c3 = st.columns([2, 1, 1])
            en = c1.text_input("Nome", r['nome'], key=f"en_{idx}").upper()
            ep = c2.number_input("Preço", parse_float(r['preco']), key=f"ep_{idx}")
            es = c3.toggle("Ativo", value=ativo, key=f"es_{idx}")
            if st.button("Salvar Alterações", key=f"btn_{idx}"):
                df_produtos.at[idx, 'nome'], df_produtos.at[idx, 'preco'], df_produtos.at[idx, 'status'] = en, ep, ("Ativo" if es else "Inativo")
                salvar_aba("Produtos", df_produtos); st.rerun()
            if st.button("🗑️ Excluir", key=f"del_{idx}"):
                salvar_aba("Produtos", df_produtos.drop(idx)); st.rerun()
