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
    # Mantendo o CSS para garantir o visual de cards e botões
    st.markdown("""
        <style>
            .hero-banner {background-color: #2e7d32; color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;}
            .total-badge {background: #e8f5e9; padding: 10px; border-radius: 5px; font-weight: bold; color: #2e7d32; border: 1px solid #2e7d32;}
            .btn-zap {background-color: #25d366; color: white !important; padding: 10px; border-radius: 5px; text-decoration: none; display: block; text-align: center; font-weight: bold;}
            .btn-print {background-color: #f0f2f6; border: 1px solid #ddd; padding: 5px; border-radius: 5px; cursor: pointer;}
            .m-total {font-size: 20px; font-weight: bold; color: #2e7d32; margin: 10px 0;}
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
    linha_final = f"{val_txt}  {status_txt}".center(largura)
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

# --- CARREGAR DADOS ---
df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

st.markdown('<div class="hero-banner"><h1>🥬 Horta Gestão</h1></div>', unsafe_allow_html=True)

# --- ABAS ---
aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro", "📦 Produtos"])

# 1. NOVO PEDIDO
with aba1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
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
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": STATUS_PENDENTE, "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR, "obs": o_ped}])
            salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True))
            st.session_state.f_id += 1; st.rerun()

# 2. COLHEITA (Restaurado)
with aba2:
    st.header("🚜 Lista de Colheita")
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
        msg_c = "*LISTA DE COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res.items()])
        st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(msg_c)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)
    else: st.info("Nenhum pedido pendente para colheita.")

# 3. MONTAGEM (Restaurado com Reimprimir e Excluir)
with aba3:
    st.header("⚖️ Montagem de Pedidos")
    pend_m = df_pedidos[df_pedidos["status"].str.lower() == STATUS_PENDENTE]
    for _, row in pend_m.iterrows():
        stpg = str(row.get("pagamento")).upper()
        with st.expander(f"👤 {row['cliente']} | {stpg}", expanded=True):
            itens_m = json.loads(row['itens'])
            total_m = 0.0
            for i, it in enumerate(itens_m):
                c_i, c_v = st.columns([3.5, 1.4])
                if str(it['tipo']).upper() == "KG":
                    it['subtotal'] = c_v.number_input(f"R$ {it['nome']}", 0.0, key=f"m_{row['id']}_{i}", label_visibility="collapsed")
                else: c_v.markdown(f"R$ {parse_float(it['subtotal']):.2f}")
                c_i.markdown(f"✅ {it['qtd']}x {it['nome']}")
                total_m += parse_float(it['subtotal'])
            st.markdown(f"<div class='m-total'>TOTAL: R$ {total_m:.2f}</div>", unsafe_allow_html=True)
            c_ok, c_pg, c_pr, c_del = st.columns([1, 1, 0.5, 0.5])
            if c_ok.button("📦 OK", key=f"ok_{row['id']}"):
                df_f = ler_aba("Pedidos", ttl=0)
                idx = df_f.index[df_f["id"].astype(str) == str(row["id"])][0]
                df_f.at[idx, "status"], df_f.at[idx, "total"], df_f.at[idx, "itens"] = STATUS_PRONTO, total_m, json.dumps(itens_m)
                salvar_aba("Pedidos", df_f); st.rerun()
            if c_pg.button("💵 Pago", key=f"pg_{row['id']}"):
                df_f = ler_aba("Pedidos", ttl=0)
                df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO
                salvar_aba("Pedidos", df_f); st.rerun()
            b64 = gerar_b64_etiqueta(row['cliente'], row['endereco'], total_m, stpg)
            c_pr.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️</a>', unsafe_allow_html=True)
            if c_del.button("🗑️", key=f"del_{row['id']}"):
                df_f = ler_aba("Pedidos", ttl=0)
                df_f = df_f[df_f["id"].astype(str) != str(row["id"])].reset_index(drop=True)
                salvar_aba("Pedidos", df_f); st.rerun()

# 4. HISTÓRICO (Restaurado Visual de Cards)
with aba4:
    st.header("📜 Histórico")
    d_sel = st.date_input("Filtrar data:", datetime.now()).strftime("%d/%m/%Y")
    hist = df_pedidos[(df_pedidos["status"].str.lower() == STATUS_PRONTO) & (df_pedidos["data"] == d_sel)].sort_values("id", ascending=False)
    if hist.empty: st.info(f"Sem pedidos em {d_sel}")
    else:
        for _, row in hist.iterrows():
            pago = str(row.get("pagamento")).upper() == PAGAMENTO_PAGO
            cor = "#28a745" if pago else "#dc3545"
            st.markdown(f"""
                <div style="background-color:white; border-radius:10px; padding:15px; border-left:8px solid {cor}; color:black; margin-bottom:5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <div style="display:flex; justify-content:space-between;"><b>👤 {row['cliente']}</b> <span>{row['pagamento']}</span></div>
                    <div style="color:gray; font-size:12px;">📍 {row['endereco']}</div>
                    <div style="font-size:18px; font-weight:bold; color:#2e7d32; margin-top:5px;">R$ {parse_float(row['total']):.2f}</div>
                </div>
            """, unsafe_allow_html=True)
            col_h1, col_h2 = st.columns(2)
            b64_h = gerar_b64_etiqueta(row['cliente'], row['endereco'], parse_float(row['total']), row['pagamento'])
            col_h1.markdown(f'<a href="intent:base64,{b64_h}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" style="text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; color:black; border:1px solid #ddd;">🖨️ Reimprimir</a>', unsafe_allow_html=True)
            if not pago:
                if col_h2.button("💵 Marcar Pago", key=f"hpay_{row['id']}", use_container_width=True):
                    df_f = ler_aba("Pedidos", ttl=0); df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO
                    salvar_aba("Pedidos", df_f); st.rerun()
            with st.expander("📋 Detalhes"):
                for it in json.loads(row['itens']): st.write(f"• {it['qtd']}x {it['nome']} - R$ {it.get('subtotal',0)}")

# 5. FINANCEIRO (Faturamento por Item)
with aba5:
    st.header("💰 Financeiro")
    menu = st.radio("Relatório:", ["Dia", "Período", "Seleção Manual"], horizontal=True)
    def gerar_fin(df_f):
        if df_f.empty: return st.warning("Sem dados.")
        t_g = df_f['total'].apply(parse_float).sum()
        st.metric("Total", f"R$ {t_g:.2f}")
        res = {}
        for _, r in df_f.iterrows():
            for it in json.loads(r['itens']):
                n = it['nome']
                if n not in res: res[n] = {"q": 0, "v": 0.0}
                res[n]["q"] += it['qtd']; res[n]["v"] += parse_float(it.get('subtotal', 0))
        tab = [{"Produto": k, "Qtd": v["q"], "Valor (R$)": f"{v['v']:.2f}"} for k, v in res.items()]
        st.table(pd.DataFrame(tab).sort_values("Valor (R$)", ascending=False))
        return t_g, res
    if menu == "Dia": gerar_fin(df_pedidos[df_pedidos["data"] == datetime.now().strftime("%d/%m/%Y")])
    elif menu == "Período":
        c1, c2 = st.columns(2); i, f = c1.date_input("De"), c2.date_input("Até")
        df_pedidos['dt_'] = pd.to_datetime(df_pedidos['data'], format='%d/%m/%Y', errors='coerce').dt.date
        gerar_fin(df_pedidos[(df_pedidos['dt_'] >= i) & (df_pedidos['dt_'] <= f)])
    elif menu == "Seleção Manual":
        d_g = st.date_input("Data:", datetime.now()).strftime("%d/%m/%Y")
        sel = [r for i, r in df_pedidos[df_pedidos["data"] == d_g].iterrows() if st.checkbox(f"{r['cliente']} (R$ {r['total']})", key=f"s_{r['id']}")]
        if sel:
            v_g, r_g = gerar_fin(pd.DataFrame(sel))
            txt = f"*RELATÓRIO GRUPO*\n" + "\n".join([f"- {v['q']}x {k}" for k, v in r_g.items()])
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)
    st.markdown("<br><br><br><br>", unsafe_allow_html=True)

# 6. PRODUTOS (Ativar/Desativar)
with aba6:
    st.header("📦 Produtos")
    with st.expander("➕ Novo Produto"):
        cn, cp, ct = st.columns([3, 1, 1])
        n_p = cn.text_input("Nome").upper()
        p_p = cp.number_input("Preço", 0.0)
        t_p = ct.selectbox("Tipo", ["UN", "KG"])
        if st.button("Adicionar"):
            if n_p:
                df_p = ler_aba("Produtos", 0)
                salvar_aba("Produtos", pd.concat([df_p, pd.DataFrame([{"nome": n_p, "preco": p_p, "tipo": t_p, "status": "Ativo"}])], ignore_index=True))
                st.rerun()
    st.markdown("---")
    df_l = ler_aba("Produtos", 0)
    for idx, r in df_l.iterrows():
        ativo = str(r.get('status', 'Ativo')).lower() == "ativo"
        with st.container():
            c1, c2, c3, c4, c5, c6 = st.columns([2, 1, 1, 1, 0.5, 0.5])
            e_n = c1.text_input("N", r['nome'], key=f"en_{idx}", label_visibility="collapsed").upper()
            e_p = c2.number_input("R$", parse_float(r['preco']), key=f"ep_{idx}", label_visibility="collapsed")
            e_t = c3.selectbox("T", ["UN", "KG"], index=0 if r['tipo']=="UN" else 1, key=f"et_{idx}", label_visibility="collapsed")
            e_s = c4.toggle("Ativo", value=ativo, key=f"es_{idx}")
            if c5.button("💾", key=f"sv_{idx}"):
                df_l.at[idx, 'nome'], df_l.at[idx, 'preco'], df_l.at[idx, 'tipo'], df_l.at[idx, 'status'] = e_n, e_p, e_t, ("Ativo" if e_s else "Inativo")
                salvar_aba("Produtos", df_l); st.rerun()
            if c6.button("🗑️", key=f"dl_{idx}"):
                salvar_aba("Produtos", df_l.drop(idx)); st.rerun()
