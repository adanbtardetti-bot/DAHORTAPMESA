import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
from datetime import datetime

st.set_page_config(page_title="Horta Gestão", layout="centered")

# Estilos para evitar quebras no celular
st.markdown('<style>div[data-testid="stColumn"]{display:flex;align-items:center;} .btn-whatsapp{background-color:#25d366;color:white;padding:15px;border-radius:10px;text-align:center;text-decoration:none;display:block;font-weight:bold;margin-top:10px;}</style>', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except: return pd.DataFrame()

def carregar_pedidos():
    try:
        # Tenta ler a aba Pedidos
        df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        # Se der erro (aba não existe), retorna um DataFrame vazio com as colunas certas
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

aba1, aba2 = st.tabs(["🛒 Novo Pedido", "🚜 Colheita"])

with aba1:
    if 'form_id' not in st.session_state: st.session_state.form_id = 0
    f_id = st.session_state.form_id
    st.header("🛒 Novo Pedido")
    
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("Cliente", key=f"n_{f_id}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f_id}").upper()
    pg = st.toggle("Pago?", key=f"p_{f_id}")
    o_ped = st.text_input("Observação", key=f"o_{f_id}")
    
    st.divider()
    df_p = carregar_produtos()
    carrinho = []; total_v = 0.0
    
    if not df_p.empty:
        for i, r in df_p.iterrows():
            col_n, col_p, col_q = st.columns([2.5, 1.2, 1.3])
            p_u = float(str(r['preco']).replace(',', '.'))
            tipo = str(r.get('tipo', 'UN')).upper()
            col_n.markdown(f"**{r['nome']}**")
            if tipo == "KG": col_p.caption("PESAGEM")
            else: col_p.write(f"R$ {p_u:.2f}")
            qtd = col_q.number_input("Q", min_value=0, step=1, key=f"q_{r['id']}_{f_id}", label_visibility="collapsed")
            if qtd > 0:
                sub = 0.0 if tipo == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": tipo})
    
    st.subheader(f"💰 TOTAL: R$ {total_v:.2f}")
    if st.button("💾 FINALIZAR PEDIDO", type="primary"):
        if n_cli and carrinho:
            df_v = carregar_pedidos()
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pg else "A PAGAR", "obs": o_ped}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.session_state.form_id += 1; st.success("Pedido Salvo!"); st.rerun()

with aba2:
    st.header("🚜 Lista de Colheita")
    df_pedidos = carregar_pedidos()
    if not df_pedidos.empty:
        # Filtra apenas quem está 'Pendente'
        pendentes = df_pedidos[df_pedidos['status'].str.lower() == 'pendente']
        if not pendentes.empty:
            resumo = {}
            for _, ped in pendentes.iterrows():
                try:
                    for it in json.loads(ped['itens']):
                        chave = f"{it['nome']} ({it.get('tipo', 'UN')})"
                        resumo[chave] = resumo.get(chave, 0) + it['qtd']
                except: continue
            
            txt_zap = f"*LISTA DE COLHEITA - {datetime.now().strftime('%d/%m/%Y')}*\n\n"
            for item, qtd in resumo.items():
                st.write(f"🟢 **{qtd}x** {item}")
                txt_zap += f"• {qtd}x {item}\n"
            
            link = f"https://wa.me/?text={urllib.parse.quote(txt_zap)}"
            st.markdown(f'<a href="{link}" target="_blank" class="btn-whatsapp">🟢 COMPARTILHAR NO WHATSAPP</a>', unsafe_allow_html=True)
        else: st.info("Nenhum pedido pendente.")
    else: st.warning("Aba 'Pedidos' não encontrada ou vazia.")
