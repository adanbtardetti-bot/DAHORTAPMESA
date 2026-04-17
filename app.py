import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# 1. CONFIGURAÇÃO INICIAL (NÃO MEXER)
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# Inicializa o estado do formulário para permitir limpeza
if "form_id" not in st.session_state:
    st.session_state.form_id = 0

# --- BLOCO 1: DADOS (ISOLADO) ---
# Aumentamos o TTL para 10 segundos para não travar o Google, mas carregar os produtos
def get_data():
    try:
        p = conn.read(worksheet="Produtos", ttl=10).dropna(how="all")
        v = conn.read(worksheet="Pedidos", ttl=10).dropna(how="all")
        p.columns = [str(c).lower().strip() for c in p.columns]
        v.columns = [str(c).lower().strip() for c in v.columns]
        # Garante que as colunas existam
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in v.columns: v[col] = ""
        return p, v
    except:
        st.error("Erro ao conectar com a planilha. Verifique a internet.")
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = get_data()

# --- BLOCO 2: IMPRESSÃO (ISOLADO) ---
def imprimir_rawbt(ped, valor, label="🖨️ IMPRIMIR"):
    nome = str(ped.get('cliente', '')).upper()
    end = str(ped.get('endereco', '')).upper()
    pg = str(ped.get('pagamento', '')).upper()
    status_txt = f"\n*** {pg} ***\n" if "PAGO" in pg else "\n"
    v_format = f"{float(valor):.2f}".replace('.', ',')
    
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{end}{status_txt}\n\x1b\x61\x01\x1b\x21\x10TOTAL: RS {v_format}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border:1px solid white;">{label}</div></a>', unsafe_allow_html=True)

# --- BLOCO 3: INTERFACE (ABAS) ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# NOVO PEDIDO
with tabs[0]:
    fid = st.session_state.form_id
    c1, c2 = st.columns(2)
    nome = c1.text_input("NOME", key=f"n{fid}").upper()
    end = c2.text_input("ENDEREÇO", key=f"e{fid}").upper()
    obs = st.text_area("OBS", key=f"o{fid}").upper()
    pago = st.checkbox("PAGO", key=f"p{fid}")
    
    st.write("---")
    itens_selecionados = []
    total_previo = 0.0
    
    if not df_produtos.empty:
        # Filtra apenas ativos e garante que os produtos APAREÇAM
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for _, row in ativos.iterrows():
            col_nome, col_qtd = st.columns([3, 1])
            q = col_qtd.number_input(f"{row['nome']} (R$ {row['preco']})", min_value=0, step=1, key=f"prod_{row['id']}_{fid}")
            if q > 0:
                p_unit = float(str(row['preco']).replace(',', '.'))
                sub = 0.0 if str(row['tipo']).upper() == "KG" else (q * p_unit)
                itens_selecionados.append({"nome": row['nome'], "qtd": q, "tipo": row['tipo'], "subtotal": sub})
                total_previo += sub
    
    if st.button("✅ SALVAR", use_container_width=True):
        if (nome or end) and itens_selecionados:
            prox_id = int(pd.to_numeric(df_pedidos['id'], errors='coerce').max() + 1) if not df_pedidos.empty else 1
            novo = pd.DataFrame([{"id": prox_id, "cliente": nome, "endereco": end, "obs": obs, "itens": json.dumps(itens_selecionados), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if pago else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
            st.session_state.form_id += 1
            st.cache_data.clear()
            st.rerun()

# COLHEITA
with tabs[1]:
    pend = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    if not pend.empty:
        res = {}
        for _, r in pend.iterrows():
            for it in json.loads(r['itens']): res[it['nome']] = res.get(it['nome'], 0) + it['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Qtd": v} for k, v in res.items()]))

# MONTAGEM
with tabs[2]:
    pend = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            st.subheader(p['cliente'])
            itens_l = json.loads(p['itens']); t_real = 0.0; pronto = True
            for i, it in enumerate(itens_l):
                if str(it['tipo']).upper() == "KG":
                    v = st.text_input(f"Valor {it['nome']}:", key=f"m{p['id']}{i}")
                    if v: it['subtotal'] = float(v.replace(',', '.')); t_real += it['subtotal']
                    else: pronto = False
                else: t_real += float(it['subtotal'])
            imprimir_rawbt(p, t_real)
            if st.button("CONCLUIR", key=f"f{p['id']}", disabled=not pronto):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_l)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()

# --- BLOCO 4: CONSULTAS ORIGINAIS (HISTÓRICO, FINANCEIRO, ESTOQUE) ---
with tabs[3]: st.dataframe(df_pedidos[df_pedidos['status'] == "Concluído"], use_container_width=True)
with tabs[4]: st.dataframe(df_pedidos, use_container_width=True)
with tabs[5]: st.dataframe(df_produtos, use_container_width=True)
