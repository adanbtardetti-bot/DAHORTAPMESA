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

def limpar_texto(texto):
    if not texto: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn')

def gerar_b64_etiqueta(cliente, endereco, valor, pagamento):
    largura = 32
    marca = "@dahortapmesa".center(largura)
    cli = limpar_texto(cliente).upper().center(largura)
    end = limpar_texto(endereco).upper().center(largura)
    val_txt = f"R$ {valor:.2f}"
    status_txt = "pago" if pagamento == "PAGO" else ""
    espacos = max(1, largura - len(val_txt) - len(status_txt) - 2)
    linha_final = f"{val_txt}{' ' * espacos}{status_txt}"
    corpo = f"{marca}\n\n{cli}\n\n{end}\n\n{linha_final}"
    return base64.b64encode(corpo.encode('ascii', 'ignore')).decode()

def parse_float(val):
    try: return float(str(val).strip().replace(",", "."))
    except: return 0.0

# CORREÇÃO DO TRAVAMENTO (RESOURCE_EXHAUSTED)
def ler_aba(aba, ttl=10):
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty:
            cols = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]
            if aba == "Produtos": cols = ["id", "nome", "preco", "tipo", "status"]
            return pd.DataFrame(columns=cols)
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna("")
    except:
        return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
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
    n_cli, e_cli = c1.text_input("Cliente", key=f"n_{f}").upper(), c2.text_input("Endereço", key=f"e_{f}").upper()
    pg, o_ped = c3.toggle("Pago?", key=f"p_{f}"), st.text_input("Observação", key=f"o_{f}").upper()
    carrinho, total_v = [], 0.0
    if not df_produtos.empty:
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
            salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True)); st.session_state.f_id += 1; st.rerun()

# --- 2. COLHEITA ---
with aba2:
    st.header("🚜 Colheita")
    if not df_pedidos.empty:
        pend = df_pedidos[df_pedidos["status"].str.lower() == "pendente"]
        if not pend.empty:
            res = {}
            for _, p in pend.iterrows():
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it['tipo']})"
                    res[k] = res.get(k, 0) + it['qtd']
            for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")
            txt_z = "*LISTA DE COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res.items()])
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_z)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)

# --- 3. MONTAGEM ---
with aba3:
    st.header("⚖️ Montagem")
    if not df_pedidos.empty:
        pend_m = df_pedidos[df_pedidos["status"].str.lower() == "pendente"]
        for _, row in pend_m.iterrows():
            stpg = str(row.get("pagamento")).upper()
            with st.expander(f"👤 {row['cliente']} | {stpg}", expanded=True):
                st.write(f"📍 {row['endereco']}")
                itens_m, total_m = json.loads(row['itens']), 0.0
                for i, it in enumerate(itens_m):
                    c_i, c_v = st.columns([3.5, 1.4])
                    if str(it['tipo']).upper() == "KG":
                        # AQUI VOCÊ LANÇA O PESO/VALOR
                        it['subtotal'] = c_v.number_input("R$", 0.0, key=f"m_{row['id']}_{i}", label_visibility="collapsed")
                        c_i.markdown(f"⚖️ {it['nome']}")
                    else:
                        c_i.markdown(f"✅ {it['qtd']}x {it['nome']}")
                        c_v.markdown(f"R$ {parse_float(it['subtotal']):.2f}")
                    total_m += parse_float(it['subtotal'])
                st.markdown(f"<div class='m-total'>TOTAL: R$ {total_m:.2f}</div>", unsafe_allow_html=True)
                c_ok, c_pg, c_pr, c_del = st.columns([1, 1, 0.5, 0.5])
                if c_ok.button("📦 OK", key=f"ok_{row['id']}"):
                    df_f = ler_aba("Pedidos", ttl=0); idx = df_f.index[df_f["id"].astype(str) == str(row["id"])][0]
                    df_f.at[idx, "status"], df_f.at[idx, "total"], df_f.at[idx, "itens"] = "pronto", total_m, json.dumps(itens_m)
                    salvar_aba("Pedidos", df_f); st.rerun()
                if stpg != "PAGO" and c_pg.button("💵 Pago", key=f"pg_{row['id']}"):
                    df_f = ler_aba("Pedidos", ttl=0); df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = "PAGO"; salvar_aba("Pedidos", df_f); st.rerun()
                b64 = gerar_b64_etiqueta(row['cliente'], row['endereco'], total_m, stpg)
                c_pr.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️</a>', unsafe_allow_html=True)

# --- 4. HISTÓRICO (CORRIGIDO PARA MOSTRAR VALORES) ---
with aba4:
    st.header("📜 Histórico")
    d_sel = st.date_input("Filtrar data:", datetime.now()).strftime("%d/%m/%Y")
    if not df_pedidos.empty:
        hist = df_pedidos[(df_pedidos["status"] == "pronto") & (df_pedidos["data"] == d_sel)].sort_values("id", ascending=False)
        for _, row in hist.iterrows():
            st.markdown(f"👤 **{row['cliente']}** - R$ {row['total']}")
            with st.expander("📋 Detalhes"):
                # MOSTRAR VALORES NO HISTÓRICO
                for it in json.loads(row['itens']):
                    st.write(f"• {it['qtd']}x {it['nome']}: R$ {parse_float(it.get('subtotal', 0)):.2f}")

# --- 5. FINANCEIRO (CORRIGIDO PARA MOSTRAR PESO/KG) ---
with aba5:
    st.header("💰 Financeiro")
    menu = st.radio("Relatório:", ["Dia", "Período", "Seleção Manual"], horizontal=True)
    def gerar_tabela_fin(df_res, t_zap="RELATÓRIO"):
        v_total = df_res['total'].apply(parse_float).sum()
        st.metric("Faturamento", f"R$ {v_total:.2f}")
        res = {}
        for _, r in df_res.iterrows():
            for it in json.loads(r['itens']):
                n = it['nome']
                if n not in res: res[n] = {"qtd": 0, "val": 0.0}
                res[n]["qtd"] += it['qtd']; res[n]["val"] += parse_float(it.get('subtotal', 0))
        # TABELA MOSTRANDO PESO E VALOR
        st.table(pd.DataFrame([{"Produto": k, "Qtd/Peso": v["qtd"], "Total": f"{v['val']:.2f}"} for k, v in res.items()]))

    if not df_pedidos.empty:
        if menu == "Dia": gerar_tabela_fin(df_pedidos[df_pedidos["data"] == datetime.now().strftime("%d/%m/%Y")], "DIA")

# --- 6. PRODUTOS ---
with aba6:
    st.header("📦 Produtos")
    if not df_produtos.empty:
        for idx, r in df_produtos.iterrows():
            st.write(f"{r['nome']} | R$ {r['preco']} | {r['tipo']}")
