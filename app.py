import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def limpar_nan(texto):
    if pd.isna(texto): return ""
    t = str(texto).replace('nan', '').replace('NaN', '').strip()
    return t

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        if df is None: return pd.DataFrame()
        df = df.dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame()

# Carga de dados unificada
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Garante colunas no Pedidos
colunas_p = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"]
for col in colunas_p:
    if col not in df_pedidos.columns: df_pedidos[col] = ""

# --- MOTOR DE IMPRESSÃO ---
def imprimir_comando(ped, valor_real, tipo="ETIQUETA"):
    nome = str(ped.get('cliente', '')).upper()
    v_f = f"{float(valor_real):.2f}".replace('.', ',')
    pag = str(ped.get('pagamento', '')).upper()
    
    if tipo == "ETIQUETA":
        cmds = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\nTOTAL: RS {v_f}\n({pag})\n\n\n\n"
        label, cor = "🖨️ ETIQUETA", "#28a745"
    else:
        detalhes = ""
        try:
            for it in json.loads(ped['itens']):
                detalhes += f"{it['nome'][:15]} -> RS {float(it['subtotal']):.2f}\n"
        except: detalhes = "Erro nos itens\n"
        cmds = f"\x1b\x61\x01\x1b\x21\x10HORTA DA MESA\n----------------\n{nome}\n----------------\n{detalhes}TOTAL: RS {v_f}\n\n\n\n"
        label, cor = "📄 RECIBO", "#007bff"

    b64 = base64.b64encode(cmds.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:{cor};color:white;padding:8px;text-align:center;border-radius:5px;font-weight:bold;font-size:12px;">{label}</div></a>', unsafe_allow_html=True)

# --- ABAS ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# ABA: NOVO
with tabs[0]:
    if "f_id" not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    c1, c2 = st.columns(2)
    n = c1.text_input("NOME", key=f"n{f}").upper()
    e = c2.text_input("ENDEREÇO", key=f"e{f}").upper()
    pa = st.checkbox("PAGO ANTECIPADO", key=f"p{f}")
    
    itens_v, t_est = [], 0.0
    if not df_produtos.empty:
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for _, row in ativos.iterrows():
            ca, cb = st.columns([4, 1])
            qtd = cb.number_input(f"{row['nome']} (R$ {row['preco']})", min_value=0, step=1, key=f"p{row['id']}{f}")
            if qtd > 0:
                pr = float(str(row['preco']).replace(',', '.'))
                sub = 0.0 if str(row['tipo']).upper() == "KG" else (qtd * pr)
                itens_v.append({"nome": row['nome'], "qtd": qtd, "tipo": row['tipo'], "subtotal": sub})
                t_est += sub
    
    st.subheader(f"Total: R$ {t_est:.2f}")
    if st.button("💾 SALVAR", use_container_width=True):
        if n and itens_v:
            nid = int(pd.to_numeric(df_pedidos['id'], errors='coerce').max() + 1) if not df_pedidos.empty else 1
            df_new = pd.DataFrame([{"id": nid, "cliente": n, "endereco": e, "itens": json.dumps(itens_v), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if pa else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, df_new], ignore_index=True))
            st.session_state.f_id += 1; st.rerun()

# ABA: MONTAGEM
with tabs[2]:
    pend = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            st.write(f"👤 **{p['cliente']}**")
            its, tf, ok = json.loads(p['itens']), 0.0, True
            for i, it in enumerate(its):
                if str(it['tipo']).upper() == "KG":
                    vk = st.text_input(f"{it['nome']} (kg):", key=f"m{p['id']}{i}")
                    if vk: v = float(vk.replace(',', '.')); it['subtotal'] = v; tf += v
                    else: ok = False
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN"); tf += float(it['subtotal'])
            imprimir_comando(p, tf, "ETIQUETA")
            if st.button("✅ FINALIZAR", key=f"f{p['id']}", disabled=not ok, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = tf; df_pedidos.at[idx, 'itens'] = json.dumps(its)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# ABA: HISTÓRICO (VERSÃO COMPACTA)
with tabs[3]:
    dt_f = st.date_input("Data", datetime.now()).strftime("%d/%m/%Y")
    h_fil = df_pedidos[(df_pedidos['status'].str.lower() == "concluído") & (df_pedidos['data'] == dt_f)]
    for idx, p in h_fil.iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 2, 2])
            c1.write(f"**{p['cliente']}**\n\n{p['endereco']}")
            cor = "green" if p['pagamento'] == "PAGO" else "red"
            c2.markdown(f"**R$ {float(p['total']):.2f}**\n\n<span style='color:{cor};font-weight:bold'>{p['pagamento']}</span>", unsafe_allow_html=True)
            with c3:
                if st.button("💳 PGTO", key=f"h{p['id']}"):
                    df_pedidos.at[idx, 'pagamento'] = "A PAGAR" if p['pagamento'] == "PAGO" else "PAGO"
                    conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
                with st.popover("📄 VER"):
                    imprimir_comando(p, p['total'], "ETIQUETA")
                    imprimir_comando(p, p['total'], "RECIBO")

# ABA: FINANCEIRO (MELHOR VERSÃO - MÉTRICAS)
with tabs[4]:
    st.header("📊 Resumo Financeiro")
    concl = df_pedidos[df_pedidos['status'].str.lower() == "concluído"]
    v_pago = concl[concl['pagamento'] == "PAGO"]['total'].astype(float).sum()
    v_pend = concl
