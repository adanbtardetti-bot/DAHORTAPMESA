import streamlit as st
import pandas as pd
from datetime import datetime

# Configuração simples
st.set_page_config(page_title="Horta Gestão Fácil", layout="wide")

# Link da sua planilha (o mesmo que você me mandou)
# Vamos converter o link para o formato de exportação CSV que o Pandas lê fácil
sheet_id = "1rTl5MfvAyN46IGLqeo6_UiPhMv8vVxog4Q7GLI9rKvc"
url_produtos = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=Produtos"

st.title("🌿 Gestão Horta - Modo Simples")

# Função para ler os dados sem precisar de Google Cloud
def carregar_produtos():
    try:
        return pd.read_csv(url_produtos).dropna(how="all")
    except:
        return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "ativo"])

# Criar um "estoque" na memória do app para começar
if 'estoque' not in st.session_state:
    st.session_state.estoque = carregar_produtos()

# --- TELA DE CADASTRO ---
st.subheader("➕ Cadastrar Produto")
with st.form("cad_novo", clear_on_submit=True):
    nome = st.text_input("Nome do Produto")
    preco = st.number_input("Preço", min_value=0.0)
    if st.form_submit_button("Salvar no App"):
        if nome:
            novo_id = len(st.session_state.estoque) + 1
            novo_item = pd.DataFrame([{"id": novo_id, "nome": nome, "preco": preco, "tipo": "Unidade", "ativo": True}])
            st.session_state.estoque = pd.concat([st.session_state.estoque, novo_item], ignore_index=True)
            st.success(f"{nome} adicionado!")
        else:
            st.error("Digite o nome!")

st.divider()

# --- MOSTRAR O QUE TEM ---
st.subheader("📦 Itens no Estoque")
st.table(st.session_state.estoque)

# --- BOTÃO DE EMERGÊNCIA ---
st.info("Nota: Como estamos sem a chave do Google Cloud, os dados ficam salvos enquanto o app estiver aberto. Para salvar definitivo na planilha, precisamos daquela 'Service Account'.")

if st.button("Explicação sobre o Google Cloud"):
    st.write("""
    Amigo, para o Google deixar o app escrever na sua planilha sem você estar lá teclando, 
    ele exige que o app se identifique. Se você não consegue criar o projeto no Google Cloud, 
    tente pedir para quem fez o antigo apenas o **Arquivo JSON da Conta de Serviço**. 
    Com esse arquivo em mãos, eu resolvo tudo pra você em 10 segundos!
    """)
