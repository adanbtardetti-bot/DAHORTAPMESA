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
            .btn-print {text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:12px; border-radius:8px; color:black; border:1px solid #ddd; font-size:20px;}
            .total-badge {background:#f0f2f6; padding:10px; border-radius:5px; font-weight:bold; margin-bottom:10px; color:black;}
            .m-total {font-size: 22px; font-weight: bold; margin-top: 10px; color: #1e1e1e;}
            hr {margin: 0.5rem 0 !important; border-bottom: 1px solid rgba(49, 51, 63, 0.2) !important;}
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
    return "".join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn').replace("*", "")

def formatar_pix(valor):
    v_str = f"{valor:.2f}"
    len_v = str(len(v_str)).zfill(2)
    pix_base = "00020126360014BR.GOV.BCB.PIX0114+5551997491035520400005303"
    pix_fim = "5802BR5925Adan Junior Bonetti Tarde6009SAO PAULO62140510rltaxjp45D6304"
    return f"{pix_base}{len_v}{v_str}{pix_fim}"

def gerar_b64_etiqueta_dupla(cliente, endereco, valor, pagamento):
    largura = 32
    negrito_on = "\x1b\x45\x01"
    negrito_off = "\x1b\x45\x00"
    
    # --- ETIQUETA 1: DADOS DO PEDIDO ---
    e1 = "\n\n" 
    e1 += f"{'@dahortapmesa'.center(largura)}\n\n" # Corrigido: adicionado aspas
    e1 += f"{limpar_texto(cliente).upper().center(largura)}\n"
    e1 += f"{limpar_texto(endereco).upper().center(largura)}\n\n"
    
    txt_val = f"R$ {valor:.2f} ({pagamento})".center(largura)
    e1 += f"{negrito_on}{txt_val}{negrito_off}\n\n\n"

    if pagamento == PAGAMENTO_PAGO:
        return base64.b64encode(e1.encode('ascii', 'ignore')).decode()

    # --- ETIQUETA 2: APENAS QR CODE (Para Pedidos A PAGAR) ---
    pix_code = formatar_pix(valor)
    e2 = "\n" 
    e2 += f"{'PAGAMENTO PIX'.center(largura)}\n"
    e2 += f"{negrito_on}{('R$ ' + f'{valor:.2f}').center(largura)}{negrito_off}\n"
    e2 += f"[qr]{pix_code}[/qr]\n\n\n"
    
    conteudo_total = e1 + e2
    return base64.b64encode(conteudo_total.encode('ascii', 'ignore')).decode()

def parse_float(val):
    try: return float(str(val).strip().replace(",", "."))
    except: return 0.0

def ler_aba(aba, ttl=0):
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty:
            cols = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]
            if aba == "Produtos": cols = ["id", "nome", "preco", "tipo", "status"]
            return pd.DataFrame(columns=cols)
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    conn.reset()

# --- CARREGAR DADOS ---
if "df_pedidos" not in st.session_state or st.session_state.get("reload_pedidos", False):
    st.session_state.df_pedidos = ler_aba("Pedidos", ttl=0)
    st.session_state.reload_pedidos = False
df_pedidos = st.session_state.df_pedidos

if "df_produtos" not in st.session_state or st.session_state.get("reload_produtos", False):
    st.session_state.df_produtos = ler_aba("Produtos", ttl=0)
    st.session_state.reload_produtos = False
df_produtos = st.session_state.df_produtos

st.markdown('<div class="hero-banner"><div class="hero-title">Horta Gestão</div></div>', unsafe_allow_html=True)
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
            col_n.markdown(f"**{limpar_texto(r['nome'])}**")
            col_p.caption(f"R$ {r['preco']} / {r['tipo']}")
            qtd = col_q.number_input("Q", 0, step=1, key=f"q_{idx}_{f}", label_visibility="collapsed")
            if qtd > 0:
                p_u = parse_float(r['preco'])
                sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": r['tipo']})
            st.divider()
    st.markdown(f"<div class='total-badge'>Total parcial: R$ {total_v:.2f}</div>", unsafe_allow_html=True)
    if st.button("💾 SALVAR PEDIDO", type="primary", use_container_width=True):
        if n_cli and carrinho:
            df_at = ler_aba("Pedidos", ttl=0)
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR, "obs": o_ped}])
            salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True)); st.session_state.f_id += 1; st.session_state.reload_pedidos = True; st.rerun()

