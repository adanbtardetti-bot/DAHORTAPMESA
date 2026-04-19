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

# --- FUNÇÕES DE UTILIDADE ---

def remover_acentos(texto):
    if not texto: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texto))
                   if unicodedata.category(c) != 'Mn')

def formatar_etiqueta_centralizada(cliente, endereco, valor, pagamento):
    largura = 32  # Padrao para fitas de 50/58mm
    
    # Nome da marca no topo
    topo = "@dahortapmesa".center(largura)
    
    # Cliente e Endereco (limpando acentos)
    cli = remover_acentos(cliente).upper().center(largura)
    end = remover_acentos(endereco).upper().center(largura)
    
    # Valor centralizado
    val_str = f"R$ {float(valor):.2f}".center(largura)
    
    # Status de pagamento: So exibe se for PAGO
    status = remover_acentos(pagamento).lower().center(largura) if pagamento == PAGAMENTO_PAGO else ""
    
    # Montagem final da etiqueta com quebras de linha
    corpo = f"{topo}\n\n{cli}\n\n{end}\n\n{val_str}\n{status}"
    return corpo

# ── Data Access Layer ────────────────────────────────────────
def ler_aba(aba: str, ttl: int = 30) -> pd.DataFrame:
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
    except Exception as e:
        st.error(f"Erro ao ler aba '{aba}': {e}")
        return pd.DataFrame()
    if df is None or df.empty: return pd.DataFrame()
    df = df.dropna(how="all")
    df.columns = [str(c).lower().strip() for c in df.columns]
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

def calcular_totais_financeiros(df: pd.DataFrame):
    if df.empty: return 0.0, 0.0
    pagamento = df.get("pagamento", pd.Series(dtype=str)).astype(str).str.strip()
    totais = df.get("total", pd.Series(dtype=float)).apply(parse_float)
    return float(totais[pagamento == PAGAMENTO_PAGO].sum()), float(totais[pagamento == PAGAMENTO_A_PAGAR].sum())

# ── Load data ──────────────────────────────────────────────
df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

# ── Hero + KPIs ──────────────────────────────────────────────
st.markdown("""<div class="hero-banner"><div class="hero-title">Horta Gestao</div></div>""", unsafe_allow_html=True)

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
        
        if st.button("💾 FINALIZAR", type="primary", use_container_width=True):
            if n_cli and carrinho:
                df_at = ler_aba("Pedidos", ttl=0)
                novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": STATUS_PENDENTE, "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR, "obs": o_ped}])
                salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True))
                st.session_state.f_id += 1
                st.rerun()

def render_tab_colheita(tab):
    with tab:
        st.header("🚜 Colheita")
        pend = filtrar_status(df_pedidos, STATUS_PENDENTE)
        if not pend.empty:
            res = {}
            for _, p in pend.iterrows():
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it['tipo']})"
                    res[k] = res.get(k, 0) + it['qtd']
            for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")

def render_tab_montagem(tab):
    with tab:
        st.header("⚖️ Montagem")
        pend_m = filtrar_status(df_pedidos, STATUS_PENDENTE)
        for _, row in pend_m.iterrows():
            status_pgto = str(row.get("pagamento", PAGAMENTO_A_PAGAR)).strip().upper()
            cor_pgto = "#28a745" if status_pgto == PAGAMENTO_PAGO else "#dc3545"
            
            with st.expander(f"👤 {row['cliente']} ({status_pgto})"):
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
                
                col_ok, col_pago, col_print = st.columns([2, 1.5, 1])
                if col_ok.button("📦 OK", key=f"ok_{row['id']}", use_container_width=True):
                    df_f = ler_aba("Pedidos", ttl=0)
                    match = df_f.index[df_f["id"].astype(str) == str(row["id"])]
                    df_f.at[match[0], "status"], df_f.at[match[0], "total"], df_f.at[match[0], "itens"] = STATUS_PRONTO, total_m, json.dumps(itens_m)
                    salvar_aba("Pedidos", df_f); st.rerun()
                
                if status_pgto != PAGAMENTO_PAGO:
                    if col_pago.button("💵 Pago", key=f"mpay_{row['id']}", use_container_width=True):
                        df_f = ler_aba("Pedidos", ttl=0)
                        df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO
                        salvar_aba("Pedidos", df_f); st.rerun()
                
                # Gerar Etiqueta Centralizada (Estilo 50x30mm)
                txt_e = formatar_etiqueta_centralizada(row['cliente'], row['endereco'], total_m, status_pgto)
                b64 = base64.b64encode(txt_e.encode('ascii', 'ignore')).decode()
                col_print.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" style="text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; border:1px solid #ccc; color:black;">🖨️</a>', unsafe_allow_html=True)

def render_tab_historico(tab):
    with tab:
        st.header("📜 Histórico")
        data_sel = st.date_input("Data:", datetime.now()).strftime("%d/%m/%Y")
        hist = filtrar_status(df_pedidos, STATUS_PRONTO)
        df_dia = hist[hist["data"] == data_sel].sort_values("id", ascending=False)
        for _, row in df_dia.iterrows():
            st.markdown(f"**👤 {row['cliente']}** - R$ {parse_float(row['total']):.2f} ({row['pagamento']})")
            with st.expander("Ver Itens"):
                for it in json.loads(row['itens']): st.write(f"• {it['qtd']}x {it['nome']}")
                if row['obs']: st.info(row['obs'])
            st.write("---")

def render_tab_financeiro(tab):
    with tab:
        st.header("💰 Financeiro")
        rec, pen = calcular_totais_financeiros(df_pedidos)
        st.metric("Recebido", f"R$ {rec:.2f}")
        st.metric("A Receber", f"R$ {pen:.2f}")

aba1, aba2, aba3, aba4, aba5 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro"])
render_tab_novo_pedido(aba1); render_tab_colheita(aba2); render_tab_montagem(aba3); render_tab_historico(aba4); render_tab_financeiro(aba5)
