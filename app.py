import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
import unicodedata
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="Horta Gestão", page_icon="🥬", layout="wide")

def aplicar_estilos():
    css_path = Path(__file__).with_name("styles.css")
    try:
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except OSError:
        st.warning("Nao foi possivel carregar styles.css")

aplicar_estilos()

conn = st.connection("gsheets", type=GSheetsConnection)
STATUS_PENDENTE = "pendente"
STATUS_PRONTO = "pronto"
PAGAMENTO_PAGO = "PAGO"
PAGAMENTO_A_PAGAR = "A PAGAR"

# --- FUNÇÃO PARA LIMPAR ACENTOS E FORMATAR ETIQUETA ---
def limpar_texto(texto):
    if not texto: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texto))
                   if unicodedata.category(c) != 'Mn')

def gerar_b64_etiqueta(cliente, endereco, valor, pagamento):
    largura = 32
    
    # Cabeçalho em Negrito (Usando caracteres matemáticos para simular negrito em texto puro)
    # Nota: Algumas impressoras aceitam tags <b>, mas o caractere especial é mais universal.
    marca = "@dahortapmesa".center(largura)
    
    cli = limpar_texto(cliente).upper().center(largura)
    end = limpar_texto(endereco).upper().center(largura)
    
    # Valor e Pago lado a lado
    val_txt = f"R$ {valor:.2f}"
    status_txt = "pago" if pagamento == PAGAMENTO_PAGO else ""
    
    # Se estiver pago, coloca espaços entre o valor e a palavra 'pago'
    if status_txt:
        espaços = largura - len(val_txt) - len(status_txt) - 4
        linha_final = f"{val_txt}{' ' * espaços}{status_txt}".center(largura)
    else:
        linha_final = val_txt.center(largura)
    
    # Montagem com o espaço solicitado entre nome e endereço
    corpo = f"{marca}\n\n{cli}\n\n{end}\n\n{linha_final}"
    return base64.b64encode(corpo.encode('ascii', 'ignore')).decode()

# ── Data Access Layer ────────────────────────────────────────
DEFAULT_READ_TTL = 30 

def ler_aba(aba: str, ttl: int = DEFAULT_READ_TTL) -> pd.DataFrame:
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
    except Exception as e:
        st.error(f"Erro ao ler aba '{aba}': {e}")
        return pd.DataFrame()
    if df is None or df.empty: return pd.DataFrame()
    df = df.dropna(how="all")
    df.columns = [str(c).lower().strip() for c in df.columns]
    mask = df.astype(str).apply(lambda r: r.str.strip().eq("").all(), axis=1)
    df = df[~mask].reset_index(drop=True)
    df = df.fillna("")
    return df

def salvar_aba(aba: str, df: pd.DataFrame):
    try:
        conn.update(worksheet=aba, data=df)
        conn.reset() 
    except Exception as e:
        st.error(f"Erro ao salvar aba '{aba}': {e}")

def filtrar_status(df: pd.DataFrame, status: str) -> pd.DataFrame:
    if df.empty or "status" not in df.columns: return pd.DataFrame()
    s = df["status"].astype(str).str.strip().str.lower()
    return df[s == status]

def parse_float(val, default: float = 0.0) -> float:
    try: return float(str(val).strip().replace(",", "."))
    except: return default

def resumo_kpis(df: pd.DataFrame) -> dict:
    if df.empty: return {"total": 0, "pendentes": 0, "prontos": 0, "recebido": 0.0, "areceber": 0.0}
    status = df.get("status", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
    pagamento = df.get("pagamento", pd.Series(dtype=str)).astype(str).str.strip()
    totais = df.get("total", pd.Series(dtype=float)).apply(parse_float)
    return {
        "total": len(df),
        "pendentes": int((status == STATUS_PENDENTE).sum()),
        "prontos": int((status == STATUS_PRONTO).sum()),
        "recebido": float(totais[pagamento == PAGAMENTO_PAGO].sum()),
        "areceber": float(totais[pagamento == PAGAMENTO_A_PAGAR].sum()),
    }

def calcular_totais_financeiros(df: pd.DataFrame):
    if df.empty: return 0.0, 0.0
    pagamento = df.get("pagamento", pd.Series(dtype=str)).astype(str).str.strip()
    totais = df.get("total", pd.Series(dtype=float)).apply(parse_float)
    return float(totais[pagamento == PAGAMENTO_PAGO].sum()), float(totais[pagamento == PAGAMENTO_A_PAGAR].sum())

# ── Load data ──────────────────────────────────────────────
df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

# ── Hero + KPIs ──────────────────────────────────────────────
st.markdown("""<div class="hero-banner"><div class="hero-title">Horta Gestao</div><div class="hero-subtitle">Painel de Controle</div></div>""", unsafe_allow_html=True)

kpis = resumo_kpis(df_pedidos)
st.markdown(f"""<div class="kpi-strip">
    <div class="kpi-card"><div class="kpi-title">Pedidos</div><div class="kpi-value">{kpis['total']}</div></div>
    <div class="kpi-card"><div class="kpi-title">Pendentes</div><div class="kpi-value">{kpis['pendentes']}</div></div>
    <div class="kpi-card"><div class="kpi-title">Prontos</div><div class="kpi-value">{kpis['prontos']}</div></div>
</div>""", unsafe_allow_html=True)

# ── ABAS ───────────────────────────────────────────────────

def render_tab_novo_pedido(tab):
    with tab:
        if 'f_id' not in st.session_state: st.session_state.f_id = 0
        f = st.session_state.f_id
        st.header("🛒 Novo Pedido")
        c1, c2, c3 = st.columns([2, 2, 1])
        n_cli = c1.text_input("Cliente", key=f"n_{f}").upper()
        e_cli = c2.text_input("Endereço", key=f"e_{f}").upper()
        pg = c3.toggle("Pago?", key=f"p_{f}")
        o_ped = st.text_input("Observação", key=f"o_{f}")
        
        carrinho, total_v = [], 0.0
        for row_idx, r in df_produtos.iterrows():
            col_n, col_p, col_q = st.columns([3.4, 1.3, 1.1])
            col_n.markdown(f"**{r['nome']}**")
            col_p.caption(f"R$ {r['preco']} / {r['tipo']}")
            qtd = col_q.number_input("Q", 0, step=1, key=f"q_{row_idx}_{f}", label_visibility="collapsed")
            if qtd > 0:
                p_u = parse_float(r['preco'])
                sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": r['tipo']})
        
        st.markdown(f"<div class='total-badge'>Total parcial: R$ {total_v:.2f}</div>", unsafe_allow_html=True)
        if st.button("💾 FINALIZAR PEDIDO", type="primary", key=f"btn_s_{f}"):
            if n_cli and carrinho:
                df_at = ler_aba("Pedidos", ttl=0)
                novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR, "obs": o_ped}])
                salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True))
                st.session_state.f_id += 1
                st.rerun()

