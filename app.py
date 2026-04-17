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
        # Busca dados brutos sem cache para não travar
        df_p = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        
        # Normaliza colunas (Tudo minúsculo e sem espaços)
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        
        # Garante que as colunas essenciais existam (Evita o KeyError do print)
        colunas_vendas = ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']
        for col in colunas_vendas:
            if col not in df_v.columns:
                df_v[col] = ""
        
        colunas_prod = ['id', 'nome', 'preco', 'tipo', 'status']
        for col in colunas_prod:
            if col not in df_p.columns:
                df_p[col] = ""
                
        return df_p, df_v
    except Exception as e:
        st.error(f"Erro Crítico de Conexão: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- 2. MOTOR DE IMPRESSÃO (CORRIGIDO SEM ERROS DE F-STRING) ---
def imprimir_comando(ped, valor_real, tipo="ETIQUETA"):
    try:
        def limpar(txt):
            if pd.isna(txt) or str(txt).lower() == 'nan': return ""
            return str(txt).strip().upper()
        
        nome = limpar(ped.get('cliente', ''))
        end = limpar(ped.get('endereco', ''))
        pag = limpar(ped.get('pagamento', ''))
        v_f = f"{float(valor_real):.2f}".replace('.', ',')
        
        if tipo == "ETIQUETA":
            txt_pg = f"\n*** {pag} ***\n" if "PAGO" in pag else "\n"
            cmds = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00\n{end}{txt_pg}\n\x1b\x61\x01\x1b\x21\x10TOTAL: RS {v_f}\n\n\n\n"
            label, cor = "🖨️ ETIQUETA", "#28a745"
        else:
            detalhes = ""
            itens_lista = json.loads(ped['itens'])
            for it in itens_lista:
                detalhes += f"{it['nome'][:15]} {it['qtd']}{it['tipo']} -> RS {float(it['subtotal']):.2f}\n"
            cmds = f"\x1b\x61\x01\x1b\x21\x10HORTA DA MESA\n\x1b\x21\x00\n--------------------------------\nCLIENTE: {nome}\nDATA: {ped['data']}\n--------------------------------\n{detalhes}--------------------------------\nTOTAL: RS {v_f}\nPGTO: {pag}\n\n\n\n"
            label, cor = "📄 RECIBO", "#007bff"

        b64 = base64.b64encode(cmds.encode('latin-1')).decode('utf-8')
        url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:{cor};color:white;padding:10px;text-align:center;border-radius:8px;font-weight:bold;margin:5px 0px;">{label}</div></a>', unsafe_allow_html=True)
    except:
        st.warning("Erro ao gerar comando de impressão.")

# --- 3. ABAS DO SISTEMA ---
tabs = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- ABA 0: NOVO PEDIDO ---
with tabs[0]:
    if "form_reset" not in st.session_state: st.session_state.form_reset = 0
    f = st.session_state.form_reset
    
    col_n, col_e = st.columns(2)
    nome_c = col_n.text_input("NOME DO CLIENTE", key=f"n_{f}").upper()
    ende_c = col_e.text_input("ENDEREÇO", key=f"e_{f}").upper()
    obs_c = st.text_area("OBSERVAÇÕES", key=f"o_{f}", height=80).upper()
    pago_ant = st.checkbox("MARCAR COMO PAGO AGORA", key=f"p_{f}")
    
    st.markdown("### Selecione os Itens")
    venda_atual = []
    total_previsto = 0.0
    
    if not df_produtos.empty:
        # Filtra apenas quem está ativo
        prods_ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        for _, r in prods_ativos.iterrows():
            c_a, c_b = st.columns([4, 1])
            quantidade = c_b.number_input(f"{r['nome']} (R$ {r['preco']})", min_value=0, step=1, key=f"prod_{r['id']}_{f}")
            if quantidade > 0:
                p_unit = float(str(r['preco']).replace(',', '.'))
                # KG começa com subtotal 0 até a pesagem na montagem
                sub = 0.0 if str(r['tipo']).upper() == "KG" else (quantidade * p_unit)
                venda_atual.append({"nome": r['nome'], "qtd": quantidade, "tipo": r['tipo'], "subtotal": sub})
                total_previsto += sub
    
    st.divider()
    st.subheader(f"💰 Total Estimado: R$ {total_previsto:.2f}")
    
    if st.button("💾 SALVAR E GERAR PEDIDO", use_container_width=True):
        if (nome_c or ende_c) and venda_atual:
            novo_id = int(pd.to_numeric(df_pedidos['id'], errors='coerce').max() + 1) if not df_pedidos.empty else 1
            linha = pd.DataFrame([{
                "id": novo_id, "cliente": nome_c, "endereco": ende_c, "obs": obs_c,
                "itens": json.dumps(venda_atual), "status": "Pendente",
                "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0,
                "pagamento": "PAGO" if pago_ant else "A PAGAR"
            }])
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, linha], ignore_index=True))
            st.session_state.form_reset += 1
            st.rerun()

# --- ABA 1: COLHEITA ---
with tabs[1]:
    if not df_pedidos.empty:
        p_pendentes = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
        if not p_pendentes.empty:
            soma_itens = {}
            for _, ped in p_pendentes.iterrows():
                try:
                    lista = json.loads(ped['itens'])
                    for i in lista:
                        soma_itens[i['nome']] = soma_itens.get(i['nome'], 0) + i['qtd']
                except: pass
            st.table(pd.DataFrame([{"Produto": k, "Total Colher": v} for k, v in soma_itens.items()]))
        else: st.info("Nada para colher no momento.")