# --- 2. COLHEITA ---
with aba2:
    st.header("🚜 Colheita")
    if not df_pedidos.empty:
        pend = df_pedidos[df_pedidos["status"].str.lower() == STATUS_PENDENTE]
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
        pend_m = df_pedidos[df_pedidos["status"].str.lower() == STATUS_PENDENTE]
        for _, row in pend_m.iterrows():
            stpg = str(row.get("pagamento")).upper()
            with st.expander(f"👤 {row['cliente']} | {stpg}", expanded=True):
                st.write(f"📍 {row['endereco']}")
                itens_m, total_m = json.loads(row['itens']), 0.0
                for i, it in enumerate(itens_m):
                    c_i, c_v = st.columns([3.5, 1.4])
                    if str(it['tipo']).upper() == "KG":
                        val_input = c_v.number_input("R$", value=None, key=f"m_{row['id']}_{i}", label_visibility="collapsed", placeholder="0,00")
                        v_digitado = parse_float(val_input) if val_input is not None else 0.0
                        it['subtotal'] = v_digitado
                        if v_digitado > 0 and parse_float(it.get('preco', 0)) > 0:
                            it['qtd'] = round(v_digitado / parse_float(it['preco']), 3)
                        c_i.markdown(f"⚖️ {limpar_texto(it['nome'])}")
                    else:
                        c_i.markdown(f"✅ {it['qtd']}x {limpar_texto(it['nome'])}")
                        c_v.markdown(f"R$ {parse_float(it['subtotal']):.2f}")
                    total_m += parse_float(it['subtotal'])
                    st.divider()
                
                st.markdown(f"<div class='m-total'>TOTAL: R$ {total_m:.2f}</div>", unsafe_allow_html=True)
                c_ok, c_pg, c_pr, c_del = st.columns([1, 1, 0.5, 0.5])
                
                if c_ok.button("📦 OK", key=f"ok_{row['id']}"):
                    df_f = ler_aba("Pedidos", ttl=0); idx_list = df_f.index[df_f["id"].astype(str) == str(row["id"])].tolist()
                    if idx_list:
                        idx = idx_list[0]; df_f.at[idx, "status"], df_f.at[idx, "total"], df_f.at[idx, "itens"] = STATUS_PRONTO, total_m, json.dumps(itens_m)
                        salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()
                
                if stpg != PAGAMENTO_PAGO and c_pg.button("💵 Pago", key=f"pg_{row['id']}"):
                    df_f = ler_aba("Pedidos", ttl=0); df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO; salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()
                
                b64 = gerar_b64_etiqueta_dupla(row['cliente'], row['endereco'], total_m, stpg)
                c_pr.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️ Imprimir</a>', unsafe_allow_html=True)
                
                if c_del.button("🗑️", key=f"del_{row['id']}"):
                    df_f = ler_aba("Pedidos", ttl=0); df_f = df_f[df_f["id"].astype(str) != str(row["id"])]; salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()

# --- 4. HISTÓRICO ---
with aba4:
    st.header("📜 Histórico")
    d_sel = st.date_input("Filtrar data:", datetime.now()).strftime("%d/%m/%Y")
    if not df_pedidos.empty:
        hist = df_pedidos[(df_pedidos["status"].str.lower() == STATUS_PRONTO) & (df_pedidos["data"] == d_sel)].sort_values("id", ascending=False)
        for _, row in hist.iterrows():
            pago = str(row.get("pagamento")).upper() == PAGAMENTO_PAGO
            cor = "#28a745" if pago else "#dc3545"
            st.markdown(f'<div style="background-color:white; border-radius:10px; padding:15px; border-left:8px solid {cor}; color:black; margin-bottom:5px;"><b>👤 {row["cliente"]}</b> | {row["pagamento"]}<br>📍 {row["endereco"]}<br><b>R$ {parse_float(row["total"]):.2f}</b></div>', unsafe_allow_html=True)
            c_h1, c_h2 = st.columns(2)
            b64_h = gerar_b64_etiqueta_dupla(row['cliente'], row['endereco'], parse_float(row['total']), row['pagamento'])
            c_h1.markdown(f'<a href="intent:base64,{b64_h}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️ Reimprimir</a>', unsafe_allow_html=True)
            if not pago and c_h2.button("💵 Marcar Pago", key=f"hpay_{row['id']}", use_container_width=True):
                df_f = ler_aba("Pedidos", ttl=0); df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO; salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()

