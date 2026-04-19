import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
import unicodedata
from datetime import datetime, timedelta

# --- CONFIGURAÇÕES ---
st.set_page_config(page_title="Horta Gestão", page_icon="🥬", layout="wide")

# SEU LAYOUT ORIGINAL (CSS RESTAURADO)
st.markdown("""
    <style>
        .hero-banner {background-color: #0f1d12; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px;}
        .btn-zap {background-color: #25d366; color: white !important; padding: 10px; border-radius: 5px; text-decoration: none; display: block; text-align: center; font-weight: bold;}
        .btn-print {text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; color:black; border:1px solid #ddd;}
    </style>
""", unsafe_allow_html=True)

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
        if aba == "Produtos" and "status" not in df.columns: df["status"] = "Ativo"
        return df.fillna("")
    except: return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    conn.reset()

# --- DADOS ---
df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

st.markdown('<div class="hero-banner"><h1>🥬 Horta Gestão</h1></div>', unsafe_allow_html=True)

aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro", "📦 Produtos"])

# 1. NOVO
with aba1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    prods_venda = df_produtos[df_produtos['status'].str.lower() == "ativo"]
    c1, c2, c3 = st.columns([2, 2, 1])
    n_cli = c1.text_input("Cliente", key=f"n_{f}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f}").upper()
    pg = c3.toggle("Pago?", key=f"p_{f}")
    carrinho, total_v = [], 0.0
    for idx, r in prods_venda.iterrows():
        col_n, col_p, col_q = st.columns([3.4, 1.3, 1.1])
        col_n.markdown(f"**{r['nome']}**")
        qtd = col_q.number_input("Q", 0, step=1, key=f"q_{idx}_{f}", label_visibility="collapsed")
        if qtd > 0:
            p_u = parse_float(r['preco'])
            sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
            total_v += sub
            carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": r['tipo']})
    if st.button("💾 SALVAR", type="primary", use_container_width=True):
        if n_cli and carrinho:
            df_at = ler_aba("Pedidos", ttl=0)
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": STATUS_PENDENTE, "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR}])
            salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True))
            st.session_state.f_id += 1; st.rerun()

# 2. COLHEITA
with aba2:
    pend = df_pedidos[df_pedidos["status"].str.lower() == STATUS_PENDENTE]
    if not pend.empty:
        res = {}
        for _, p in pend.iterrows():
            for it in json.loads(p['itens']):
                k = f"{it['nome']} ({it['tipo']})"
                res[k] = res.get(k, 0) + it['qtd']
        for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")
        msg = "*LISTA DE COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res.items()])
        st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(msg)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)

# 3. MONTAGEM
with aba3:
    pend_m = df_pedidos[df_pedidos["status"].str.lower() == STATUS_PENDENTE]
    for _, row in pend_m.iterrows():
        with st.expander(f"👤 {row['cliente']}", expanded=True):
            itens_m = json.loads(row['itens'])
            total_m = 0.0
            for i, it in enumerate(itens_m):
                c_i, c_v = st.columns([3.5, 1.4])
                if str(it['tipo']).upper() == "KG":
                    it['subtotal'] = c_v.number_input(f"R$ {it['nome']}", 0.0, key=f"m_{row['id']}_{i}")
                else:
                    c_v.write(f"R$ {parse_float(it['subtotal']):.2f}")
                total_m += parse_float(it['subtotal'])
                c_i.write(f"✅ {it['qtd']}x {it['nome']}")
            st.write(f"**TOTAL: R$ {total_m:.2f}**")
            c_ok, c_pg, c_pr, c_del = st.columns([1, 1, 0.5, 0.5])
            if c_ok.button("📦 OK", key=f"ok_{row['id']}"):
                df_f = ler_aba("Pedidos", 0); idx = df_f.index[df_f["id"].astype(str) == str(row["id"])][0]
                df_f.at[idx, "status"], df_f.at[idx, "total"], df_f.at[idx, "itens"] = STATUS_PRONTO, total_m, json.dumps(itens_m)
                salvar_aba("Pedidos", df_f); st.rerun()
            if c_pg.button("💵 Pago", key=f"pg_{row['id']}"):
                df_f = ler_aba("Pedidos", 0); df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO
                salvar_aba("Pedidos", df_f); st.rerun()
            b64 = gerar_b64_etiqueta(row['cliente'], row['endereco'], total_m, row['pagamento'])
            c_pr.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️</a>', unsafe_allow_html=True)
            if c_del.button("🗑️", key=f"del_{row['id']}"):
                df_f = ler_aba("Pedidos", 0); df_f = df_f[df_f["id"].astype(str) != str(row["id"])]; salvar_aba("Pedidos", df_f); st.rerun()

