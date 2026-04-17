import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO VISUAL (TEMA CLARO IGUAL ÀS FOTOS) ---
st.set_page_config(page_title="Horta Gestão", layout="centered")

# CSS para criar os cards brancos e botões lado a lado das fotos
st.markdown("""
    <style>
    .stButton>button { border-radius: 10px; height: 3em; width: 100%; }
    div[data-testid="stExpander"] { border: none !important; box-shadow: 0px 2px 10px rgba(0,0,0,0.05); border-radius: 15px; }
    .card { background: white; padding: 15px; border-radius: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-bottom: 10px; border: 1px solid #eee; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def buscar_dados(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except: return pd.DataFrame()

df_p = buscar_dados("Produtos")
df_v = buscar_dados("Pedidos")

# Navegação por abas igual ao rodapé das fotos
tab = st.tabs(["🛒 Vendas", "🌱 Colheita", "⚖️ Montagem", "📦 Estoque", "📈 Financeiro", "🕒 Histórico"])

# --- 1. VENDAS (IGUAL FOTO 1000381875) ---
with tab[0]:
    st.subheader("Novo Pedido")
    nome = st.text_input("Nome do cliente", placeholder="Ex: Cristiane")
    ende = st.text_input("Endereço", placeholder="Endereço de entrega")
    
    st.write("**Produtos**")
    carrinho = []
    if not df_p.empty:
        for i, r in df_p[df_p['status'] == 'ativo'].iterrows():
            # Card de produto igual à foto
            with st.container(border=True):
                col_txt, col_qtd = st.columns([3, 1])
                col_txt.write(f"**{r['nome']}** `{r['tipo']}`\nR$ {r['preco']}")
                qtd = col_qtd.number_input("Qtd", min_value=0, step=1, key=f"add_{i}")
                if qtd > 0:
                    carrinho.append({"nome": r['nome'], "qtd": qtd, "tipo": r['tipo'], "preco": float(str(r['preco']).replace(',','.')), "subtotal": 0.0})

    if st.button("FINALIZAR PEDIDO", type="primary", use_container_width=True):
        if nome and carrinho:
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": nome, "endereco": ende, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": 0.0, "pagamento": "A PAGAR"}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.success("Pedido Salvo!"); st.rerun()

# --- 2. MONTAGEM (IGUAL FOTO 1000381879 e 1000381881) ---
with tab[2]:
    st.header("Montagem")
    pendentes = df_v[df_v['status'].str.lower() == 'pendente']
    
    for idx, p in pendentes.iterrows():
        with st.container(border=True):
            st.write(f"👤 **{p.get('cliente', 'Sem Nome')}**")
            st.write(f"📍 {p.get('endereco', 'Sem Endereço')}")
            
            itens = json.loads(p['itens'])
            total_final = 0.0
            pronto = True
            
            for i, it in enumerate(itens):
                # Se for KG, abre campo de valor (Foto 1776458619715)
                if str(it.get('tipo')).upper() == "KG":
                    val = st.text_input(f"Valor {it['nome']} (Peso):", key=f"peso_{idx}_{i}")
                    if val: 
                        v = float(val.replace(',', '.')); it['subtotal'] = v; total_final += v
                    else: pronto = False
                else:
                    st.write(f"• {it['qtd']}x {it['nome']} = R$ {it['qtd'] * it['preco']:.2f}")
                    it['subtotal'] = it['qtd'] * it['preco']
                    total_final += it['subtotal']
            
            st.subheader(f"Total: R$ {total_final:.2f}")
            
            # BOTÕES LADO A LADO (Sua solicitação principal)
            c1, c2, c3 = st.columns(3)
            
            # Etiqueta (RawBT) - Valor sempre sai aqui
            cmd = f"intent:base64,{base64.b64encode(f'CLIENTE: {p.get('cliente')}\nTOTAL: R$ {total_final:.2f}\n'.encode('latin-1')).decode()}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
            c1.link_button("🖨️ Imprimir", cmd)
            
            if c2.button("🗑️ Excluir", key=f"del_{idx}"):
                conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                
            # Botão Salvar: Só libera se pesar os itens de KG
            if c3.button("✅ Pronto", key=f"ok_{idx}", type="primary", disabled=not pronto):
                df_v.at[idx, 'status'] = "Concluído"
                df_v.at[idx, 'total'] = total_final
                df_v.at[idx, 'itens'] = json.dumps(itens)
                conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- 3. HISTÓRICO (IGUAL FOTO 1000381887) ---
with tab[5]:
    st.header("Histórico")
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_hoje = df_v[df_v['data'] == hoje]
    
    # Resumo no topo igual à foto
    m1, m2, m3 = st.columns(3)
    m1.metric("Pedidos", len(df_hoje))
    m2.metric("Pagos", len(df_hoje[df_hoje['pagamento'] == "PAGO"]))
    m3.metric("Total", f"R$ {df_hoje['total'].astype(float).sum():.2f}")
    
    st.divider()
    
    for idx, p in df_hoje.iterrows():
        with st.expander(f"{p['cliente']} - R$ {p['total']}"):
            st.write(f"Status: {p['pagamento']}")
            if st.button("Marcar como Pago", key=f"pay_{idx}"):
                df_v.at[idx, 'pagamento'] = "PAGO"
                conn.update(worksheet="Pedidos", data=df_v); st.rerun()
