import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Horta Gestão", layout="centered")

st.markdown("""
    <style>
    .stButton>button { border-radius: 10px; height: 3.5em; width: 100%; font-weight: bold; }
    [data-testid="stMetric"] { background: white; padding: 15px; border-radius: 15px; border: 1px solid #eee; }
    div[data-testid="stContainer"] { background: white; padding: 15px; border-radius: 15px; border: 1px solid #eee; margin-bottom: 10px; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        cols = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]
        return pd.DataFrame(columns=cols)

df_p = carregar("Produtos")
df_v = carregar("Pedidos")

# --- ABAS ---
tab = st.tabs(["🛒 Vendas", "🚜 Colheita", "⚖️ Montagem", "📊 Financeiro", "🕒 Histórico"])

# --- 1. TELA DE VENDAS (COMO VOCÊ PEDIU) ---
with tab[0]:
    st.subheader("Novo Pedido")
    
    # Nome e Endereço
    nome = st.text_input("Nome do Cliente").upper()
    ende = st.text_input("Endereço de Entrega").upper()
    
    # Botão Pago (Embaixo do nome/endereço)
    pago_venda = st.checkbox("MARCAR COMO PAGO AGORA?")
    status_pg = "PAGO" if pago_venda else "A PAGAR"
    
    # Campo de Observação
    observacao = st.text_area("Observações do Pedido")
    
    st.divider()
    st.write("**Selecione os Produtos:**")
    
    carrinho = []
    if not df_p.empty:
        for i, r in df_p.iterrows():
            with st.container():
                c1, c2 = st.columns([3, 1])
                c1.write(f"**{r.get('nome', '---')}**\nR$ {r.get('preco', '0')}")
                q = c2.number_input("Qtd", min_value=0, step=1, key=f"v_{i}")
                if q > 0:
                    preco_unit = float(str(r.get('preco', '0')).replace(',', '.'))
                    carrinho.append({
                        "nome": r.get('nome'), 
                        "qtd": q, 
                        "tipo": r.get('tipo', 'un'), 
                        "preco": preco_unit,
                        "subtotal": 0.0 if str(r.get('tipo')).upper() == "KG" else (q * preco_unit)
                    })

    # Botão Salvar no final de tudo
    if st.button("SALVAR PEDIDO", type="primary", use_container_width=True):
        if nome and carrinho:
            novo_pedido = pd.DataFrame([{
                "id": int(datetime.now().timestamp()),
                "cliente": nome,
                "endereco": ende,
                "itens": json.dumps(carrinho),
                "status": "Pendente",
                "data": datetime.now().strftime("%d/%m/%Y"),
                "total": sum(i['subtotal'] for i in carrinho),
                "pagamento": status_pg,
                "obs": observacao
            }])
            df_final = pd.concat([df_v, novo_pedido], ignore_index=True)
            conn.update(worksheet="Pedidos", data=df_final)
            st.success("Pedido Salvo!"); st.rerun()
        else:
            st.warning("Preencha o Nome e escolha ao menos um produto.")

# --- 2. TELA DE COLHEITA ---
with tab[1]:
    st.subheader("Resumo para Colheita")
    if not df_v.empty:
        pendentes = df_v[df_v['status'].astype(str).str.upper() == "PENDENTE"]
        resumo = {}
        for _, p in pendentes.iterrows():
            try: its = json.loads(p['itens'])
            except: its = []
            for it in its:
                n = it.get('nome'); resumo[n] = resumo.get(n, 0) + it.get('qtd', 0)
        
        for prod, qtd in resumo.items():
            st.write(f"🥦 {prod}: **{qtd}**")

# --- 3. TELA DE MONTAGEM (COM IMPRIMIR) ---
with tab[2]:
    st.subheader("Montagem")
    if not df_v.empty:
        pendentes = df_v[df_v['status'].astype(str).str.upper() == "PENDENTE"]
        for idx, p in pendentes.iterrows():
            with st.container():
                st.write(f"👤 **{p.get('cliente')}**")
                if p.get('obs'): st.info(f"📝 OBS: {p['obs']}")
                
                try: its = json.loads(p['itens'])
                except: its = []
                
                t_calc, pronto = 0.0, True
                for i, it in enumerate(its):
                    if str(it.get('tipo', '')).upper() == "KG":
                        peso = st.text_input(f"Peso {it['nome']}:", key=f"m_{idx}_{i}")
                        if peso:
                            v = float(peso.replace(',','.')); it['subtotal'] = v; t_calc += v
                        else: pronto = False
                    else:
                        st.write(f"• {it['qtd']}x {it['nome']}")
                        t_calc += float(it.get('subtotal', 0))
                
                st.write(f"### Total: R$ {t_calc:.2f}")
                
                c1, c2, c3 = st.columns(3)
                # Botão Imprimir (Etiq)
                txt = f"CLIENTE: {p['cliente']}\nTOTAL: R$ {t_calc:.2f}"
                link = f"intent:base64,{base64.b64encode(txt.encode()).decode()}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                c1.markdown(f'<a href="{link}"><button style="width:100%; border-radius:10px; height:3.5em; background:#444; color:white; border:none;">🖨️</button></a>', unsafe_allow_html=True)
                
                if c2.button("🗑️", key=f"d_{idx}"):
                    conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                
                if c3.button("✔️", key=f"s_{idx}", type="primary", disabled=not pronto):
                    df_v.at[idx, 'status'] = "Concluído"; df_v.at[idx, 'total'] = t_calc; df_v.at[idx, 'itens'] = json.dumps(its)
                    conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- 5. HISTÓRICO (MÉTRICAS NO TOPO) ---
with tab[4]:
    st.subheader("Histórico")
    hoje = datetime.now().strftime("%d/%m/%Y")
    df_hj = df_v[df_v['data'] == hoje] if not df_v.empty else pd.DataFrame()
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Pedidos", len(df_hj))
    m2.metric("Pagos", len(df_hj[df_hj['pagamento'] == "PAGO"]) if not df_hj.empty else 0)
    total_dia = df_hj['total'].astype(float).sum() if not df_hj.empty else 0
    m3.metric("Total", f"R$ {total_dia:.2f}")
    
    st.divider()
    for idx, p in df_hj.iterrows():
        with st.expander(f"{p['cliente']} - R$ {p['total']} ({p['pagamento']})"):
            if st.button("PAGO", key=f"h_{idx}"):
                df_v.at[idx, 'pagamento'] = "PAGO"; conn.update(worksheet="Pedidos", data=df_v); st.rerun()
