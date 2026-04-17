import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# Configuração da Página
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# Conexão com Google Sheets
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
        # Padronizar nomes das colunas para minúsculo
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except Exception as e:
        return pd.DataFrame()

# Carga inicial
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Criar colunas se a planilha estiver vazia ou com erro
colunas_pedidos = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"]
for col in colunas_pedidos:
    if col not in df_pedidos.columns:
        df_pedidos[col] = ""

if not df_produtos.empty and 'status' not in df_produtos.columns:
    df_produtos['status'] = 'Ativo'

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

# --- NAVEGAÇÃO ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "🥦 ESTOQUE"])

# --- FUNÇÃO DE IMPRESSÃO ---
def disparar_impressao_rawbt(ped, label="IMPRIMIR ETIQUETA"):
    try:
        nome = limpar_nan(ped.get('cliente', '')).upper()
        endereco = limpar_nan(ped.get('endereco', '')).upper()
        pgto = limpar_nan(ped.get('pagamento', '')).upper()
        try:
            v_num = float(str(ped.get('total', 0)).replace(',', '.'))
        except: v_num = 0.0
        valor_fmt = f"{v_num:.2f}".replace('.', ',')
        
        comandos = "\x1b\x61\x01" 
        if nome: comandos += "\x1b\x21\x38" + nome + "\n"
        if endereco: comandos += "\x1b\x21\x38" + endereco + "\n"
        comandos += "\x1b\x21\x00" + "----------------\n"
        comandos += "TOTAL: RS " + valor_fmt + "\n"
        if pgto == "PAGO": comandos += "PAGO\n"
        comandos += "\n\n\n\n"
        
        b64_texto = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url_rawbt = f"intent:base64,{b64_texto}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'''<a href="{url_rawbt}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">🖨️ {label}</div></a>''', unsafe_allow_html=True)
    except: pass

# --- ABA 1: NOVO ---
with tab1:
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    with st.form("form_venda", clear_on_submit=True):
        col_c1, col_c2 = st.columns(2)
        c = col_c1.text_input("CLIENTE", value=edit['cliente'] if edit else "").upper()
        e = col_c2.text_input("ENDEREÇO", value=edit['endereco'] if edit else "").upper()
        fp = st.checkbox("PAGO", value=(str(edit['pagamento']).lower() == "pago") if edit else False)
        itens_selecionados = []
        if not df_produtos.empty:
            p_ativos = df_produtos[df_produtos['status'] == 'Ativo']
            for _, p in p_ativos.iterrows():
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"n_{p['id']}")
                if qtd > 0:
                    itens_selecionados.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * float(p['preco']))})
        if st.form_submit_button("✅ SALVAR"):
            if c and itens_selecionados:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty and pd.to_numeric(df_pedidos['id'], errors='coerce').notnull().any() else 1
                novo_p = pd.DataFrame([{"id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_selecionados), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if fp else "A Pagar"}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_p], ignore_index=True))
                st.session_state.edit_data = None; st.cache_data.clear(); st.rerun()

# --- ABA 2: COLHEITA ---
with tab2:
    st.header("🚜 Colheita")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"] if not df_pedidos.empty else pd.DataFrame()
    if pend.empty: st.info("Nada pendente.")
    else:
        soma = {}
        for _, ped in pend.iterrows():
            try:
                for i in json.loads(ped['itens']):
                    soma[i['nome']] = soma.get(i['nome'], 0) + i['qtd']
            except: pass
        if soma:
            st.table(pd.DataFrame([{"Produto": k, "Qtd": v} for k, v in soma.items()]))

# --- ABA 3: MONTAGEM ---
with tab3:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"] if not df_pedidos.empty else pd.DataFrame()
    for idx, ped in pend.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {limpar_nan(ped['cliente'])}")
            try:
                itens_lista = json.loads(ped['itens']); t_real = 0.0; trava = False
                for i, it in enumerate(itens_lista):
                    if it['tipo'] == "KG":
                        v_in = st.text_input(f"Valor R$ {it['nome']}:", key=f"m_{ped['id']}_{i}")
                        if v_in:
                            val = float(v_in.replace(',', '.')); it['subtotal'] = val; t_real += val
                        else: trava = True
                    else:
                        st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += float(it['subtotal'])
                st.write(f"Total: R$ {t_real:.2f}")
                disparar_impressao_rawbt({"cliente":ped['cliente'], "endereco":ped['endereco'], "total":t_real, "pagamento":ped['pagamento']})
                if st.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava, use_container_width=True):
                    df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_lista)
                    conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()
            except: st.error("Erro no pedido.")

# --- ABA 4: HISTÓRICO ---
with tab4:
    st.header("📅 Histórico")
    concl = df_pedidos[df_pedidos['status'] == "Concluído"] if not df_pedidos.empty else pd.DataFrame()
    if concl.empty: st.info("Vazio.")
    else:
        for _, ped in concl.iterrows():
            with st.expander(f"{limpar_nan(ped['cliente'])} - R$ {ped['total']}"):
                st.write(f"📍 {limpar_nan(ped['endereco'])} | {ped['data']}")
                disparar_impressao_rawbt(ped, "REIMPRIMIR")
                if st.button("💳 ALTERAR PAGO/A PAGAR", key=f"p_{ped['id']}"):
                    df_pedidos.at[ped.name, 'pagamento'] = "A Pagar" if ped['pagamento'] == "Pago" else "Pago"
                    conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()

# --- ABA 5: ESTOQUE ---
with tab5:
    st.header("🥦 Estoque")
    if not df_produtos.empty:
        for idx, row in df_produtos.iterrows():
            col1, col2 = st.columns([3, 1])
            col1.write(f"**{row['nome']}** - R$ {row['preco']}")
            if col2.button("🗑️", key=f"d_{row['id']}"):
                conn.update(worksheet="Produtos", data=df_produtos.drop(idx)); st.cache_data.clear(); st.rerun()
