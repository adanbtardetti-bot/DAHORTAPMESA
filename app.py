import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO E DADOS ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def limpar_nan(texto):
    if pd.isna(texto): return ""
    return str(texto).replace('nan', '').replace('NaN', '').strip()

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        if df is None: return pd.DataFrame()
        df = df.dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except: return pd.DataFrame()

df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Blindagem de colunas
for col in ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]:
    if col not in df_pedidos.columns: df_pedidos[col] = ""

# --- FUNÇÕES DE APOIO ---
def enviar_whatsapp(numero, mensagem):
    msg_codificada = urllib.parse.quote(mensagem)
    return f"https://wa.me/{numero}?text={msg_codificada}"

def imprimir_rawbt(texto, tipo="ETIQUETA"):
    b64 = base64.b64encode(texto.encode('latin-1')).decode('utf-8')
    return f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"

# --- INTERFACE ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tabs[0]:
    if "f_id" not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    
    c1, c2 = st.columns(2)
    nome = c1.text_input("Nome do Cliente", key=f"n{f}").upper()
    ende = c2.text_input("Endereço", key=f"e{f}").upper()
    obse = st.text_area("Observações", key=f"o{f}").upper()
    pago = st.checkbox("Pedido já está PAGO", key=f"p{f}")
    
    st.markdown("### Itens Disponíveis")
    venda, total_est = [], 0.0
    if not df_produtos.empty:
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for _, r in ativos.iterrows():
            col_a, col_b = st.columns([4, 1])
            q = col_b.number_input(f"{r['nome']} (R$ {r['preco']})", min_value=0, step=1, key=f"it{r['id']}{f}")
            if q > 0:
                p_unit = float(str(r['preco']).replace(',', '.'))
                # REGRA DE OURO: KG começa com 0.00
                sub = 0.0 if str(r['tipo']).upper() == "KG" else (q * p_unit)
                venda.append({"nome": r['nome'], "qtd": q, "tipo": r['tipo'], "subtotal": sub, "preco": p_unit})
                total_est += sub
    
    st.subheader(f"💰 Total Estimado: R$ {total_est:.2f}")
    if st.button("SALVAR PEDIDO", use_container_width=True):
        if nome and venda:
            nid = int(pd.to_numeric(df_pedidos['id'], errors='coerce').max() + 1) if not df_pedidos.empty else 1
            novo = pd.DataFrame([{"id": nid, "cliente": nome, "endereco": ende, "obs": obse, "itens": json.dumps(venda), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if pago else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
            st.session_state.f_id += 1; st.rerun()

# --- 2. COLHEITA ---
with tabs[1]:
    st.header("🚜 Resumo para Colheita")
    pendentes = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    if not pendentes.empty:
        soma = {}
        for _, p in pendentes.iterrows():
            for it in json.loads(p['itens']):
                soma[it['nome']] = soma.get(it['nome'], 0) + it['qtd']
        df_colheita = pd.DataFrame([{"Produto": k, "Quantidade Total": v} for k, v in soma.items()])
        st.table(df_colheita)
        
        texto_whats = "*LISTA DE COLHEITA*\n" + "\n".join([f"- {k}: {v}" for k, v in soma.items()])
        st.markdown(f'<a href="{enviar_whatsapp("", texto_whats)}" target="_blank">📲 Enviar para WhatsApp</a>', unsafe_allow_html=True)

# --- 3. MONTAGEM ---
with tabs[2]:
    st.header("📦 Montagem de Pedidos")
    pend = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            st.write(f"**Cliente:** {p['cliente']} | **Endereço:** {p['endereco']}")
            itens_p, t_real, ok = json.loads(p['itens']), 0.0, True
            for i, it in enumerate(itens_p):
                if str(it['tipo']).upper() == "KG":
                    val = st.text_input(f"Valor Real {it['nome']} (Ped: {it['qtd']}kg):", key=f"mt{p['id']}{i}")
                    if val: 
                        v = float(val.replace(',', '.')); it['subtotal'] = v; t_real += v
                    else: ok = False
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += float(it['subtotal'])
            
            st.subheader(f"Total Real: R$ {t_real:.2f}")
            
            # Botão de Impressão (Etiqueta 50x30)
            txt_pago = "PAGO" if p['pagamento'] == "PAGO" else f"VALOR: RS {t_real:.2f}"
            cmd = f"\x1b\x61\x01\x1b\x21\x10{p['cliente']}\n\x1b\x21\x00{p['endereco']}\n\x1b\x21\x08{txt_pago}\n\n\n"
            st.markdown(f'<a href="{imprimir_rawbt(cmd)}">🖨️ IMPRIMIR ETIQUETA</a>', unsafe_allow_html=True)
            
            c1, c2, c3 = st.columns(3)
            if c1.button("MARCAR PAGO", key=f"pg{idx}"):
                df_pedidos.at[idx, 'pagamento'] = "PAGO"; conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
            if c2.button("SALVAR PEDIDO", key=f"sv{idx}", disabled=not ok, type="primary"):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_p)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
            if c3.button("EXCLUIR", key=f"del{idx}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.rerun()

# --- 4. HISTÓRICO ---
with tabs[3]:
    st.header("📅 Histórico")
    data_h = st.date_input("Filtrar Dia", datetime.now()).strftime("%d/%m/%Y")
    h_fil = df_pedidos[(df_pedidos['status'].str.lower() == "concluído") & (df_pedidos['data'] == data_h)]
    
    for idx, p in h_fil.iterrows():
        with st.expander(f"👤 {p['cliente']} - R$ {p['total']:.2f}"):
            st.write(f"📍 Endereço: {p['endereco']}")
            st.write(f"💳 Pagamento: {p['pagamento']}")
            
            # Recibo WhatsApp
            msg_recibo = f"*RECIBO HORTA DA MESA*\nCliente: {p['cliente']}\nTotal: R$ {p['total']:.2f}\nStatus: {p['pagamento']}"
            st.markdown(f'<a href="{enviar_whatsapp("", msg_recibo)}">📲 Enviar Recibo WhatsApp</a>', unsafe_allow_html=True)
            
            if st.button("INVERTER PAGAMENTO", key=f"inv{idx}"):
                df_pedidos.at[idx, 'pagamento'] = "A PAGAR" if p['pagamento'] == "PAGO" else "PAGO"
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# --- 5. FINANCEIRO ---
with tabs[4]:
    st.header("📊 Panorama Geral do Dia")
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_hoje = df_pedidos[(df_pedidos['data'] == hoje) & (df_pedidos['status'].str.lower() == "concluído")]
    if not df_hoje.empty:
        st.write(f"Total arrecadado hoje: R$ {df_hoje['total'].sum():.2f}")
        st.dataframe(df_hoje[['cliente', 'total', 'pagamento']])
    
    st.divider()
    st.subheader("Filtro por Período")
    d1 = st.date_input("Início", datetime.now())
    d2 = st.date_input("Fim", datetime.now())
    # Lógica de resumo por período deve converter datas para comparação real

# --- 6. ESTOQUE ---
with tabs[5]:
    st.header("🥦 Gestão de Estoque")
    with st.form("Novo Produto"):
        n = st.text_input("Nome"); p = st.text_input("Preço"); t = st.selectbox("Tipo", ["UN", "KG"])
        if st.form_submit_button("ADICIONAR"):
            nid = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
            nv = pd.DataFrame([{"id": nid, "nome": n.upper(), "preco": p, "tipo": t, "status": "ativo"}])
            conn.update(worksheet="Produtos", data=pd.concat([df_produtos, nv], ignore_index=True)); st.rerun()
    
    for i, r in df_produtos.iterrows():
        c1, c2, c3 = st.columns([4, 1, 1])
        c1.write(f"**{r['nome']}** - {r['tipo']} (R$ {r['preco']})")
        if c2.button("🚫" if r['status'] == "ativo" else "✅", key=f"st{i}"):
            df_produtos.at[i, 'status'] = "inativo" if r['status'] == "ativo" else "ativo"
            conn.update(worksheet="Produtos", data=df_produtos); st.rerun()
        if c3.button("🗑️", key=f"exc{i}"):
            conn.update(worksheet="Produtos", data=df_produtos.drop(i)); st.rerun()
