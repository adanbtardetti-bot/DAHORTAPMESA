import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime, timedelta

# Configuração da Página
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# Conexão
conn = st.connection("gsheets", type=GSheetsConnection)

def limpar_nan(texto):
    if pd.isna(texto): return ""
    return str(texto).strip()

def formatar_unidade(valor, tipo):
    try:
        v = float(valor)
        if tipo == "KG": return f"{v:.3f}".replace('.', ',') + " kg"
        return str(int(v)) + " un"
    except: return str(valor)

# --- CARREGAR DADOS ---
df_produtos = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
df_pedidos = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
df_produtos.columns = [str(c).lower().strip() for c in df_produtos.columns]
df_pedidos.columns = [str(c).lower().strip() for c in df_pedidos.columns]

dict_precos = {}
if not df_produtos.empty:
    for _, r in df_produtos.iterrows():
        dict_precos[r['nome']] = {"preco": float(str(r['preco']).replace(',', '.')), "tipo": r['tipo']}

# --- ESTILO BOTÃO IMPRIMIR ---
def botao_imprimir(ped, label="🖨️ IMPRIMIR"):
    try:
        nome = limpar_nan(ped.get('cliente', '')).upper()
        total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
        comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {total}\n\n\n\n"
        b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">{label}</div></a>', unsafe_allow_html=True)
    except: pass

