import streamlit as st
import pandas as pd
from datetime import datetime
import urllib.parse

st.set_page_config(page_title="Gestão Horta", layout="wide")

# --- INICIALIZAÇÃO DO BANCO DE DADOS ---
if 'produtos' not in st.session_state:
    st.session_state.produtos = [
        {"id": 1, "nome": "Alface Crespa", "preco": 3.50, "tipo": "Unidade", "ativo": True},
        {"id": 2, "nome": "Tomate", "preco": 8.90, "tipo": "KG", "ativo": True},
    ]
if 'pedidos' not in st.session_state:
    st.session_state.pedidos = []

# --- FUNÇÃO PARA LIMPAR CAMPOS DO PEDIDO ---
def limpar_campos_pedido():
    st.session_state.nome_cliente = ""
    st.session_state.end_cliente = ""
    st.session_state.obs_cliente = ""
    for p in st.session_state.produtos:
        if f"ped_{p['id']}" in st.session_state:
            st.session_state[f"ped_{p['id']}"] = 0

menu = st.sidebar.radio("Navegação", ["Novo Pedido", "Colheita", "Montagem/Expedição", "Estoque", "Financeiro", "Histórico"])

# --- TELA 1: NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    nome = st.text_input("Nome do Cliente", key="nome_cliente")
    endereco = st.text_input("Endereço", key="end_cliente")
    obs = st.text_area("Observações", key="obs_cliente")
    
    st.subheader("Selecione os Produtos")
    itens_selecionados = []
    total_parcial_venda = 0.0
    
    for p in st.session_state.produtos:
        if p.get('ativo', True):
            col1, col2 = st.columns([3, 1])
            qtd = col1.number_input(f"{p['nome']} (R$ {p['preco']}/{p['tipo']})", min_value=0, step=1, key=f"ped_{p['id']}")
            if qtd > 0:
                # Regra: Só soma no total agora se for Unidade
                valor_item = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
                total_parcial_venda += valor_item
                itens_selecionados.append({
                    "produto": p['nome'], "qtd": qtd, "tipo": p['tipo'], 
                    "preco_unit": p['preco'], "subtotal": valor_item, "faltante": False
                })

    st.markdown(f"### 💰 Total Parcial (Unidades): R$ {total_parcial_venda:.2f}")

    if st.button("💾 Salvar Pedido", use_container_width=True):
        if nome or endereco:
            novo_pedido = {
                "id": len(st.session_state.pedidos) + 1,
                "cliente": nome, "endereco": endereco,
                "itens": itens_selecionados, "status": "Pendente",
                "obs": obs, "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "total": total_parcial_venda
            }
            st.session_state.pedidos.append(novo_pedido)
            st.success("✅ Pedido registrado com sucesso!")
            limpar_campos_pedido()
            st.rerun()
        else:
            st.error("Erro: Preencha pelo menos o Nome ou o Endereço!")

# --- TELA 3: MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Montagem e Pesagem")
    pendentes = [p for p in st.session_state.pedidos if p['status'] == "Pendente"]
    
    if not pendentes:
        st.info("Não há pedidos pendentes para montagem.")

    for ped in pendentes:
        with st.expander(f"Pedido #{ped['id']} - {ped['cliente']}", expanded=True):
            st.write(f"📍 Endereço: {ped['endereco']}")
            total_final_pedido = 0.0
            
            for i, item in enumerate(ped['itens']):
                st.markdown("---")
                col_info, col_acao = st.columns([2, 1])
                
                faltante = col_acao.checkbox("Item Faltante", key=f"falt_{ped['id']}_{i}")
                item['faltante'] = faltante
                
                if not faltante:
                    if item['tipo'] == "KG":
                        # Campo vazio para facilitar digitação
                        val_balanca = col_info.number_input(f"Valor Balança R$ ({item['produto']})", 
                                                           value=None, placeholder="Digite o valor lido...", 
                                                           key=f"val_{ped['id']}_{i}")
                        item['subtotal'] = val_balanca if val_balanca else 0.0
                    else:
                        col_info.write(f"✅ {item['produto']} ({item['qtd']} un) - R$ {item['subtotal']:.2f}")
                    
                    total_final_pedido += item['subtotal']
                else:
                    col_info.warning(f"❌ {item['produto']} marcado como FALTANTE")
                    item['subtotal'] = 0.0

            ped['total'] = total_final_pedido
            st.subheader(f"Total do Pedido: R$ {total_final_pedido:.2f}")
            
            c1, c2 = st.columns(2)
            if c1.button(f"✅ Finalizar Pedido #{ped['id']}", use_container_width=True):
                ped['status'] = "Concluído"
                st.rerun()
            
            # --- ETIQUETA FORMATADA ---
            linha = "-" * 30
            txt_etiq = (
                f"       HORTA DA MESA\n"
                f"{linha}\n"
                f"PEDIDO: #{ped['id']}\n"
                f"CLIENTE: {ped['cliente']}\n"
                f"END: {ped['endereco']}\n"
                f"{linha}\n"
            )
            for it in ped['itens']:
                if not it['faltante']:
                    txt_etiq += f"{it['qtd']}x {it['produto']} -> R$ {it['subtotal']:.2f}\n"
            txt_etiq += f"{linha}\nTOTAL: R$ {ped['total']:.2f}\n"
            if ped['obs']: txt_etiq += f"OBS: {ped['obs']}\n"
            txt_etiq += f"\n   Obrigado pela compra!\n\n\n"
            
            link_rawbt = f"intent://{urllib.parse.quote(txt_etiq)}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
            c2.link_button("🖨️ Imprimir Etiqueta", link_rawbt, use_container_width=True)

