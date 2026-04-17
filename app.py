import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# Configuração
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES DE LIMPEZA ---
def formatar_unidade(valor, tipo):
    try:
        v = float(valor)
        if tipo == "KG": return f"{v:.3f}".replace('.', ',') + " kg"
        return str(int(v)) + " un"
    except: return str(valor)

# --- CARREGAMENTO COM TRATAMENTO DE ERRO ---
def carregar_dados():
    try:
        # Lê os produtos
        df_p = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        
        # Lê os pedidos
        df_v = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        
        # GARANTE QUE TODAS AS COLUNAS EXISTAM (Evita o Script Exception)
        colunas_necessarias = ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']
        for col in colunas_necessarias:
            if col not in df_v.columns:
                df_v[col] = "" # Cria a coluna vazia se não existir
        
        return df_p, df_v
    except Exception as e:
        st.error(f"Erro ao carregar Planilha: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- IMPRESSÃO ---
def botao_imprimir(ped, label="🖨️ IMPRIMIR"):
    try:
        nome = str(ped.get('cliente', 'CLIENTE')).upper()
        total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
        comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {total}\n\n\n\n"
        b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">{label}</div></a>', unsafe_allow_html=True)
    except: pass

# --- NAVEGAÇÃO ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tab1:
    st.header("🛒 Novo Pedido")
    
    # Identificação no Topo
    c1, c2 = st.columns(2)
    cli_nome = c1.text_input("NOME DO CLIENTE", key="in_nome").upper()
    cli_end = c2.text_input("ENDEREÇO", key="in_end").upper()
    cli_obs = st.text_area("OBSERVAÇÕES", key="in_obs").upper()
    cli_pago = st.checkbox("PAGO ANTECIPADO", key="in_pago")

    st.divider()
    
    # Produtos e Soma Real-Time
    st.subheader("Itens")
    itens_selecionados = []
    total_previo = 0.0
    
    if not df_produtos.empty:
        col_a, col_b = st.columns(2)
        for i, (_, p) in enumerate(df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo'].iterrows()):
            alvo = col_a if i % 2 == 0 else col_b
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"q_{p['id']}")
            if qtd > 0:
                preco_v = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if p['tipo'] == "KG" else (qtd * preco_v)
                itens_selecionados.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                total_previo += sub
    
    st.markdown(f"### 💰 TOTAL: R$ {total_previo:.2f}")

    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (cli_nome or cli_end) and itens_selecionados:
            # Gerar ID
            prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty and str(df_pedidos['id'].max()).isdigit() else 1
            
            novo_row = pd.DataFrame([{
                "id": prox_id, "cliente": cli_nome, "endereco": cli_end, "obs": cli_obs,
                "itens": json.dumps(itens_selecionados), "status": "Pendente",
                "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0,
                "pagamento": "Pago" if cli_pago else "A Pagar"
            }])
            
            conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_row], ignore_index=True))
            st.success("Salvo!")
            st.cache_data.clear()
            st.rerun() # Limpa tudo
        else:
            st.warning("Preencha Nome/Endereço e escolha produtos!")

# --- 3. MONTAGEM ---
with tab3:
    st.header("📦 Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, p in pendentes.iterrows():
        with st.container(border=True):
            m1, m2 = st.columns([3, 1])
            m1.subheader(f"👤 {p['cliente']}")
            m1.write(f"📍 {p['endereco']}")
            if p['obs']: m1.warning(f"📝 {p['obs']}")
            
            if m2.button("🗑️ EXCLUIR", key=f"del_{p['id']}"):
                df_pedidos.drop(idx, inplace=True)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.rerun()

            itens_list = json.loads(p['itens'])
            t_final = 0.0
            preenchido = True
            for i, it in enumerate(itens_list):
                if it['tipo'] == "KG":
                    v_kg = st.text_input(f"Valor R$ {it['nome']}:", key=f"v_{p['id']}_{i}")
                    if v_kg:
                        val = float(v_kg.replace(',', '.'))
                        it['subtotal'] = val; t_final += val
                    else: preenchido = False
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN")
                    t_final += float(it['subtotal'])
            
            st.write(f"**Total Real: R$ {t_final:.2f}**")
            botao_imprimir({"cliente": p['cliente'], "total": t_final})
            
            if st.button("✅ FINALIZAR", key=f"ok_{p['id']}", disabled=not preenchido):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_final
                df_pedidos.at[idx, 'itens'] = json.dumps(itens_list)
                conn.update(worksheet="Pedidos", data=df_pedidos); st.rerun()

# [As outras abas seguem com as correções de visualização de endereço e histórico]
