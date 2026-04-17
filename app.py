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

# Dicionário para cálculos no financeiro
dict_precos = {}
if not df_produtos.empty:
    for _, r in df_produtos.iterrows():
        dict_precos[r['nome']] = {"preco": float(str(r['preco']).replace(',', '.')), "tipo": r['tipo']}

# --- ESTILO BOTÃO IMPRIMIR (VERDE COM LETRA BRANCA) ---
def botao_imprimir(ped, label="🖨️ IMPRIMIR"):
    try:
        nome = limpar_nan(ped.get('cliente', '')).upper()
        total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
        # Comandos ESC/POS para RawBT
        comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {total}\n\n\n\n"
        b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border: 1px solid white;">{label}</div></a>', unsafe_allow_html=True)
    except: pass

# --- NAVEGAÇÃO ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tabs[0]:
    st.header("🛒 Novo Pedido")
    with st.form("f_venda", clear_on_submit=True):
        c1, c2 = st.columns(2)
        cli = c1.text_input("CLIENTE").upper()
        end = c2.text_input("ENDEREÇO").upper()
        obs = st.text_area("OBSERVAÇÃO / TROCO / ENTREGA").upper()
        pago_f = st.checkbox("JÁ ESTÁ PAGO?")
        
        st.divider()
        st.subheader("Itens do Pedido")
        itens_sel = []; v_previo = 0.0
        
        # Exibição de produtos para seleção
        if not df_produtos.empty:
            for _, p in df_produtos[df_produtos['status'] == 'Ativo'].iterrows():
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"n_{p['id']}")
                if qtd > 0:
                    # Se for KG, o subtotal é 0 até a montagem. Se for UN, calcula agora.
                    sub = 0.0 if p['tipo'] == "KG" else (qtd * float(str(p['preco']).replace(',', '.')))
                    itens_sel.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                    v_previo += sub
        
        st.markdown(f"### 💰 Valor Prévio: R$ {v_previo:.2f}")
        
        if st.form_submit_button("✅ SALVAR PEDIDO"):
            if (cli or end) and itens_sel:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo = pd.DataFrame([{"id": prox_id, "cliente": cli, "endereco": end, "itens": json.dumps(itens_sel), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "Pago" if pago_f else "A Pagar", "obs": obs}])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
                st.cache_data.clear(); st.rerun()
            else: st.error("Erro: Preencha pelo menos o Nome ou Endereço e adicione itens!")

# --- 2. COLHEITA ---
with tabs[1]:
    st.header("🚜 Lista para Colheita")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"]
    if not pend.empty:
        soma = {}
        for _, p in pend.iterrows():
            for i in json.loads(p['itens']):
                soma[i['nome']] = soma.get(i['nome'], 0) + i['qtd']
        
        df_colheita = pd.DataFrame([{"Produto": k, "Qtd Total": v} for k, v in soma.items()])
        st.table(df_colheita)
        
        txt_w = "*LISTA DE COLHEITA - " + datetime.now().strftime("%d/%m") + "*\n" + "\n".join([f"• {k}: {v}" for k, v in soma.items()])
        st.markdown(f'''<a href="https://wa.me/?text={urllib.parse.quote(txt_w)}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;">📱 COMPARTILHAR WHATSAPP</div></a>''', unsafe_allow_html=True)
    else: st.info("Não há pedidos pendentes para colheita.")

