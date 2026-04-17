import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import json

st.set_page_config(page_title="Horta da Mesa - Gestão", layout="wide")

# Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except:
        if aba == "Produtos":
            return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "ativo"])
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento"])

df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque", "Financeiro"])

# --- FUNÇÃO DE ETIQUETA ---
def gerar_etiqueta_html(ped):
    # Estilização baseada na sua foto
    html = f"""
    <div style="border: 2px solid #333; border-radius: 15px; padding: 20px; width: 350px; font-family: sans-serif; background: white; color: black;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <b style="font-size: 22px;">@dahortapmesa</b>
            <span style="font-size: 25px;">🌱</span>
        </div>
        <div style="margin-top: 20px; font-size: 24px; font-weight: bold;">{ped['cliente']}</div>
        <div style="margin-top: 15px; font-size: 18px; line-height: 1.4;">{ped['endereco']}</div>
        <div style="margin-top: 20px; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #eee; padding-top: 10px;">
            <b style="font-size: 22px;">R$ {ped['total']:.2f}</b>
            <b style="font-size: 20px; text-transform: uppercase;">{ped['pagamento']}</b>
        </div>
    </div>
    <script>window.print();</script>
    """
    return html

# --- TELA: MONTAGEM ---
if menu == "Montagem/Expedição":
    st.header("📦 Montagem e Conferência")
    pendentes = df_pedidos[df_pedidos['status'] == "Pendente"]
    
    if pendentes.empty:
        st.info("Nenhum pedido aguardando montagem.")
    
    for idx, ped in pendentes.iterrows():
        with st.expander(f"Pedido #{ped['id']} - {ped['cliente']}", expanded=True):
            itens = json.loads(ped['itens'])
            t_real = 0.0
            trava_kg = False
            
            st.write(f"📍 **Endereço:** {ped['endereco']}")
            
            cols = st.columns(2)
            for i, it in enumerate(itens):
                with cols[i % 2]:
                    if it['tipo'] == "KG":
                        # Input para valor da balança
                        v_balanca = st.number_input(f"Balança R$: {it['nome']}", min_value=0.0, step=0.1, key=f"v_{ped['id']}_{i}")
                        it['subtotal'] = v_balanca
                        if v_balanca <= 0:
                            trava_kg = True
                            st.warning("Insira o valor")
                    else:
                        st.write(f"✅ {it['nome']}: {it['qtd']} un")
                    t_real += it['subtotal']
            
            st.divider()
            st.write(f"### Total: R$ {t_real:.2f}")
            
            c1, c2, c3, c4 = st.columns(4)
            
            # Botão Finalizar com TRAVA
            if c1.button("✅ Concluir", key=f"fin_{ped['id']}", disabled=trava_kg, use_container_width=True):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_real
                df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.success("Pedido Finalizado!")
                st.rerun()

            # Botão Etiqueta
            if c2.button("🖨️ Etiqueta", key=f"et_{ped['id']}", use_container_width=True):
                ped_atual = ped.to_dict()
                ped_atual['total'] = t_real # Garante o total da balança na etiqueta
                st.components.v1.html(gerar_etiqueta_html(ped_atual), height=400)

            # Botão Editar
            if c3.button("✏️ Editar", key=f"ed_{ped['id']}", use_container_width=True):
                st.info("Para editar itens, exclua e refaça o pedido (versão simplificada).")

            # Botão Excluir
            if c4.button("🗑️ Excluir", key=f"del_{ped['id']}", use_container_width=True):
                df_pedidos = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

# --- TELA: NOVO PEDIDO (AJUSTADA) ---
elif menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    with st.form("cad_venda", clear_on_submit=True):
        cliente = st.text_input("Cliente")
        endereco = st.text_input("Endereço Completo")
        pagamento = st.selectbox("Forma de Pagamento", ["Pago", "A Pagar", "Pix", "Cartão"])
        st.divider()
        
        itens_venda = []
        for _, p in df_produtos.iterrows():
            qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, key=f"n_{p['id']}")
            if qtd > 0:
                sub = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
                itens_venda.append({"id": int(p['id']), "nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "preco": p['preco'], "subtotal": sub})
        
        if st.form_submit_button("Enviar para Montagem"):
            if cliente and itens_venda:
                novo_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo_p = pd.DataFrame([{
                    "id": novo_id, "cliente": cliente, "endereco": endereco,
                    "itens": json.dumps(itens_venda), "status": "Pendente",
                    "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": pagamento
                }])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo_p], ignore_index=True))
                st.cache_data.clear()
                st.success("Pedido criado!")
                st.rerun()

# --- ESTOQUE E FINANCEIRO (MANTIDOS) ---
elif menu == "Estoque":
    st.header("⚙️ Estoque")
    with st.form("add_prod"):
        n = st.text_input("Nome")
        p = st.number_input("Preço")
        t = st.selectbox("Venda por", ["Unidade", "KG"])
        if st.form_submit_button("Cadastrar"):
            prox = int(df_produtos['id'].max() + 1) if not df_produtos.empty else 1
            df_produtos = pd.concat([df_produtos, pd.DataFrame([{"id": prox, "nome": n, "preco": p, "tipo": t, "ativo": True}])])
            conn.update(worksheet="Produtos", data=df_produtos)
            st.rerun()
    st.dataframe(df_produtos)
