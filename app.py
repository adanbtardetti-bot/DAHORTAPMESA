import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import base64
from datetime import datetime

# --- CONFIGURAÇÃO VISUAL ---
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

# --- ABAS (ESTOQUE ADICIONADO) ---
tab = st.tabs(["🛒 Vendas", "🚜 Colheita", "⚖️ Montagem", "📦 Estoque", "📊 Financeiro", "🕒 Histórico"])

# --- 1. TELA DE VENDAS (COM SOMA EM TEMPO REAL) ---
with tab[0]:
    st.subheader("Novo Pedido")
    nome = st.text_input("Nome do Cliente").upper()
    ende = st.text_input("Endereço de Entrega").upper()
    pago_venda = st.checkbox("MARCAR COMO PAGO?")
    observacao = st.text_area("Observações")
    
    st.divider()
    carrinho = []
    total_venda_viva = 0.0
    
    if not df_p.empty:
        for i, r in df_p.iterrows():
            with st.container():
                c1, c2 = st.columns([3, 1])
                preco_unit = float(str(r.get('preco', '0')).replace(',', '.'))
                c1.write(f"**{r.get('nome', '---')}**\nR$ {preco_unit:.2f}")
                q = c2.number_input("Qtd", min_value=0, step=1, key=f"v_{i}")
                if q > 0:
                    sub = q * preco_unit
                    total_venda_viva += sub
                    carrinho.append({"nome": r.get('nome'), "qtd": q, "tipo": r.get('tipo', 'un'), "preco": preco_unit, "subtotal": sub})

    # Mostra o total da venda antes de salvar
    st.markdown(f"### Total do Pedido: R$ {total_venda_viva:.2f}")
    
    if st.button("SALVAR PEDIDO", type="primary", use_container_width=True):
        if nome and carrinho:
            novo = pd.DataFrame([{
                "id": int(datetime.now().timestamp()), "cliente": nome, "endereco": ende,
                "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"),
                "total": total_venda_viva, "pagamento": "PAGO" if pago_venda else "A PAGAR", "obs": observacao
            }])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.success("Salvo!"); st.rerun()

# --- 3. TELA DE MONTAGEM (CORRIGIDA: ENDEREÇO, TOTAL E OBS) ---
with tab[2]:
    st.subheader("Montagem")
    if not df_v.empty:
        pendentes = df_v[df_v['status'].astype(str).str.upper() == "PENDENTE"]
        for idx, p in pendentes.iterrows():
            with st.container():
                st.write(f"👤 **{p.get('cliente', '---')}**")
                
                # Mostra endereço se existir
                if p.get('endereco') and str(p['endereco']).lower() != 'nan':
                    st.write(f"📍 {p['endereco']}")
                
                # Mostra OBS apenas se não for vazio ou "nan"
                obs_texto = str(p.get('obs', ''))
                if obs_texto.lower() != 'nan' and obs_texto.strip() != '':
                    st.info(f"📝 OBS: {obs_texto}")
                
                try: its = json.loads(p['itens'])
                except: its = []
                
                t_calc, pronto = 0.0, True
                for i, it in enumerate(its):
                    if str(it.get('tipo', '')).upper() == "KG":
                        peso = st.text_input(f"Peso {it['nome']}:", key=f"m_{idx}_{i}")
                        if peso:
                            try:
                                v_peso = float(peso.replace(',','.')); it['subtotal'] = v_peso; t_calc += v_peso
                            except: pronto = False
                        else: pronto = False
                    else:
                        st.write(f"• {it['qtd']}x {it['nome']}")
                        # Se não for KG, usa o subtotal que já veio da venda
                        t_calc += float(it.get('subtotal', 0))
                
                st.write(f"### Total: R$ {t_calc:.2f}")
                
                c1, c2, c3 = st.columns(3)
                # Imprimir
                txt = f"CLIENTE: {p['cliente']}\nTOTAL: R$ {t_calc:.2f}"
                link = f"intent:base64,{base64.b64encode(txt.encode()).decode()}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                c1.markdown(f'<a href="{link}"><button style="width:100%; border-radius:10px; height:3.5em; background:#444; color:white; border:none;">🖨️</button></a>', unsafe_allow_html=True)
                
                if c2.button("🗑️", key=f"d_{idx}"):
                    conn.update(worksheet="Pedidos", data=df_v.drop(idx)); st.rerun()
                
                if c3.button("✔️", key=f"s_{idx}", type="primary", disabled=not pronto):
                    df_v.at[idx, 'status'] = "Concluído"; df_v.at[idx, 'total'] = t_calc
                    conn.update(worksheet="Pedidos", data=df_v); st.rerun()

# --- 4. TELA DE ESTOQUE (RESTAURADA) ---
with tab[3]:
    st.subheader("Estoque de Produtos")
    if not df_p.empty:
        st.dataframe(df_p, use_container_width=True)
    else:
        st.write("Nenhum produto cadastrado.")

# --- FINANCEIRO E HISTÓRICO ---
with tab[4]:
    st.subheader("Financeiro")
    st.metric("Total Geral", f"R$ {df_v['total'].astype(float).sum():.2f}")
    st.dataframe(df_v)
