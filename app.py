import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import json
import urllib.parse

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

# --- FUNÇÃO DE IMPRESSÃO (ESTRATÉGIA DE TEXTO PURO) ---
def disparar_impressao_rawbt(ped):
    status_pg = ped.get('pagamento', 'A Pagar')
    
    # Montando o texto sem acentos ou caracteres que travam emuladores
    # Usamos \n para quebra de linha
    linhas = [
        "--------------------------------",
        "        DA HORTA P/ MESA",
        "--------------------------------",
        f"{str(ped['cliente']).upper()}",
        f"{str(ped['endereco']).upper()}",
        "--------------------------------",
        f"TOTAL: R$ {float(ped['total']):.2f}",
        f"PAGAMENTO: {status_pg.upper()}",
        "--------------------------------",
        "\n\n\n" # Espaço final
    ]
    
    texto_final = "\n".join(linhas)
    
    # Codificação URL simples
    texto_url = urllib.parse.quote(texto_final)
    
    # Intent para o RawBT capturar como texto (S.text)
    # Adicionamos o parâmetro 'show=true' para o app abrir e mostrar o texto antes
    url_rawbt = f"intent:#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;S.text={texto_url};end;"
    
    botao_html = f"""
        <a href="{url_rawbt}" style="text-decoration: none;">
            <div style="
                background-color: #000000;
                color: white;
                padding: 18px;
                text-align: center;
                border-radius: 12px;
                font-weight: bold;
                font-size: 20px;
                border: 2px solid #28a745;
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
                st.rerun()

# --- MONTAGEM ---
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
                # Botão de impressão
                p_copy = ped.to_dict()
                p_copy['total'] = t_real
                disparar_impressao_rawbt(p_copy)

            if c3.button("✏️ Editar", key=f"e_{ped['id']}"):
                st.session_state.edit_data = ped.to_dict()
                df_pedidos = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()

            if col4_ex := c4.button("🗑️ Excluir", key=f"x_{ped['id']}"):
                df_pedidos = df_pedidos.drop(idx)
                conn.update(worksheet="Pedidos", data=df_pedidos)
                st.cache_data.clear()
                st.rerun()
