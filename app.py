import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# Configuração da Página
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# Conexão (Aumentamos o TTL para 10 segundos para evitar erro de cota)
conn = st.connection("gsheets", type=GSheetsConnection)

# --- CARREGAR DADOS COM CACHE SEGURO ---
def carregar_dados():
    try:
        # ttl=10 ajuda a não estourar o limite de 60 requisições/min do Google
        df_p = conn.read(worksheet="Produtos", ttl=10).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=10).dropna(how="all")
        
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        
        # Garante as colunas para não dar Script Exception
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
            
        return df_p, df_v
    except Exception as e:
        # Se der erro de cota, mostra uma mensagem amigável
        if "429" in str(e):
            st.error("⏳ O Google pediu um descanso! Aguarde 30 segundos e atualize a página.")
        else:
            st.error(f"Erro: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- FUNÇÃO DE IMPRESSÃO (VERDE E BRANCO) ---
def botao_imprimir(ped, label="🖨️ IMPRIMIR"):
    nome = str(ped.get('cliente', 'CLIENTE')).upper()
    total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {total}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border:1px solid white;">{label}</div></a>', unsafe_allow_html=True)

# --- ABAS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tab1:
    st.header("🛒 Novo Pedido")
    
    # IDENTIFICAÇÃO NO TOPO (Como solicitado)
    col_cli1, col_cli2 = st.columns(2)
    with col_cli1:
        c_nome = st.text_input("NOME DO CLIENTE", key="new_nome").upper()
    with col_cli2:
        c_end = st.text_input("ENDEREÇO", key="new_end").upper()
    
    c_obs = st.text_area("OBSERVAÇÕES (Troco, etc)", key="new_obs").upper()
    c_pago = st.checkbox("PAGO ANTECIPADO", key="new_pago")

    st.divider()
    
    # SELEÇÃO DE PRODUTOS E SOMA
    st.subheader("Itens")
    itens_atuais = []
    soma_venda = 0.0
    
    if not df_produtos.empty:
        p_ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        c_p1, c_p2 = st.columns(2)
        
        for i, (_, p) in enumerate(p_ativos.iterrows()):
            alvo = c_p1 if i % 2 == 0 else c_p2
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"inp_{p['id']}")
            if qtd > 0:
                preco_f = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if p['tipo'] == "KG" else (qtd * preco_f)
                itens_atuais.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                soma_venda += sub
    
    st.markdown(f"## 💰 TOTAL: R$ {soma_venda:.2f}")

    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (c_nome or c_end) and itens_atuais:
            # Gerar ID novo
            try:
                prox_id = int(df_pedidos['id'].max()) + 1
            except:
                prox_id = 1
                
            novo_ped = pd.DataFrame([{
                "id": prox_id, "cliente": c_nome, "endereco": c_end, "obs": c_obs,
                "itens": json.dumps(itens_atuais), "status": "Pendente",
                "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0,
                "pagamento": "Pago" if c_pago else "A Pagar"
            }])
            
            # Salvar
            df_atualizado = pd.concat([df_pedidos, novo_ped], ignore_index=True)
            conn.update(worksheet="Pedidos", data=df_atualizado)
            
            st.success("Pedido Gravado com Sucesso!")
            st.cache_data.clear()
            # O Rerun garante que todos os campos key="..." voltem ao vazio
            st.rerun()
        else:
            st.warning("Preencha Nome/Endereço e adicione produtos!")

# --- 3. MONTAGEM ---
with tab3:
    st.header("📦 Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    
    if pendentes.empty:
        st.info("Nenhum pedido para montar.")
    
    for idx, p in pendentes.iterrows():
        with st.container(border=True):
            m1, m2 = st.columns([3, 1])
            m1.subheader(f"👤 {p['cliente'] if p['cliente'] else 'SEM NOME'}")
            m1.write(f"📍 {p['endereco']}")
            if p['obs']: m1.warning(f"📝 {p['obs']}")
            
            if m2.button("🗑️ EXCLUIR", key=f"del_{p['id']}"):
                df_temp = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_temp)
                st.cache_data.clear()
                st.rerun()

            itens_list = json.loads(p['itens'])
            t_final = 0.0
            preenchido = True
            
            for i, it in enumerate(itens_list):
                if it['tipo'] == "KG":
                    val_kg = st.text_input(f"R$ {it['nome']} (Sugestão {it['qtd']}kg):", key=f"v_{p['id']}_{i}")
                    if val_kg:
                        v = float(val_kg.replace(',', '.'))
                        it['subtotal'] = v; t_final += v
                    else: preenchido = False
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} UN")
                    t_final += float(it['subtotal'])
            
            st.write(f"**Total Real: R$ {t_final:.2f}**")
            botao_imprimir({"cliente": p['cliente'], "total": t_final})
            
            if st.button("✅ FINALIZAR", key=f"ok_{p['id']}", disabled=not preenchido, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_final
                df_pedidos.at[idx, 'itens'] = json.dumps(itens_list)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()
