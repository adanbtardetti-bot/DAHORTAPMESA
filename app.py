import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# 1. Configuração da Página
st.set_page_config(page_title="Horta da Mesa", layout="wide")

# 2. Conexão com Google Sheets (TTL=5 para equilíbrio entre velocidade e cota)
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÃO DE CARREGAMENTO SEGURO ---
def carregar_dados():
    try:
        df_p = conn.read(worksheet="Produtos", ttl=5).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=5).dropna(how="all")
        
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        
        # Garante que colunas essenciais existam
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- ESTILO BOTÃO IMPRIMIR ---
def botao_imprimir(ped, label="🖨️ IMPRIMIR"):
    nome = str(ped.get('cliente', 'CLIENTE')).upper()
    total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {total}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;border:1px solid white;">{label}</div></a>', unsafe_allow_html=True)

# --- NAVEGAÇÃO ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🛒 NOVO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "📊 FINANCEIRO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tab1:
    st.header("🛒 Novo Pedido")
    
    # Identificação no Topo
    c1, c2 = st.columns(2)
    nome = c1.text_input("NOME DO CLIENTE", key="c_nome").upper()
    endereco = c2.text_input("ENDEREÇO", key="c_end").upper()
    obs = st.text_area("OBSERVAÇÕES", key="c_obs").upper()
    pago_f = st.checkbox("PAGO ANTECIPADO", key="c_pago")

    st.divider()
    
    # PRODUTOS E CÁLCULO
    st.subheader("Itens")
    itens_venda = []
    total_previo = 0.0
    
    if not df_produtos.empty:
        # Filtra apenas ativos
        p_ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        cp1, cp2 = st.columns(2)
        
        for i, (_, p) in enumerate(p_ativos.iterrows()):
            alvo = cp1 if i % 2 == 0 else cp2
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"v_{p['id']}")
            
            if qtd > 0:
                # Converte preço para número garantindo que vírgulas virem pontos
                try:
                    preco_num = float(str(p['preco']).replace(',', '.'))
                except:
                    preco_num = 0.0
                
                # Se for KG, o subtotal é 0.0 para ser preenchido na montagem
                sub = 0.0 if str(p['tipo']).upper() == "KG" else (qtd * preco_num)
                
                itens_venda.append({
                    "nome": p['nome'], 
                    "qtd": qtd, 
                    "tipo": p['tipo'], 
                    "subtotal": sub
                })
                total_previo += sub
    
    st.markdown(f"## 💰 TOTAL DOS ITENS FIXOS: R$ {total_previo:.2f}")

    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (nome or endereco) and itens_venda:
            try:
                # Gerar ID numérico seguro
                ids_existentes = pd.to_numeric(df_pedidos['id'], errors='coerce').dropna()
                prox_id = int(ids_existentes.max() + 1) if not ids_existentes.empty else 1
                
                novo_p = pd.DataFrame([{
                    "id": prox_id, "cliente": nome, "endereco": endereco, "obs": obs,
                    "itens": json.dumps(itens_venda), "status": "Pendente",
                    "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0,
                    "pagamento": "Pago" if pago_f else "A Pagar"
                }])
                
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_p], ignore_index=True))
                st.success("Pedido Gravado!")
                st.cache_data.clear()
                st.rerun() # Limpa todos os campos
            except Exception as e:
                st.error(f"Erro ao salvar na planilha: {e}")
        else:
            st.warning("Preencha Nome ou Endereço e escolha pelo menos um produto.")

# --- 3. MONTAGEM ---
with tab3:
    st.header("📦 Montagem")
    pend = df_pedidos[df_pedidos['status'] == "Pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            m1, m2 = st.columns([3, 1])
            m1.subheader(f"👤 {p['cliente']}")
            m1.write(f"📍 {p['endereco']}")
            if p['obs']: m1.warning(f"📝 {p['obs']}")
            
            if m2.button("🗑️ EXCLUIR", key=f"del_{p['id']}"):
                df_pedidos.drop(idx, inplace=True)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear(); st.rerun()

            itens_list = json.loads(p['itens'])
            t_final = 0.0
            trava_kg = False
            
            for i, it in enumerate(itens_list):
                if str(it['tipo']).upper() == "KG":
                    v_kg = st.text_input(f"Valor R$ {it['nome']}:", key=f"m_{p['id']}_{i}")
