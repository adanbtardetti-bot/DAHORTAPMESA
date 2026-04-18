import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO E ESTILO ---
st.set_page_config(page_title="Horta Gestão", layout="centered")

st.markdown("""
    <style>
    .stButton>button { border-radius: 10px; height: 3em; width: 100%; font-weight: bold; }
    .stTextInput>div>div>input { background-color: #f9f9f9; }
    [data-testid="stMetric"] { background: white; padding: 10px; border-radius: 15px; border: 1px solid #eee; }
    div[data-testid="stContainer"] { background: white; padding: 10px; border-radius: 12px; border: 1px solid #f0f0f0; margin-bottom: 5px; }
    .total-card { background: #2e7d32; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar(aba):
    try:
        df = conn.read(worksheet=aba, ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        if aba == "Produtos":
            return pd.DataFrame(columns=["id", "nome", "preco", "tipo", "status"])
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

df_p = carregar("Produtos")
df_v = carregar("Pedidos")

tab = st.tabs(["🛒 Vendas", "🚜 Colheita", "⚖️ Montagem", "📦 Estoque", "📊 Financeiro", "🕒 Histórico"])

# --- 1. TELA DE VENDAS (OTIMIZADA) ---
with tab[0]:
    st.subheader("Novo Pedido")
    
    # Informações fixas no topo
    col_cli, col_end = st.columns(2)
    nome = col_cli.text_input("Cliente").upper()
    ende = col_end.text_input("Endereço").upper()
    
    col_pg, col_obs = st.columns([1, 2])
    pago_venda = col_pg.checkbox("PAGO?")
    obs_venda = col_obs.text_input("Observação (opcional)")

    st.divider()
    
    # BARRA DE BUSCA PARA MUITOS PRODUTOS
    busca = st.text_input("🔍 Pesquisar produto...", "").strip().lower()
    
    carrinho = []
    total_live = 0.0
    
    if not df_p.empty:
        # Filtra apenas Ativos e pelo que foi buscado
        produtos_visiveis = df_p[df_p['status'].astype(str).str.lower() != 'oculto']
        if busca:
            produtos_visiveis = produtos_visiveis[produtos_visiveis['nome'].str.lower().contains(busca)]
        
        for i, r in produtos_visiveis.iterrows():
            with st.container():
                c1, c2, c3 = st.columns([2, 1, 1])
                p_u = float(str(r.get('preco', 0)).replace(',', '.'))
                c1.markdown(f"**{r['nome']}**")
                c2.write(f"R$ {p_u:.2f}")
                q = c3.number_input("Qtd", min_value=0, step=1, key=f"v_{i}")
                
                if q > 0:
                    sub = q * p_u
                    total_live += sub
                    carrinho.append({"nome": r['nome'], "qtd": q, "tipo": r['tipo'], "preco": p_u, "subtotal": sub})

    # Total e Botão Salvar
    st.markdown(f"<div class='total-card'><h3>TOTAL: R$ {total_live:.2f}</h3></div>", unsafe_allow_html=True)
    
    if st.button("💾 CONCLUIR E SALVAR PEDIDO", type="primary"):
        if nome and carrinho:
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": nome, "endereco": ende, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_live, "pagamento": "PAGO" if pago_venda else "A PAGAR", "obs": obs_venda}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.success("Pedido registrado!"); st.rerun()
        else:
            st.error("Preencha o nome e selecione itens!")

# --- 2. TELA DE COLHEITA (SOMA AUTOMÁTICA) ---
with tab[1]:
    st.subheader("O que colher agora")
    if not df_v.empty:
        pendentes = df_v[df_v['status'].astype(str).str.lower() == 'pendente']
        soma_colheita = {}
        for _, p in pendentes.iterrows():
            try:
                for it in json.loads(p['itens']):
                    n = it['nome']; soma_colheita[n] = soma_colheita.get(n, 0) + it['qtd']
            except: pass
        
        if soma_colheita:
            for p, q in soma_colheita.items():
                st.write(f"🥦 **{p}**: {q}")
        else: st.write("Nenhum pedido pendente.")

# --- 3. TELA DE MONTAGEM (COM ENDEREÇO E OBS) ---
with tab[2]:
    st.subheader("Pedidos para Montar")
    if not df_v.empty:
        pendentes = df_v[df_v['status'].astype(str).str.lower() == 'pendente']
        for idx, p in pendentes.iterrows():
            with st.container():
                st.write(f"👤 **{p['cliente']}**")
                if p.get('endereco') and str(p['endereco']) != 'nan': st.caption(f"📍 {p['endereco']}")
                if p.get('obs') and str(p['obs']) != 'nan' and p['obs'].strip() != "": st.info(f"💡 {p['obs']}")
                
                try: its = json.loads(p['itens'])
                except: its = []
                
                t_m, pronto = 0.0, True
                for i, it in enumerate(its):
                    if str(it.get('tipo', '')).upper() == "KG":
                        peso = st.text_input(f"Peso {it['nome']}:", key=f"m_{idx}_{i}")
                        if peso:
                            v = float(peso.replace(',','.')); it['subtotal'] = v; t_m += v
                        else: pronto = False
                    else:
                        st.write(f"• {it['qtd']}x {it['nome']}")
                        t_m += float(it.get('subtotal', 0))
                
                st.write(f"**Total: R$ {t_m:.2f}**")
                c1, c2, c3 = st.columns(3)
                txt_imprimir = f"CLIENTE: {p['cliente']}\nTOTAL: R$ {t_m:.2f}"
                link = f"intent:base64,{base64.b64encode(txt_imprimir.encode()).decode()}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                c1.markdown(f'<a href="{link}"><button style="width:100%; border-radius:10px; background:#444; color:white; border:none;">🖨️</button></a>', unsafe_allow_html=True)
                if c2.button("🗑️", key=f"ex_{idx}"):
                    conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                if c3.button
