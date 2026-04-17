import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

st.set_page_config(page_title="Horta da Mesa", layout="wide")

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        # TTL=0 para garantir que ele pegue os dados frescos da planilha
        df = conn.read(worksheet=aba, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao carregar aba {aba}: {e}")
        return pd.DataFrame()

df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque"])

# --- FUNÇÃO DE IMPRESSÃO (REGRA: SÓ PAGO + LAYOUT AJUSTADO) ---
def disparar_impressao_rawbt(ped):
    nome = str(ped.get('cliente', '')).strip().upper() if pd.notna(ped.get('cliente')) else ""
    endereco = str(ped.get('endereco', '')).strip().upper() if pd.notna(ped.get('endereco')) else ""
    
    # Lógica de Pagamento: SÓ aparece se for exatamente "Pago"
    status_raw = str(ped.get('pagamento', '')).strip().upper()
    exibir_pg = "PAGO" if status_raw == "PAGO" else ""
    
    valor_formatado = f"{float(ped['total']):.2f}".replace('.', ',')

    # COMANDOS ESC/POS (Mágica que funcionou no seu HTML)
    comandos = "\x1b\x61\x01"  # Centralizar
    
    # Nome e Endereço em FONTE GRANDE
    if nome:
        comandos += "\x1b\x21\x38" + nome + "\n"
    if endereco:
        comandos += "\x1b\x21\x38" + endereco + "\n"
    
    comandos += "\x1b\x21\x00" + "----------------\n" # Linha normal
    
    # Valor em FONTE NORMAL
    comandos += "TOTAL: RS " + valor_formatado + "\n"
    
    if exibir_pg:
        comandos += exibir_pg + "\n"
        
    comandos += "\n\n\n"
    
    try:
        b64_texto = base64.b64encode(comandos.encode('latin-1')).decode('utf-8')
        url_rawbt = f"intent:base64,{b64_texto}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
        
        st.markdown(
            f"""
            <a href="{url_rawbt}" style="text-decoration: none;">
                <div style="background-color: #28a745; color: white; padding: 15px; text-align: center; 
                border-radius: 10px; font-weight: bold; font-size: 20px;">
                    🖨️ IMPRIMIR ETIQUETA
                </div>
            </a>
            """, 
            unsafe_allow_html=True
        )
    except:
        st.error("Erro nos caracteres.")

# --- TELA: NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    
    with st.form("form_venda", clear_on_submit=True):
        c = st.text_input("Cliente", value=edit['cliente'] if edit else "")
        e = st.text_input("Endereço", value=edit['endereco'] if edit else "")
        foi_pago = st.checkbox("Marcar como PAGO", value=(edit['pagamento'] == "Pago") if edit else False)
        
        st.write("---")
        itens_p = []
        if not df_produtos.empty:
            for _, p in df_produtos.iterrows():
                def_qtd = 0
                if edit:
                    try:
                        for oi in json.loads(edit['itens']):
                            if oi['nome'] == p['nome']: def_qtd = int(oi.get('qtd', 0))
                    except: pass
                
                qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, value=def_qtd, key=f"p_{p['id']}")
                if qtd > 0:
                    itens_p.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * p['preco'])})
        
        if st.form_submit_button("✅ SALVAR PEDIDO"):
            if c and itens_p:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo_df = pd.DataFrame([{
                    "id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_p),
                    "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), 
                    "total": 0.0, "pagamento": "Pago" if foi_pago else "A Pagar"
                }])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_df], ignore_index=True))
                st.session_state.edit_data = None
                st.cache_data.clear()
                st.success("Pedido Salvo!")
                st.rerun()

# --- TELA: MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Montagem")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    
    for idx, ped in pendentes.iterrows():
        with st.container(border=True):
            st.subheader(f"👤 {ped['cliente']}")
            itens = json.loads(ped['itens'])
            t_real = 0.0
            trava_kg = False
            
            for i, it in enumerate(itens):
                if it['tipo'] == "KG":
                    st.write(f"⚖️ **{it['nome']}**")
                    v_input = st.text_input(f"Valor R$:", key=f"v_{ped['id']}_{i}")
                    if v_input:
                        try:
                            v_float = float(v_input.replace(',', '.'))
                            it['subtotal'] = v_float
                            t_real += v_float
                        except: trava_kg = True
                    else: trava_kg = True
                else:
                    st.write(f"✅ {it['nome']} - {it['qtd']} un")
                    t_real += it['subtotal']
            
            st.write(f"**Total: R$ {t_real:.2f}** ({ped['pagamento']})")
            
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("✅ Concluir", key=f"f_{ped['id']}", disabled=trava_kg):
                df_pedidos.at[idx, 'status'] = "Concluído"; df_pedidos.at[idx, 'total'] = t_real
                df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear(); st.rerun()

            with c2:
                p_copy = ped.to_dict(); p_copy['total'] = t_real
                disparar_impressao_rawbt(p_copy)

            if c3.button("✏️ Editar", key=f"e_{ped['id']}"):
                st.session_state.edit_data = ped.to_dict()
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx))
                st.cache_data.clear(); st.rerun()

            if c4.button("🗑️ Excluir", key=f"x_{ped['id']}"):
                conn.update(worksheet="Pedidos", data=df_pedidos.drop(idx))
                st.cache_data.clear(); st.rerun()

# --- TELA: ESTOQUE (CORRIGIDA) ---
elif menu == "Estoque":
    st.header("🥦 Gerenciar Produtos")
    
    if not df_produtos.empty:
        # Exibe a tabela de produtos atual
        st.dataframe(df_produtos[["id", "nome", "preco", "tipo"]], use_container_width=True, hide_index=True)
        
        with st.expander("➕ Adicionar / Editar Produto"):
            with st.form("form_produto"):
                nome_p = st.text_input("Nome do Produto")
                preco_p = st.number_input("Preço", min_value=0.0, format="%.2f")
                tipo_p = st.selectbox("Tipo", ["UN", "KG"])
                
                if st.form_submit_button("Gravar no Estoque"):
                    if nome_p:
                        novo_id = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
                        novo_item = pd.DataFrame([{"id": novo_id, "nome": nome_p, "preco": preco_p, "tipo": tipo_p}])
                        df_atualizado = pd.concat([df_produtos, novo_item], ignore_index=True)
                        conn.update(worksheet="Produtos", data=df_atualizado)
                        st.cache_data.clear()
                        st.success("Estoque Atualizado!")
                        st.rerun()
    else:
        st.warning("Nenhum produto cadastrado na aba 'Produtos'.")
