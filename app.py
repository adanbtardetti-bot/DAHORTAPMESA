import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO (Baseada na sua versão) ---
st.set_page_config(page_title="Horta da Mesa", layout="wide")
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
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame()

# Carga inicial seguindo seu padrão
df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

# Garante as colunas que você definiu como seguras
colunas_pedidos = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"]
for col in colunas_pedidos:
    if col not in df_pedidos.columns:
        df_pedidos[col] = ""

# --- MOTOR DE IMPRESSÃO ---
def imprimir_comando(ped, valor_real, tipo="ETIQUETA"):
    nome = limpar_nan(ped.get('cliente', '')).upper()
    end = limpar_nan(ped.get('endereco', '')).upper()
    pag = limpar_nan(ped.get('pagamento', '')).upper()
    v_f = f"{float(valor_real):.2f}".replace('.', ',')
    
    if tipo == "ETIQUETA":
        cmds = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{end}\nTOTAL: RS {v_f}\n({pag})\n\n\n\n"
        label, cor = "🖨️ ETIQUETA", "#28a745"
    else:
        detalhes = ""
        try:
            itens_l = json.loads(ped['itens'])
            for it in itens_l:
                detalhes += f"{it['nome'][:15]} -> RS {float(it['subtotal']):.2f}\n"
        except: detalhes = "Erro nos itens\n"
        cmds = f"\x1b\x61\x01\x1b\x21\x10HORTA DA MESA\n----------------\n{nome}\n----------------\n{detalhes}TOTAL: RS {v_f}\n\n\n\n"
        label, cor = "📄 RECIBO", "#007bff"

    b64 = base64.b64encode(cmds.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:{cor};color:white;padding:8px;text-align:center;border-radius:5px;font-weight:bold;margin-bottom:2px;">{label}</div></a>', unsafe_allow_html=True)

# --- INTERFACE ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# ABA: NOVO PEDIDO (Mantendo seu estilo)
with tabs[0]:
    if "f_id" not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    c1, c2 = st.columns(2)
    n = c1.text_input("NOME", key=f"n{f}").upper()
    e = c2.text_input("ENDEREÇO", key=f"e{f}").upper()
    pa = st.checkbox("PAGO ANTECIPADO", key=f"p{f}")
    
    itens_venda, total_est = [], 0.0
    if not df_produtos.empty:
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for _, row in ativos.iterrows():
            ca, cb = st.columns([4, 1])
            qtd = cb.number_input(f"{row['nome']} (R$ {row['preco']})", min_value=0, step=1, key=f"p{row['id']}{f}")
            if qtd > 0:
                pr = float(str(row['preco']).replace(',', '.'))
                sub = 0.0 if str(row['tipo']).upper() == "KG" else (qtd * pr)
                itens_venda.append({"nome": row['nome'], "qtd": qtd, "tipo": row['tipo'], "subtotal": sub})
                total_est += sub
    
    st.subheader(f"Total Estimado: R$ {total_est:.2f}")
    if st.button("💾 SALVAR PEDIDO", use_container_width=True):
        if n and itens_venda:
            novo_id = int(pd.to_numeric(df_pedidos['id'], errors='coerce').max() + 1) if not df_pedidos.empty else 1
            novo_df = pd.DataFrame([{"id": novo_id, "cliente": n, "endereco": e, "itens": json.dumps(itens_venda), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "PAGO" if pa else "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_df], ignore_index=True))
            st.session_state.f_id += 1; st.rerun()

# ABA: HISTÓRICO (Otimizada e Compacta)
with tabs[3]:
    st.header("📅 Histórico")
    data_sel = st.date_input("Filtrar Data", datetime.now()).strftime("%d/%m/%Y")
    # Filtro que funciona na sua planilha
    df_dia = df_pedidos[(df_pedidos['status'].str.lower() == "concluído") & (df_pedidos['data'] == data_sel)]
    
    for idx, p in df_dia.iterrows():
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 2, 2])
            col1.markdown(f"**{p['cliente']}**\n\n{p['endereco']}")
            cor = "green" if p['pagamento'] == "PAGO" else "red"
            col2.markdown(f"**R$ {float(p['total']):.2f}**\n\n<span style='color:{cor};font-weight:bold'>{p['pagamento']}</span>", unsafe_allow_html=True)
            with col3:
                if st.button("💳 PGTO", key=f"btn_h_{p['id']}", use_container_width=True):
                    df_pedidos.at[idx, 'pagamento'] = "A PAGAR" if p['pagamento'] == "PAGO" else "PAGO"
                    conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
                with st.popover("📄 VER", use_container_width=True):
                    imprimir_comando(p, p['total'], "ETIQUETA")
                    imprimir_comando(p, p['total'], "RECIBO")

# ABA: FINANCEIRO (A melhor versão que você pediu)
with tabs[4]:
    st.header("📊 Financeiro")
    concluidos = df_pedidos[df_pedidos['status'].str.lower() == "concluído"]
    v_pago = concluidos[concluidos['pagamento'] == "PAGO"]['total'].astype(float).sum()
    v_pend = concluidos[concluidos['pagamento'] == "A PAGAR"]['total'].astype(float).sum()
    
    c_m1, c_m2 = st.columns(2)
    c_m1.metric("DINHEIRO EM MÃO", f"R$ {v_pago:.2f}")
    c_m2.metric("A RECEBER", f"R$ {v_pend:.2f}")
    st.divider()
    st.dataframe(concluidos[['cliente', 'total', 'pagamento', 'data']], use_container_width=True)

# ABA: MONTAGEM (Garante que os pedidos saiam do 'Pendente')
with tabs[2]:
    p_montar = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
    for idx, p in p_montar.iterrows():
        with st.container(border=True):
            st.write(f"👤 **{p['cliente']}**")
            its, tf, ok = json.loads(p['itens']), 0.0, True
            for i, it in enumerate(its):
                if str(it['tipo']).upper() == "KG":
                    vk = st.text_input(f"{it['nome']} (kg):", key=f"mt{p['id']}{i}")
                    if vk: v = float(vk.replace(',', '.')); it['subtotal'] = v; tf += v
                    else: ok = False
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN"); tf += float(it['subtotal'])
            imprimir_comando(p, tf, "ETIQUETA")
            if st.button("✅ FINALIZAR", key=f"fin_{p['id']}", disabled=not ok, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = tf; df_pedidos.at[idx, 'itens'] = json.dumps(its)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# ABA: ESTOQUE
with tabs[5]:
    st.header("🥦 Estoque")
    if not df_produtos.empty:
        st.dataframe(df_produtos[['nome', 'preco', 'tipo', 'status']], use_container_width=True)
