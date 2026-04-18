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

st.markdown(
    """
<div class="hero">
    <div class="title">Horta Gestao</div>
    <div class="subtitle">Pedidos, colheita, montagem e financeiro em um painel simples.</div>
</div>
""",
    unsafe_allow_html=True,
)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna('')
    except:
        return pd.DataFrame()


def resumo_kpis(df):
    if df.empty:
        return {"total": 0, "pendentes": 0, "prontos": 0, "recebido": 0.0, "areceber": 0.0}

    status = df.get("status", pd.Series(dtype=str)).astype(str).str.lower()
    pagamento = df.get("pagamento", pd.Series(dtype=str)).astype(str)
    totais = pd.to_numeric(df.get("total", pd.Series(dtype=float)), errors="coerce").fillna(0)
    total = len(df)
    pend = int((status == STATUS_PENDENTE).sum())
    pronto = int((status == STATUS_PRONTO).sum())
    recebido = float(totais[pagamento == PAGAMENTO_PAGO].sum())
    areceber = float(totais[pagamento == PAGAMENTO_A_PAGAR].sum())
    return {"total": total, "pendentes": pend, "prontos": pronto, "recebido": recebido, "areceber": areceber}


def carregar_pedidos():
    return carregar_dados("Pedidos")


def filtrar_status(df, status):
    if df.empty:
        return pd.DataFrame()

    status_series = df.get("status", pd.Series(dtype=str)).astype(str).str.lower()
    return df[status_series == status]


def calcular_totais_financeiros(df):
    if df.empty:
        return 0.0, 0.0

    pagamento = df.get("pagamento", pd.Series(dtype=str)).astype(str)
    totais = pd.to_numeric(df.get("total", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    recebido = float(totais[pagamento == PAGAMENTO_PAGO].sum())
    pendente = float(totais[pagamento == PAGAMENTO_A_PAGAR].sum())
    return recebido, pendente


df_global = carregar_dados("Pedidos")
kpis = resumo_kpis(df_global)

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

        df_p = carregar_dados("Produtos")
        carrinho = []
        total_v = 0.0
        if not df_p.empty:
            for _, r in df_p.iterrows():
                col_n, col_p, col_q = st.columns([3.4, 1.3, 1.1])
                p_u = float(str(r.get('preco', 0)).replace(',', '.'))
                tipo = str(r.get('tipo', 'UN')).upper()
                col_n.markdown(f"**{r['nome']}**")
                col_p.caption(f"R$ {p_u:.2f} / {tipo}")
                qtd = col_q.number_input("Q", 0, step=1, key=f"q_{r['id']}_{f}", label_visibility="collapsed")
                if qtd > 0:
                    sub = 0.0 if tipo == "KG" else (qtd * p_u)
                    total_v += sub
                    carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": tipo})
        else:
            st.info("Nenhum produto encontrado na aba 'Produtos'.")

        st.markdown(f"<div class='total-badge'>Total parcial: R$ {total_v:.2f}</div>", unsafe_allow_html=True)

        if st.button("💾 FINALIZAR PEDIDO", type="primary", key=f"btn_s_{f}"):
            if n_cli and carrinho:
                df_v = carregar_dados("Pedidos")
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
                conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
                st.session_state.f_id += 1
                st.rerun()


def render_tab_colheita(tab):
    with tab:
        st.header("🚜 Lista de Colheita")
        st.caption("Resumo dos itens pendentes para preparar na horta.")
        df_ped = carregar_pedidos()
        if not df_ped.empty:
            pend = filtrar_status(df_ped, STATUS_PENDENTE)
            if not pend.empty:
                resumo = {}
                for _, ped in pend.iterrows():
                    try:
                        for it in json.loads(ped['itens']):
                            chave = f"{it['nome']} ({it.get('tipo', 'UN')})"
                            resumo[chave] = resumo.get(chave, 0) + it['qtd']
                    except:
                        continue

                for item, qtd in resumo.items():
                    st.write(f"🟢 **{qtd}x** {item}")

                txt_z = "*COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in resumo.items()])
                st.markdown(
                    f'<a href="https://wa.me/?text={urllib.parse.quote(txt_z)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>',
                    unsafe_allow_html=True,
                )
            else:
                st.success("Nao ha pedidos pendentes de colheita.")
        else:
            st.info("Sem dados na aba 'Pedidos'.")


def render_tab_montagem(tab):
    with tab:
        st.header("⚖️ Montagem")
        st.caption("Ajuste valores dos itens por quilo e finalize os pedidos.")
        df_m = carregar_pedidos()
        if not df_m.empty:
            pend_m = filtrar_status(df_m, STATUS_PENDENTE)
            if pend_m.empty:
                st.success("Nao ha pedidos para montar no momento.")

            for idx, row in pend_m.iterrows():
                with st.expander(f"👤 {row['cliente']}", expanded=True):
                    st.write(f"📍 {row['endereco']}")
                    try:
                        itens_m = json.loads(row['itens'])
                    except Exception:
                        st.warning("Nao foi possivel ler os itens deste pedido.")
                        continue

                    st.markdown("<div class='m-list-header'><span>Item</span><span>Valor</span></div>", unsafe_allow_html=True)
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
                            subtotal = float(it.get('subtotal', 0))
                            c_i.markdown(
                                f"<div class='m-item-row'><span class='m-item-name'>✅ {nome}</span><span class='m-item-tag'>{qtd}x</span></div>",
                                unsafe_allow_html=True,
                            )
                            c_v.markdown(f"<div class='m-item-price'>R$ {subtotal:.2f}</div>", unsafe_allow_html=True)
                        total_m += float(it['subtotal'])

                    st.markdown(f"<div class='m-total'>TOTAL: R$ {total_m:.2f}</div>", unsafe_allow_html=True)
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
                        df_m.at[idx, 'status'] = 'Pronto'
                        df_m.at[idx, 'total'] = total_m
                        df_m.at[idx, 'itens'] = json.dumps(itens_m)
                        conn.update(worksheet="Pedidos", data=df_m)
                        st.rerun()

                    if col_delete.button("🗑️", key=f"del_{row['id']}"):
                        df_m = df_m.drop(idx)
                        conn.update(worksheet="Pedidos", data=df_m)
                        st.rerun()


def render_tab_historico(tab):
    with tab:
        st.header("📜 Histórico")
        st.caption("Pedidos finalizados com valor total e status de pagamento.")
        df_h = carregar_pedidos()
        if not df_h.empty:
            finalizados = filtrar_status(df_h, STATUS_PRONTO)
            st.dataframe(finalizados[["data", "cliente", "total", "pagamento"]])
        else:
            st.info("Sem historico para exibir.")


def render_tab_financeiro(tab):
    with tab:
        st.header("💰 Financeiro")
        st.caption("Acompanhe o que ja foi recebido e o que ainda falta receber.")
        df_f = carregar_pedidos()
        if not df_f.empty:
            recebido, pendente = calcular_totais_financeiros(df_f)
            c_rec, c_pen = st.columns(2)
            c_rec.metric("Recebido", f"R$ {recebido:.2f}")
            c_pen.metric("A Receber", f"R$ {pendente:.2f}")
        else:
            st.info("Sem dados financeiros disponiveis.")


# 5 ABAS
aba1, aba2, aba3, aba4, aba5 = st.tabs(["🛒 Novo Pedido", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro"])
render_tab_novo_pedido(aba1)
render_tab_colheita(aba2)
render_tab_montagem(aba3)
render_tab_historico(aba4)
render_tab_financeiro(aba5)
