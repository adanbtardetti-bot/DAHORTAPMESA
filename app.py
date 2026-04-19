import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime
from pathlib import Path

st.set_page_config(page_title="Horta Gestão", page_icon="🥬", layout="wide")

def aplicar_estilos():
    css_path = Path(__file__).with_name("styles.css")
    try:
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except OSError:
        # Fallback caso o styles.css não exista
        st.markdown("""
        <style>
        .hero-banner {background-color: #2e7d32; color: white; padding: 20px; border-radius: 10px; text-align: center;}
        .kpi-card {background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center;}
        .kpi-value {font-size: 20px; font-weight: bold; color: #2e7d32;}
        .total-badge {background: #e8f5e9; padding: 10px; border-radius: 5px; font-weight: bold; margin: 10px 0;}
        </style>
        """, unsafe_allow_html=True)

aplicar_estilos()

conn = st.connection("gsheets", type=GSheetsConnection)
STATUS_PENDENTE = "pendente"
STATUS_PRONTO = "pronto"
PAGAMENTO_PAGO = "PAGO"
PAGAMENTO_A_PAGAR = "A PAGAR"

# ── Camada de Dados ──────────────────────────────────────────

def ler_aba(aba: str, ttl: int = 30) -> pd.DataFrame:
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty: return pd.DataFrame()
        df = df.dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        df = df.fillna("")
        return df
    except Exception as e:
        st.error(f"Erro ao ler {aba}: {e}")
        return pd.DataFrame()

def salvar_aba(aba: str, df: pd.DataFrame):
    try:
        conn.update(worksheet=aba, data=df)
        conn.reset()
    except Exception as e:
        st.error(f"Erro ao salvar {aba}: {e}")

def filtrar_status(df: pd.DataFrame, status: str) -> pd.DataFrame:
    if df.empty or "status" not in df.columns: return pd.DataFrame()
    return df[df["status"].astype(str).str.strip().str.lower() == status]

def parse_float(val, default: float = 0.0) -> float:
    try: return float(str(val).strip().replace(",", "."))
    except: return default

# ── Dashboards ───────────────────────────────────────────────

df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

st.markdown('<div class="hero-banner"><h1>Horta Gestão</h1><p>Controle total da horta ao cliente</p></div>', unsafe_allow_html=True)

def resumo_kpis(df: pd.DataFrame):
    if df.empty: return {"total": 0, "pend": 0, "prontos": 0, "rec": 0.0, "arec": 0.0}
    status = df.get("status", pd.Series(dtype=str)).astype(str).str.strip().str.lower()
    pag = df.get("pagamento", pd.Series(dtype=str)).astype(str).str.strip()
    vols = df.get("total", pd.Series(dtype=float)).apply(parse_float)
    return {
        "total": len(df),
        "pend": int((status == STATUS_PENDENTE).sum()),
        "prontos": int((status == STATUS_PRONTO).sum()),
        "rec": float(vols[pag == PAGAMENTO_PAGO].sum()),
        "arec": float(vols[pag == PAGAMENTO_A_PAGAR].sum()),
    }

k = resumo_kpis(df_pedidos)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Pedidos", k['total'])
c2.metric("Pendentes", k['pend'])
c3.metric("Prontos", k['prontos'])
c4.metric("Recebido", f"R$ {k['rec']:.2f}")
c5.metric("A Receber", f"R$ {k['arec']:.2f}")

# ── Funções das Abas ─────────────────────────────────────────

def render_tab_novo_pedido(tab):
    with tab:
        if 'f_id' not in st.session_state: st.session_state.f_id = 0
        f = st.session_state.f_id
        st.subheader("🛒 Novo Pedido")
        col1, col2 = st.columns(2)
        n_cli = col1.text_input("Cliente", key=f"n_{f}").upper()
        e_cli = col2.text_input("Endereço", key=f"e_{f}").upper()
        col3, col4 = st.columns([1, 3])
        pg = col3.toggle("Já está pago?", key=f"p_{f}")
        obs = col4.text_input("Observação", key=f"o_{f}")

        carrinho, total_parcial = [], 0.0
        if not df_produtos.empty:
            st.write("---")
            for i, r in df_produtos.iterrows():
                nome = str(r.get("nome", "")).strip()
                if not nome: continue
                preco = parse_float(r.get("preco", 0))
                tipo = str(r.get("tipo", "UN")).upper()
                c_n, c_q = st.columns([3, 1])
                qtd = c_q.number_input(f"{tipo}", 0, key=f"q_{i}_{f}", label_visibility="collapsed")
                c_n.markdown(f"**{nome}** (R$ {preco:.2f})")
                if qtd > 0:
                    sub = 0.0 if tipo == "KG" else (qtd * preco)
                    total_parcial += sub
                    carrinho.append({"nome": nome, "qtd": qtd, "preco": preco, "subtotal": sub, "tipo": tipo})

        st.markdown(f"<div class='total-badge'>Subtotal: R$ {total_parcial:.2f}</div>", unsafe_allow_html=True)
        if st.button("💾 SALVAR PEDIDO", type="primary", use_container_width=True):
            if n_cli and carrinho:
                df_at = ler_aba("Pedidos", ttl=0)
                novo = pd.DataFrame([{
                    "id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli,
                    "itens": json.dumps(carrinho), "status": "Pendente", "total": total_parcial,
                    "data": datetime.now().strftime("%d/%m/%Y"),
                    "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR, "obs": obs
                }])
                salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True))
                st.session_state.f_id += 1
                st.rerun()

