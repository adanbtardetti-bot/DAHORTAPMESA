import streamlit as st
import pandas as pd
from datetime import datetime
import urllib.parse

st.set_page_config(page_title="Gestão Horta", layout="wide")

# Inicialização do Banco de Dados Simulado
if 'produtos' not in st.session_state:
    st.session_state.produtos = [
        {"id": 1, "nome": "Alface Crespa", "preco": 3.50, "tipo": "Unidade", "ativo": True},
        {"id": 2, "nome": "Tomate", "preco": 8.90, "tipo": "KG", "ativo": True},
    ]
if 'pedidos' not in st.session_state:
    st.session_state.pedidos = []

menu = st.sidebar.radio("Menu", ["Novo Pedido", "Colheita", "Montagem/Expedição", "Estoque", "Financeiro", "Histórico"])

# --- TELA 1: NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    nome = st.text_input("Nome do Cliente")
    endereco = st.text_input("Endereço")
    obs = st.text_area("Observações")
    pago = st.checkbox("Pedido Pago")
    
    st.subheader("Selecione os Produtos")
    itens_selecionados = []
    for p in st.session_state.produtos:
        if p['ativo']:
            col1, col2 = st.columns([3, 1])
            qtd = col1.number_input(f"{p['nome']} (R$ {p['preco']}/{p['tipo']})", min_value=0, step=1, key=f"ped_{p['id']}")
            if qtd > 0:
                # Valor inicial: Unidade já soma, KG começa com 0 e espera pesagem
                valor_inicial = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
                itens_selecionados.append({
                    "produto": p['nome'], 
                    "qtd": qtd, 
                    "tipo": p['tipo'], 
                    "preco_unit": p['preco'],
                    "subtotal": valor_inicial,
                    "faltante": False
                })

    if st.button("💾 Salvar Pedido", use_container_width=True):
        if nome or endereco:
            novo_pedido = {
                "id": len(st.session_state.pedidos) + 1,
                "cliente": nome,
                "endereco": endereco,
                "itens": itens_selecionados,
                "status": "Pendente",
                "pago": pago,
                "obs": obs,
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "total": sum(i['subtotal'] for i in itens_selecionados)
            }
            st.session_state.pedidos.append(novo_pedido)
            st.success("Pedido registrado!")
        else:
            st.error("Preencha Nome ou Endereço!")

# --- TELA 3: MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Montagem e Pesagem")
    pendentes = [p for p in st.session_state.pedidos if p['status'] == "Pendente"]
    
    if not pendentes:
        st.info("Nenhum pedido pendente.")
    
    for ped in pendentes:
        with st.expander(f"Pedido #{ped['id']} - {ped['cliente']}", expanded=True):
            st.write(f"📍 {ped['endereco']}")
            total_pedido = 0
            
            for i, item in enumerate(ped['itens']):
                st.markdown(f"---")
                col_info, col_acao = st.columns([2, 1])
                
                # Regra: Se faltante, não soma nada
                is_faltante = col_acao.checkbox("Item Faltante", key=f"falt_{ped['id']}_{i}")
                item['faltante'] = is_faltante
                
                if is_faltante:
                    col_info.warning(f"❌ {item['produto']} (Faltante)")
                    item['subtotal'] = 0
                else:
                    if item['tipo'] == "KG":
                        val_lido = col_info.number_input(f"Valor Balança R$ ({item['produto']})", value=float(item['subtotal']), key=f"val_{ped['id']}_{i}")
                        item['subtotal'] = val_lido
                    else:
                        col_info.write(f"✅ {item['produto']} - {item['qtd']} un (R$ {item['subtotal']:.2f})")
                    
                    total_pedido += item['subtotal']
            
            ped['total'] = total_pedido
            st.subheader(f"Total: R$ {total_pedido:.2f}")
            
            c1, c2 = st.columns(2)
            if c1.button(f"✅ Pedido Pronto #{ped['id']}", use_container_width=True):
                ped['status'] = "Concluído"
                st.rerun()
            
            # Botão de Impressão via Link Intent (RawBT)
            texto_etiqueta = f"PEDIDO: {ped['id']}\nCLIENTE: {ped['cliente']}\nEND: {ped['endereco']}\nTOTAL: R${ped['total']:.2f}\n{ped['obs']}"
            texto_codificado = urllib.parse.quote(texto_etiqueta)
            link_rawbt = f"intent://{texto_codificado}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
            c2.link_button("🖨️ Imprimir Etiqueta", link_rawbt, use_container_width=True)

# --- TELA: HISTÓRICO ---
elif menu == "Histórico":
    st.header("📜 Histórico Detalhado")
    for i, ped in enumerate(st.session_state.pedidos):
        cor_status = "green" if ped['status'] == "Concluído" else "orange"
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 4, 1])
            c1.write(f"#{ped['id']}")
            c2.markdown(f"**{ped['cliente']}** - :{cor_status}[{ped['status']}]")
            if c3.button("🗑️", key=f"del_{i}"):
                st.session_state.pedidos.pop(i)
                st.rerun()
            
            st.write(f"Data: {ped['data']} | Total: R$ {ped['total']:.2f}")
            detalhes = ", ".join([f"{it['qtd']}x {it['produto']}" for it in ped['itens'] if not it['faltante']])
            st.caption(f"Itens: {detalhes}")

# --- OUTRAS TELAS (SIMPLIFICADAS PARA O CÓDIGO NÃO FICAR GIGANTE) ---
elif menu == "Colheita":
    st.header("🌿 Colheita")
    consolidado = {}
    for ped in st.session_state.pedidos:
        if ped['status'] == "Pendente":
            for it in ped['itens']:
                consolidado[it['produto']] = consolidado.get(it['produto'], 0) + it['qtd']
    for k, v in consolidado.items():
        st.info(f"{k}: {v}")

elif menu == "Estoque":
    st.header("⚙️ Estoque")
    nome_p = st.text_input("Nome do Produto")
    preco_p = st.number_input("Preço", 0.0)
    tipo_p = st.selectbox("Tipo", ["Unidade", "KG"])
    if st.button("Adicionar"):
        st.session_state.produtos.append({"id": len(st.session_state.produtos)+1, "nome": nome_p, "preco": preco_p, "tipo": tipo_p, "ativo": True})
        st.rerun()
    st.write(pd.DataFrame(st.session_state.produtos))

elif menu == "Financeiro":
    st.header("💰 Financeiro")
    total = sum(p['total'] for p in st.session_state.pedidos if p['status'] == "Concluído")
    st.metric("Total Faturado", f"R$ {total:.2f}")
