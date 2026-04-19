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

# Conexão e Constantes
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
        # Garante coluna status para desativar produtos
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
# Adicionada a aba "📦 Produtos"
aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro", "📦 Produtos"])

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
    # FILTRO: Mostra apenas produtos Ativos
    prods_ativos = df_produtos[df_produtos['status'] != "Inativo"]
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

# 2. COLHEITA
with aba2:
    st.header("🚜 Colheita")
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

# 3. MONTAGEM
with aba3:
    st.header("⚖️ Montagem")
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
            if stpg != PAGAMENTO_PAGO:
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

# 4. HISTÓRICO
with aba4:
    st.header("📜 Histórico")
    d_sel = st.date_input("Filtrar data:", datetime.now()).strftime("%d/%m/%Y")
    hist = df_pedidos[(df_pedidos["status"].str.lower() == STATUS_PRONTO) & (df_pedidos["data"] == d_sel)].sort_values("id", ascending=False)
    
    if hist.empty:
        st.info(f"Sem pedidos em {d_sel}")
    else:
        for _, row in hist.iterrows():
            pago = str(row.get("pagamento")).upper() == PAGAMENTO_PAGO
            cor = "#28a745" if pago else "#dc3545"
            st.markdown(f"""
            <div style="background-color:white; border-radius:10px; padding:15px; border-left:8px solid {cor}; color:black; margin-bottom:5px;">
                <b>👤 {row['cliente']}</b> | {row['pagamento']}<br>📍 {row['endereco']}<br><b>R$ {parse_float(row['total']):.2f}</b>
            </div>
            """, unsafe_allow_html=True)
            
            c_h1, c_h2 = st.columns(2)
            b64_h = gerar_b64_etiqueta(row['cliente'], row['endereco'], parse_float(row['total']), row['pagamento'])
            c_h1.markdown(f'<a href="intent:base64,{b64_h}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print" style="text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; color:black;">🖨️ Reimprimir</a>', unsafe_allow_html=True)
            if not pago:
                if c_h2.button("💵 Marcar Pago", key=f"hpay_{row['id']}", use_container_width=True):
                    df_f = ler_aba("Pedidos", ttl=0)
                    df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO
                    salvar_aba("Pedidos", df_f); st.rerun()
            with st.expander("📋 Detalhes"):
                for it in json.loads(row['itens']): st.write(f"• {it['qtd']}x {it['nome']}")

# 5. FINANCEIRO
with aba5:
    st.header("💰 Financeiro")
    menu = st.radio("Relatório:", ["Dia", "Período", "Seleção Manual"], horizontal=True)

    def gerar_tabela_fin(df_res):
        if df_res.empty:
            st.warning("Nenhum dado.")
            return 0, {}
        v_total = df_res['total'].apply(parse_float).sum()
        st.metric("Faturamento", f"R$ {v_total:.2f}")
        res = {}
        for _, r in df_res.iterrows():
            for it in json.loads(r['itens']):
                n = it['nome']
                if n not in res: res[n] = {"qtd": 0, "val": 0.0}
                res[n]["qtd"] += it['qtd']
                res[n]["val"] += parse_float(it.get('subtotal', 0))
        
        tab_dados = [{"Produto": k, "Qtd": v["qtd"], "Total (R$)": f"{v['val']:.2f}"} for k, v in res.items()]
        st.table(pd.DataFrame(tab_dados).sort_values("Total (R$)", ascending=False))
        return v_total, res

    if menu == "Dia":
        hoje = datetime.now().strftime("%d/%m/%Y")
        gerar_tabela_fin(df_pedidos[df_pedidos["data"] == hoje])
    elif menu == "Período":
        c1, c2 = st.columns(2)
        i, f = c1.date_input("De", datetime.now()-timedelta(days=7)), c2.date_input("Até", datetime.now())
        df_pedidos['dt_obj'] = pd.to_datetime(df_pedidos['data'], format='%d/%m/%Y', errors='coerce').dt.date
        gerar_tabela_fin(df_pedidos[(df_pedidos['dt_obj'] >= i) & (df_pedidos['dt_obj'] <= f)])
    elif menu == "Seleção Manual":
        d_g = st.date_input("Data dos pedidos:", datetime.now()).strftime("%d/%m/%Y")
        df_d = df_pedidos[df_pedidos["data"] == d_g]
        sel = []
        for i, r in df_d.iterrows():
            if st.checkbox(f"👤 {r['cliente']} | R$ {r['total']}", key=f"f_{r['id']}"): sel.append(r)
        if sel:
            st.markdown("---")
            v_g, r_g = gerar_tabela_fin(pd.DataFrame(sel))
            txt = f"*RELATÓRIO GRUPO ({d_g})*\nTotal: R$ {v_g:.2f}\n" + "\n".join([f"- {v['qtd']}x {k}: R$ {v['val']:.2f}" for k, v in r_g.items()])
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)
    
    st.markdown("<br><br><br><br>", unsafe_allow_html=True)

# 6. GERENCIAR PRODUTOS (Aba Nova seguindo seu layout)
with aba6:
    st.header("📦 Gerenciar Produtos")
    
    with st.expander("➕ Adicionar Novo"):
        c_n, c_p, c_t = st.columns([3, 1, 1])
        n_p = c_n.text_input("Nome").upper()
        p_p = c_p.number_input("Preço", 0.0)
        t_p = c_t.selectbox("Tipo", ["UN", "KG"])
        if st.button("SALVAR NOVO PRODUTO", type="primary", use_container_width=True):
            if n_p:
                df_p = ler_aba("Produtos", 0)
                novo_p = pd.DataFrame([{"nome": n_p, "preco": p_p, "tipo": t_p, "status": "Ativo"}])
                salvar_aba("Produtos", pd.concat([df_p, novo_p], ignore_index=True))
                st.rerun()

    st.markdown("---")
    df_l = ler_aba("Produtos", 0)
    for idx, r in df_l.iterrows():
        c1, c2, c3, c4, c5, c6 = st.columns([2.5, 1, 1, 1, 0.5, 0.5])
        
        en = c1.text_input("N", r['nome'], key=f"en_{idx}", label_visibility="collapsed").upper()
        ep = c2.number_input("R$", parse_float(r['preco']), key=f"ep_{idx}", label_visibility="collapsed")
        et = c3.selectbox("T", ["UN", "KG"], index=0 if r['tipo']=="UN" else 1, key=f"et_{idx}", label_visibility="collapsed")
        
        # Ativar/Desativar
        status_ativo = (r['status'] == "Ativo")
        est = c4.toggle("Ativo", value=status_ativo, key=f"es_{idx}")
        
        if c5.button("💾", key=f"sv_{idx}"):
            df_l.at[idx, 'nome'] = en
            df_l.at[idx, 'preco'] = ep
            df_l.at[idx, 'tipo'] = et
            df_l.at[idx, 'status'] = "Ativo" if est else "Inativo"
            salvar_aba("Produtos", df_l)
            st.rerun()
            
        if c6.button("🗑️", key=f"dl_{idx}"):
            salvar_aba("Produtos", df_l.drop(idx))
            st.rerun()
    st.markdown("<br><br><br><br>", unsafe_allow_html=True)
