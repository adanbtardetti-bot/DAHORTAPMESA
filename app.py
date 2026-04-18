import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
from datetime import datetime

st.set_page_config(page_title="Horta Vendas", layout="centered")

conn = st.connection("gsheets", type=GSheetsConnection)

menu = st.sidebar.radio("Menu", [
    "Novo Pedido",
    "Colheita",
    "Montagem"
])

def carregar_produtos():
    df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
    df.columns = [str(c).lower().strip() for c in df.columns]
    return df

def carregar_pedidos():
    return conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")

# ---------------- NOVO PEDIDO ----------------
if menu == "Novo Pedido":
    st.header("Novo Pedido")

    nome = st.text_input("Cliente")
    endereco = st.text_input("Endereco")

    df_p = carregar_produtos()
    carrinho = []
    total = 0

    for _, row in df_p.iterrows():
        qtd = st.number_input(row["nome"], 0)

        if qtd > 0:
            preco = float(row["preco"])
            sub = qtd * preco
            total += sub

            carrinho.append({
                "id": row["id"],
                "nome": row["nome"],
                "qtd": qtd,
                "preco": preco,
                "subtotal": sub
            })

    st.write("Total:", total)

    if st.button("Salvar"):
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
        st.success("Salvo")

# ---------------- COLHEITA ----------------
elif menu == "Colheita":
    st.header("Colheita")

    df = carregar_pedidos()
    df = df[df["status"] == "Pendente"]

    resumo = {}

    for _, row in df.iterrows():
        itens = json.loads(row["itens"])
        for i in itens:
            resumo[i["nome"]] = resumo.get(i["nome"], 0) + i["qtd"]

    st.write(resumo)

# ---------------- MONTAGEM ----------------
elif menu == "Montagem":
    st.header("Montagem")

    df = carregar_pedidos()
    df = df[df["status"] == "Pendente"]

    for idx, row in df.iterrows():
        st.subheader(row["cliente"])

        itens = json.loads(row["itens"])
        total = 0

        for i in itens:
            valor = st.number_input(i["nome"], value=float(i["subtotal"]), key=str(row["id"]) + "_" + str(i["id"]))
            i["subtotal"] = valor
            total += valor

        st.write("Total:", total)

        if st.button("Salvar", key="s" + str(row["id"])):
            df.at[idx, "itens"] = json.dumps(itens)
            df.at[idx, "status"] = "Montado"
            df.at[idx, "total"] = total

            conn.update(worksheet="Pedidos", data=df)
            st.success("Atualizado")