# --- 5. FINANCEIRO ---
with aba5:
    st.header("💰 Financeiro")
    menu = st.radio("Relatório:", ["Dia", "Período", "Seleção Manual"], horizontal=True)
    def gerar_tabela_fin(df_res, titulo_zap="RELATÓRIO"):
        v_total = df_res['total'].apply(parse_float).sum()
        st.metric("Faturamento", f"R$ {v_total:.2f}")
        res = {}
        for _, r in df_res.iterrows():
            try: itens_lista = json.loads(r['itens'])
            except: continue
            for it in itens_lista:
                n = it['nome'].strip().upper() 
                if n not in res: res[n] = {"qtd": 0.0, "val": 0.0, "tipo": it.get('tipo', 'UN')}
                res[n]["qtd"] += float(it.get('qtd', 0)); res[n]["val"] += parse_float(it.get('subtotal', 0))
        if res:
            df_tab = pd.DataFrame([{"Produto": k, "Qtd/Peso": f"{v['qtd']:.3f}" if v['tipo'] == 'KG' else int(v['qtd']), "Total (R$)": f"{v['val']:.2f}"} for k, v in res.items()]).sort_values("Produto")
            st.table(df_tab); msg_detalhada = f"*{titulo_zap}*\n\n"
            for _, row in df_tab.iterrows(): msg_detalhada += f"• {row['Produto']}: {row['Qtd/Peso']} -> R$ {row['Total (R$)']}\n"
            msg_detalhada += f"\n*TOTAL GERAL: R$ {v_total:.2f}*"; st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(msg_detalhada)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)
    if not df_pedidos.empty:
        if menu == "Dia": gerar_tabela_fin(df_pedidos[df_pedidos["data"] == datetime.now().strftime("%d/%m/%Y")], "RELATÓRIO DO DIA")
        elif menu == "Período":
            c1, c2 = st.columns(2); data_ini, data_fim = c1.date_input("De", datetime.now() - timedelta(days=7)), c2.date_input("Até", datetime.now())
            df_pedidos['dt_obj'] = pd.to_datetime(df_pedidos['data'], format='%d/%m/%Y', errors='coerce').dt.date
            gerar_tabela_fin(df_pedidos[(df_pedidos['dt_obj'] >= data_ini) & (df_pedidos['dt_obj'] <= data_fim)], f"RELATÓRIO DE {data_ini.strftime('%d/%m')} A {data_fim.strftime('%d/%m')}")
        elif menu == "Seleção Manual":
            data_sel = st.date_input("Data:", datetime.now()).strftime("%d/%m/%Y"); df_d = df_pedidos[df_pedidos["data"] == data_sel]
            if not df_d.empty:
                selecionados = [r for idx, r in df_d.iterrows() if st.checkbox(f"👤 {r['cliente']} | R$ {r['total']}", key=f"fin_sel_{idx}")]
                if selecionados: gerar_tabela_fin(pd.DataFrame(selecionados), "RELATÓRIO SELECIONADO")

# --- 6. PRODUTOS ---
with aba6:
    st.header("📦 Produtos")
    if not df_produtos.empty:
        for idx, r in df_produtos.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([2.5, 1, 1, 1, 0.5, 0.5])
            en, ep, et = c1.text_input("N", r['nome'], key=f"en_{idx}", label_visibility="collapsed").upper(), c2.number_input("R$", parse_float(r['preco']), key=f"ep_{idx}", label_visibility="collapsed"), c3.selectbox("T", ["UN", "KG"], index=0 if r['tipo']=="UN" else 1, key=f"et_{idx}", label_visibility="collapsed")
            est = c4.toggle("Ativo", value=(str(r['status']).lower() == "ativo"), key=f"es_{idx}")
            if c5.button("💾", key=f"sv_{idx}"):
                df_produtos.at[idx, 'nome'], df_produtos.at[idx, 'preco'], df_produtos.at[idx, 'tipo'], df_produtos.at[idx, 'status'] = en, ep, et, ("Ativo" if est else "Inativo")
                salvar_aba("Produtos", df_produtos); st.session_state.reload_produtos = True; st.rerun()
            if c6.button("🗑️", key=f"dl_{idx}"): salvar_aba("Produtos", df_produtos.drop(idx)); st.session_state.reload_produtos = True; st.rerun()
            st.divider()