# --- TELA 4: GESTÃO DE ESTOQUE ---
elif menu == "Estoque":
    st.header("⚙️ Gestão de Produtos")
    
    with st.form("form_produto", clear_on_submit=True):
        st.subheader("Adicionar Novo Produto")
        n = st.text_input("Nome do Produto")
        p = st.number_input("Preço Base (R$)", min_value=0.0, format="%.2f")
        t = st.selectbox("Tipo de Venda", ["Unidade", "KG"])
        if st.form_submit_button("➕ Cadastrar Produto"):
            if n:
                st.session_state.produtos.append({"id": len(st.session_state.produtos)+1, "nome": n, "preco": p, "tipo": t, "ativo": True})
                st.success(f"{n} adicionado!")
                st.rerun()

    st.subheader("Produtos Ativos")
    if st.session_state.produtos:
        df_prod = pd.DataFrame(st.session_state.produtos)
        # Interface simples para excluir
        for i, prod in enumerate(st.session_state.produtos):
            col_p, col_btn = st.columns([4, 1])
            col_p.write(f"**{prod['nome']}** - R$ {prod['preco']}/{prod['tipo']}")
            if col_btn.button("🗑️", key=f"del_prod_{i}"):
                st.session_state.produtos.pop(i)
                st.rerun()
    else:
        st.info("Nenhum produto cadastrado.")

# --- TELA 5: FINANCEIRO ---
elif menu == "Financeiro":
    st.header("💰 Relatório Financeiro")
    concluidos = [p for p in st.session_state.pedidos if p['status'] == "Concluído"]
    
    if not concluidos:
        st.warning("Ainda não existem vendas concluídas para o relatório.")
    else:
        # Resumo no Topo
        total_dia = sum(p['total'] for p in concluidos)
        st.metric("Faturamento Total", f"R$ {total_dia:.2f}")
        
        st.markdown("---")
        st.subheader("📦 Detalhe por Item Vendido")
        
        resumo = {}
        for ped in concluidos:
            for it in ped['itens']:
                if not it['faltante']:
                    nome = it['produto']
                    if nome not in resumo:
                        resumo[nome] = {"qtd": 0, "valor": 0.0, "tipo": it['tipo']}
                    resumo[nome]["qtd"] += it['qtd']
                    resumo[nome]["valor"] += it['subtotal']
        
        # Criar tabela de resumo
        lista_resumo = []
        for prod, dados in resumo.items():
            lista_resumo.append({
                "Produto": prod,
                "Quantidade Total": f"{dados['qtd']} ({dados['tipo']})",
                "Valor Total (R$)": f"R$ {dados['valor']:.2f}"
            })
        
        st.table(pd.DataFrame(lista_resumo))

# --- TELA 6: HISTÓRICO ---
elif menu == "Histórico":
    st.header("📜 Histórico de Pedidos")
    if not st.session_state.pedidos:
        st.info("Nenhum pedido no histórico.")
    else:
        for i, ped in enumerate(st.session_state.pedidos):
            with st.container(border=True):
                c1, c2, c3 = st.columns([1, 4, 1])
                c1.write(f"#{ped['id']}")
                status_cor = "green" if ped['status'] == "Concluído" else "blue"
                c2.markdown(f"**{ped['cliente']}** - {ped['data']} - :{status_cor}[{ped['status']}]")
                if c3.button("🗑️", key=f"del_ped_{i}"):
                    st.session_state.pedidos.pop(i)
                    st.rerun()
                st.write(f"Total: R$ {ped['total']:.2f} | Endereço: {ped['endereco']}")
                # Mostra mini lista de itens
                txt_itens = ", ".join([f"{it['qtd']}x {it['produto']}" for it in ped['itens'] if not it['faltante']])
                st.caption(f"Itens entregues: {txt_itens}")

# --- TELA 2: COLHEITA (Logística) ---
elif menu == "Colheita":
    st.header("🌿 Resumo para Colheita")
    pendentes = [p for p in st.session_state.pedidos if p['status'] == "Pendente"]
    
    colheita = {}
    for ped in pendentes:
        for it in ped['itens']:
            nome = it['produto']
            colheita[nome] = colheita.get(nome, 0) + it['qtd']
            
    if colheita:
        for prod, qtd in colheita.items():
            st.info(f"**{prod}**: colher {qtd} unidades/itens")
    else:
        st.success("Tudo colhido por enquanto!")
