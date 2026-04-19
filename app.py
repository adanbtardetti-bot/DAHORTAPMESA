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
        st.warning("Nao foi possivel carregar styles.css")


aplicar_estilos()

conn = st.connection("gsheets", type=GSheetsConnection)
STATUS_PENDENTE = "pendente"
STATUS_PRONTO = "pronto"
PAGAMENTO_PAGO = "PAGO"
PAGAMENTO_A_PAGAR = "A PAGAR"

# ── Data Access Layer ────────────────────────────────────────

# Short TTL for display reads — avoids hammering the API on every rerun.
# Write handlers pass ttl=0 when they need guaranteed-fresh data.
DEFAULT_READ_TTL = 30  # seconds


def ler_aba(aba: str, ttl: int = DEFAULT_READ_TTL) -> pd.DataFrame:
    """Read and clean a Google Sheets worksheet.

    Args:
        aba: worksheet name
        ttl: cache lifetime in seconds. 0 = bypass cache (use before writes).

    Returns an empty DataFrame on failure and shows a user-visible error.
    """
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
    except Exception as e:
        st.error(f"Erro ao ler aba '{aba}': {e}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # Drop fully-empty rows
    df = df.dropna(how="all")

    # Normalise column names
    df.columns = [str(c).lower().strip() for c in df.columns]

    # Drop rows that are only whitespace (ghost rows from Google Sheets)
    mask = df.astype(str).apply(lambda r: r.str.strip().eq("").all(), axis=1)
    df = df[~mask].reset_index(drop=True)

    # Fill remaining NaN so downstream code never sees NaN
    df = df.fillna("")

    return df


def salvar_aba(aba: str, df: pd.DataFrame):
    """Write a DataFrame back to a Google Sheets worksheet.

    Clears the Streamlit connection cache after writing so the next
    rerun picks up the change without waiting for TTL expiry.
    """
    try:
        conn.update(worksheet=aba, data=df)
        conn.reset()  # invalidate cached reads
    except Exception as e:
        st.error(f"Erro ao salvar aba '{aba}': {e}")


def filtrar_status(df: pd.DataFrame, status: str) -> pd.DataFrame:
    """Filter rows by status (case-insensitive, whitespace-tolerant)."""
    if df.empty or "status" not in df.columns:
        return pd.DataFrame()
    s = df["status"].astype(str).str.strip().str.lower()
    return df[s == status]


def parse_float(val, default: float = 0.0) -> float:
    """Safely convert a value to float, handling commas and blanks."""
    try:
        return float(str(val).strip().replace(",", "."))
    except (ValueError, TypeError):
        return default


def resumo_kpis(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"total": 0, "pendentes": 0, "prontos": 0, "recebido": 0.0, "areceber": 0.0}

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
    if df.empty:
        return 0.0, 0.0

    pagamento = df.get("pagamento", pd.Series(dtype=str)).astype(str).str.strip()
    totais = df.get("total", pd.Series(dtype=float)).apply(parse_float)
    recebido = float(totais[pagamento == PAGAMENTO_PAGO].sum())
    pendente = float(totais[pagamento == PAGAMENTO_A_PAGAR].sum())
    return recebido, pendente


# ── Load sheets ONCE per rerun ───────────────────────────────

df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

# ── Hero + KPIs ──────────────────────────────────────────────

st.markdown(
    """
<div class="hero-banner">
    <div class="hero-title">Horta Gestao</div>
    <div class="hero-subtitle">Pedidos, colheita, montagem e financeiro em um painel simples.</div>
</div>
""",
    unsafe_allow_html=True,
)

kpis = resumo_kpis(df_pedidos)

st.markdown(
    f"""
<div class="kpi-strip">
    <div class="kpi-card"><div class="kpi-title">Pedidos totais</div><div class="kpi-value">{kpis['total']}</div></div>
    <div class="kpi-card"><div class="kpi-title">Pendentes</div><div class="kpi-value">{kpis['pendentes']}</div></div>
    <div class="kpi-card"><div class="kpi-title">Prontos</div><div class="kpi-value">{kpis['prontos']}</div></div>
    <div class="kpi-card"><div class="kpi-title">Recebido</div><div class="kpi-value">R$ {kpis['recebido']:.2f}</div></div>
    <div class="kpi-card"><div class="kpi-title">A receber</div><div class="kpi-value">R$ {kpis['areceber']:.2f}</div></div>
</div>
""",
    unsafe_allow_html=True,
)

def render_tab_novo_pedido(tab):
    with tab:
        if 'f_id' not in st.session_state:
            st.session_state.f_id = 0

        f = st.session_state.f_id
        st.header("🛒 Novo Pedido")
        st.caption("Registre os dados do cliente e monte o carrinho do pedido.")
        c1, c2, c3 = st.columns([2, 2, 1])
        n_cli = c1.text_input("Cliente", key=f"n_{f}").upper()
        e_cli = c2.text_input("Endereço", key=f"e_{f}").upper()
        pg = c3.toggle("Pago?", key=f"p_{f}")
        o_ped = st.text_input("Observação", key=f"o_{f}")

        carrinho = []
        total_v = 0.0

        # Validate products sheet has required columns
        colunas_necessarias = {"nome", "preco"}
        if df_produtos.empty:
            st.info("Nenhum produto encontrado na aba 'Produtos'.")
        elif not colunas_necessarias.issubset(df_produtos.columns):
            faltando = colunas_necessarias - set(df_produtos.columns)
            st.warning(f"Colunas ausentes na aba Produtos: {', '.join(faltando)}")
        else:
            for row_idx, r in df_produtos.iterrows():
                nome = str(r.get("nome", "")).strip()
                if not nome:
                    continue  # skip blank product rows

                p_u = parse_float(r.get("preco", 0))
                tipo = str(r.get("tipo", "UN")).strip().upper() or "UN"
                # Use row index as stable key fallback when id is missing/blank
                prod_id = str(r.get("id", "")).strip() or str(row_idx)

                col_n, col_p, col_q = st.columns([3.4, 1.3, 1.1])
                col_n.markdown(f"**{nome}**")
                col_p.caption(f"R$ {p_u:.2f} / {tipo}")
                qtd = col_q.number_input(
                    "Q", 0, step=1, key=f"q_{prod_id}_{f}", label_visibility="collapsed"
                )
                if qtd > 0:
                    sub = 0.0 if tipo == "KG" else (qtd * p_u)
                    total_v += sub
                    carrinho.append(
                        {"nome": nome, "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": tipo}
                    )

        st.markdown(
            f"<div class='total-badge'>Total parcial: R$ {total_v:.2f}</div>",
            unsafe_allow_html=True,
        )

        if st.button("💾 FINALIZAR PEDIDO", type="primary", key=f"btn_s_{f}"):
            if n_cli and carrinho:
                # Fresh read before write to avoid overwriting concurrent changes
                df_atual = ler_aba("Pedidos", ttl=0)
                novo = pd.DataFrame([
                    {
                        "id": int(datetime.now().timestamp()),
                        "cliente": n_cli,
                        "endereco": e_cli,
                        "itens": json.dumps(carrinho),
                        "status": "Pendente",
                        "data": datetime.now().strftime("%d/%m/%Y"),
                        "total": total_v,
                        "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR,
                        "obs": o_ped,
                    }
                ])
                salvar_aba("Pedidos", pd.concat([df_atual, novo], ignore_index=True))
                st.session_state.f_id += 1
                st.rerun()


def render_tab_colheita(tab):
    with tab:
        st.header("🚜 Lista de Colheita")
        st.caption("Resumo dos itens pendentes para preparar na horta.")
        if df_pedidos.empty:
            st.info("Sem dados na aba 'Pedidos'.")
            return

        pend = filtrar_status(df_pedidos, STATUS_PENDENTE)
        if pend.empty:
            st.success("Nao ha pedidos pendentes de colheita.")
            return

        resumo = {}
        for _, ped in pend.iterrows():
            try:
                for it in json.loads(ped.get("itens", "[]")):
                    chave = f"{it['nome']} ({it.get('tipo', 'UN')})"
                    resumo[chave] = resumo.get(chave, 0) + it['qtd']
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        for item, qtd in resumo.items():
            st.write(f"🟢 **{qtd}x** {item}")

        txt_z = "*COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in resumo.items()])
        st.markdown(
            f'<a href="https://wa.me/?text={urllib.parse.quote(txt_z)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>',
            unsafe_allow_html=True,
        )


def render_tab_montagem(tab):
    with tab:
        st.header("⚖️ Montagem")
        st.caption("Ajuste valores dos itens por quilo e finalize os pedidos.")
        if df_pedidos.empty:
            st.info("Sem dados na aba 'Pedidos'.")
            return

        pend_m = filtrar_status(df_pedidos, STATUS_PENDENTE)
        if pend_m.empty:
            st.success("Nao ha pedidos para montar no momento.")
            return

        for idx, row in pend_m.iterrows():
            with st.expander(f"👤 {row.get('cliente', '?')}", expanded=True):
                st.write(f"📍 {row.get('endereco', '')}")
                try:
                    itens_m = json.loads(row.get("itens", "[]"))
                except (json.JSONDecodeError, TypeError):
                    st.warning("Nao foi possivel ler os itens deste pedido.")
                    continue

                st.markdown(
                    "<div class='m-list-header'><span>Item</span><span>Valor</span></div>",
                    unsafe_allow_html=True,
                )
                total_m = 0.0
                for i, it in enumerate(itens_m):
                    tipo = str(it.get('tipo', 'UN')).upper()
                    nome = str(it.get('nome', 'Item sem nome'))
                    c_i, c_v = st.columns([3.5, 1.4])
                    if tipo == "KG":
                        c_i.markdown(
                            f"<div class='m-item-row'><span class='m-item-name'>⚖️ {nome}</span><span class='m-item-tag'>KG</span></div>",
                            unsafe_allow_html=True,
                        )
                        val_kg = c_v.number_input("R$", 0.0, step=0.1, key=f"m_{row['id']}_{i}", label_visibility="collapsed")
                        it['subtotal'] = val_kg
                    else:
                        qtd = int(it.get('qtd', 0))
                        subtotal = parse_float(it.get('subtotal', 0))
                        c_i.markdown(
                            f"<div class='m-item-row'><span class='m-item-name'>✅ {nome}</span><span class='m-item-tag'>{qtd}x</span></div>",
                            unsafe_allow_html=True,
                        )
                        c_v.markdown(
                            f"<div class='m-item-price'>R$ {subtotal:.2f}</div>",
                            unsafe_allow_html=True,
                        )
                    total_m += parse_float(it.get('subtotal', 0))

                st.markdown(
                    f"<div class='m-total'>TOTAL: R$ {total_m:.2f}</div>",
                    unsafe_allow_html=True,
                )
                st.markdown("<div class='m-actions-anchor m-actions-ok'></div>", unsafe_allow_html=True)
                col_ok = st.columns(1)[0]
                st.markdown("<div class='m-actions-anchor m-actions-secondary'></div>", unsafe_allow_html=True)
                col_print, col_delete = st.columns(2, gap="small")

                txt_e = f"{row['cliente']}\n{row['endereco']}\n\nTOTAL: R$ {total_m:.2f}"
                b64 = base64.b64encode(txt_e.encode()).decode()
                col_print.markdown(
                    f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️</a>',
                    unsafe_allow_html=True,
                )

                if col_ok.button("📦 OK", key=f"ok_{row['id']}", use_container_width=True):
                    # Fresh read before write to avoid stale data
                    df_fresh = ler_aba("Pedidos", ttl=0)
                    match = df_fresh.index[df_fresh["id"].astype(str) == str(row["id"])]
                    if not match.empty:
                        df_fresh.at[match[0], "status"] = "Pronto"
                        df_fresh.at[match[0], "total"] = total_m
                        df_fresh.at[match[0], "itens"] = json.dumps(itens_m)
                        salvar_aba("Pedidos", df_fresh)
                    st.rerun()

                if col_delete.button("🗑️", key=f"del_{row['id']}"):
                    # Fresh read before write to avoid stale data
                    df_fresh = ler_aba("Pedidos", ttl=0)
                    match = df_fresh.index[df_fresh["id"].astype(str) == str(row["id"])]
                    if not match.empty:
                        df_fresh = df_fresh.drop(match[0]).reset_index(drop=True)
                        salvar_aba("Pedidos", df_fresh)
                    st.rerun()


def render_tab_historico(tab):
    with tab:
        st.header("📜 Histórico de Pedidos")
        st.caption("Visualize aqui todos os pedidos que já foram finalizados.")
        
        if df_pedidos.empty:
            st.info("O banco de dados de pedidos está vazio.")
            return

        finalizados = filtrar_status(df_pedidos, STATUS_PRONTO)
        
        if finalizados.empty:
            st.warning("Ainda não existem pedidos finalizados no histórico.")
            return

        finalizados = finalizados.sort_values(by="id", ascending=False)

        for _, row in finalizados.iterrows():
            pago = str(row.get("pagamento", "")).strip().upper() == PAGAMENTO_PAGO
            cor_status = "#28a745" if pago else "#dc3545"
            label_pgto = "PAGO" if pago else "A PAGAR"
            valor_total = parse_float(row.get("total", 0))
            
            # CRIANDO O HTML EM UMA VARIÁVEL PARA GARANTIR LIMPEZA
            html_card = f"""
            <div style="
                background-color: white;
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 15px;
                border-left: 6px solid {cor_status};
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                color: #1e1e1e !important;
            ">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <span style="font-size: 1.2em; font-weight: bold;">👤 {row.get('cliente', 'Não informado')}</span>
                    <span style="background-color: {cor_status}; color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: bold;">
                        {label_pgto}
                    </span>
                </div>
                
                <div style="color: #555; font-size: 0.95em; line-height: 1.4;">
                    <p style="margin: 0;">📅 <b>Data:</b> {row.get('data', 'S/D')}</p>
                    <p style="margin: 0;">📍 <b>Endereço:</b> {row.get('endereco', 'Não informado')}</p>
                </div>

                <div style="margin-top: 15px; border-top: 1px solid #eee; padding-top: 10px; display: flex; justify-content: space-between; align-items: flex-end;">
                    <div>
                        <span style="color: #888; font-size: 0.8em; display: block;">VALOR TOTAL</span>
                        <span style="font-size: 1.5em; font-weight: 800; color: #2e7d32;">R$ {valor_total:.2f}</span>
                    </div>
                </div>
            </div>
            """
            
            # O comando st.markdown precisa estar fora de qualquer outra indentação de texto
            st.markdown(html_card, unsafe_allow_html=True)

            with st.expander(f"📋 Ver itens do pedido"):
                try:
                    itens = json.loads(row.get("itens", "[]"))
                    for it in itens:
                        st.write(f"• {it['qtd']}x **{it['nome']}** — R$ {parse_float(it['subtotal']):.2f}")
                    if row.get('obs'):
                        st.info(f"**Obs:** {row['obs']}")
                except:
                    st.error("Erro ao carregar detalhes.")
def render_tab_financeiro(tab):
    with tab:
        st.header("💰 Financeiro")
        st.caption("Acompanhe o que ja foi recebido e o que ainda falta receber.")
        if df_pedidos.empty:
            st.info("Sem dados financeiros disponiveis.")
            return

        recebido, pendente = calcular_totais_financeiros(df_pedidos)
        c_rec, c_pen = st.columns(2)
        c_rec.metric("Recebido", f"R$ {recebido:.2f}")
        c_pen.metric("A Receber", f"R$ {pendente:.2f}")


# 5 ABAS
aba1, aba2, aba3, aba4, aba5 = st.tabs(["🛒 Novo Pedido", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro"])
render_tab_novo_pedido(aba1)
render_tab_colheita(aba2)
render_tab_montagem(aba3)
render_tab_historico(aba4)
render_tab_financeiro(aba5)
