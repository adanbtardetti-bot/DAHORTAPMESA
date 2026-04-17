import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# 1. Configuração e Conexão
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

if "form_id" not in st.session_state:
    st.session_state.form_id = 0

def carregar_dados():
    try:
        df_p = conn.read(worksheet="Produtos", ttl=2).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=2).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except: return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- ETIQUETA COM ENDEREÇO E OBS (MANTIDA) ---
def botao_imprimir(ped, label="🖨️ IMPRIMIR"):
    nome = str(ped.get('cliente', '')).upper()
    endereco = str(ped.get('endereco', '')).upper()
    obs = str(ped.get('obs', '')).upper()
    total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
    
    # Comandos RawBT com endereço e observação inclusos
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{endereco}\n{obs}\n\x1b\x21\x10TOTAL: RS {total}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border:1px solid white;">{label}</div></a>', unsafe_allow_html=True)

# 2. ABAS
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- NOVO PEDIDO ---
with tabs[0]:
    fid = st.session_state.form_id
    c1, c2 = st.columns(2)
    nome = c1.text_input("NOME DO CLIENTE", key=f"n_{fid}").upper()
    end = c2.text_input("ENDEREÇO", key=f"e_{fid}").upper()
    obs = st.text_area("OBSERVAÇÕES", key=f"o_{fid}").upper()
    pago = st.checkbox("PAGO ANTECIPADO", key=f"p_{fid}")
    st.divider()
    itens_v = []; total_p = 0.0
    if not df_produtos.empty:
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        cp1, cp2 = st.columns(2)
        for i, (_, p) in enumerate(ativos.iterrows()):
            alvo = cp1 if i % 2 == 0 else cp2
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"prod_{p['id']}_{fid}")
            if qtd > 0:
                pr = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if str(p['tipo']).upper() == "KG" else (qtd * pr)
                itens_v.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                total_p += sub
    st.markdown(f"### 💰 Total: R$ {total_p:.2f}")
    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (nome or end) and itens_v:
            ids = pd.to_numeric(df_pedidos['id'], errors='coerce').dropna()
            px_id = int(ids.max() + 1) if not ids.empty else 1
            novo = pd.DataFrame([{"id": px_id, "cliente": nome, "endereco": end, "obs": obs, "itens": json.dumps(itens_v), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if pago else "A Pagar"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
            st.session_state.form_id += 1; st.cache_data.clear(); st.rerun()

# --- MONTAGEM ---
with tabs[2]:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            m1, m2 = st.columns([3, 1])
            m1.subheader(f"👤 {p['cliente']}")
            m1.write(f"📍 {p['endereco']}")
            if p['obs']: m1.info(f"📝 {p['obs']}")
            if m2.button("🗑️ EXCLUIR", key=f"exc_{p['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()
            itens_l = json.loads(p['itens']); t_r = 0.0; trava = False
            for i, it in enumerate(itens_l):
                if str(it['tipo']).upper() == "KG":
                    val = st.text_input(f"R$ {it['nome']}:", key=f"mt_{p['id']}_{i}")
                    if val: v = float(val.replace(',', '.')); it['subtotal'] = v; t_r += v
                    else: trava = True
                else: st.write(f"- {it['nome']}: {it['qtd']} UN"); t_r += float(it['subtotal'])
            st.write(f"**Total: R$ {t_r:.2f}**")
            botao_imprimir(p, "🖨️ IMPRIMIR") # Passa o objeto p completo agora
            if st.button("✅ FINALIZAR", key=f"fin_{p['id']}", disabled=trava, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_r; df_pedidos.at[idx, 'itens'] = json.dumps(itens_l)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()

# --- HISTÓRICO ---
with tabs[3]:
    st.header("📅 Histórico")
    data_h = st.date_input("Data:", datetime.now()).strftime("%d/%m/%Y")
    hists = df_pedidos[(df_pedidos['status'] == "Concluído") & (df_pedidos['data'] == data_h)]
    for idx, p in hists.iterrows():
        with st.expander(f"{p['cliente']} - R$ {p['total']}"):
            st.write(f"📍 {p['endereco']}\n📝 {p['obs']}")
            botao_imprimir(p, "🖨️ REIMPRIMIR")

# --- FINANCEIRO ---
with tabs[4]:
    st.header("📊 Financeiro")
    concl = df_pedidos[df_pedidos['status'] == "Concluído"].copy()
    if not concl.empty:
        st.metric("Total Faturado", f"R$ {concl['total'].astype(float).sum():.2f}")
        st.dataframe(concl[['data', 'cliente', 'total', 'pagamento']])

# --- ESTOQUE ---
with tabs[5]:
    st.header("🥦 Estoque")
    st.dataframe(df_produtos)
