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
        # Aumentei o TTL para 600 segundos para evitar o erro 429 de "Quota Exceeded"
        df_p = conn.read(worksheet="Produtos", ttl=600).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=600).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except Exception as e:
        st.error(f"Erro ao carregar Planilha: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- ETIQUETA CORRIGIDA (SEM ERRO DE SINTAXE E SEM NAN) ---
def botao_imprimir(ped, valor_real, label="🖨️ IMPRIMIR"):
    def limpar(txt):
        if pd.isna(txt) or str(txt).lower() == 'nan' or not str(txt).strip(): return ""
        return str(txt).strip().upper()

    nome = limpar(ped.get('cliente', ''))
    endereco = limpar(ped.get('endereco', ''))
    pagamento = limpar(ped.get('pagamento', ''))
    
    # Só mostra o status se for PAGO
    txt_status = f"\n*** {pagamento} ***\n" if "PAGO" in pagamento else "\n"
    valor_formatado = f"{float(valor_real):.2f}".replace('.', ',')
    
    # Comandos RawBT
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{endereco}\n{txt_status}\n\x1b\x61\x01\x1b\x21\x10TOTAL: RS {valor_formatado}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    
    # Botão com a sintaxe corrigida (terminando as aspas corretamente)
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border:1px solid white;">{label}</div></a>', unsafe_allow_html=True)

# 2. ABAS
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- ABA 1: NOVO PEDIDO ---
with tabs[0]:
    fid = st.session_state.form_id
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("NOME DO CLIENTE", key=f"n_{fid}").upper()
    e_cli = c2.text_input("ENDEREÇO", key=f"e_{fid}").upper()
    o_cli = st.text_area("OBSERVAÇÕES", key=f"o_{fid}").upper()
    p_cli = st.checkbox("PAGO ANTECIPADO", key=f"p_{fid}")
    st.divider()
    
    itens_v = []; total_p = 0.0
    if not df_produtos.empty:
        cp1, cp2 = st.columns(2)
        for i, (_, p) in enumerate(df_produtos[df_produtos['status'] == 'ativo'].iterrows()):
            alvo = cp1 if i % 2 == 0 else cp2
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"p_{p['id']}_{fid}")
            if qtd > 0:
                pr = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if str(p['tipo']).upper() == "KG" else (qtd * pr)
                itens_v.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                total_p += sub
    
    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (n_cli or e_cli) and itens_v:
            ids = pd.to_numeric(df_pedidos['id'], errors='coerce').dropna()
            px_id = int(ids.max() + 1) if not ids.empty else 1
            novo = pd.DataFrame([{"id": px_id, "cliente": n_cli, "endereco": e_cli, "obs": o_cli, "itens": json.dumps(itens_v), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if p_cli else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
            st.session_state.form_id += 1; st.cache_data.clear(); st.rerun()

# --- ABA 2: COLHEITA ---
with tabs[1]:
    st.header("🚜 Colheita")
    pend = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    if not pend.empty:
        resumo = {}
        for _, r in pend.iterrows():
            for it in json.loads(r['itens']): resumo[it['nome']] = resumo.get(it['nome'], 0) + it['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Total": v} for k, v in resumo.items()]))

# --- ABA 3: MONTAGEM ---
with tabs[2]:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            m1, m2 = st.columns([3, 1])
            m1.subheader(f"👤 {p['cliente']}")
            m1.write(f"📍 {p['endereco']}")
            if m2.button("🗑️ EXCLUIR", key=f"exc_{p['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.cache_data.clear(); st.rerun()
            
            itens_l = json.loads(p['itens']); t_r = 0.0; trava = False
            for i, it in enumerate(itens_l):
                if str(it['tipo']).upper() == "KG":
                    val = st.text_input(f"Peso {it['nome']}:", key=f"mt_{p['id']}_{i}")
                    if val: v = float(val.replace(',', '.')); it['subtotal'] = v; t_r += v
                    else: trava = True
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN")
                    t_r += float(it['subtotal'])
            
            st.write(f"### Total: R$ {t_r:.2f}")
            botao_imprimir(p, t_r)
            if st.button("✅ FINALIZAR", key=f"fin_{p['id']}", disabled=trava, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_r; df_pedidos.at[idx, 'itens'] = json.dumps(itens_l)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()

# --- ABA 4, 5, 6: HISTÓRICO, FINANCEIRO, ESTOQUE (ORIGINAIS) ---
with tabs[3]:
    st.header("📅 Histórico")
    st.dataframe(df_pedidos[df_pedidos['status'] == "Concluído"], use_container_width=True)

with tabs[4]:
    st.header("📊 Financeiro")
    st.dataframe(df_pedidos, use_container_width=True)

with tabs[5]:
    st.header("🥦 Estoque")
    st.dataframe(df_produtos, use_container_width=True)