# --- NAVEGAÇÃO ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO (COM SOMA EM TEMPO REAL) ---
with tab1:
    st.header("🛒 Novo Pedido")
    
    # Campos fora do form para atualizar a soma em tempo real
    st.subheader("Selecione os Produtos")
    itens_sel = []
    v_previo = 0.0
    
    if not df_produtos.empty:
        # Organiza em colunas para ficar bonito
        p_ativos = df_produtos[df_produtos['status'] == 'Ativo']
        for _, p in p_ativos.iterrows():
            qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"n_{p['id']}")
            if qtd > 0:
                # Soma apenas itens que não são KG (ou use o preço base se desejar)
                preco_num = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if p['tipo'] == "KG" else (qtd * preco_num)
                itens_sel.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                v_previo += sub
    
    st.markdown(f"## 💰 Valor Prévio: R$ {v_previo:.2f}")

    # Form apenas para os dados finais e salvamento
    with st.form("f_finalizar_pedido"):
        c1, c2 = st.columns(2)
        cli = c1.text_input("CLIENTE").upper()
        end = c2.text_input("ENDEREÇO").upper()
        obs = st.text_area("OBSERVAÇÃO / TROCO").upper()
        pago_f = st.checkbox("JÁ ESTÁ PAGO?")
        
        if st.form_submit_button("✅ SALVAR PEDIDO"):
            if (cli or end) and itens_sel:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo = pd.DataFrame([{"id": prox_id, "cliente": cli, "endereco": end, "itens": json.dumps(itens_sel), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if pago_f else "A Pagar", "obs": obs}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
                st.cache_data.clear(); st.rerun()
            else:
                st.error("Preencha Nome ou Endereço e selecione produtos!")

# --- 2. COLHEITA (COM WHATSAPP) ---
with tab2:
    st.header("🚜 Colheita")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"]
    if not pend.empty:
        soma = {}
        for _, p in pend.iterrows():
            for i in json.loads(p['itens']): soma[i['nome']] = soma.get(i['nome'], 0) + i['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Qtd": v} for k, v in soma.items()]))
        txt_w = "*COLHEITA*\n" + "\n".join([f"• {k}: {v}" for k, v in soma.items()])
        st.markdown(f'''<a href="https://wa.me/?text={urllib.parse.quote(txt_w)}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;">📱 WHATSAPP</div></a>''', unsafe_allow_html=True)

# --- 3. MONTAGEM (COM ENDEREÇO, EXCLUIR E IMPRIMIR VERDE) ---
with tab3:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pend.iterrows():
        with st.container(border=True):
            col_m1, col_m2 = st.columns([3, 1])
            col_m1.subheader(f"👤 {ped['cliente']}")
            col_m1.write(f"📍 {ped['endereco']}")
            if ped['obs']: col_m1.warning(f"📝 {ped['obs']}")
            
            if col_m2.button("🗑️ EXCLUIR", key=f"ex_{ped['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.rerun()

            itens_l = json.loads(ped['itens']); t_real = 0.0; trava = False
            for i, it in enumerate(itens_l):
                if it['tipo'] == "KG":
                    v_in = st.text_input(f"R$ {it['nome']}:", key=f"m_{ped['id']}_{i}")
                    if v_in: val = float(v_in.replace(',', '.')); it['subtotal'] = val; t_real += val
                    else: trava = True
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += float(it['subtotal'])
            
            st.write(f"**Total: R$ {t_real:.2f}**")
            botao_imprimir({"cliente":ped['cliente'], "total":t_real})
            if st.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_l)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# --- 4. HISTÓRICO (COM ENDEREÇO, STATUS E RECIBO) ---
with tab4:
    st.header("📅 Histórico")
    dia_h = st.date_input("Data:", datetime.now()).strftime("%d/%m/%Y")
    filtro = df_pedidos[(df_pedidos['status'] == "Concluído") & (df_pedidos['data'] == dia_h)]
    for idx, p in filtro.iterrows():
        with st.expander(f"{p['cliente']} - R$ {p['total']}"):
            st.write(f"📍 Endereço: {p['endereco']}\n📝 Obs: {p['obs']}")
            pag = st.selectbox("Pagamento", ["Pago", "A Pagar"], index=0 if p['pagamento'] == "Pago" else 1, key=f"p_h_{p['id']}")
            if pag != p['pagamento']:
                df_pedidos.at[idx, 'pagamento'] = pag
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
            txt_r = f"*RECIBO*\n*Cliente:* {p['cliente']}\n*Total:* R$ {p['total']}\n*Status:* {pag}"
            st.markdown(f'''<a href="https://wa.me/?text={urllib.parse.quote(txt_r)}" target="_blank" style="text-decoration:none;"><div style="background-color:#007bff;color:white;padding:10px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:5px;">📱 RECIBO</div></a>''', unsafe_allow_html=True)
            botao_imprimir(p, "🖨️ REIMPRIMIR")

# --- 5. FINANCEIRO (ESTÁVEL) ---
with tab5:
    st.header("📊 Financeiro")
    menu_f = st.radio("Filtro:", ["Visão Diária", "Relatório por Período", "Selecionar Pedidos"], horizontal=True)
    concl = df_pedidos[df_pedidos['status'] == "Concluído"].copy()
    if not concl.empty:
        concl['dt_obj'] = pd.to_datetime(concl['data'], format='%d/%m/%Y', errors='coerce')
        if menu_f == "Visão Diária":
            df_atual = concl[concl['data'] == st.date_input("Escolha o dia:").strftime("%d/%m/%Y")]
        elif menu_f == "Relatório por Período":
            c1, c2 = st.columns(2)
            df_atual = concl[(concl['dt_obj'].dt.date >= c1.date_input("De:")) & (concl['dt_obj'].dt.date <= c2.date_input("Até:"))]
        else:
            dia_p = st.date_input("Pedidos de:", key="f_p")
            df_dia = concl[concl['data'] == dia_p.strftime("%d/%m/%Y")]
            sel = [r['id'] for _, r in df_dia.iterrows() if st.checkbox(f"{r['cliente']} (R$ {r['total']})", key=f"f_{r['id']}")]
            df_atual = df_dia[df_dia['id'].isin(sel)] if st.button("GERAR RELATÓRIO") else pd.DataFrame()

        if not df_atual.empty:
            st.metric("Total", f"R$ {df_atual['total'].astype(float).sum():.2f}")
            # ... (Tabela de itens resumida aqui)

# --- 6. ESTOQUE (LAYOUT LISTA) ---
with tab6:
    st.header("🥦 Estoque")
    with st.expander("➕ NOVO PRODUTO"):
        with st.form("add_p"):
            n = st.text_input("Nome").upper(); p = st.text_input("Preço"); t = st.selectbox("Tipo", ["UN", "KG"])
            if st.form_submit_button("SALVAR"):
                prox = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, pd.DataFrame([{"id":prox,"nome":n,"preco":p,"tipo":t,"status":"Ativo"}])])); st.rerun()
    for idx, r in df_produtos.iterrows():
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        c1.write(f"**{r['nome']}** - R$ {r['preco']} ({r['tipo']})")
        if c2.button("✏️", key=f"ed_{r['id']}"): st.write("Editar em breve")
        st_label = "Ocultar" if r['status']=="Ativo" else "Ativar"
        if c3.button(st_label, key=f"st_{r['id']}"):
            df_produtos.at[idx, 'status'] = "Inativo" if r['status']=="Ativo" else "Ativo"
            conn.update(worksheet="Produtos", data=df_produtos); st.rerun()
        if c4.button("🗑️", key=f"dl_{r['id']}"):
            conn.update(worksheet="Produtos", data=df_produtos.drop(idx)); st.rerun()
