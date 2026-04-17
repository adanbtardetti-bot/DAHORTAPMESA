import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        # ttl=0 garante que ele ignore o lixo da memória e pegue o que está no Google agora
        df_p = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        
        # LIMPEZA AGRESSIVA: Tira espaços e deixa tudo minúsculo
        df_p.columns = [str(c).strip().lower() for c in df_p.columns]
        df_v.columns = [str(c).strip().lower() for c in df_v.columns]
        
        # BLINDAGEM: Se a coluna sumiu da planilha, o código cria ela aqui dentro
        col_v = ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']
        for c in col_v:
            if c not in df_v.columns: df_v[c] = ""
            
        col_p = ['id', 'nome', 'preco', 'tipo', 'status']
        for c in col_p:
            if c not in df_p.columns: df_p[c] = ""
            
        return df_p, df_v
    except Exception as e:
        st.error(f"Erro ao ler Planilha: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- 2. MOTOR DE IMPRESSÃO ---
def imprimir_acao(ped, valor, modo="ETIQUETA"):
    try:
        nome = str(ped.get('cliente', '')).upper()
        v_f = f"{float(valor):.2f}".replace('.', ',')
        pag = str(ped.get('pagamento', '')).upper()
        
        if modo == "ETIQUETA":
            cmds = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\nTOTAL: RS {v_f}\n({pag})\n\n\n\n"
            lbl, cor = "🖨️ ETIQUETA", "#28a745"
        else:
            itens_str = ""
            for it in json.loads(ped['itens']):
                itens_str += f"{it['nome']} -> RS {float(it['subtotal']):.2f}\n"
            cmds = f"\x1b\x61\x01\x1b\x21\x10HORTA DA MESA\n----------------\n{nome}\n----------------\n{itens_str}TOTAL: RS {v_f}\n\n\n\n"
            lbl, cor = "📄 RECIBO", "#007bff"
            
        b64 = base64.b64encode(cmds.encode('latin-1')).decode('utf-8')
        url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:{cor};color:white;padding:10px;text-align:center;border-radius:5px;font-weight:bold;margin-bottom:5px;">{lbl}</div></a>', unsafe_allow_html=True)
    except: pass

# --- 3. INTERFACE ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- NOVO PEDIDO ---
with tabs[0]:
    if "reset" not in st.session_state: st.session_state.reset = 0
    r = st.session_state.reset
    c1, c2 = st.columns(2)
    nc = c1.text_input("NOME", key=f"n{r}").upper()
    ec = c2.text_input("ENDEREÇO", key=f"e{r}").upper()
    oc = st.text_area("OBS", key=f"o{r}", height=70).upper()
    pa = st.checkbox("PAGO ANTECIPADO", key=f"p{r}")
    
    itens_v, t_est = [], 0.0
    if not df_produtos.empty:
        # Busca produtos onde status é 'ativo' (não importa se é Ativo, ATIVO ou ativo na planilha)
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for _, row in ativos.iterrows():
            ca, cb = st.columns([4, 1])
            qtd = cb.number_input(f"{row['nome']} (R$ {row['preco']})", min_value=0, step=1, key=f"pr{row['id']}{r}")
            if qtd > 0:
                p_u = float(str(row['preco']).replace(',', '.'))
                sub = 0.0 if str(row['tipo']).upper() == "KG" else (qtd * p_u)
                itens_v.append({"nome": row['nome'], "qtd": qtd, "tipo": row['tipo'], "subtotal": sub})
                t_est += sub
    
    st.subheader(f"Total: R$ {t_est:.2f}")
    if st.button("💾 SALVAR", use_container_width=True):
        if (nc or ec) and itens_v:
            n_id = int(pd.to_numeric(df_pedidos['id'], errors='coerce').max() + 1) if not df_pedidos.empty else 1
            novo = pd.DataFrame([{"id": n_id, "cliente": nc, "endereco": ec, "obs": oc, "itens": json.dumps(itens_v), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if pa else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
            st.session_state.reset += 1; st.rerun()

# --- MONTAGEM ---
with tabs[2]:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {p['cliente']}")
            st.write(f"📍 {p['endereco']}")
            its, tf, ready = json.loads(p['itens']), 0.0, True
            for i, it in enumerate(its):
                if str(it['tipo']).upper() == "KG":
                    vk = st.text_input(f"Peso {it['nome']} ({it['qtd']}kg):", key=f"m{p['id']}{i}")
                    if vk: 
                        v = float(vk.replace(',', '.')); it['subtotal'] = v; tf += v
                    else: ready = False
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN"); tf += float(it['subtotal'])
            st.write(f"**Total: R$ {tf:.2f}**")
            imprimir_acao(p, tf, "ETIQUETA"); imprimir_acao(p, tf, "RECIBO")
            if st.button("✅ FINALIZAR", key=f"f{p['id']}", disabled=not ready, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = tf; df_pedidos.at[idx, 'itens'] = json.dumps(its)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# --- HISTÓRICO ---
with tabs[3]:
    st.header("📅 Histórico")
    dt = st.date_input("Data", datetime.now()).strftime("%d/%m/%Y")
    h_fil = df_pedidos[(df_pedidos['status'].astype(str).str.lower() == "concluído") & (df_pedidos['data'] == dt)]
    for idx, p in h_fil.iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            c1.write(f"**{p['cliente']}**\n\n{p['endereco']}")
            cor = "green" if p['pagamento'] == "PAGO" else "red"
            c2.markdown(f"**R$ {float(p['total']):.2f}**\n\n<span style='color:{cor}'>{p['pagamento']}</span>", unsafe_allow_html=True)
            with c3:
                if st.button("💳 PGTO", key=f"pg{p['id']}"):
                    df_pedidos.at[idx, 'pagamento'] = "A PAGAR" if p['pagamento'] == "PAGO" else "PAGO"
                    conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
                with st.popover("📄 VER"):
                    for it in json.loads(p['itens']): st.write(f"{it['nome']}: R$ {it['subtotal']:.2f}")
                    imprimir_acao(p, p['total'], "ETIQUETA"); imprimir_acao(p, p['total'], "RECIBO")

# --- ESTOQUE ---
with tabs[5]:
    st.header("🥦 Estoque")
    # Adicionar
    with st.expander("➕ NOVO"):
        with st.form("add_p"):
            n, pr, t = st.text_input("Nome"), st.text_input("Preço"), st.selectbox("Tipo", ["UN", "KG"])
            if st.form_submit_button("SALVAR"):
                px = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
                nv = pd.DataFrame([{"id": px, "nome": n.upper(), "preco": pr, "tipo": t, "status": "ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, nv], ignore_index=True)); st.rerun()
    # Lista
    for i, r in df_produtos.iterrows():
        c1, c2, c3 = st.columns([4, 1, 1])
        c1.write(f"**{r['nome']}** ({r['status']})")
        btn_l = "🚫" if r['status'] == "ativo" else "✅"
        if c2.button(btn_l, key=f"s{r['id']}"):
            df_produtos.at[i, 'status'] = "inativo" if r['status'] == "ativo" else "ativo"
            conn.update(worksheet="Produtos", data=df_produtos); st.rerun()
        if c3.button("🗑️", key=f"d{r['id']}"):
            conn.update(worksheet="Produtos", data=df_produtos.drop(i)); st.rerun()
