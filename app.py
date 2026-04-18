import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

st.set_page_config(page_title="Horta Vendas", layout="centered")

conn = st.connection("gsheets", type=GSheetsConnection)

# -------- MENU --------
menu = st.sidebar.radio("Menu", [
    "🛒 Novo Pedido",
    "🚜 Colheita",
    "📦 Montagem"
])

# -------- FUNÇÕES --------
def carregar_produtos():
    df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
    df.columns = [str(c).lower().strip() for c in df.columns]
    return df

def carregar_pedidos():
    return conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")

# -------- CONTROLE FORM --------
if "form_id" not in st.session_state:
    st.session_state.form_id = 0

f_id = st.session_state.form_id

# ---------------- NOVO PEDIDO ----------------
if menu == "🛒 Novo Pedido":
    st.header("🛒 Novo Pedido")

    nome = st.text_input("Cliente", key=f"cliente_{f_id}")
    endereco = st.text_input("Endereço", key=f"end_{f_id}")

    df_p = carregar_produtos()
    carrinho = []
    total = 0.0

    for _, row in df_p.iterrows():
        col1, col2, col3 = st.columns([2,1,1])

        col1.write(row["nome"])

        preco = float(row["preco"])
        col2.write(f"R$ {preco:.2f}")

        qtd = col3.number_input(
            "Qtd",
            min_value=0,
            step=1,
            key=f"qtd_{row['id']}_{f_id}"
        )

        if qtd > 0:
            sub = qtd * preco
            total += sub

            carrinho.append({
                "id": row["id"],
                "nome": row["nome"],
                "qtd": qtd,
                "preco": preco,
                "subtotal": sub
            })

    st.subheader(f"💰 Total: R$ {total:.2f}")

    if st.button("Salvar Pedido", key=f"btn_salvar_{f_id}"):
        if nome and carrinho:
            df = carregar_pedidos()

            novo = pd.DataFrame([{
                "id": int(datetime.now().timestamp()),
                "cliente": nome,
                "endereco": endereco,
                "itens": json.dumps(carrinho),
                "status": "Pendente",
                "data": datetime.now().strftime("%d/%m/%Y"),
                "total": total
            }])

            conn.update(worksheet="Pedidos", data=pd.concat([df, novo], ignore_index=True))

            st.session_state.form_id += 1
            st.success("Pedido salvo!")
            st.rerun()
        else:
            st.warning("Preencha nome e produtos!")

# ---------------- COLHEITA ----------------
elif menu == "🚜 Colheita":
    st.header("🚜 Colheita")

    df = carregar_pedidos()
    df = df[df["status"] == "Pendente"]

    resumo = {}

    for _, row in df.iterrows():
        itens = json.loads(row["itens"])
        for i in itens:
            resumo[i["nome"]] = resumo.get(i["nome"], 0) + i["qtd"]

    df_resumo = pd.DataFrame([
        {"Produto": k, "Quantidade": v} for k, v in resumo.items()
    ])

    st.dataframe(df_resumo, use_container_width=True)

# ---------------- MONTAGEM ----------------
elif menu == "📦 Montagem":
    st.header("📦 Montagem")

    df = carregar_pedidos()
    df = df[df["status"] == "Pendente"]

    for idx, row in df.iterrows():
        st.subheader(row["cliente"])

        itens = json.loads(row["itens"])
        total = 0.0

        for i in itens:
            col1, col2 = st.columns([2,1])

            valor = col2.number_input(
                label=i["nome"],
                value=float(i["subtotal"]),
                key=f"mont_{row['id']}_{i['id']}"
            )

            i["subtotal"] = valor

            col1.write(f"{i['nome']} x {i['qtd']}")
            total += valor

        st.write(f"Total: R$ {total:.2f}")

        colA, colB = st.columns(2)

        if colA.button("Salvar", key=f"salvar_{row['id']}"):
            df.at[idx, "itens"] = json.dumps(itens)
            df.at[idx, "status"] = "Montado"
            df.at[idx, "total"] = total

            conn.update(worksheet="Pedidos", data=df)
            st.success("Pedido atualizado!")
            st.rerun()

        if colB.button("Excluir", key=f"excluir_{row['id']}"):
            df = df.drop(idx)
            conn.update(worksheet="Pedidos", data=df)
            st.rerun()

        st.divider()