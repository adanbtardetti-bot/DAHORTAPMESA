import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# 1. Configuração e Conexão
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

if "form_id" not in st.session_state:
    st.session_state.form_id = 0

def carregar_dados():
    try:
        # TTL de 60 segundos para equilibrar atualização e não travar o Google (Erro 429)
        df_p = conn.read(worksheet="Produtos", ttl=60).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=60).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except Exception as e:
        st.error(f"Erro de conexão com a planilha. Aguarde um instante.")
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- ETIQUETA ---
def botao_imprimir(ped, valor_real, label="🖨️ IMPRIMIR"):
    def limpar(txt):
        if pd.isna(txt) or str(txt).lower() == 'nan' or not str(txt).strip(): return ""
        return str(txt).strip().upper()
    
    nome = limpar(ped.get('cliente', ''))
    endereco = limpar(ped.get('endereco', ''))
    pagamento = limpar(ped.get('pagamento', ''))
    
    status_doc = f"\n*** {pagamento} ***\n" if "PAGO" in pagamento else "\n"
    valor_formatado = f"{float(valor_real):.2f}".replace('.', ',')
    
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{endereco}\n{status_doc}\n\x1b\x61\x01\x1b\x21\x10TOTAL: RS {valor_formatado}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border:1px solid white;">{label}</div></a>', unsafe_allow_html=True)

# 2. ABAS
tabs = st.tabs(["🛒 NOVO PEDIDO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- ABA 1: NOVO PEDIDO ---
with tabs[0]:
    st.subheader("📝 Dados do Cliente")
    fid = st.session_state.form_id
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("NOME DO CLIENTE", key=f"n_{fid}").upper()
    e_cli = c2.text_input("ENDEREÇO", key=f"e_{fid}").upper()
    o_cli = st.text_area("OBSERVAÇÕES", key=f"o_{fid}").upper()
    p_cli = st.checkbox("MARCAR COMO PAGO", key=f"p_{fid}")
    
    st.divider()
    st.subheader("🥦 Escolha os Produtos")
    
    itens_v = []; total_p = 0.0
    if not df_produtos.empty:
        # Mostra produtos ativos
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for i, row in ativos.iterrows():
            col1, col2 = st.columns([3, 1])
            qtd = col2.number_input(f"{row['nome']} (R$ {row['preco']})", min_value=0, step=1, key=f"prod_{row['id']}_{fid}")
            if qtd > 0:
                preco = float(str(row['preco']).replace(',', '.'))
                sub = 0.0 if str(row['tipo']).upper() == "KG" else (qtd * preco)
                itens_v.append({"nome": row['nome'], "qtd": qtd, "tipo": row['tipo'], "subtotal": sub})
                total_p += sub
    
    st.markdown(f"### 💰 Total Estimado: R$ {total_p:.2f}")
    if st.button("✅ FINALIZAR E SALVAR PEDIDO", use_container_width=True):
        if (n_cli or e_cli) and itens_v:
            ids = pd.to_numeric(df_pedidos['id'], errors='coerce').dropna()
            prox_id = int(ids.max() + 1) if not ids.empty else 1
            novo_p = pd.DataFrame([{"id": prox_id, "cliente": n_cli, "endereco": e_cli, "obs": o_cli, "itens": json.dumps(itens_v), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if p_cli else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_p], ignore_index=True))
            st.session_state.form_id += 1; st.cache_data.clear(); st.rerun()

# --- ABAS DE CONSULTA (HISTÓRICO, FINANCEIRO, ESTOQUE) ---
with tabs[3]: # Histórico
    st.header("📅 Histórico")
    st.dataframe(df_pedidos[df_pedidos['status'] == "Concluído"], use_container_width=True)

with tabs[4]: # Financeiro
    st.header("📊 Financeiro")
    st.dataframe(df_pedidos, use_container_width=True)

with tabs[5]: # Estoque
    st.header("🥦 Estoque")
    st.dataframe(df_produtos, use_container_width=True)

# --- COLHEITA E MONTAGEM MANTIDOS ---
with tabs[1]:
    st.header("🚜 Colheita")
    pendentes = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    if not pendentes.empty:
        res = {}
        for