# --- 3. MONTAGEM ---
with tabs[2]:
    st.header("📦 Montagem de Pedidos")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, ped in pend.iterrows():
        with st.container(border=True):
            col_m1, col_m2 = st.columns([3, 1])
            col_m1.subheader(f"👤 {ped['cliente'] if ped['cliente'] else 'SEM NOME'}")
            col_m1.write(f"📍 {ped['endereco']}")
            if ped['obs']: col_m1.warning(f"📝 {ped['obs']}")
            
            if col_m2.button("🗑️ EXCLUIR", key=f"ex_{ped['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx))
                st.cache_data.clear(); st.rerun()

            itens_l = json.loads(ped['itens']); t_real = 0.0; trava = False
            for i, it in enumerate(itens_l):
                if it['tipo'] == "KG":
                    v_in = st.text_input(f"Valor R$ {it['nome']} (Sugerido {it['qtd']}kg):", key=f"m_{ped['id']}_{i}")
                    if v_in:
                        val = float(v_in.replace(',', '.')); it['subtotal'] = val; t_real += val
                    else: trava = True
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN"); t_real += float(it['subtotal'])
            
            st.write(f"**Total Real: R$ {t_real:.2f}**")
            botao_imprimir({"cliente":ped['cliente'], "total":t_real})
            
            if st.button("✅ CONCLUIR E FINALIZAR", key=f"f_{ped['id']}", disabled=trava, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real; df_pedidos.at[idx, 'itens'] = json.dumps(itens_l)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.cache_data.clear(); st.rerun()

# --- 4. HISTÓRICO ---
with tabs[3]:
    st.header("📅 Histórico de Pedidos")
    dia_h = st.date_input("Ver pedidos do dia:", datetime.now()).strftime("%d/%m/%Y")
    filtro = df_pedidos[(df_pedidos['status'] == "Concluído") & (df_pedidos['data'] == dia_h)]
    
    for idx, p in filtro.iterrows():
        with st.expander(f"{p['cliente']} - R$ {p['total']}"):
            st.write(f"📍 Endereço: {p['endereco']}")
            st.write(f"📝 Obs: {p['obs']}")
            
            # Alterar Status de Pagamento
            pag = st.selectbox("Status de Pagamento:", ["Pago", "A Pagar"], index=0 if p['pagamento'] == "Pago" else 1, key=f"p_hist_{p['id']}")
            if pag != p['pagamento']:
                df_pedidos.at[idx, 'pagamento'] = pag
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
            
            # Enviar Recibo WhatsApp
            txt_recibo = f"*RECIBO - HORTA DA MESA*\n*Cliente:* {p['cliente']}\n*Valor:* R$ {p['total']}\n*Status:* {pag}\n*Data:* {p['data']}"
            st.markdown(f'''<a href="https://wa.me/?text={urllib.parse.quote(txt_recibo)}" target="_blank" style="text-decoration:none;"><div style="background-color:#007bff;color:white;padding:10px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:5px;">📱 ENVIAR RECIBO WHATSAPP</div></a>''', unsafe_allow_html=True)
            
            botao_imprimir(p, "🖨️ REIMPRIMIR ETIQUETA")

# --- 5. FINANCEIRO (VERSÃO ORIGINAL RESTAURADA) ---
with tabs[4]:
    st.header("📊 Financeiro")
    menu_f = st.radio("Modo:", ["Visão Diária", "Relatório por Período", "Selecionar Pedidos"], horizontal=True)
    concl = df_pedidos[df_pedidos['status'] == "Concluído"].copy()
    
    if not concl.empty:
        concl['dt_obj'] = pd.to_datetime(concl['data'], format='%d/%m/%Y', errors='coerce')
        df_atual = pd.DataFrame()

        if menu_f == "Visão Diária":
            dia_f = st.date_input("Dia:", datetime.now(), key="f_dia").strftime("%d/%m/%Y")
            df_atual = concl[concl['data'] == dia_f]
        elif menu_f == "Relatório por Período":
            c1, c2 = st.columns(2)
            d1 = c1.date_input("De:", datetime.now() - timedelta(days=7))
            d2 = c2.date_input("Até:", datetime.now())
            df_atual = concl[(concl['dt_obj'].dt.date >= d1) & (concl['dt_obj'].dt.date <= d2)]
        else:
            dia_p = st.date_input("Pedidos de:", datetime.now(), key="f_sel_data")
            pedidos_dia = concl[concl['data'] == dia_p.strftime("%d/%m/%Y")]
            sel = []
            for _, r in pedidos_dia.iterrows():
                if st.checkbox(f"{r['cliente']} (R$ {r['total']})", key=f"chk_f_{r['id']}"): sel.append(r['id'])
            if st.button("📊 GERAR RELATÓRIO DOS SELECIONADOS"):
                df_atual = pedidos_dia[pedidos_dia['id'].isin(sel)]

        if not df_atual.empty:
            total_fat = df_atual['total'].astype(float).sum()
            st.divider()
            st.metric("Faturamento Total", f"R$ {total_fat:.2f}")
            
            # Resumo de Itens (com cálculo de KG)
            res_i = {}
            for _, r in df_atual.iterrows():
                for it in json.loads(r['itens']):
                    n = it['nome']; t = it.get('tipo', 'UN'); v = float(it['subtotal'])
                    if n not in res_i: res_i[n] = {"qtd": 0.0, "valor": 0.0, "tipo": t}
                    if t == "KG" and n in dict_precos:
                        p_u = dict_precos[n]['preco']
                        if p_u > 0: res_i[n]["qtd"] += (v / p_u)
                    else: res_i[n]["qtd"] += float(it['qtd'])
                    res_i[n]["valor"] += v
            
            dados_fin = [{"Produto": k, "Qtd": formatar_unidade(v['qtd'], v['tipo']), "Faturamento": f"R$ {v['valor']:.2f}"} for k, v in res_i.items()]
            st.table(pd.DataFrame(dados_fin))
            
            txt_f = f"*RESUMO FINANCEIRO*\nTotal: R$ {total_fat:.2f}\n" + "\n".join([f"• {d['Produto']}: {d['Qtd']}" for d in dados_fin])
            st.markdown(f'''<a href="https://wa.me/?text={urllib.parse.quote(txt_f)}" target="_blank" style="text-decoration:none;"><div style="background-color:#25D366;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;">📱 ENVIAR RESUMO NO WHATSAPP</div></a>''', unsafe_allow_html=True)

# --- 6. ESTOQUE (LAYOUT EM TABELA) ---
with tabs[5]:
    st.header("🥦 Gestão de Estoque")
    with st.expander("➕ CADASTRAR NOVO PRODUTO"):
        with st.form("add_p"):
            n = st.text_input("Nome do Produto").upper()
            p = st.text_input("Preço (ex: 5.50)")
            t = st.selectbox("Tipo", ["UN", "KG"])
            if st.form_submit_button("SALVAR NO ESTOQUE"):
                prox = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, pd.DataFrame([{"id":prox,"nome":n,"preco":p,"tipo":t,"status":"Ativo"}])]))
                st.rerun()

    st.subheader("Produtos Cadastrados")
    for idx, r in df_produtos.iterrows():
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            status_cor = "🟢" if r['status'] == "Ativo" else "🔴"
            c1.write(f"{status_cor} **{r['nome']}** - R$ {r['preco']} ({r['tipo']})")
            
            if c2.button("✏️", key=f"ed_{r['id']}"):
                st.info("Função de edição rápida em breve.")
            
            label_vis = "Ocultar" if r['status'] == "Ativo" else "Ativar"
            if c3.button(label_vis, key=f"vis_{r['id']}"):
                df_produtos.at[idx, 'status'] = "Inativo" if r['status'] == "Ativo" else "Ativo"
                conn.update(worksheet="Produtos", data=df_produtos); st.rerun()
                
            if c4.button("🗑️", key=f"del_p_{r['id']}"):
                conn.update(worksheet="Produtos", data=df_produtos.drop(idx))
                conn.update(worksheet="Produtos", data=df_produtos.drop(idx)); st.rerun()
