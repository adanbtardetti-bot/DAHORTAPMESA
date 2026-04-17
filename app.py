import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime, timedelta

# 1. Configuração e Conexão
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# --- CONTROLE DE LIMPEZA (NÃO MEXER) ---
if "form_id" not in st.session_state:
    st.session_state.form_id = 0

def resetar_formulario():
    st.session_state.form_id += 1
    st.cache_data.clear()

# --- CARREGAMENTO DE DADOS ---
def carregar_dados():
    try:
        df_p = conn.read(worksheet="Produtos", ttl=2).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=2).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except:
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- FUNÇÃO IMPRIMIR ---
def botao_imprimir(ped, label="🖨️ IMPRIMIR"):
    nome = str(ped.get('cliente', 'CLIENTE')).upper()
    total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {total}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">{label}</div></a>', unsafe_allow_html=True)

# --- NAVEGAÇÃO (TODAS AS ABAS VOLTARAM) ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO (MANTIDO) ---
with tab1:
    st.header("🛒 Novo Pedido")
    fid = st.session_state.form_id
    col1, col2 = st.columns(2)
    nome = col1.text_input("NOME DO CLIENTE", key=f"nome_{fid}").upper()
    end = col2.text_input("ENDEREÇO", key=f"end_{fid}").upper()
    obs = st.text_area("OBSERVAÇÕES", key=f"obs_{fid}").upper()
    pago = st.checkbox("PAGO ANTECIPADO", key=f"pago_{fid}")
    st.divider()
    itens_venda = []; total_previo = 0.0
    if not df_produtos.empty:
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        c_prod1, c_prod2 = st.columns(2)
        for i, (_, p) in enumerate(ativos.iterrows()):
            alvo = c_prod1 if i % 2 == 0 else c_prod2
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"p_{p['id']}_{fid}")
            if qtd > 0:
                preco = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if str(p['tipo']).upper() == "KG" else (qtd * preco)
                itens_venda.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                total_previo += sub
    st.markdown(f"### 💰 Total: R$ {total_previo:.2f}")
    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (nome or end) and itens_venda:
            ids = pd.to_numeric(df_pedidos['id'], errors='coerce').dropna()
            prox_id = int(ids.max() + 1) if not ids.empty else 1
            novo_row = pd.DataFrame([{"id": prox_id, "cliente": nome, "endereco": end, "obs": obs, "itens": json.dumps(itens_venda), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if pago else "A Pagar"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_row], ignore_index=True))
            resetar_formulario(); st.rerun()

# --- 2. COLHEITA (MANTIDO) ---
with tab2:
    st.header("🚜 Colheita")
    pendentes = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    if not pendentes.empty:
        resumo = {}
        for _, p in pendentes.iterrows():
            for it in json.loads(p['itens']):
                resumo[it['nome']] = resumo.get(it['nome'], 0) + it['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Total": v} for k, v in resumo.items()]))

# --- 3. MONTAGEM (MANTIDO) ---
with tab3:
    st.header("📦 Montagem")
    pendentes = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    for idx, p in pendentes.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {p['cliente']}")
            st.write(f"📍 {p['endereco']}")
            itens_list = json.loads(p['itens']); t_real = 0.0; trava = False
            for i, it in enumerate(itens_list):
                if str(it['tipo']).upper() == "KG":
                    val = st.text_input(f"R$ {it['nome']}:", key=f"m_{p['id']}_{i}")
                    if val: v = float(val.replace(',', '.')); it['subtotal'] = v; t_real += v
                    else: trava = True
                else:
                    st.write(f"- {it['nome']}: {it['qtd']} UN"); t_real += float(it['subtotal'])
            botao_imprimir({"cliente": p['cliente'], "total": t_real})
            if st.button("✅ FINALIZAR", key=f"f_{p['id']}", disabled=trava):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_list)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# --- 4. HISTÓRICO (RESTAURADO) ---
with tab4:
    st.header("📅 Histórico")
    dia = st.date_input("Data:", datetime.now()).strftime("%d/%m/%Y")
    filtro = df_pedidos[(df_pedidos['status'] == "Concluído") & (df_pedidos['data'] == dia)]
    for idx, p in filtro.iterrows():
        with st.expander(f"{p['cliente']} - R$ {p['total']}"):
            st.write(f"📍 {p['endereco']}")
            pag = st.selectbox("Pagamento", ["Pago", "A Pagar"], index=0 if p['pagamento'] == "Pago" else 1, key=f"h_{p['id']}")
            if pag != p['pagamento']:
                df_pedidos.at[idx, 'pagamento'] = pag
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
            botao_imprimir(p, "🖨️ REIMPRIMIR")

# --- 5. FINANCEIRO (RESTAURADO) ---
with tab5:
    st.header("📊 Financeiro")
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"].copy()
    if not concluidos.empty:
        total_f = concluidos['total'].astype(float).sum()
        st.metric("Faturamento Total", f"R$ {total_f:.2f}")
        st.dataframe(concluidos[['data', 'cliente', 'total', 'pagamento']])

# --- 6. ESTOQUE (RESTAURADO) ---
with tab6:
    st.header("🥦 Estoque")
    for idx, r in df_produtos.iterrows():
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.write(f"**{r['nome']}** - R$ {r['preco']} ({r['tipo']})")
        if c2.button("Ativo/Inativo", key=f"st_{idx}"):
            df_produtos.at[idx, 'status'] = "Inativo" if r['status'] == "Ativo" else "Ativo"
            conn.update(worksheet="Produtos", data=df_produtos); st.rerun()
