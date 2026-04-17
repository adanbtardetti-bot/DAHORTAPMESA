import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except: return pd.DataFrame()

df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Garante colunas
for col in ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]:
    if col not in df_pedidos.columns: df_pedidos[col] = ""

# --- ABAS ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tabs[0]:
    if "f_id" not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    
    nome = st.text_input("Nome do Cliente", key=f"n{f}").upper()
    ende = st.text_input("Endereço", key=f"e{f}").upper()
    obse = st.text_area("Observação", key=f"o{f}").upper() # Campo adicionado conforme pedido
    pago_check = st.checkbox("Pago", key=f"p{f}")
    
    venda, total_est = [], 0.0
    if not df_produtos.empty:
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for _, r in ativos.iterrows():
            c1, c2 = st.columns([4, 1])
            qtd = c2.number_input(f"{r['nome']} (R$ {r['preco']})", min_value=0, step=1, key=f"it{r['id']}{f}")
            if qtd > 0:
                p_unit = float(str(r['preco']).replace(',', '.'))
                sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_unit)
                venda.append({"nome": r['nome'], "qtd": qtd, "tipo": r['tipo'], "subtotal": sub, "preco": p_unit})
                total_est += sub
    
    st.write(f"### Total Estimado: R$ {total_est:.2f}")
    if st.button("SALVAR PEDIDO"):
        if nome and venda:
            nid = int(pd.to_numeric(df_pedidos['id'], errors='coerce').max() + 1) if not df_pedidos.empty else 1
            novo = pd.DataFrame([{"id": nid, "cliente": nome, "endereco": ende, "obs": obse, "itens": json.dumps(venda), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if pago_check else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
            st.session_state.f_id += 1
            st.rerun()

# --- 2. COLHEITA ---
with tabs[1]:
    st.header("Colheita")
    pendentes = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    if not pendentes.empty:
        soma = {}
        for _, p in pendentes.iterrows():
            try:
                for it in json.loads(p['itens']):
                    soma[it['nome']] = soma.get(it['nome'], 0) + it['qtd']
            except: pass
        
        resumo_c = [{"Produto": k, "Quantidade Total": v} for k, v in soma.items()]
        st.table(pd.DataFrame(resumo_c))
        
        texto_w = "*LISTA DE COLHEITA*\n" + "\n".join([f"- {k}: {v}" for k, v in soma.items()])
        link_w = f"https://wa.me/?text={urllib.parse.quote(texto_w)}"
        st.markdown(f'[📲 Compartilhar WhatsApp]({link_w})')

# --- 3. MONTAGEM ---
with tabs[2]:
    st.header("Montagem")
    pend = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            st.write(f"**Cliente:** {p['cliente']}") # Endereço removido conforme pedido
            its, tf, ok = json.loads(p['itens']), 0.0, True
            for i, it in enumerate(its):
                if str(it['tipo']).upper() == "KG":
                    val = st.text_input(f"Valor {it['nome']} ({it['qtd']}kg):", key=f"m{p['id']}{i}")
                    if val: 
                        v = float(val.replace(',', '.')); it['subtotal'] = v; tf += v
                    else: ok = False
                else:
                    st.write(f"{it['nome']} - {it['qtd']} UN"); tf += float(it['subtotal'])
            
            # Impressão RawBT
            txt_pago = "PAGO" if p['pagamento'] == "PAGO" else f"VALOR: RS {tf:.2f}"
            cmd = f"\x1b\x61\x01\x1b\x21\x10{p['cliente']}\n\x1b\x21\x00{p['endereco']}\n\x1b\x21\x08{txt_pago}\n\n\n"
            b64 = base64.b64encode(cmd.encode('latin-1')).decode('utf-8')
            url_p = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
            
            st.markdown(f'[🖨️ IMPRIMIR ETIQUETA]({url_p})')
            if st.button("MARCAR PAGO", key=f"pg{idx}"):
                df_pedidos.at[idx, 'pagamento'] = "PAGO"; conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
            if st.button("EXCLUIR", key=f"ex{idx}"):
                df_pedidos = df_pedidos.drop(idx); conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
            if st.button("SALVAR PEDIDO", key=f"sv{idx}", disabled=not ok):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = tf; df_pedidos.at[idx, 'itens'] = json.dumps(its)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# --- 4. HISTÓRICO ---
with tabs[3]:
    st.header("Histórico")
    data_sel = st.date_input("Data").strftime("%d/%m/%Y")
    h_fil = df_pedidos[(df_pedidos['status'].str.lower() == "concluído") & (df_pedidos['data'] == data_sel)]
    
    for idx, p in h_fil.iterrows():
        with st.expander(f"{p['cliente']} - {p['endereco']} - R$ {p['total']:.2f}"):
            if st.button("PAGO", key=f"h_pg{idx}"):
                df_pedidos.at[idx, 'pagamento'] = "PAGO"; conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
            
            # Recibo WhatsApp
            msg = f"RECIBO: {p['cliente']}\nTotal: R$ {p['total']:.2f}"
            st.markdown(f'[Gera Recibo WhatsApp](https://wa.me/?text={urllib.parse.quote(msg)})')
            # Botão de impressão repetido conforme pedido
            st.markdown(f'[Imprimir Etiqueta]({url_p})') 

# --- 5. FINANCEIRO ---
with tabs[4]:
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_h = df_pedidos[(df_pedidos['data'] == hoje) & (df_pedidos['status'].str.lower() == "concluído")]
    st.subheader(f"Panorama Geral {hoje}")
    if not df_h.empty:
        for _, r in df_h.iterrows():
            st.write(f"{r['cliente']}: R$ {r['total']:.2f}")
        st.write(f"**TOTAL DO DIA: R$ {df_h['total'].sum():.2f}**")
    
    st.divider()
    st.subheader("Filtro por Período")
    # Filtro de período e relatório de grupo (seleção via checkbox)
    df_periodo = df_pedidos[df_pedidos['status'].str.lower() == "concluído"]
    sel_pedidos = st.multiselect("Selecione Pedidos para Relatório", df_periodo['cliente'].unique())
    if sel_pedidos:
        df_grupo = df_periodo[df_periodo['cliente'].isin(sel_pedidos)]
        st.write(f"Total Grupo: R$ {df_grupo['total'].sum():.2f}")
        st.dataframe(df_grupo)

# --- 6. ESTOQUE ---
with tabs[5]:
    st.header("Estoque")
    with st.form("Novo"):
        n = st.text_input("Nome"); pr = st.text_input("Preço"); t = st.selectbox("Tipo", ["UN", "KG"])
        if st.form_submit_button("ADICIONAR"):
            nid = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
            novo_p = pd.DataFrame([{"id": nid, "nome": n.upper(), "preco": pr, "tipo": t, "status": "ativo"}])
            conn.update(worksheet="Produtos", data=pd.concat([df_produtos, novo_p], ignore_index=True)); st.rerun()
    
    for i, r in df_produtos.iterrows():
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        c1.write(f"{r['nome']} - R$ {r['preco']}")
        if c2.button("🚫" if r['status'] == "ativo" else "✅", key=f"at{i}"):
            df_produtos.at[i, 'status'] = "inativo" if r['status'] == "ativo" else "ativo"
            conn.update(worksheet="Produtos", data=df_produtos); st.rerun()
        if c3.button("EDITAR", key=f"ed{i}"): st.info("Use a planilha para editar preços")
        if c4.button("EXCLUIR", key=f"exc{i}"):
            df_produtos = df_produtos.drop(i); conn.update(worksheet="Produtos", data=df_produtos); st.rerun()
