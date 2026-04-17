import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# 1. Configuração e Conexão
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# Controle de limpeza do formulário
if "form_id" not in st.session_state:
    st.session_state.form_id = 0

def carregar_dados():
    try:
        df_p = conn.read(worksheet="Produtos", ttl=5).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=5).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except: return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- FUNÇÃO IMPRIMIR CORRIGIDA (SEM NAN E COM VALOR REAL) ---
def botao_imprimir(ped, total_venda, label="🖨️ IMPRIMIR"):
    nome = str(ped.get('cliente', '')).upper()
    endereco = str(ped.get('endereco', '')).upper()
    # Remove o 'nan' das observações
    obs_raw = ped.get('obs', '')
    obs = str(obs_raw).upper() if pd.notna(obs_raw) and str(obs_raw).lower() != 'nan' else ""
    
    valor_formatado = f"{float(total_venda):.2f}".replace('.', ',')
    
    # Montagem da etiqueta RawBT
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{endereco}\n{obs}\n\n\x1b\x61\x01\x1b\x21\x10TOTAL: RS {valor_formatado}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border:1px solid white;">{label}</div></a>', unsafe_allow_html=True)

# 2. ABAS
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- NOVO PEDIDO ---
with tabs[0]:
    fid = st.session_state.form_id
    c1, c2 = st.columns(2)
    nome_cli = c1.text_input("NOME DO CLIENTE", key=f"n_{fid}").upper()
    end_cli = c2.text_input("ENDEREÇO", key=f"e_{fid}").upper()
    obs_cli = st.text_area("OBSERVAÇÕES", key=f"o_{fid}").upper()
    pago_cli = st.checkbox("PAGO ANTECIPADO", key=f"p_{fid}")
    st.divider()
    
    itens_v = []; total_p = 0.0
    if not df_produtos.empty:
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        cp1, cp2 = st.columns(2)
        for i, (_, p) in enumerate(ativos.iterrows()):
            alvo = cp1 if i % 2 == 0 else cp2
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"prod_{p['id']}_{fid}")
            if qtd > 0:
                pr = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if str(p['tipo']).upper() == "KG" else (qtd * pr)
                itens_v.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                total_p += sub
    
    st.markdown(f"### 💰 Total Prévio: R$ {total_p:.2f}")
    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (nome_cli or end_cli) and itens_v:
            ids = pd.to_numeric(df_pedidos['id'], errors='coerce').dropna()
            px_id = int(ids.max() + 1) if not ids.empty else 1
            novo = pd.DataFrame([{"id": px_id, "cliente": nome_cli, "endereco": end_cli, "obs": obs_cli, "itens": json.dumps(itens_v), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if pago_cli else "A Pagar"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
            st.session_state.form_id += 1
            st.cache_data.clear()
            st.rerun()

# --- COLHEITA ---
with tabs[1]:
    st.header("🚜 Resumo de Colheita")
    pend = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    if not pend.empty:
        res = {}
        for _, r in pend.iterrows():
            for it in json.loads(r['itens']):
                res[it['nome']] = res.get(it['nome'], 0) + it['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Total": v} for k, v in res.items()]))
    else: st.info("Nada pendente.")

# --- MONTAGEM ---
with tabs[2]:
    st.header("📦 Montagem de Pedidos")
    pend = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            m1, m2 = st.columns([3, 1])
            m1.subheader(f"👤 {p['cliente']}")
            m1.write(f"📍 {p['endereco']}")
            
            if m2.button("🗑️ EXCLUIR", key=f"exc_{p['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx))
                st.cache_data.clear(); st.rerun()
            
            itens_l = json.loads(p['itens']); t_r = 0.0; trava = False
            for i, it in enumerate(itens_l):
                if str(it['tipo']).upper() == "KG":
                    val = st.text_input(f"Valor R$ {it['nome']} ({it['qtd']} unidades solicitadas):", key=f"mt_{p['id']}_{i}")
                    if val:
                        v = float(val.replace(',', '.'))
                        it['subtotal'] = v; t_r += v
                    else: trava = True
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN")
                    t_r += float(it['subtotal'])
            
            st.write(f"### Total Real: R$ {t_r:.2f}")
            # Aqui passamos o t_r (total real da montagem) para a etiqueta
            botao_imprimir(p, t_r)
            
            if st.button("✅ CONCLUIR PEDIDO", key=f"fin_{p['id']}", disabled=trava, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_r
                df_pedidos.at[idx, 'itens'] = json.dumps(itens_l)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear(); st.rerun()

# --- HISTÓRICO ---
with tabs[3]:
    st.header("📅 Histórico de Vendas")
    data_sel = st.date_input("Filtrar Data:", datetime.now()).strftime("%d/%m/%Y")
    hists = df_pedidos[(df_pedidos['status'] == "Concluído") & (df_pedidos['data'] == data_sel)]
    for idx, p in hists.iterrows():
        with st.expander(f"🛒 {p['cliente']} - R$ {float(p['total']):.2f}"):
            st.write(f"Endereço: {p['endereco']}")
            botao_imprimir(p, p['total'], "🖨️ REIMPRIMIR")

# --- FINANCEIRO ---
with tabs[4]:
    st.header("📊 Financeiro")
    concl = df_pedidos[df_pedidos['status'] == "Concluído"].copy()
    if not concl.empty:
        concl['total'] = concl['total'].astype(float)
        st.metric("Faturamento Total Concluído", f"R$ {concl['total'].sum():.2f}")
        st.dataframe(concl[['data', 'cliente', 'total', 'pagamento']])

# --- ESTOQUE ---
with tabs[5]:
    st.header("🥦 Gerenciar Produtos")
    st.dataframe(df_produtos)
    if st.button("🔄 Atualizar Estoque"):
        st.cache_data.clear(); st.rerun()
