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
            col_h1, col_h2 = st.columns(2)
            b64_h = gerar_b64_etiqueta(row['cliente'], row['endereco'], parse_float(row['total']), row['pagamento'])
            col_h1.markdown(f'<a href="intent:base64,{b64_h}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print" style="text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; color:black;">🖨️ Reimprimir</a>', unsafe_allow_html=True)
            if not pago:
                if col_h2.button("💵 Marcar Pago", key=f"hpay_{row['id']}", use_container_width=True):
                    df_f = ler_aba("Pedidos", ttl=0)
                    df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO
                    salvar_aba("Pedidos", df_f); st.rerun()
            with st.expander("📋 Detalhes"):
                for it in json.loads(row['itens']): st.write(f"• {it['qtd']}x {it['nome']}")

# 5. FINANCEIRO (COM VALOR POR ITEM)
with aba5:
    st.header("💰 Financeiro")
    menu = st.radio("Tipo de Relatório:", ["Resumo do Dia", "Resumo por Período", "Seleção Manual (Grupo)"], horizontal=True)

    def mostrar_resumo_financeiro(df_foco):
        if df_foco.empty:
            st.warning("Nenhum pedido encontrado.")
            return
        
        total_geral = df_foco['total'].apply(parse_float).sum()
        st.metric("Faturamento Total", f"R$ {total_geral:.2f}")
        
        resumo_itens = {}
        for _, r in df_foco.iterrows():
            try:
                itens = json.loads(r['itens'])
                for it in itens:
                    nome = it['nome']
                    valor_it = parse_float(it.get('subtotal', 0))
                    if nome not in resumo_itens:
                        resumo_itens[nome] = {"qtd": 0, "valor": 0.0}
                    resumo_itens[nome]["qtd"] += it['qtd']
                    resumo_itens[nome]["valor"] += valor_it
            except: continue
        
        # Criação da tabela com valor total por item
        dados_tabela = []
        for nome, dados in resumo_itens.items():
            dados_tabela.append({
                "Produto": nome,
                "Qtd Total": dados["qtd"],
                "Valor Total (R$)": f"{dados['valor']:.2f}"
            })
        
        df_tabela = pd.DataFrame(dados_tabela).sort_values(by="Valor Total (R$)", ascending=False)
        st.table(df_tabela)
        return total_geral, resumo_itens

    if menu == "Resumo do Dia":
        hoje = datetime.now().strftime("%d/%m/%Y")
        st.subheader(f"📅 Hoje: {hoje}")
        mostrar_resumo_financeiro(df_pedidos[df_pedidos["data"] == hoje])

    elif menu == "Resumo por Período":
        c1, c2 = st.columns(2)
        ini, fim = c1.date_input("Início", datetime.now() - timedelta(days=7)), c2.date_input("Fim", datetime.now())
        df_pedidos['dt_aux'] = pd.to_datetime(df_pedidos['data'], format='%d/%m/%Y', errors='coerce').dt.date
        df_per = df_pedidos[(df_pedidos['dt_aux'] >= ini) & (df_pedidos['dt_aux'] <= fim)]
        mostrar_resumo_financeiro(df_per)

    elif menu == "Seleção Manual (Grupo)":
        d_grupo = st.date_input("Escolha a data:", datetime.now()).strftime("%d/%m/%Y")
        df_dia_g = df_pedidos[df_pedidos["data"] == d_grupo]
        
        if df_dia_g.empty:
            st.warning(f"Sem pedidos em {d_grupo}")
        else:
            selecionados = []
            for i, r in df_dia_g.iterrows():
                if st.checkbox(f"👤 {r['cliente']} | R$ {r['total']}", key=f"fin_{r['id']}"):
                    selecionados.append(r)
            
            if selecionados:
                st.markdown("---")
                t_g, res_g = mostrar_resumo_financeiro(pd.DataFrame(selecionados))
                
                # WhatsApp com valores por item
                texto_zap = f"*RELATÓRIO DE GRUPO ({d_grupo})*\nTotal: R$ {t_g:.2f}\n\n"
                for k, v in res_g.items():
                    texto_zap += f"- {v['qtd']}x {k}: R$ {v['valor']:.2f}\n"
                
                st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(texto_zap)}" target="_blank" class="btn-zap">ENVIAR RELATÓRIO</a>', unsafe_allow_html=True)
