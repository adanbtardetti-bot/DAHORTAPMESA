# --- ABA 1: NOVO PEDIDO (COM LIMPEZA AUTOMÁTICA) ---
with tab1:
    st.header("🛒 Novo Pedido")
    
    # 1. Função para resetar os campos (limpa a memória do navegador)
    def limpar_formulario():
        for chave in st.session_state.keys():
            if chave.startswith("new_") or chave.startswith("q_") or chave.startswith("inp_"):
                del st.session_state[chave]

    # 2. IDENTIFICAÇÃO NO TOPO
    col_cli1, col_cli2 = st.columns(2)
    # Usamos o 'key' para o session_state conseguir limpar depois
    c_nome = col_cli1.text_input("NOME DO CLIENTE", key="new_nome").upper()
    c_end = col_cli2.text_input("ENDEREÇO", key="new_end").upper()
    c_obs = st.text_area("OBSERVAÇÕES (Troco, etc)", key="new_obs").upper()
    c_pago = st.checkbox("PAGO ANTECIPADO", key="new_pago")

    st.divider()
    
    # 3. SELEÇÃO DE PRODUTOS E SOMA REAL-TIME
    st.subheader("Selecione os Produtos")
    itens_atuais = []
    soma_venda = 0.0
    
    if not df_produtos.empty:
        p_ativos = df_produtos[df_produtos['status'].astype(str).str.lower() == 'ativo']
        c_p1, c_p2 = st.columns(2)
        
        for i, (_, p) in enumerate(p_ativos.iterrows()):
            alvo = c_p1 if i % 2 == 0 else c_p2
            # IMPORTANTE: o key aqui garante que o número volte para 0
            qtd = alvo.number_input(f"{p['nome']} (R$ {p['preco']})", min_value=0, step=1, key=f"inp_{p['id']}")
            
            if qtd > 0:
                preco_f = float(str(p['preco']).replace(',', '.'))
                # Se for KG, o subtotal é 0 até a montagem
                sub = 0.0 if p['tipo'] == "KG" else (qtd * preco_f)
                itens_atuais.append({"nome": p['nome'], "qtd": qtd, "tipo": p['tipo'], "subtotal": sub})
                soma_venda += sub
    
    st.markdown(f"## 💰 TOTAL ESTIMADO: R$ {soma_venda:.2f}")

    # 4. BOTÃO SALVAR COM LÓGICA DE LIMPEZA
    if st.button("✅ SALVAR PEDIDO", use_container_width=True):
        if (c_nome or c_end) and itens_atuais:
            try:
                # Gerar ID
                prox_id = int(df_pedidos['id'].max()) + 1 if not df_pedidos.empty else 1
                
                novo_ped = pd.DataFrame([{
                    "id": prox_id, "cliente": c_nome, "endereco": c_end, "obs": c_obs,
                    "itens": json.dumps(itens_atuais), "status": "Pendente",
                    "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0,
                    "pagamento": "Pago" if c_pago else "A Pagar"
                }])
                
                # Salvar no Google Sheets
                df_final = pd.concat([df_pedidos, novo_ped], ignore_index=True)
                conn.update(worksheet="Pedidos", data=df_final)
                
                st.success("Pedido Gravado!")
                
                # EXECUTA A LIMPEZA DOS CAMPOS
                st.cache_data.clear()
                limpar_formulario() # Apaga os valores salvos no navegador
                st.rerun()          # Recarrega a página com tudo vazio
                
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")
        else:
            st.warning("Preencha Nome ou Endereço e selecione pelo menos um produto!")
