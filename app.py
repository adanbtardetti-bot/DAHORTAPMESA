import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
import urllib.parse
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Gestão", layout="centered")
conn = st.connection("gsheets", type=GSheetsConnection)

def carregar(aba):
    df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
    df.columns = [str(c).lower().strip() for c in df.columns]
    return df

df_p = carregar("Produtos")
df_v = carregar("Pedidos")

# --- MENU IGUAL AO EXEMPLO ---
aba = st.tabs(["🛒 Vendas", "🚜 Colheita", "⚖️ Montagem", "📦 Estoque", "📊 Financeiro", "🕒 Histórico"])

# --- 1. VENDAS (IGUAL À FOTO: LISTA DE PRODUTOS + QTD) ---
with aba[0]:
    st.subheader("Novo Pedido")
    nome = st.text_input("Cliente").upper()
    ende = st.text_input("Endereço").upper()
    
    venda_it = []
    for _, r in df_p[df_p['status'] == 'ativo'].iterrows():
        c1, c2 = st.columns([3, 1])
        # Organização: Nome e Preço na esquerda, seletor na direita
        c1.write(f"**{r['nome']}**\nR$ {r['preco']}")
        qtd = c2.number_input("", min_value=0, step=1, key=f"v{r['id']}")
        if qtd > 0:
            p_u = float(str(r['preco']).replace(',', '.'))
            sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
            venda_it.append({"nome": r['nome'], "qtd": qtd, "tipo": r['tipo'], "subtotal": sub, "preco": p_u})

    if st.button("FINALIZAR PEDIDO", use_container_width=True, type="primary"):
        if nome and venda_it:
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": nome, "endereco": ende, "itens": json.dumps(venda_it), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.rerun()

# --- 2. MONTAGEM (IGUAL À FOTO: CARD COM BOTÕES LADO A LADO) ---
with aba[2]:
    st.subheader("Pedidos para Montar")
    pend = df_v[df_v['status'].str.lower() == "pendente"]
    for idx, p in pend.iterrows():
        with st.container(border=True):
            st.write(f"👤 **{p['cliente']}**")
            its, total_m, pronto = json.loads(p['itens']), 0.0, True
            
            for i, it in enumerate(its):
                if str(it.get('tipo')).upper() == "KG":
                    val = st.text_input(f"Peso {it['nome']} (R$ {it['preco']}/kg)", key=f"m{idx}{i}")
                    if val: 
                        v = float(val.replace(',', '.')); it['subtotal'] = v * it['qtd']; total_m += it['subtotal']
                    else: pronto = False
                else:
                    st.write(f"• {it['qtd']}x {it['nome']}")
                    total_m += float(it.get('subtotal', 0))
            
            st.write(f"**Total: R$ {total_m:.2f}**")
            
            # BOTÕES LADO A LADO COMO NO EXEMPLO
            col1, col2, col3 = st.columns(3)
            # Botão Pago: Muda cor se clicado
            btn_pago = col1.button("✅ PAGO", key=f"pg{idx}", type="primary" if p['pagamento'] == "PAGO" else "secondary", use_container_width=True)
            if btn_pago:
                df_v.at[idx, 'pagamento'] = "PAGO"; conn.update(worksheet="Pedidos", data=df_v); st.rerun()
                
            if col2.button("🗑️ EXCLUIR", key=f"ex{idx}", use_container_width=True):
                conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                
            if col3.button("💾 SALVAR", key=f"sv{idx}", disabled=not pronto, use_container_width=True):
                df_v.at[idx, 'status'] = "Concluído"; df_v.at[idx, 'total'] = total_m; df_v.at[idx, 'itens'] = json.dumps(its)
                conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- 3. HISTÓRICO (IGUAL À FOTO: RESUMO NO TOPO + CARDS) ---
with aba[5]:
    st.subheader("Histórico de Vendas")
    hoje = datetime.now().strftime("%d/%m/%Y")
    filtro = df_v[df_v['data'] == hoje]
    
    # RESUMO NO TOPO (Igual à sua foto do Dashboard)
    r1, r2, r3 = st.columns(3)
    r1.metric("Pedidos", len(filtro))
    r2.metric("Pagos", len(filtro[filtro['pagamento'] == "PAGO"]))
    r3.metric("Total", f"R$ {filtro['total'].astype(float).sum():.2f}")
    st.divider()

    for idx, p in filtro.iterrows():
        with st.expander(f"{p['cliente']} - R$ {p['total']}"):
            st.write(f"Pagamento: {p['pagamento']}")
            st.write(f"Endereço: {p['endereco']}")
            # Link WhatsApp rápido
            txt = f"Recibo {p['cliente']}: R$ {p['total']}"
            st.markdown(f"[📲 Enviar Recibo](https://wa.me/?text={urllib.parse.quote(txt)})")
