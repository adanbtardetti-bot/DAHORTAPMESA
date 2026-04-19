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
aba1, aba2, aba3, aba4, aba5 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro"])

# 1. NOVO PEDIDO
with aba1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    st.header("🛒 Novo Pedido")
    c1, c2, c3 = st.columns([2, 2, 1])
    n_cli = c1.text_input("Cliente", key=f"n_{f}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f}").upper()
    pg = c3.toggle("Pago?", key=f"p_{f}")
    o_ped = st.text_input("Observação", key=f"o_{f}")
    
    carrinho, total_v = [], 0.0
    for idx, r in df_produtos.iterrows():
        col_n, col_p, col_q = st.columns([3.4, 1.3, 1.1])
        col_n.markdown(f"**{r['nome']}**")
        col_p.caption(f"R$ {r['preco']} / {r['tipo']}")
        qtd = col_q.number_input("Q", 0, step=1, key=f"q_{idx}_{f}", label_visibility="collapsed")
        if qtd > 0:
            p_u = parse_float(r['preco'])
            sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
            total_v += sub
            carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": r['tipo']})
    
    if st.button("💾 SALVAR PEDIDO", type="primary", use_container_width=True):
        if n_cli and carrinho:
            df_at = ler_aba("Pedidos", ttl=0)
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR, "obs": o_ped}])
            salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True))
            st.session_state.f_id += 1
            st.rerun()

# 2. COLHEITA
with aba2:
    st.header("🚜 Colheita")
    pend = df_pedidos[df_pedidos["status"] == STATUS_PENDENTE]
    if not pend.empty:
        res = {}
        for _, p in pend.iterrows():
            for it in json.loads(p['itens']):
                k = f"{it['nome']} ({it['tipo']})"
                res[k] = res.get(k, 0) + it['qtd']
        for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")

# 3. MONTAGEM
with aba3:
    st.header("⚖️ Montagem")
    pend_m = df_pedidos[df_pedidos["status"] == STATUS_PENDENTE]
    for _, row in pend_m.iterrows():
        stpg = str(row.get("pagamento")).upper()
        with st.expander(f"👤 {row['cliente']} | {stpg}"):
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
            
            c_ok, c_pg, c_pr = st.columns([1, 1, 1])
            if c_ok.button("📦 OK", key=f"ok_{row['id']}"):
                df_f = ler_aba("Pedidos", ttl=0)
                idx = df_f.index[df_f["id"].astype(str) == str(row["id"])][0]
                df_f.at[idx, "status"], df_f.at[idx, "total"], df_f.at[idx, "itens"] = STATUS_PRONTO, total_m, json.dumps(itens_m)
                salvar_aba("Pedidos", df_f); st.rerun()
            if stpg != PAGAMENTO_PAGO:
                if c_pg.button("💵 Pago", key=f"pg_{row['id']}"):
                    df_f = ler_aba("Pedidos", ttl=0)
                    df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO
                    salvar_aba("Pedidos", df_f); st.rerun()
            b64 = gerar_b64_etiqueta(row['cliente'], row['endereco'], total_m, stpg)
            c_pr.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️</a>', unsafe_allow_html=True)

# 4. HISTÓRICO
with aba4:
    st.header("📜 Histórico")
    d_sel = st.date_input("Data:", datetime.now()).strftime("%d/%m/%Y")
    hist = df_pedidos[(df_pedidos["status"] == STATUS_PRONTO) & (df_pedidos["data"] == d_sel)]
    for _, row in hist.iterrows():
        st.write(f"👤 **{row['cliente']}** - R$ {parse_float(row['total']):.2f} ({row['pagamento']})")
        with st.expander("Ver Itens"):
            for it in json.loads(row['itens']): st.write(f"• {it['qtd']}x {it['nome']}")

# 5. FINANCEIRO (NOVO)
with aba5:
    st.header("💰 Financeiro")
    opcao = st.radio("Escolha o relatório:", ["Hoje", "Período", "Relatório de Grupo"], horizontal=True)

    if opcao == "Hoje":
        hoje = datetime.now().strftime("%d/%m/%Y")
        df_hoje = df_pedidos[df_pedidos["data"] == hoje]
        v_total = 0.0
        itens_hoje = {}
        for _, r in df_hoje.iterrows():
            v_total += parse_float(r['total'])
            for it in json.loads(r['itens']):
                itens_hoje[it['nome']] = itens_hoje.get(it['nome'], 0) + it['qtd']
        st.metric("Total Hoje", f"R$ {v_total:.2f}")
        for k, v in itens_hoje.items(): st.write(f"• {v}x {k}")

    elif opcao == "Período":
        c1, c2 = st.columns(2)
        ini, fim = c1.date_input("Início", datetime.now() - timedelta(days=7)), c2.date_input("Fim", datetime.now())
        df_pedidos['dt_obj'] = pd.to_datetime(df_pedidos['data'], format='%d/%m/%Y').dt.date
        df_per = df_pedidos[(df_pedidos['dt_obj'] >= ini) & (df_pedidos['dt_obj'] <= fim)]
        total_per = df_per['total'].apply(parse_float).sum()
        st.metric("Total Período", f"R$ {total_per:.2f}")
        res_p = {}
        for _, r in df_per.iterrows():
            for it in json.loads(r['itens']):
                res_p[it['nome']] = res_p.get(it['nome'], 0) + it['qtd']
        st.table(pd.DataFrame([{"Item": k, "Qtd": v} for k, v in res_p.items()]))

    elif opcao == "Relatório de Grupo":
        st.write("Selecione os pedidos:")
        selecionados = []
        for i, row in df_pedidos.tail(15).iterrows():
            if st.checkbox(f"👤 {row['cliente']} | R$ {row['total']} | {row['data']}", key=f"g_{row['id']}"):
                selecionados.append(row)
        if selecionados:
            df_g = pd.DataFrame(selecionados)
            st.metric("Total Grupo", f"R$ {df_g['total'].apply(parse_float).sum():.2f}")
            res_g = {}
            for _, r in df_g.iterrows():
                for it in json.loads(r['itens']):
                    res_g[it['nome']] = res_g.get(it['nome'], 0) + it['qtd']
            for k, v in res_g.items(): st.write(f"• {v}x {k}")
