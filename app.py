import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- BLOCO 1: CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

if "form_id" not in st.session_state:
    st.session_state.form_id = 0

def carregar_dados():
    try:
        # TTL de 10s para não travar o Google e manter os dados atualizados
        df_p = conn.read(worksheet="Produtos", ttl=10).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=10).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except:
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- BLOCO 2: FUNÇÃO DE IMPRESSÃO (SEM NAN / SEM OBS) ---
def botao_imprimir(ped, valor_real, label="🖨️ IMPRIMIR"):
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
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border:1px solid white;">{label}</div></a>', unsafe_allow_html=True)

# --- BLOCO 3: INTERFACE PRINCIPAL ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# ABA 1: NOVO PEDIDO
with tabs[0]:
    fid = st.session_state.form_id
    c1, c2 = st.columns(2)
    n_c = c1.text_input("NOME", key=f"n_{fid}").upper()
    e_c = c2.text_input("ENDEREÇO", key=f"e_{fid}").upper()
    o_c = st.text_area("OBSERVAÇÕES", key=f"o_{fid}").upper()
    p_c = st.checkbox("PAGO ANTECIPADO", key=f"p_{fid}")
    st.divider()
    itens_sel = []
    if not df_produtos.empty:
        # MOSTRA APENAS PRODUTOS "ATIVO"
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for _, r in ativos.iterrows():
            col_n, col_q = st.columns([3, 1])
            qtd = col_q.number_input(f"{r['nome']} (R$ {r['preco']})", min_value=0, step=1, key=f"pr_{r['id']}_{fid}")
            if qtd > 0:
                p_u = float(str(r['preco']).replace(',', '.'))
                sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
                itens_sel.append({"nome": r['nome'], "qtd": qtd, "tipo": r['tipo'], "subtotal": sub})
    if st.button("✅ SALVAR PEDIDO"):
        if (n_c or e_c) and itens_sel:
            px_id = int(pd.to_numeric(df_pedidos['id'], errors='coerce').max() + 1) if not df_pedidos.empty else 1
            novo = pd.DataFrame([{"id": px_id, "cliente": n_c, "endereco": e_c, "obs": o_c, "itens": json.dumps(itens_sel), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if p_c else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
            st.session_state.form_id += 1; st.cache_data.clear(); st.rerun()

# ABA 2: COLHEITA
with tabs[1]:
    pend = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    if not pend.empty:
        res = {}
        for _, r in pend.iterrows():
            for it in json.loads(r['itens']): res[it['nome']] = res.get(it['nome'], 0) + it['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Total": v} for k, v in res.items()]))

# ABA 3: MONTAGEM (CORREÇÃO DOS ITENS SUMIDOS)
with tabs[2]:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {p['cliente']}")
            st.write(f"📍 {p['endereco']}")
            itens_l = json.loads(p['itens']) # AQUI É ONDE OS ITENS VOLTAM A APARECER
            t_r = 0.0; trava = False
            for i, it in enumerate(itens_l):
                if str(it['tipo']).upper() == "KG":
                    val = st.text_input(f"Peso {it['nome']} ({it['qtd']}kg):", key=f"mt_{p['id']}_{i}")
                    if val:
                        v = float(val.replace(',', '.')); it['subtotal'] = v; t_r += v
                    else: trava = True
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN")
                    t_r += float(it['subtotal'])
            st.write(f"**Total: R$ {t_r:.2f}**")
            botao_imprimir(p, t_r)
            if st.button("✅ FINALIZAR", key=f"f_{p['id']}", disabled=trava):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_r; df_pedidos.at[idx, 'itens'] = json.dumps(itens_l)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()

# ABA 4 E 5: HISTÓRICO E FINANCEIRO (VOLTANDO AO SEU PADRÃO)
with tabs[3]: # Histórico
    st.dataframe(df_pedidos[df_pedidos['status'] == "Concluído"], use_container_width=True)
with tabs[4]: # Financeiro
    st.dataframe(df_pedidos, use_container_width=True)

# ABA 6: ESTOQUE (ADICIONAR, EDITAR, OCULTAR)
with tabs[5]:
    st.header("🥦 Gerenciar Estoque")
    # Adicionar Novo
    with st.expander("➕ ADICIONAR NOVO PRODUTO"):
        with st.form("form_prod"):
            n_p = st.text_input("Nome do Produto")
            p_p = st.text_input("Preço (ex: 5.50)")
            t_p = st.selectbox("Tipo", ["UN", "KG"])
            if st.form_submit_button("SALVAR NOVO"):
                p_id = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
                novo_pr = pd.DataFrame([{"id": p_id, "nome": n_p.upper(), "preco": p_p, "tipo": t_p, "status": "ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, novo_pr], ignore_index=True))
                st.cache_data.clear(); st.rerun()

    st.divider()
    # Lista para Editar/Ocultar
    for i, r in df_produtos.iterrows():
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        col1.write(f"**{r['nome']}** (R$ {r['preco']})")
        
        # Ocultar/Ativar
        novo_status = "inativo" if str(r['status']).lower() == "ativo" else "ativo"
        label_btn = "🚫 OCULTAR" if novo_status == "inativo" else "✅ ATIVAR"
        if col2.button(label_btn, key=f"st_{r['id']}"):
            df_produtos.at[i, 'status'] = novo_status
            conn.update(worksheet="Produtos", data=df_produtos); st.cache_data.clear(); st.rerun()
            
        # Excluir
        if col3.button("🗑️", key=f"del_{r['id']}"):
            df_produtos = df_produtos.drop(i)
            conn.update(worksheet="Produtos", data=df_produtos); st.cache_data.clear(); st.rerun()
    
    st.divider()
    st.write("Planilha Completa:")
    st.dataframe(df_produtos, use_container_width=True)