def render_tab_colheita(tab):
    with tab:
        st.subheader("🚜 Colheita do Dia")
        pend = filtrar_status(df_pedidos, STATUS_PENDENTE)
        if pend.empty: st.success("Nada para colher!"); return
        res = {}
        for _, p in pend.iterrows():
            for it in json.loads(p['itens']):
                k = f"{it['nome']} ({it['tipo']})"
                res[k] = res.get(k, 0) + it['qtd']
        for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")

def render_tab_montagem(tab):
    with tab:
        st.subheader("⚖️ Montagem e Pesagem")
        pend = filtrar_status(df_pedidos, STATUS_PENDENTE)
        for _, row in pend.iterrows():
            with st.expander(f"📦 {row['cliente']}", expanded=True):
                itens = json.loads(row['itens'])
                t_m = 0.0
                for i, it in enumerate(itens):
                    c_i, c_p = st.columns([3, 1])
                    if it['tipo'] == "KG":
                        val = c_p.number_input("R$", 0.0, key=f"v_{row['id']}_{i}", label_visibility="collapsed")
                        it['subtotal'] = val
                        c_i.write(f"⚖️ {it['nome']} (Pesar)")
                    else:
                        c_i.write(f"✅ {it['qtd']}x {it['nome']}")
                        c_p.write(f"R$ {it['subtotal']:.2f}")
                    t_m += it['subtotal']
                
                if st.button("FINALIZAR 📦", key=f"f_{row['id']}", use_container_width=True):
                    df_f = ler_aba("Pedidos", ttl=0)
                    idx = df_f.index[df_f['id'].astype(str) == str(row['id'])]
                    if not idx.empty:
                        df_f.at[idx[0], "status"] = "Pronto"
                        df_f.at[idx[0], "total"] = t_m
                        df_f.at[idx[0], "itens"] = json.dumps(itens)
                        salvar_aba("Pedidos", df_f)
                    st.rerun()

def render_tab_historico(tab):
    with tab:
        st.subheader("📜 Histórico de Pedidos")
        finalizados = filtrar_status(df_pedidos, STATUS_PRONTO)
        if finalizados.empty: st.info("Histórico vazio."); return
        
        for _, row in finalizados.sort_values("id", ascending=False).iterrows():
            pago = str(row['pagamento']).upper() == PAGAMENTO_PAGO
            cor = "#28a745" if pago else "#dc3545"
            v_total = parse_float(row['total'])
            
            # Card HTML
            card = f"""<div style="background:white; border-radius:10px; padding:15px; margin-bottom:10px; border-left:6px solid {cor}; color:black;">
            <div style="display:flex; justify-content:space-between;"><b>👤 {row['cliente']}</b> <span>{row['pagamento']}</span></div>
            <div style="font-size:12px; color:gray;">📅 {row['data']} | 📍 {row['endereco']}</div>
            <div style="font-size:18px; font-weight:bold; color:#2e7d32; margin-top:5px;">R$ {v_total:.2f}</div>
            </div>"""
            st.markdown(card, unsafe_allow_html=True)

            c_imp, c_pag = st.columns(2)
            
            # Botão Imprimir (RawBT)
            txt_imp = f"CLIENTE: {row['cliente']}\nEND: {row['endereco']}\nTOTAL: R$ {v_total:.2f}\n{row['pagamento']}"
            b64 = base64.b64encode(txt_imp.encode()).decode()
            c_imp.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" style="text-decoration:none;"><button style="width:100%; cursor:pointer; padding:5px; background:#f0f2f6; border:1px solid #ccc; border-radius:5px;">🖨️ Etiqueta</button></a>', unsafe_allow_html=True)

            # Botão Pagar
            if not pago:
                if c_pag.button("💵 Marcar Pago", key=f"pago_{row['id']}", use_container_width=True):
                    df_f = ler_aba("Pedidos", ttl=0)
                    idx = df_f.index[df_f['id'].astype(str) == str(row['id'])]
                    if not idx.empty:
                        df_f.at[idx[0], "pagamento"] = PAGAMENTO_PAGO
                        salvar_aba("Pedidos", df_f)
                    st.rerun()
            else:
                c_pag.button("✅ Recebido", disabled=True, key=f"d_{row['id']}", use_container_width=True)

def render_tab_financeiro(tab):
    with tab:
        st.subheader("💰 Resumo Financeiro")
        rec, pend = calcular_totais_financeiros(df_pedidos)
        st.metric("Total em Caixa", f"R$ {rec:.2f}")
        st.metric("Total a Receber", f"R$ {pend:.2f}")

# ── Renderização Final ───────────────────────────────────────
t1, t2, t3, t4, t5 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Finanças"])
render_tab_novo_pedido(t1)
render_tab_colheita(t2)
render_tab_montagem(t3)
render_tab_historico(t4)
render_tab_financeiro(t5)
