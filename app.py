import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados():
    try:
        df_p = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except:
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- 2. FUNÇÃO DE IMPRESSÃO ---
def botao_imprimir(ped, valor_real, label="🖨️ IMPRIMIR ETIQUETA"):
    def limpar(txt):
        if pd.isna(txt) or str(txt).lower() == 'nan': return ""
        return str(txt).strip().upper()
    nome = limpar(ped.get('cliente', ''))
    end = limpar(ped.get('endereco', ''))
    pag = limpar(ped.get('pagamento', ''))
    txt_pg = f"\n*** {pag} ***\n" if "PAGO" in pag else "\n"
    v_f = f"{float(valor_real):.2f}".replace('.', ',')
    cmds = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{end}{txt_pg}\n\x1b\x61\x01\x1b\x21\x10TOTAL: RS {v_f}\n\n\n\n"
    b64 = base64.b64encode(cmds.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin:5px 0px;">{label}</div></a>', unsafe_allow_html=True)

# --- 3. ABAS DO SISTEMA ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- ABA: NOVO PEDIDO ---
with tabs[0]:
    if "f_id" not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    c1, c2 = st.columns(2)
    n = c1.text_input("NOME DO CLIENTE", key=f"n{f}").upper()
    e = c2.text_input("ENDEREÇO", key=f"e{f}").upper()
    o = st.text_area("OBSERVAÇÕES", key=f"o{f}").upper()
    p_check = st.checkbox("PAGO ANTECIPADO", key=f"p{f}")
    st.write("---")
    itens_venda = []
    if not df_produtos.empty:
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for _, row in ativos.iterrows():
            col_a, col_b = st.columns([3, 1])
            qtd = col_b.number_input(f"{row['nome']} (R$ {row['preco']})", min_value=0, step=1, key=f"p{row['id']}{f}")
            if qtd > 0:
                pr = float(str(row['preco']).replace(',', '.'))
                sub = 0.0 if str(row['tipo']).upper() == "KG" else (qtd * pr)
                itens_venda.append({"nome": row['nome'], "qtd": qtd, "tipo": row['tipo'], "subtotal": sub})
    if st.button("💾 SALVAR PEDIDO", use_container_width=True):
        if (n or e) and itens_venda:
            novo_id = int(pd.to_numeric(df_pedidos['id'], errors='coerce').max() + 1) if not df_pedidos.empty else 1
            novo_df = pd.DataFrame([{"id": novo_id, "cliente": n, "endereco": e, "obs": o, "itens": json.dumps(itens_venda), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if p_check else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_df], ignore_index=True))
            st.session_state.f_id += 1; st.rerun()

# --- ABA: COLHEITA ---
with tabs[1]:
    p_pend = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    if not p_pend.empty:
        resumo = {}
        for _, r in p_pend.iterrows():
            for it in json.loads(r['itens']): resumo[it['nome']] = resumo.get(it['nome'], 0) + it['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Qtd Total": v} for k, v in resumo.items()]))

# --- ABA: MONTAGEM ---
with tabs[2]:
    pend = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {p['cliente']}")
            st.write(f"📍 {p['endereco']}")
            itens_m = json.loads(p['itens'])
            t_final = 0.0; pode = True
            for i, it in enumerate(itens_m):
                if str(it['tipo']).upper() == "KG":
                    v_kg = st.text_input(f"Peso {it['nome']} (Ped: {it['qtd']}kg):", key=f"m{p['id']}{i}")
                    if v_kg: 
                        val = float(v_kg.replace(',', '.')); it['subtotal'] = val; t_final += val
                    else: pode = False
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_final += float(it['subtotal'])
            st.write(f"**Total: R$ {t_final:.2f}**")
            botao_imprimir(p, t_final)
            if st.button("✅ FINALIZAR", key=f"fin{p['id']}", disabled=not pode):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_final; df_pedidos.at[idx, 'itens'] = json.dumps(itens_m)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# --- ABA: HISTÓRICO (CARDS + CALENDÁRIO) ---
with tabs[3]:
    st.header("📅 Histórico de Pedidos")
    data_sel = st.date_input("Selecione o Dia", datetime.now())
    data_str = data_sel.strftime("%d/%m/%Y")
    df_dia = df_pedidos[(df_pedidos['status'] == "Concluído") & (df_pedidos['data'] == data_str)]
    if df_dia.empty: st.info("Nenhum pedido nesta data.")
    else:
        for idx, p in df_dia.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.markdown(f"**{p['cliente']}**\n\n{p['endereco']}")
                c2.markdown(f"**R$ {float(p['total']):.2f}**\n\n{p['pagamento']}")
                with c3.popover("🔍 Detalhes"):
                    for it in json.loads(p['itens']): st.write(f"- {it['nome']}: {it['qtd']} (R$ {it['subtotal']:.2f})")
                    st.divider()
                    botao_imprimir(p, p['total'], "🖨️ REIMPRIMIR")
                    if st.button(f"Mudar Pagamento", key=f"pg_h_{p['id']}"):
                        df_pedidos.at[idx, 'pagamento'] = "A PAGAR" if p['pagamento'] == "PAGO" else "PAGO"
                        conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# --- ABA: FINANCEIRO ---
with tabs[4]:
    st.header("📊 Financeiro")
    concl = df_pedidos[df_pedidos['status'] == "Concluído"]
    v_pago = concl[concl['pagamento'] == "PAGO"]['total'].astype(float).sum()
    v_pend = concl[concl['pagamento'] == "A PAGAR"]['total'].astype(float).sum()
    st.metric("Total Recebido", f"R$ {v_pago:.2f}")
    st.metric("Total a Receber", f"R$ {v_pend:.2f}")
    st.dataframe(concl, use_container_width=True)

# --- ABA: ESTOQUE (ADICIONAR/OCULTAR/EXCLUIR) ---
with tabs[5]:
    st.header("🥦 Estoque")
    with st.expander("➕ NOVO PRODUTO"):
        with st.form("add"):
            n_p = st.text_input("Nome"); p_p = st.text_input("Preço"); t_p = st.selectbox("Tipo", ["UN", "KG"])
            if st.form_submit_button("SALVAR"):
                nid = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
                new = pd.DataFrame([{"id": nid, "nome": n_p.upper(), "preco": p_p, "tipo": t_p, "status": "ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, new], ignore_index=True)); st.rerun()
    for i, r in df_produtos.iterrows():
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.write(f"**{r['nome']}** (R$ {r['preco']}) - {r['status']}")
        label = "🚫 Ocultar" if r['status'] == "ativo" else "✅ Ativar"
        if c2.button(label, key=f"st{r['id']}"):
            df_produtos.at[i, 'status'] = "inativo" if r['status'] == "ativo" else "ativo"
            conn.update(worksheet="Produtos", data=df_produtos); st.rerun()
        if c3.button("🗑️", key=f"dl{r['id']}"):
            conn.update(worksheet="Produtos", data=df_produtos.drop(i)); st.rerun()
