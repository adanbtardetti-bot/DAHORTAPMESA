import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import json
import urllib.parse
import base64

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

# --- FUNÇÃO DE IMPRESSÃO (NOVA TÉCNICA BASE64) ---
def disparar_impressao_rawbt(ped):
    status_pg = ped.get('pagamento', 'A Pagar')
    # Texto ultra-simples para evitar erro de buffer da impressora
    texto = (
        f"--------------------------\n"
        f"      DA HORTA P/ MESA\n"
        f"--------------------------\n"
        f"{str(ped['cliente']).upper()}\n"
        f"{str(ped['endereco']).upper()}\n"
        f"--------------------------\n"
        f"VALOR: R$ {float(ped['total']):.2f}\n"
        f"PAGTO: {status_pg}\n"
        f"--------------------------\n"
        f"\n\n\n\n" # Espaço para o corte do papel
    )
    
    # Codificando em Base64 para o RawBT ler como arquivo de dados puro
    b64_texto = base64.b64encode(texto.encode('utf-8')).decode('utf-8')
    
    # Intent específica para Base64 (mais estável)
    url_rawbt = f"intent:#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;S.base64={b64_texto};end;"
    
    botao_html = f"""
        <a href="{url_rawbt}" style="text-decoration: none;">
            <div style="
                background-color: #28a745;
                color: white;
                padding: 15px;
                text-align: center;
                border-radius: 10px;
                font-weight: bold;
                font-size: 18px;
                margin: 5px 0px;
            ">
                🖨️ IMPRIMIR ETIQUETA
            </div>
        </a>
    """
    st.markdown(botao_html, unsafe_allow_html=True)

# --- NOVO PEDIDO ---
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
                st.success("Enviado para montagem!")
                st.rerun()

# --- MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Central de Montagem")
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
            
            st.write(f"**Total: R$ {t_real:.2f}**")
            
            c1, c2, c3, c4 = st.columns(4)
            
            if c1.button("✅ Concluir", key=f"f_{ped['id']}", disabled=trava_kg):
                df_pedidos.at[idx, 'status'] = "Concluído"
                df_pedidos.at[idx, 'total'] = t_real
                df_pedidos.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

            with c2:
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
