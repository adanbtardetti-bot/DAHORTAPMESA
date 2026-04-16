import streamlit as st
import pandas as pd
from datetime import datetime
import urllib.parse

st.set_page_config(page_title="Gestão Horta", layout="wide")

# Inicialização do Banco de Dados
if 'produtos' not in st.session_state:
    st.session_state.produtos = []
if 'pedidos' not in st.session_state:
    st.session_state.pedidos = []

# --- FUNÇÃO PARA LIMPAR CAMPOS DO PEDIDO ---
def limpar_pedido():
    st.session_state.nome_cliente = ""
    st.session_state.end_cliente = ""
    st.session_state.obs_cliente = ""
    for p in st.session_state.produtos:
        st.session_state[f"ped_{p['id']}"] = 0

menu = st.sidebar.radio("Menu", ["Novo Pedido", "Colheita", "Montagem/Expedição", "Estoque", "Financeiro", "Histórico"])

# --- TELA 1: NOVO PEDIDO ---
if menu == "Novo Pedido":
    st.header("🛒 Novo Pedido")
    nome = st.text_input("Nome do Cliente", key="nome_cliente")
    endereco = st.text_input("Endereço", key="end_cliente")
    obs = st.text_area("Observações", key="obs_cliente")
    
    st.subheader("Selecione os Produtos")
    itens_selecionados = []
    total_parcial = 0.0
    
    for p in st.session_state.produtos:
        col1, col2 = st.columns([3, 1])
        qtd = col1.number_input(f"{p['nome']} (R$ {p['preco']}/{p['tipo']})", min_value=0, step=1, key=f"ped_{p['id']}")
        if qtd > 0:
            subtotal = (qtd * p['preco']) if p['tipo'] == "Unidade" else 0.0
            total_parcial += subtotal
            itens_selecionados.append({
                "produto": p['nome'], "qtd": qtd, "tipo": p['tipo'], 
                "preco_unit": p['preco'], "subtotal": subtotal, "faltante": False
            })

    st.markdown(f"### 💰 Total Parcial (Unidades): R$ {total_parcial:.2f}")

    if st.button("💾 Salvar Pedido", use_container_width=True):
        if nome or endereco:
            novo_pedido = {
                "id": len(st.session_state.pedidos) + 1,
                "cliente": nome, "endereco": endereco,
                "itens": itens_selecionados, "status": "Pendente",
                "obs": obs, "data": datetime.now().strftime("%d/%m/%Y"),
                "total": total_parcial
            }
            st.session_state.pedidos.append(novo_pedido)
            st.success("✅ Pedido Salvo!")
            limpar_pedido()
            st.rerun()
        else:
            st.error("Preencha Nome ou Endereço!")

# --- TELA 3: MONTAGEM ---
elif menu == "Montagem/Expedição":
    st.header("📦 Montagem e Pesagem")
    pendentes = [p for p in st.session_state.pedidos if p['status'] == "Pendente"]
    
    for ped in pendentes:
        with st.expander(f"Pedido #{ped['id']} - {ped['cliente']}", expanded=True):
            total_pedido = 0
            for i, item in enumerate(ped['itens']):
                st.markdown(f"---")
                col_info, col_acao = st.columns([2, 1])
                is_faltante = col_acao.checkbox("Faltante", key=f"falt_{ped['id']}_{i}")
                item['faltante'] = is_faltante
                
                if not is_faltante:
                    if item['tipo'] == "KG":
                        # Campo de valor da balança agora aceita 'None' (vazio) por padrão
                        val_lido = col_info.number_input(f"Valor Balança R$ ({item['produto']})", 
                                                        value=None, placeholder="Digite o valor...", 
                                                        key=f"val_{ped['id']}_{i}")
                        item['subtotal'] = val_lido if val_lido else 0.0
                    else:
                        col_info.write(f"✅ {item['produto']} ({item['qtd']} un) - R$ {item['subtotal']:.2f}")
                    total_pedido += item['subtotal']
            
            ped['total'] = total_pedido
            st.subheader(f"Total: R$ {total_pedido:.2f}")
            
            c1, c2 = st.columns(2)
            if c1.button(f"✅ Finalizar #{ped['id']}", use_container_width=True):
                ped['status'] = "Concluído"
                st.rerun()
            
            # --- LAYOUT MELHORADO DA ETIQUETA ---
            # Comandos básicos de formatação para impressoras térmicas (simulados via texto)
            linha = "------------------------------"
            txt_etiqueta = (
                f"       HORTA DA MESA\n"
                f"{linha}\n"
                f"PEDIDO: #{ped['id']}\n"
                f"CLIENTE: {ped['cliente']}\n"
                f"END: {ped['endereco']}\n"
                f"{linha}\n"
            )
            for it in ped['itens']:
                if not it['faltante']:
                    txt_etiqueta += f"{it['qtd']}x {it['produto']} -> R$ {it['subtotal']:.2f}\n"
            
            txt_etiqueta += f"{linha}\nTOTAL: R$ {ped['total']:.2f}\n"
            if ped['obs']: txt_etiqueta += f"OBS: {ped['obs']}\n"
            txt_etiqueta += f"\n   Obrigado pela compra!\n\n\n"
            
            texto_codificado = urllib.parse.quote(txt_etiqueta)
            link_rawbt = f"intent://{texto_codificado}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
            c2.link_button("🖨️ Imprimir Etiqueta", link_rawbt, use_container_width=True)

# --- OUTRAS TELAS MANTIDAS ---
elif menu == "Estoque":
    st.header("⚙️ Estoque")
    nome_p = st.text_input("Nome do Produto")
    preco_p = st.number_input("Preço", 0.0)
    tipo_p = st.selectbox("Tipo", ["Unidade", "KG"])
    if st.button("Adicionar"):
        st.session_state.produtos.append({"id": len(st.session_state.produtos)+1, "nome": nome_p, "preco": preco_p, "tipo": tipo_p, "ativo": True})
        st.rerun()
    st.write(pd.DataFrame(st.session_state.produtos))

elif menu == "Histórico":
    st.header("📜 Histórico")
    for i, ped in enumerate(st.session_state.pedidos):
        with st.container(border=True):
            col_id, col_info, col_del = st.columns([1, 4, 1])
            col_id.write(f"#{ped['id']}")
            col_info.write(f"**{ped['cliente']}** - {ped['data']} - R$ {ped['total']:.2f} ({ped['status']})")
            if col_del.button("🗑️", key=f"del_{i}"):
                st.session_state.pedidos.pop(i)
                st.rerun()

elif menu == "Colheita":
    st.header("🌿 Colheita")
    consolidado = {}
    for ped in st.session_state.pedidos:
        if ped['status'] == "Pendente":
            for it in ped['itens']:
                consolidado[it['produto']] = consolidado.get(it['produto'], 0) + it['qtd']
    for k, v in consolidado.items():
        st.info(f"{k}: {v}")

elif menu == "Financeiro":
    st.header("💰 Financeiro")
    total = sum(p['total'] for p in st.session_state.pedidos if p['status'] == "Concluído")
    st.metric("Total Faturado", f"R$ {total:.2f}")
