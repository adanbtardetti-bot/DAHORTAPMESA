import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime
from pathlib import Path

# Configuração inicial
st.set_page_config(page_title="Horta Gestão", page_icon="🥬", layout="wide")

# Estilos CSS Integrados para evitar erros de arquivo ausente
st.markdown("""
<style>
    .hero-banner {background-color: #2e7d32; color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px;}
    .total-badge {background-color: #e8f5e9; padding: 10px; border-radius: 5px; font-weight: bold; color: #2e7d32; margin: 10px 0;}
    .btn-print {text-decoration: none; background: #f0f2f6; border: 1px solid #ccc; padding: 5px 10px; border-radius: 5px; color: black; display: inline-block; text-align: center; width: 100%;}
</style>
""", unsafe_allow_html=True)

# Conexão e Constantes
conn = st.connection("gsheets", type=GSheetsConnection)
STATUS_PENDENTE = "pendente"
STATUS_PRONTO = "pronto"
PAGAMENTO_PAGO = "PAGO"
PAGAMENTO_A_PAGAR = "A PAGAR"

# --- FUNÇÕES DE DADOS ---

def ler_aba(aba: str, ttl: int = 10) -> pd.DataFrame:
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty: return pd.DataFrame()
        df = df.dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna("")
    except:
        return pd.DataFrame()

def salvar_aba(aba: str, df: pd.DataFrame):
    conn.update(worksheet=aba, data=df)
    conn.reset()

def parse_float(val):
    try: return float(str(val).replace(",", "."))
    except: return 0.0

def filtrar_status(df, status):
    if df.empty or "status" not in df.columns: return pd.DataFrame()
    return df[df["status"].astype(str).str.lower() == status.lower()]

# --- CARREGAMENTO ---
df_pedidos = ler_aba("Pedidos")
df_produtos = ler_aba("Produtos")

# --- CABEÇALHO ---
st.markdown('<div class="hero-banner"><h1>🥬 Horta Gestão</h1></div>', unsafe_allow_html=True)

# --- ABAS ---
t1, t2, t3, t4, t5 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Finanças"])

# 1. NOVO PEDIDO
with t1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("Cliente", key=f"n_{f}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f}").upper()
    pg_inicial = st.toggle("Pago agora?", key=f"p_{f}")
    
    carrinho, total_p = [], 0.0
    for i, r in df_produtos.iterrows():
        c_n, c_q = st.columns([3, 1])
        qtd = c_q.number_input("Qtd", 0, key=f"q_{i}_{f}", label_visibility="collapsed")
        c_n.write(f"**{r['nome']}** (R$ {r['preco']})")
        if qtd > 0:
            sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * parse_float(r['preco']))
            total_p += sub
            carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": r['preco'], "subtotal": sub, "tipo": r['tipo']})
    
    st.markdown(f"<div class='total-badge'>Subtotal: R$ {total_p:.2f}</div>", unsafe_allow_html=True)
    if st.button("💾 SALVAR", key=f"btn_{f}", use_container_width=True):
        if n_cli and carrinho:
            df_at = ler_aba("Pedidos", ttl=0)
            novo = pd.DataFrame([{
                "id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli,
                "itens": json.dumps(carrinho), "status": STATUS_PENDENTE, "total": total_p,
                "data": datetime.now().strftime("%d/%m/%Y"),
                "pagamento": PAGAMENTO_PAGO if pg_inicial else PAGAMENTO_A_PAGAR
            }])
            salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True))
            st.session_state.f_id += 1
            st.rerun()

# 2. COLHEITA
with t2:
    pend = filtrar_status(df_pedidos, STATUS_PENDENTE)
    if not pend.empty:
        res = {}
        for _, p in pend.iterrows():
            for it in json.loads(p['itens']):
                k = f"{it['nome']} ({it['tipo']})"
                res[k] = res.get(k, 0) + it['qtd']
        for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")
    else: st.write("Tudo colhido!")

# 3. MONTAGEM
with t3:
    pend_m = filtrar_status(df_pedidos, STATUS_PENDENTE)
    for _, row in pend_m.iterrows():
        with st.expander(f"📦 {row['cliente']}"):
            itens = json.loads(row['itens'])
            t_m = 0.0
            for i, it in enumerate(itens):
                if it['tipo'] == "KG":
                    v = st.number_input(f"Peso {it['nome']}", 0.0, key=f"v_{row['id']}_{i}")
                    it['subtotal'] = v
                t_m += it['subtotal']
            if st.button("PRONTO", key=f"ok_{row['id']}"):
                df_f = ler_aba("Pedidos", ttl=0)
                df_f.loc[df_f['id'].astype(str) == str(row['id']), ["status", "total", "itens"]] = [STATUS_PRONTO, t_m, json.dumps(itens)]
                salvar_aba("Pedidos", df_f)
                st.rerun()

# 4. HISTÓRICO (Com Impressão e Botão Pago)
with t4:
    hist = filtrar_status(df_pedidos, STATUS_PRONTO).sort_values("id", ascending=False)
    for _, row in hist.iterrows():
        pago = str(row['pagamento']).upper() == PAGAMENTO_PAGO
        cor = "#28a745" if pago else "#dc3545"
        
        card = f"""<div style="background:white; border-radius:10px; padding:15px; margin-bottom:10px; border-left:6px solid {cor}; color:black; border:1px solid #eee;">
            <b>👤 {row['cliente']}</b> - {row['pagamento']}<br>
            <small>📅 {row['data']} | R$ {parse_float(row['total']):.2f}</small>
        </div>"""
        st.markdown(card, unsafe_allow_html=True)
        
        c_i, c_p = st.columns(2)
        # Botão Imprimir
        txt_etiqueta = f"CLIENTE: {row['cliente']}\nTOTAL: R$ {row['total']}\n{row['pagamento']}"
        b64 = base64.b64encode(txt_etiqueta.encode()).decode()
        c_i.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️ Etiqueta</a>', unsafe_allow_html=True)
        
        if not pago:
            if c_p.button("💵 Marcar Pago", key=f"pay_{row['id']}", use_container_width=True):
                df_f = ler_aba("Pedidos", ttl=0)
                df_f.loc[df_f['id'].astype(str) == str(row['id']), "pagamento"] = PAGAMENTO_PAGO
                salvar_aba("Pedidos", df_f)
                st.rerun()

# 5. FINANÇAS (Corrigido)
with t5:
    if not df_pedidos.empty:
        df_pedidos["total_num"] = df_pedidos["total"].apply(parse_float)
        recebido = df_pedidos[df_pedidos["pagamento"] == PAGAMENTO_PAGO]["total_num"].sum()
        a_receber = df_pedidos[df_pedidos["pagamento"] == PAGAMENTO_A_PAGAR]["total_num"].sum()
        st.metric("Recebido", f"R$ {recebido:.2f}")
        st.metric("A Receber", f"R$ {a_receber:.2f}")