# 4. HISTÓRICO (LAYOUT ORIGINAL)
with aba4:
    d_sel = st.date_input("Filtrar data:", datetime.now()).strftime("%d/%m/%Y")
    hist = df_pedidos[(df_pedidos["status"].str.lower() == STATUS_PRONTO) & (df_pedidos["data"] == d_sel)].sort_values("id", ascending=False)
    for _, row in hist.iterrows():
        pago = str(row.get("pagamento")).upper() == PAGAMENTO_PAGO
        cor = "#28a745" if pago else "#dc3545"
        st.markdown(f"""
            <div style="background-color:white; border-radius:10px; padding:15px; border-left:10px solid {cor}; color:black; margin-bottom:10px;">
                <div style="font-size:18px;">👤 <b>{row['cliente']}</b> | {row['pagamento']}</div>
                <div style="color:#555;">📍 {row['endereco']}</div>
                <div style="font-size:20px; font-weight:bold; margin-top:5px;">R$ {parse_float(row['total']):.2f}</div>
            </div>
        """, unsafe_allow_html=True)
        col_h1, col_h2 = st.columns(2)
        b64_h = gerar_b64_etiqueta(row['cliente'], row['endereco'], parse_float(row['total']), row['pagamento'])
        col_h1.markdown(f'<a href="intent:base64,{b64_h}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️ Reimprimir</a>', unsafe_allow_html=True)
        if not pago:
            if col_h2.button("💵 Marcar Pago", key=f"hpay_{row['id']}", use_container_width=True):
                df_f = ler_aba("Pedidos", 0); df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO
                salvar_aba("Pedidos", df_f); st.rerun()
        with st.expander("📋 Detalhes"):
            for it in json.loads(row['itens']): st.write(f"• {it['qtd']}x {it['nome']}")

# 5. FINANCEIRO
with aba5:
    menu = st.radio("Relatório:", ["Dia", "Período", "Seleção Manual"], horizontal=True)
    if menu == "Seleção Manual":
        d_g = st.date_input("Data:", datetime.now()).strftime("%d/%m/%Y")
        df_d = df_pedidos[df_pedidos["data"] == d_g]
        sel = [r for i, r in df_d.iterrows() if st.checkbox(f"👤 {r['cliente']} | R$ {r['total']}", key=f"f_{r['id']}")]
        if sel:
            df_sel = pd.DataFrame(sel)
            st.metric("Total", f"R$ {df_sel['total'].apply(parse_float).sum():.2f}")
            res = {}
            for _, r in df_sel.iterrows():
                for it in json.loads(r['itens']):
                    n = it['nome']
                    if n not in res: res[n] = {"q": 0, "v": 0.0}
                    res[n]["q"] += it['qtd']; res[n]["v"] += parse_float(it.get('subtotal', 0))
            st.table(pd.DataFrame([{"Produto": k, "Qtd": v["q"], "Total": f"{v['v']:.2f}"} for k, v in res.items()]))

# 6. PRODUTOS (ATIVAR/DESATIVAR)
with aba6:
    with st.expander("➕ Adicionar"):
        cn = st.text_input("Nome")
        if st.button("Salvar"):
            df_p = ler_aba("Produtos", 0); novo_p = pd.DataFrame([{"nome": cn.upper(), "preco": 0, "tipo": "UN", "status": "Ativo"}])
            salvar_aba("Produtos", pd.concat([df_p, novo_p], ignore_index=True)); st.rerun()
    df_l = ler_aba("Produtos", 0)
    for idx, r in df_l.iterrows():
        c1, c2, c3, c4 = st.columns([3, 1, 0.5, 0.5])
        c1.write(f"**{r['nome']}**")
        est = c2.toggle("Ativo", value=(r['status'] == "Ativo"), key=f"s_{idx}")
        if c3.button("💾", key=f"sv_{idx}"):
            df_l.at[idx, 'status'] = "Ativo" if est else "Inativo"; salvar_aba("Produtos", df_l); st.rerun()
        if c4.button("🗑️", key=f"dl_{idx}"):
            salvar_aba("Produtos", df_l.drop(idx)); st.rerun()
