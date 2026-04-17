import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import json

st.set_page_config(page_title="Horta da Mesa", layout="wide")

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0)
        return df.dropna(how="all") if df is not None else pd.DataFrame()
    except:
        return pd.DataFrame()

df_produtos = carregar_dados("Produtos")
df_pedidos = carregar_dados("Pedidos")

if 'edit_data' not in st.session_state:
    st.session_state.edit_data = None

menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Montagem/Expedição", "Estoque"])

# --- FUNÇÃO DE IMPRESSÃO VIA WEB-VIEW (PLANO C) ---
def disparar_impressao_rawbt(ped):
    status_pg = ped.get('pagamento', 'A Pagar')
    
    # Criamos uma mini-página HTML para a etiqueta
    html_etiqueta = f"""
    <html>
    <body style="font-family: Arial, sans-serif; width: 280px; margin: 0; padding: 10px; color: black; background-color: white;">
        <div style="text-align: center; border-bottom: 1px solid black; padding-bottom: 5px;">
            <b style="font-size: 18px;">DA HORTA P/ MESA</b>
        </div>
        <div style="margin: 15px 0; font-size: 22px; font-weight: bold;">
            {str(ped['cliente']).upper()}
        </div>
        <div style="margin-bottom: 15px; font-size: 16px;">
            {str(ped['endereco']).upper()}
        </div>
        <div style="border-top: 1px solid black; padding-top: 5px; display: flex; justify-content: space-between;">
            <b style="font-size: 18px;">R$ {float(ped['total']):.2f}</b>
            <b style="font-size: 14px;">{status_pg.upper()}</b>
        </div>
        <script>
            // Comando para abrir o diálogo de impressão assim que carregar
            window.onload = function() {{
                window.print();
                setTimeout(function() {{ window.close(); }}, 500);
            }};
        </script>
    </body>
    </html>
    """
    
    # Botão que abre a etiqueta em um frame invisível ou nova aba
    with st.expander("📄 Gerar Etiqueta"):
        st.components.v1.html(html_etiqueta, height=350)
        st.caption("Se a tela de impressão não abrir sozinha, clique com o botão direito e escolha Imprimir.")

# --- TELA: NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    edit = st.session_state.edit_data
    
    with st.form("form_venda"):
        c = st.text_input("Cliente", value=edit['cliente'] if edit else "")
        e = st.text_input("Endereço", value=edit['endereco'] if edit else "")
        pg = st.selectbox("Pagamento", ["A Pagar", "Pago", "Pix", "Dinheiro"])
        
        st.write("---")
        itens_p = []
        for _, p in df_produtos.iterrows():
            def_qtd = 0
            if edit:
                for oi in json.loads(edit['itens']):
                    if oi['nome'] == p['nome']: def_qtd = int(oi.get('qtd', 0))
            
            qtd = st.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, value=def_qtd, key=f"p_{p['id']}")
            if qtd > 0:
                itens_p.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": 0.0 if p['tipo'] == "KG" else (qtd * p['preco'])})
        
        if st.form_submit_button("✅ Gravar Pedido"):
            if c and itens_p:
                prox_id = int(df_pedidos['id'].max() + 1) if not df_pedidos.empty else 1
                novo = pd.DataFrame([{
                    "id": prox_id, "cliente": c, "endereco": e, "itens": json.dumps(itens_p),
                    "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), 
                    "total": 0.0, "pagamento": pg
                }])
                conn.update(worksheet="Pedidos", data=pd.concat([df_pedidos, novo], ignore_index=True))
                st.session_state.edit_data = None
                st.cache_data.clear()
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
                    v_input = st.text_input(f"Valor R$:", key=f"v_{ped['id']}_{i}", value="")
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
            
            st.markdown(f"### Total: R$ {t_real:.2f}")
            
            c1, c2, c3, c4 = st.columns(4)
            
            if c1.button("✅ Concluir", key=f"f_{ped['id']}", disabled=trava_kg, type="primary"):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_real
                df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

            with c2:
                # Agora gera a etiqueta visual que dispara a impressão
                p_copy = ped.to_dict()
                p_copy['total'] = t_real
                disparar_impressao_rawbt(p_copy)

            if c3.button("✏️ Editar", key=f"e_{ped['id']}"):
                st.session_state.edit_data = ped.to_dict()
                df_pedidos = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

            if c4.button("🗑️ Excluir", key=f"x_{ped['id']}"):
                df_pedidos = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()
