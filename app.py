import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO (NÃO ALTERAR) ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

if "form_id" not in st.session_state:
    st.session_state.form_id = 0

# --- CARREGAMENTO DE DADOS ---
def carregar_dados():
    try:
        # TTL de 15 segundos para evitar o erro 429 do Google
        df_p = conn.read(worksheet="Produtos", ttl=15).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=15).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except:
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- FUNÇÃO DE IMPRESSÃO (A pedido: Nome, Endereço, Valor e PAGO) ---
def botao_imprimir(ped, valor_real, label="🖨️ IMPRIMIR ETIQUETA"):
    def limpar(txt):
        if pd.isna(txt) or str(txt).lower() == 'nan': return ""
        return str(txt).strip().upper()

    nome = limpar(ped.get('cliente', ''))
    endereco = limpar(ped.get('endereco', ''))
    pagamento = limpar(ped.get('pagamento', ''))
    
    # Só exibe "PAGO" se estiver marcado, caso contrário fica em branco
    txt_pago = f"\n*** {pagamento} ***\n" if "PAGO" in pagamento else "\n"
    valor_formatado = f"{float(valor_real):.2f}".replace('.', ',')
    
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{endereco}\n{txt_pago}\n\x1b\x61\x01\x1b\x21\x10TOTAL: RS {valor_formatado}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border:1px solid white;">{label}</div></a>', unsafe_allow_html=True)

# --- INTERFACE POR ABAS ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# 1. NOVO PEDIDO
with tabs[0]:
    fid = st.session_state.form_id
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("NOME DO CLIENTE", key=f"n_{fid}").upper()
    e_cli = c2.text_input("ENDEREÇO", key=f"e_{fid}").upper()
    o_cli = st.text_area("OBSERVAÇÕES", key=f"o_{fid}").upper()
    p_cli = st.checkbox("PAGO ANTECIPADO", key=f"p_{fid}")
    st.divider()
    
    itens_v = []
    if not df_produtos.empty:
        # Garante que os itens apareçam
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for i, row in ativos.iterrows():
            col1, col2 = st.columns([3, 1])
            qtd = col2.number_input(f"{row['nome']} (R$ {row['preco']})", min_value=0, step=1, key=f"pr_{row['id']}_{fid}")
            if qtd > 0:
                p_u = float(str(row['preco']).replace(',', '.'))
                sub = 0.0 if str(row['tipo']).upper() == "KG" else (qtd * p_u)
                itens_v.append({"nome": row['nome'], "qtd": qtd, "tipo": row['tipo'], "subtotal": sub})

    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (n_cli or e_cli) and itens_v:
            prox_id = int(pd.to_numeric(df_pedidos['id'], errors='coerce').max() + 1) if not df_pedidos.empty else 1
            novo = pd.DataFrame([{"id": prox_id, "cliente": n_cli, "endereco": e_cli, "obs": o_cli, "itens": json.dumps(itens_v), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if p_cli else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
            st.session_state.form_id += 1
            st.cache_data.clear()
            st.rerun()

# 2. COLHEITA
with tabs[1]:
    st.header("🚜 Lista de Colheita")
    pend = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    if not pend.empty:
        res = {}
        for _, r in pend.iterrows():
            for it in json.loads(r['itens']): res[it['nome']] = res.get(it['nome'], 0) + it['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Total": v} for k, v in res.items()]))

# 3. MONTAGEM
with tabs[2]:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {p['cliente']}")
            st.write(f"📍 {p['endereco']}")
            if p['obs'] and str(p['obs']).lower() != 'nan': st.info(f"📝 {p['obs']}")
            
            itens_l = json.loads(p['itens']); t_r = 0.0; trava = False
            for i, it in enumerate(itens_l):
                if str(it['tipo']).upper() == "KG":
                    val = st.text_input(f"Peso {it['nome']}:", key=f"mt_{p['id']}_{i}")
                    if val: t_r += float(val.replace(',', '.'))
                    else: trava = True
                else: t_r += float(it['subtotal'])
            
            st.write(f"**Total: R$ {t_r:.2f}**")
            botao_imprimir(p, t_r)
            if st.button("✅ FINALIZAR", key=f"f_{p['id']}", disabled=trava):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_r
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()

# --- TELAS ORIGINAIS (CONFORME VOCÊ DISSE QUE ESTAVA PERFEITO) ---
with tabs[3]: # HISTÓRICO
    st.header("📅 Histórico")
    st.dataframe(df_pedidos[df_pedidos['status'] == "Concluído"], use_container_width=True)

with tabs[4]: # FINANCEIRO
    st.header("📊 Financeiro")
    st.dataframe(df_pedidos, use_container_width=True)

with tabs[5]: # ESTOQUE
    st.header("🥦 Estoque")
    st.dataframe(df_produtos, use_container_width=True)
