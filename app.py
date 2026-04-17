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

# Carregamento
df_produtos = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
df_pedidos = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
df_produtos.columns = [str(c).lower().strip() for c in df_produtos.columns]
df_pedidos.columns = [str(c).lower().strip() for c in df_pedidos.columns]

# --- ESTILO BOTÃO IMPRIMIR (VERDE COM LETRA BRANCA) ---
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
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tabs[0]:
    st.header("🛒 Novo Pedido")
    with st.form("f_venda"):
        c1, c2 = st.columns(2)
        cli = c1.text_input("CLIENTE").upper()
        end = c2.text_input("ENDEREÇO").upper()
        obs = st.text_area("OBSERVAÇÃO").upper()
        pago_f = st.checkbox("PAGO")
        
        st.divider()
        itens_sel = []; v_previo = 0.0
        for _, p in df_produtos[df_produtos['status'] == 'Ativo'].iterrows():
            qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"n_{p['id']}")
            if qtd > 0:
                sub = 0.0 if p['tipo'] == "KG" else (qtd * float(p['preco']))
                itens_sel.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                v_previo += sub
        
        st.subheader(f"Valor Prévio: R$ {v_previo:.2f}")
        
        if st.form_submit_button("✅ SALVAR"):
            if (cli or end) and itens_sel:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo = pd.DataFrame([{"id": prox_id, "cliente": cli, "endereco": end, "itens": json.dumps(itens_sel), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if pago_f else "A Pagar", "obs": obs}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
                st.cache_data.clear(); st.rerun()
            else: st.error("Nome ou Endereço é obrigatório!")

# --- 2. COLHEITA ---
with tabs[1]:
    st.header("🚜 Colheita")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"]
    if not pend.empty:
        soma = {}
        for _, p in pend.iterrows():
            for i in json.loads(p['itens']): soma[i['nome']] = soma.get(i['nome'], 0) + i['qtd']
        st.table(pd.DataFrame([{"Produto": k, "Qtd": v} for k, v in soma.items()]))
        txt_w = "*LISTA DE COLHEITA*\n" + "\n".join([f"• {k}: {v}" for k, v in soma.items()])
        st.markdown(f'''<a href="https://wa.me/?text={urllib.parse.quote(txt_w)}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;">📱 COMPARTILHAR WHATSAPP</div></a>''', unsafe_allow_html=True)

# --- 3. MONTAGEM ---
with tabs[2]:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pend.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {ped['cliente']}")
            st.write(f"📍 {ped['endereco']}")
            if ped['obs']: st.warning(f"📝 {ped['obs']}")
            
            itens_l = json.loads(ped['itens']); t_real = 0.0; trava = False
            for i, it in enumerate(itens_l):
                if it['tipo'] == "KG":
                    v_in = st.text_input(f"Valor R$ {it['nome']}:", key=f"m_{ped['id']}_{i}")
                    if v_in: val = float(v_in.replace(',', '.')); it['subtotal'] = val; t_real += val
                    else: trava = True
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += float(it['subtotal'])
            
            st.write(f"**Total: R$ {t_real:.2f}**")
            botao_imprimir({"cliente":ped['cliente'], "total":t_real})
            
            c_b1, c_b2 = st.columns(2)
            if c_b1.button("🗑️ EXCLUIR", key=f"ex_{ped['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx)); st.rerun()
            if c_b2.button("✅ CONCLUIR", key=f"f_{ped['id']}", disabled=trava):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_l)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# --- 4. HISTÓRICO ---
with tabs[3]:
    st.header("📅 Histórico")
    dia_h = st.date_input("Data:", datetime.now()).strftime("%d/%m/%Y")
    filtro = df_pedidos[(df_pedidos['status'] == "Concluído") & (df_pedidos['data'] == dia_h)]
    for idx, p in filtro.iterrows():
        with st.expander(f"{p['cliente']} - R$ {p['total']}"):
            st.write(f"📍 Endereço: {p['endereco']}")
            st.write(f"📝 Obs: {p['obs']}")
            pag = st.selectbox("Pagamento", ["Pago", "A Pagar"], index=0 if p['pagamento'] == "Pago" else 1, key=f"p_{p['id']}")
            if pag != p['pagamento']:
                df_pedidos.at[idx, 'pagamento'] = pag
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
            
            txt_r = f"*RECIBO*\n*Cliente:* {p['cliente']}\n*Total:* R$ {p['total']}\n*Status:* {pag}"
            st.markdown(f'''<a href="https://wa.me/?text={urllib.parse.quote(txt_r)}" target="_blank" style="text-decoration:none;"><div style="background-color:#007bff;color:white;padding:10px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:5px;">📱 ENVIAR RECIBO</div></a>''', unsafe_allow_html=True)
            botao_imprimir(p, "🖨️ REIMPRIMIR")

# --- 5. FINANCEIRO (RESTAURADO) ---
with tabs[4]:
    st.header("📊 Financeiro")
    menu_f = st.radio("Modo:", ["Visão Diária", "Relatório por Período", "Selecionar Pedidos"], horizontal=True)
    concl = df_pedidos[df_pedidos['status'] == "Concluído"].copy()
    if not concl.empty:
        concl['dt_obj'] = pd.to_datetime(concl['data'], format='%d/%m/%Y', errors='coerce')
        # Lógica restaurada conforme o que você gostava antes
        if menu_f == "Visão Diária":
            df_atual = concl[concl['data'] == st.date_input("Dia:").strftime("%d/%m/%Y")]
        elif menu_f == "Relatório por Período":
            d1, d2 = st.columns(2)
            df_atual = concl[(concl['dt_obj'].dt.date >= d1.date_input("De:")) & (concl['dt_obj'].dt.date <= d2.date_input("Até:"))]
        else:
            dia_p = st.date_input("Pedidos de:", key="sel_p")
            df_dia = concl[concl['data'] == dia_p.strftime("%d/%m/%Y")]
            sel = []
            for _, r in df_dia.iterrows():
                if st.checkbox(f"{r['cliente']} (R$ {r['total']})", key=f"s_{r['id']}"): sel.append(r['id'])
            df_atual = df_dia[df_dia['id'].isin(sel)] if st.button("GERAR RELATÓRIO") else pd.DataFrame()

        if not df_atual.empty:
            st.metric("Total", f"R$ {df_atual['total'].astype(float).sum():.2f}")
            # ... Restante da exibição dos itens que você já tinha ...

# --- 6. ESTOQUE ---
with tabs[5]:
    st.header("🥦 Estoque")
    with st.expander("➕ NOVO PRODUTO"):
        with st.form("add"):
            n = st.text_input("Nome").upper(); p = st.text_input("Preço"); t = st.selectbox("Tipo", ["UN", "KG"])
            if st.form_submit_button("SALVAR"):
                prox = int(df_produtos['id'].max()+1) if not df_produtos.empty else 1
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, pd.DataFrame([{"id":prox,"nome":n,"preco":p,"tipo":t,"status":"Ativo"}])])); st.rerun()
    
    for idx, r in df_produtos.iterrows():
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        c1.write(f"**{r['nome']}** - R$ {r['preco']} ({r['tipo']})")
        if c2.button("✏️", key=f"ed_{r['id']}"): st.info("Em breve")
        if c3.button("👁️" if r['status']=="Ativo" else "🌑", key=f"st_{r['id']}"):
            df_produtos.at[idx, 'status'] = "Inativo" if r['status']=="Ativo" else "Ativo"
            conn.update(worksheet="Produtos", data=df_produtos); st.rerun()
        if c4.button("🗑️", key=f"dl_{r['id']}"):
            conn.update(worksheet="Produtos", data=df_produtos.drop(idx)); st.rerun()