# --- ABA 2: MONTAGEM ---
with tabs[2]:
    if not df_pedidos.empty:
        ped_montar = df_pedidos[df_pedidos['status'].str.lower() == "pendente"]
        for idx, p in ped_montar.iterrows():
            with st.container(border=True):
                st.markdown(f"#### 👤 {p['cliente']}")
                st.caption(f"📍 {p['endereco']}")
                if p['obs']: st.warning(f"⚠️ OBS: {p['obs']}")
                
                itens_p = json.loads(p['itens'])
                valor_final = 0.0
                pronto = True
                
                for i, item in enumerate(itens_p):
                    if str(item['tipo']).upper() == "KG":
                        peso = st.text_input(f"Peso {item['nome']} (Ped: {item['qtd']}kg):", key=f"peso_{p['id']}_{i}")
                        if peso:
                            v = float(peso.replace(',', '.'))
                            item['subtotal'] = v
                            valor_final += v
                        else: pronto = False
                    else:
                        st.write(f"✅ {item['nome']} - {item['qtd']} UN")
                        valor_final += float(item['subtotal'])
                
                st.write(f"**Total Final: R$ {valor_final:.2f}**")
                c1, c2 = st.columns(2)
                with c1: imprimir_comando(p, valor_final, "ETIQUETA")
                with c2: imprimir_comando(p, valor_final, "RECIBO")
                
                if st.button("✅ FINALIZAR", key=f"btn_f_{p['id']}", disabled=not pronto, use_container_width=True):
                    df_pedidos.at[idx, 'status'] = "Concluído"
                    df_pedidos.at[idx, 'total'] = valor_final
                    df_pedidos.at[idx, 'itens'] = json.dumps(itens_p)
                    conn.update(worksheet="Pedidos", data=df_pedidos)
                    st.rerun()

# --- ABA 3: HISTÓRICO (CARDS OTIMIZADOS) ---
with tabs[3]:
    escolha_data = st.date_input("Filtrar por data", datetime.now())
    data_formatada = escolha_data.strftime("%d/%m/%Y")
    
    filtro = df_pedidos[(df_pedidos['status'] == "Concluído") & (df_pedidos['data'] == data_formatada)]
    
    if filtro.empty:
        st.info(f"Nenhum pedido finalizado em {data_formatada}")
    else:
        for idx, p in filtro.iterrows():
            with st.container(border=True):
                col_a, col_b, col_c = st.columns([3, 2, 2])
                col_a.markdown(f"**{p['cliente']}**\n\n{p['endereco']}")
                
                cor_pg = "green" if p['pagamento'] == "PAGO" else "red"
                col_b.markdown(f"**R$ {float(p['total']):.2f}**\n\n<span style='color:{cor_pg}; font-weight:bold;'>{p['pagamento']}</span>", unsafe_allow_html=True)
                
                with col_c:
                    if st.button("💳 ALTERAR PGTO", key=f"pg_btn_{p['id']}", use_container_width=True):
                        df_pedidos.at[idx, 'pagamento'] = "A PAGAR" if p['pagamento'] == "PAGO" else "PAGO"
                        conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()
                    
                    with st.popover("📄 VER / REIMPRIMIR", use_container_width=True):
                        st.write("--- Itens ---")
                        for it in json.loads(p['itens']):
                            st.write(f"{it['nome']}: R$ {it['subtotal']:.2f}")
                        st.divider()
                        imprimir_comando(p, p['total'], "ETIQUETA")
                        imprimir_comando(p, p['total'], "RECIBO")

# --- ABA 4: FINANCEIRO ---
with tabs[4]:
    concluidos = df_pedidos[df_pedidos['status'] == "Concluído"]
    t_pago = concluidos[concluidos['pagamento'] == "PAGO"]['total'].astype(float).sum()
    t_pend = concluidos[concluidos['pagamento'] == "A PAGAR"]['total'].astype(float).sum()
    
    col1, col2 = st.columns(2)
    col1.metric("DINHEIRO EM CAIXA", f"R$ {t_pago:.2f}")
    col2.metric("PENDENTE (A RECEBER)", f"R$ {t_pend:.2f}")
    st.divider()
    st.dataframe(concluidos[['cliente', 'data', 'total', 'pagamento']], use_container_width=True)

# --- ABA 5: ESTOQUE ---
with tabs[5]:
    st.header("🥦 Gerenciar Produtos")
    with st.expander("➕ ADICIONAR NOVO"):
        with st.form("novo_p"):
            n_nome = st.text_input("Nome do Produto")
            n_preco = st.text_input("Preço (Ex: 5.50)")
            n_tipo = st.selectbox("Tipo", ["UN", "KG"])
            if st.form_submit_button("SALVAR"):
                prox_id = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
                novo_p = pd.DataFrame([{"id": prox_id, "nome": n_nome.upper(), "preco": n_preco, "tipo": n_tipo, "status": "ativo"}])
                conn.update(worksheet="Produtos", data=pd.concat([df_produtos, novo_p], ignore_index=True)); st.rerun()
    
    for i, r in df_produtos.iterrows():
        c1, c2, c3 = st.columns([4, 1, 1])
        c1.write(f"**{r['nome']}** - {r['tipo']} (R$ {r['preco']})")
        # Botão Ativar/Desativar
        st_label = "🚫" if r['status'] == "ativo" else "✅"
        if c2.button(st_label, key=f"st_bt_{r['id']}"):
            df_produtos.at[i, 'status'] = "inativo" if r['status'] == "ativo" else "ativo"
            conn.update(worksheet="Produtos", data=df_produtos); st.rerun()
        # Botão Excluir
        if c3.button("🗑️", key=f"del_bt_{r['id']}"):
            conn.update(worksheet="Produtos", data=df_produtos.drop(i)); st.rerun()
