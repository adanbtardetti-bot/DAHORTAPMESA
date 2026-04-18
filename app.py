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
    "📦 Montagem",
    "📅 Histórico",
    "📊 Financeiro",
    "📦 Estoque"
])

# -------- FUNÇÕES --------
def carregar_produtos():
    df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
    df.columns = [str(c).lower().strip() for c in df.columns]
    return df[df['status'].astype(str).str.lower() != 'oculto']

def carregar_pedidos():
    return conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")

# -------- NOVO PEDIDO --------
if menu == "🛒 Novo Pedido":
    st.header("🛒 Novo Pedido")

    if 'form_id' not in st.session_state:
        st.session_state.form_id = 0

    f_id = st.session_state.form_id

    nome = st.text_input("Cliente", key=f"n_{f_id}")
    endereco = st.text_input("Endereço", key=f"e_{f_id}")
    pago = st.toggle("Pago?", key=f"p_{f_id}")
    obs = st.text_area("Observações", key=f"o_{f_id}")

    st.divider()

    df_p = carregar_produtos()
    carrinho = []
    total = 0

    for _, row in df_p.iterrows():
        col1, col2, col3 = st.columns([2,1,1])

        col1.write(row["nome"])

        tipo = row["tipo"]
        preco = float(row["preco"])

        if tipo == "KG":
            col2.caption("PESAGEM")
        else:
            col2.write(f"R$ {preco:.2f}")

        qtd = col3.number_input("qtd", 0, key=f"{row['id']}_{f_id}")

        if qtd > 0:
            sub = 0 if tipo == "KG" else qtd * preco
            total += sub

            carrinho.append({
                "id": row["id"],
                "nome": row["nome"],
                "qtd": qtd,
                "preco": preco,
                "subtotal": sub,
                "tipo": tipo
            })

    st.subheader(f"Total: R$ {total:.2f}")

    if st.button("Salvar Pedido"):
        df = carregar_pedidos()

        novo = pd.DataFrame([{
            "id": int(datetime.now().timestamp()),
            "cliente": nome,
            "endereco": endereco,
            "itens": json.dumps(carrinho),
            "status": "Pendente",
            "data": datetime.now().strftime("%d/%m/%Y"),
            "total_estimado": total,
            "total_final": total,
            "pagamento": "PAGO" if pago else "A PAGAR",
            "obs": obs
        }])

        conn.update(worksheet="Pedidos", data=pd.concat([df, novo], ignore_index=True))

        st.session_state.form_id += 1
        st.rerun()

# -------- COLHEITA --------
elif menu == "🚜 Colheita":
    st.header("🚜 Colheita")

    df = carregar_pedidos()
    df = df[df["status"] == "Pendente"]

    resumo = {}

    for _, row in df.iterrows():
        itens = json.loads(row["itens"])

        for i in itens:
            resumo[i["nome"]] = resumo.get(i["nome"], 0) + i["qtd"]

    st.dataframe(pd.DataFrame([
        {"Produto": k, "Qtd": v} for k,v in resumo.items()
    ]))

# -------- MONTAGEM --------
elif menu == "📦 Montagem":
    st.header("📦 Montagem")

    df = carregar_pedidos()
    df = df[df["status"] == "Pendente"]

    for idx, row in df.iterrows():
        st.subheader(row["cliente"])

        itens = json.loads(row["itens"])
        total = 0

        for i in itens:
            col1, col2 = st.columns([2,1])

            if i["tipo"] == "KG":
                valor = col2.number_input(
                    f"{i['nome']}",
                    value=float(i["subtotal"]),
                    key=f"{row['id']}_{i['id']}"
                )
                i["subtotal"] = valor
            else:
                valor = i["subtotal"]
                col2.write(f"{valor:.2f}")

            col1.write(f"{i['nome']} x {i['qtd']}")
            total += float(i["subtotal"])

        st.write(f"Total: R$ {total:.2f}")

        colA, colB, colC = st.columns(3)

        if colA.button("Salvar", key=f"s_{row['id']}"):
            df.at[idx, "itens"] = json.dumps(itens)
            df.at[idx, "total_final"] = total
            df.at[idx, "status"] = "Mont