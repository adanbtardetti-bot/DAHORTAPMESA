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
            .m-total {font-size: 20px; font-weight: bold; margin-top: 10px; color: #1e1e1e;}
        </style>
    """, unsafe_allow_html=True)

aplicar_estilos()

conn = st.connection("gsheets", type=GSheetsConnection)

STATUS_PENDENTE = "pendente"
STATUS_PRONTO = "pronto"
PAGAMENTO_PAGO = "PAGO"
PAGAMENTO_A_PAGAR = "A PAGAR"

# --- FUNÇÕES DE UTILIDADE ---
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
    espacos = max(1, largura - len(val_txt) - len(status_txt) - 2)
    linha_final = f"{val_txt}{' ' * espacos}{status_txt}"
    corpo = f"{marca}\n\n{cli}\n\n{end}\n\n{linha_final}"
    return base64.b64encode(corpo.encode('ascii', 'ignore')).decode()

def parse_float(val):
    try: return float(str(val).strip().replace(",", "."))
    except: return 0.0

# --- LEITURA COM CACHE PARA EVITAR ERRO DE COTA ---
def ler_aba(aba, ttl=5):
    try:
        # ttl=5 garante que o app espere 5 segundos antes de pedir o dado novo pro Google
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty:
            cols = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]
            if aba == "Produtos": cols = ["id", "nome", "preco", "tipo", "status"]
            return pd.DataFrame(columns=cols)
        
        df.columns = [str(c).lower().strip() for c in df.columns]
        if aba == "Produtos" and "status" not in df.columns:
            df["status"] = "Ativo"
        return df.fillna("")
    except Exception:
        st.warning("Aguardando liberação do Google (Cota excedida). Tente novamente em alguns segundos.")
        return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    # Limpa o cache após salvar para que o usuário veja a mudança imediatamente
    st.cache_data.clear()

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
        prods_ativos = df_produtos[df_produtos['status'].astype(str).str.lower() != "inativo"]
        for idx, r in prods_ativos.iterrows():
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

# --- 2. COLHEITA ---
with aba2:
    st.header("🚜 Colheita")
    if not df_pedidos.empty and "status" in df_pedidos.columns:
        pend = df_pedidos[df_pedidos["status"].str.lower() == STATUS_PENDENTE]
        if not pend.empty:
            res = {}
            for _, p in pend.iterrows():
                try:
                    for it in json.loads(p['itens']):
                        k = f"{it['nome']} ({it['tipo']})"
                        res[k] = res.get(k, 0) + it['qtd']
                except: continue
            for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")
            txt_z = "*LISTA DE COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res.items()])
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_z)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)

# --- 3. MONTAGEM ---
with aba3:
    st.header("⚖️ Montagem")
    if not df_pedidos.empty and "status" in df_pedidos.columns:
        pend_m = df_pedidos[df_pedidos["status"].str.lower() == STATUS_PENDENTE]
        for _, row in pend_m.iterrows():
            stpg = str(row.get("pagamento")).upper()
            with st.expander(f"👤 {row['cliente']} | {stpg}", expanded=True):
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
                c_ok, c_pg, c_pr, c_del = st.columns([1, 1, 0.5, 0.5])
                if c_ok.button("📦 OK", key=f"ok_{row['id']}"):
                    df_f = ler_aba("Pedidos", ttl=0)
                    idx = df_f.index[df_f["id"].astype(str) == str(row["id"])][0]
                    df_f.at[idx, "status"], df_f.at[idx, "total"], df_f.at[idx, "itens"] = STATUS_PRONTO, total_m, json.dumps(itens_m)
                    salvar_aba("Pedidos", df_f); st.rerun()
                b64 = gerar_b64_etiqueta(row['cliente'], row['endereco'], total_m, stpg)
                c_pr.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️</a>', unsafe_allow_html=True)

# --- 4. HISTÓRICO ---
with aba4:
    st.header("📜 Histórico")
    d_sel = st.date_input("Filtrar data:", datetime.now()).strftime("%d/%m/%Y")
    if not df_pedidos.empty:
        hist = df_pedidos[(df_pedidos["status"].str.lower() == STATUS_PRONTO) & (df_pedidos["data"] == d_sel)]
        for _, row in hist.iterrows():
            with st.expander(f"👤 {row['cliente']} | R$ {row['total']}"):
                for it in json.loads(row['itens']): 
                    st.write(f"• {it['qtd']}x {it['nome']}: R$ {parse_float(it.get('subtotal')):.2f}")

# --- 5. FINANCEIRO ---
with aba5:
    st.header("💰 Financeiro")
    menu = st.radio("Relatório:", ["Dia", "Período"], horizontal=True)
    if menu == "Dia":
        df_dia = df_pedidos[df_pedidos["data"] == datetime.now().strftime("%d/%m/%Y")]
        v_t = df_dia['total'].apply(parse_float).sum()
        st.metric("Total Hoje", f"R$ {v_t:.2f}")

# --- 6. PRODUTOS ---
with aba6:
    st.header("📦 Produtos")
    with st.expander("➕ Adicionar Novo Produto"):
        c_n, c_p, c_t = st.columns([3, 1, 1])
        n_p = c_n.text_input("Nome").upper()
        p_p = c_p.number_input("Preço", 0.0)
        t_p = c_t.selectbox("Tipo", ["UN", "KG"])
        if st.button("SALVAR PRODUTO", type="primary"):
            df_p = ler_aba("Produtos", 0)
            novo_p = pd.DataFrame([{"nome": n_p, "preco": p_p, "tipo": t_p, "status": "Ativo"}])
            salvar_aba("Produtos", pd.concat([df_p, novo_p], ignore_index=True))
            st.rerun()

    if not df_produtos.empty:
        for idx, r in df_produtos.iterrows():
            c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 1])
            en = c1.text_input("N", r['nome'], key=f"en_{idx}", label_visibility="collapsed").upper()
            ep = c2.number_input("R$", parse_float(r['preco']), key=f"ep_{idx}", label_visibility="collapsed")
            et = c3.selectbox("T", ["UN", "KG"], index=0 if r['tipo']=="UN" else 1, key=f"et_{idx}", label_visibility="collapsed")
            if c4.button("💾", key=f"sv_{idx}"):
                df_produtos.at[idx, 'nome'], df_produtos.at[idx, 'preco'], df_produtos.at[idx, 'tipo'] = en, ep, et
                salvar_aba("Produtos", df_produtos); st.rerun()
            if c5.button("🗑️", key=f"dl_{idx}"):
                salvar_aba("Produtos", df_produtos.drop(idx)); st.rerun()