def render_tab_colheita(tab):
    with tab:
        st.header("🚜 Lista de Colheita")
        pend = filtrar_status(df_pedidos, STATUS_PENDENTE)
        if not pend.empty:
            res = {}
            for _, p in pend.iterrows():
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it['tipo']})"
                    res[k] = res.get(k, 0) + it['qtd']
            for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")
            txt_z = "*COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res.items()])
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_z)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)

def render_tab_montagem(tab):
    with tab:
        st.header("⚖️ Montagem")
        pend_m = filtrar_status(df_pedidos, STATUS_PENDENTE)
        for _, row in pend_m.iterrows():
            status_pgto = str(row.get("pagamento", PAGAMENTO_A_PAGAR)).strip().upper()
            with st.expander(f"👤 {row['cliente']} | {status_pgto}", expanded=True):
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
                
                col_ok, col_pago, col_print, col_del = st.columns([1.5, 1.5, 1, 1])
                if col_ok.button("📦 OK", key=f"ok_{row['id']}", use_container_width=True):
                    df_f = ler_aba("Pedidos", ttl=0)
                    match = df_f.index[df_f["id"].astype(str) == str(row["id"])]
                    df_f.at[match[0], "status"], df_f.at[match[0], "total"], df_f.at[match[0], "itens"] = "Pronto", total_m, json.dumps(itens_m)
                    salvar_aba("Pedidos", df_f); st.rerun()
                
                if status_pgto != PAGAMENTO_PAGO:
                    if col_pago.button("💵 PAGO", key=f"mpay_{row['id']}", use_container_width=True):
                        df_f = ler_aba("Pedidos", ttl=0)
                        df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO
                        salvar_aba("Pedidos", df_f); st.rerun()
                
                # Impressão com os novos ajustes
                b64 = gerar_b64_etiqueta(row['cliente'], row['endereco'], total_m, status_pgto)
                col_print.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️</a>', unsafe_allow_html=True)
                
                if col_del.button("🗑️", key=f"del_{row['id']}"):
                    df_f = ler_aba("Pedidos", ttl=0)
                    df_f = df_f[df_f["id"].astype(str) != str(row["id"])].reset_index(drop=True)
                    salvar_aba("Pedidos", df_f); st.rerun()

def render_tab_historico(tab):
    with tab:
        st.header("📜 Histórico")
        data_sel = st.date_input("Filtrar data:", datetime.now()).strftime("%d/%m/%Y")
        hist = filtrar_status(df_pedidos, STATUS_PRONTO)
        df_dia = hist[hist["data"] == data_sel].sort_values("id", ascending=False)
        for _, row in df_dia.iterrows():
            pago = str(row.get("pagamento")).strip().upper() == PAGAMENTO_PAGO
            cor = "#28a745" if pago else "#dc3545"
            card_html = f"""<div style="background-color:white; border-radius:10px; padding:15px; margin-bottom:5px; border-left:6px solid {cor}; color:black;">
            <b>👤 {row['cliente']}</b> | {row['pagamento']}<br>📍 {row['endereco']}<br><b>R$ {parse_float(row['total']):.2f}</b></div>"""
            st.markdown(card_html, unsafe_allow_html=True)
            
            col_print, col_pago = st.columns(2)
            b64_h = gerar_b64_etiqueta(row['cliente'], row['endereco'], parse_float(row['total']), row['pagamento'])
            col_print.markdown(f'<a href="intent:base64,{b64_h}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print" style="text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; color:black;">🖨️ Reimprimir</a>', unsafe_allow_html=True)
            
            if not pago:
                if col_pago.button("💵 Marcar Pago", key=f"hpay_{row['id']}"):
                    df_f = ler_aba("Pedidos", ttl=0)
                    df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO
                    salvar_aba("Pedidos", df_f); st.rerun()
            
            with st.expander("📋 Detalhes"):
                for it in json.loads(row['itens']): st.write(f"• {it['qtd']}x {it['nome']}")
                if row['obs']: st.info(f"Obs: {row['obs']}")

def render_tab_financeiro(tab):
    with tab:
        st.header("💰 Financeiro")
        rec, pen = calcular_totais_financeiros(df_pedidos)
        st.metric("Recebido", f"R$ {rec:.2f}")
        st.metric("A Receber", f"R$ {pen:.2f}")

aba1, aba2, aba3, aba4, aba5 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro"])
render_tab_novo_pedido(aba1); render_tab_colheita(aba2); render_tab_montagem(aba3); render_tab_historico(aba4); render_tab_financeiro(aba5)
