import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# 1. Configuração e Conexão
st.set_page_config(page_title="Horta da Mesa", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# --- INICIALIZAÇÃO DE ESTADO PARA LIMPAR CAMPOS ---
if "form_id" not in st.session_state:
    st.session_state.form_id = 0

def resetar_formulario():
    st.session_state.form_id += 1
    st.cache_data.clear()

# --- CARREGAMENTO DE DADOS ---
def carregar_dados():
    try:
        df_p = conn.read(worksheet="Produtos", ttl=2).dropna(how="all")
        df_v = conn.read(worksheet="Pedidos", ttl=2).dropna(how="all")
        df_p.columns = [str(c).lower().strip() for c in df_p.columns]
        df_v.columns = [str(c).lower().strip() for c in df_v.columns]
        # Garante colunas
        for col in ['id', 'cliente', 'endereco', 'obs', 'itens', 'status', 'data', 'total', 'pagamento']:
            if col not in df_v.columns: df_v[col] = ""
        return df_p, df_v
    except:
        return pd.DataFrame(), pd.DataFrame()

df_produtos, df_pedidos = carregar_dados()

# --- IMPRESSÃO ---
def botao_imprimir(ped, label="🖨️ IMPRIMIR"):
    nome = str(ped.get('cliente', 'CLIENTE')).upper()
    total = f"{float(ped.get('total', 0)):.2f}".replace('.', ',')
    comandos = f"\x1b\x61\x01\x1b\x21\x38{nome}\n\x1b\x21\x00TOTAL: RS {total}\n\n\n\n"
    b64 = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
    url = f"intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
    st.markdown(f'<a href="{url}" style="text-decoration:none;"><div style="background-color:#28a745;color:white;padding:12px;text-align:center;border-radius:8px;font-weight:bold;margin-bottom:10px;">{label}</div></a>', unsafe_allow_html=True)

# --- ABAS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🛒 NOVO PEDIDO", "🚜 COLHEITA", "📦 MONTAGEM", "📅 HISTÓRICO", "🥦 ESTOQUE"])

# --- 1. NOVO PEDIDO ---
with tab1:
    st.header("🛒 Novo Pedido")
    # A 'key' do form_id muda toda vez que salvamos, limpando os campos abaixo
    fid = st.session_state.form_id
    
    col1, col2 = st.columns(2)
    nome = col1.text_input("NOME DO CLIENTE", key=f"nome_{fid}").upper()
    end = col2.text_input("ENDEREÇO", key=f"end_{fid}").upper()
    obs = st.text_area("OBSERVAÇÕES", key=f"obs_{fid}").upper()
    pago = st.checkbox("PAGO ANTECIPADO", key=f"pago_{fid}")

    st.divider()
    st.subheader("Selecione os Produtos")
    itens_venda = []
    total_previo = 0.0
    
    if not df_produtos.empty:
        ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        c_prod1, c_prod2 = st.columns(2)
        for i, (_, p) in enumerate(ativos.iterrows()):
            alvo = c_prod1 if i % 2 == 0 else c_prod2
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"p_{p['id']}_{fid}")
            if qtd > 0:
                preco = float(str(p['preco']).replace(',', '.'))
                sub = 0.0 if str(p['tipo']).upper() == "KG" else (qtd * preco)
                itens_venda.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                total_previo += sub
    
    st.markdown(f"### 💰 Total (Itens Fixos): R$ {total_previo:.2f}")

    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (nome or end) and itens_venda:
            try:
                ids = pd.to_numeric(df_pedidos['id'], errors='coerce').dropna()
                prox_id = int(ids.max() + 1) if not ids.empty else 1
                
                novo_row = pd.DataFrame([{
                    "id": prox_id, "cliente": nome, "endereco": end, "obs": obs,
                    "itens": json.dumps(itens_venda), "status": "Pendente",
                    "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0,
                    "pagamento": "Pago" if pago else "A Pagar"
                }])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_row], ignore_index=True))
                st.success("Salvo!")
                resetar_formulario()
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")
        else:
            st.warning("Preencha Nome/Endereço e escolha itens.")

# --- 2. COLHEITA ---
with tab2:
    st.header("🚜 Lista de Colheita")
    pendentes = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    if not pendentes.empty:
        resumo = {}
        for _, p in pendentes.iterrows():
            itens = json.loads(p['itens'])
            for it in itens:
                nome_it = it['nome']
                resumo[nome_it] = resumo.get(nome_it, 0) + it['qtd']
        
        df_colheita = pd.DataFrame([{"Produto": k, "Total": v} for k, v in resumo.items()])
        st.table(df_colheita)
    else:
        st.info("Nenhum pedido pendente para colheita.")

# --- 3. MONTAGEM ---
with tab3:
    st.header("📦 Detalhes para Montagem")
    pendentes = df_pedidos[df_pedidos['status'].astype(str).str.lower() == "pendente"]
    for idx, p in pendentes.iterrows():
        with st.container(border=True):
            col_a, col_b = st.columns([3, 1])
            col_a.subheader(f"👤 {p['cliente']}")
            col_a.write(f"📍 {p['endereco']}")
            if p['obs']: col_a.info(f"📝 {p['obs']}")
            
            if col_b.button("🗑️ EXCLUIR", key=f"exc_{p['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx))
                st.cache_data.clear(); st.rerun()

            itens_list = json.loads(p['itens'])
            t_real = 0.0
            preenchido = True
            
            st.write("**Itens do Pedido:**")
            for i, it in enumerate(itens_list):
                if str(it['tipo']).upper() == "KG":
                    val = st.text_input(f"Valor R$ {it['nome']} (Sugerido {it['qtd']}kg):", key=f"mont_{p['id']}_{i}")
                    if val:
                        v_num = float(val.replace(',', '.'))
                        it['subtotal'] = v_num; t_real += v_num
                    else: preenchido = False
                else:
                    st.write(f"- {it['nome']}: {it['qtd']} UN")
                    t_final_it = float(it['subtotal'])
                    t_real += t_final_it
            
            st.write(f"### Total: R$ {t_real:.2f}")
            botao_imprimir({"cliente": p['cliente'], "total": t_real})
            
            if st.button("✅ FINALIZAR", key=f"fin_{p['id']}", disabled=not preenchido):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_real
                df_pedidos.at[idx, 'itens'] = json.dumps(itens_list)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear(); st.rerun()
