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
    css_path = Path(__file__).with_name("styles.css")
    try:
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except: pass

aplicar_estilos()

conn = st.connection("gsheets", type=GSheetsConnection)
STATUS_PENDENTE = "pendente"
STATUS_PRONTO = "pronto"
PAGAMENTO_PAGO = "PAGO"
PAGAMENTO_A_PAGAR = "A PAGAR"

# --- FUNÇÕES DE UTILIDADE ---
def limpar_texto(texto):
    if not texto: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texto))
                   if unicodedata.category(c) != 'Mn')

def gerar_b64_etiqueta(cliente, endereco, valor, pagamento):
    largura = 32
    marca = "@dahortapmesa".center(largura)
    cli = limpar_texto(cliente).upper().center(largura)
    end = limpar_texto(endereco).upper().center(largura)
    val_txt = f"R$ {valor:.2f}"
    status_txt = "pago" if pagamento == PAGAMENTO_PAGO else ""
    if status_txt:
        espacos = largura - len(val_txt) - len(status_txt) - 2
        linha_final = f"{val_txt}{' ' * espacos}{status_txt}"
    else:
        linha_final = val_txt.center(largura)
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
        if aba == "Produtos" and "status" not in df.columns:
            df["status"] = "Ativo"
        return df.fillna("")
    except: return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    conn.reset()

# --- CARREGAR DADOS ---
df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

# --- HERO ---
st.markdown('<div class="hero-banner"><div class="hero-title">Horta Gestao</div></div>', unsafe_allow_html=True)

# --- ABAS ---
aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro", "📦 Produtos"])

# 1. NOVO PEDIDO (Filtrado apenas ativos)
with aba1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    st.header("🛒 Novo Pedido")
    
    # Filtro: Apenas produtos com status 'Ativo'
    prods_venda = df_produtos[df_produtos['status'].str.lower() == "ativo"]
    
    c1, c2, c3 = st.columns([2, 2, 1])
    n_cli = c1.text_input("Cliente", key=f"n_{f}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f}").upper()
    pg = c3.toggle("Pago?", key=f"p_{f}")
    o_ped = st.text_input("Observação", key=f"o_{f}")
    
    carrinho, total_v = [], 0.0
    for idx, r in prods_venda.iterrows():
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
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR, "obs": o_ped}])
            salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True))
            st.session_state.f_id += 1
            st.rerun()

# [ABAS 2, 3, 4, 5 MANTIDAS IGUAIS À VERSÃO ANTERIOR]

# 6. GERENCIAR PRODUTOS (COM ATIVAR/DESATIVAR)
with aba6:
    st.header("📦 Gerenciar Produtos")
    
    with st.expander("➕ Adicionar Novo Produto"):
        cn, cp, ct = st.columns([3, 1, 1])
        n_p = cn.text_input("Nome").upper()
        p_p = cp.number_input("Preço", 0.0)
        t_p = ct.selectbox("Tipo", ["UN", "KG"])
        if st.button("Salvar"):
            if n_p:
                df_p = ler_aba("Produtos", 0)
                novo_item = pd.DataFrame([{"nome": n_p, "preco": p_p, "tipo": t_p, "status": "Ativo"}])
                salvar_aba("Produtos", pd.concat([df_p, novo_item], ignore_index=True))
                st.rerun()

    st.markdown("---")
    st.subheader("Lista de Produtos")
    
    df_lista = ler_aba("Produtos", 0)
    for idx, r in df_lista.iterrows():
        # Cor de fundo para itens desativados
        ativo = r['status'].lower() == "ativo"
        bg_color = "#ffffff" if ativo else "#f0f0f0"
        
        with st.container():
            st.markdown(f'<div style="background:{bg_color}; padding:10px; border-radius:5px; margin-bottom:5px; border:1px solid #ddd;">', unsafe_allow_html=True)
            c1, c2, c3, c4, c5, c6 = st.columns([2.5, 1, 1, 1.5, 0.6, 0.6])
            
            e_nome = c1.text_input("N", r['nome'], key=f"en_{idx}", label_visibility="collapsed").upper()
            e_prec = c2.number_input("R$", parse_float(r['preco']), key=f"ep_{idx}", label_visibility="collapsed")
            e_tipo = c3.selectbox("T", ["UN", "KG"], index=0 if r['tipo']=="UN" else 1, key=f"et_{idx}", label_visibility="collapsed")
            
            # Switch de Ativo/Inativo
            e_stat = c4.toggle("Ativo", value=ativo, key=f"es_{idx}")
            
            if c5.button("💾", key=f"sv_{idx}"):
                df_lista.at[idx, 'nome'] = e_nome
                df_lista.at[idx, 'preco'] = e_prec
                df_lista.at[idx, 'tipo'] = e_tipo
                df_lista.at[idx, 'status'] = "Ativo" if e_stat else "Inativo"
                salvar_aba("Produtos", df_lista)
                st.rerun()
                
            if c6.button("🗑️", key=f"dl_{idx}"):
                df_lista = df_lista.drop(idx)
                salvar_aba("Produtos", df_lista)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<br><br><br><br>", unsafe_allow_html=True) # Respiro para o Manage App
