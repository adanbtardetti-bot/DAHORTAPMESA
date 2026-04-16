import streamlit as st
import pandas as pd
from datetime import datetime

# Configuração da Página
st.set_page_config(page_title="Gestão Horta", layout="wide")

# Simulação de Banco de Dados (Em produção, usar st.connection ou banco real)
if 'produtos' not in st.session_state:
    st.session_state.produtos = [
        {"id": 1, "nome": "Alface", "preco": 3.50, "tipo": "Unidade", "ativo": True},
        {"id": 2, "nome": "Tomate", "preco": 8.90, "tipo": "KG", "ativo": True},
    ]
if 'pedidos' not in st.session_state:
    st.session_state.pedidos = []

# --- NAVEGAÇÃO ---
menu = st.sidebar.radio("Menu", ["Novo Pedido", "Colheita", "Montagem/Expedição", "Estoque", "Financeiro", "Histórico"])

# --- TELA 1: NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    nome = st.text_input("Nome do Cliente")
    endereco = st.text_input("Endereço")
    obs = st.text_area("Observações")
    pago = st.checkbox("Pedido já está pago?")
    
    st.subheader("Produtos")
    itens_selecionados = []
    for p in st.session_state.produtos:
        if p['ativo']:
            col1, col2 = st.columns([3, 1])
            qtd = col1.number_input(f"{p['nome']} (R$ {p['preco']}/{p['tipo']})", min_value=0, step=1, key=f"p_{p['id']}")
            if qtd > 0:
                valor_inicial = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
                itens_selecionados.append({
                    "produto": p['nome'], 
                    "qtd": qtd, 
                    "tipo": p['tipo'], 
                    "preco_unit": p['preco'],
                    "subtotal": valor_inicial,
                    "faltante": False
                })

    if st.button("Salvar Pedido"):
        if nome or endereco:
            novo_pedido = {
                "id": len(st.session_state.pedidos) + 1,
                "cliente": nome,
                "endereco": endereco,
                "itens": itens_selecionados,
                "status": "Pendente",
                "pago": pago,
                "obs": obs,
                "data": datetime.now().strftime("%d/%m/%Y"),
                "total": sum(i['subtotal'] for i in itens_selecionados)
            }
            st.session_state.pedidos.append(novo_pedido)
            st.success("Pedido salvo com sucesso!")
        else:
            st.error("Preencha pelo menos o Nome ou o Endereço.")

# --- TELA 2: PAINEL DE COLHEITA ---
elif menu == "Colheita":
    st.header("🌿 Lista de Colheita do Dia")
    consolidado = {}
    for ped in st.session_state.pedidos:
        if ped['status'] == "Pendente":
            for item in ped['itens']:
                nome_p = item['produto']
                consolidado[nome_p] = consolidado.get(nome_p, 0) + item['qtd']
    
    if consolidado:
        for prod, total in consolidado.items():
            st.info(f"**{prod}**: {total} unidades/itens")
    else:
        st.write("Nada para colher hoje.")

# --- TELA 3: MONTAGEM (Expedição) ---
elif menu == "Montagem/Expedição":
    st.header("📦 Montagem de Pedidos")
    pendentes = [p for p in st.session_state.pedidos if p['status'] == "Pendente"]
    
    for idx, ped in enumerate(pendentes):
        with st.expander(f"Pedido #{ped['id']} - {ped['cliente']}"):
            st.write(f"📍 {ped['endereco']}")
            total_pedido = 0
            
            for i, item in enumerate(ped['itens']):
                col_item, col_val = st.columns([2, 2])
                if item['tipo'] == "KG":
                    valor_balanca = col_val.number_input(f"Valor R$ (Balança) - {item['produto']}", key=f"bal_{ped['id']}_{i}")
                    if valor_balanca > 0:
                        item['subtotal'] = valor_balanca
                        item['peso_calc'] = valor_balanca / item['preco_unit']
                
                faltante = col_item.checkbox("Faltante", key=f"fal_{ped['id']}_{i}")
                item['faltante'] = faltante
                if not faltante:
                    total_pedido += item['subtotal']
            
            ped['total'] = total_pedido
            st.write(f"**Total Atual: R$ {total_pedido:.2f}**")
            
            if st.button(f"Finalizar Pedido #{ped['id']}", key=f"btn_{ped['id']}"):
                ped['status'] = "Concluído"
                st.rerun()
            
            # Botão de Impressão (Simulação RawBT)
            txt_print = f"PEDIDO {ped['id']}\n{ped['cliente']}\nTotal: {ped['total']}"
            link_rawbt = f"intent://{txt_print}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
            st.markdown(f"[Print Etiqueta (RawBT)]({link_rawbt})")

# --- TELA 4: ESTOQUE ---
elif menu == "Estoque":
    st.header("⚙️ Gerenciar Produtos")
    with st.form("add_prod"):
        n = st.text_input("Nome do Produto")
        p = st.number_input("Preço", min_value=0.0)
        t = st.selectbox("Tipo", ["Unidade", "KG"])
        if st.form_submit_button("Adicionar"):
            st.session_state.produtos.append({"id": len(st.session_state.produtos)+1, "nome": n, "preco": p, "tipo": t, "ativo": True})
    
    st.write(pd.DataFrame(st.session_state.produtos))

# --- TELA 5: FINANCEIRO & HISTÓRICO ---
elif menu == "Financeiro":
    st.header("💰 Resumo Financeiro")
    concluidos = [p for p in st.session_state.pedidos if p['status'] == "Concluído"]
    total_fat = sum(p['total'] for p in concluidos)
    st.metric("Total Faturado", f"R$ {total_fat:.2f}")

elif menu == "Histórico":
    st.header("📜 Histórico de Pedidos")
    st.table(st.session_state.pedidos)
