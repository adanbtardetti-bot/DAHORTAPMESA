import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

st.set_page_config(page_title="Horta Gestão", layout="centered")

# Estilos CSS otimizados
st.markdown('<style>div[data-testid="stColumn"]{display:flex;align-items:center;} .stButton>button{border-radius:10px;font-weight:bold;} .card-montagem{border:1px solid #ddd; padding:15px; border-radius:10px; margin-bottom:10px; background-color:#f9f9f9;} .btn-whatsapp{background-color:#25d366;color:white;padding:15px;border-radius:10px;text-align:center;text-decoration:none;display:block;font-weight:bold;margin-top:10px;}</style>', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNÇÕES DE DADOS ---
def carregar_pedidos():
    try:
        df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except: return pd.DataFrame()

aba1, aba2, aba3 = st.tabs(["🛒 Venda", "🚜 Colheita", "⚖️ Montagem"])

# --- ABA 1 E 2 MANTIDAS (Lógica anterior funcional) ---
with aba1:
    if 'form_id' not in st.session_state: st.session_state.form_id = 0
    f_id = st.session_state.form_id
    st.header("🛒 Novo Pedido")
    c1, c2 = st.columns(2)
    n_cli = c1.text_input("Cliente", key=f"n_{f_id}").upper()
    e_cli = c2.text_input("Endereço", key=f"e_{f_id}").upper()
    pg_toggle = st.toggle("Pago?", key=f"p_{f_id}")
    o_ped = st.text_input("Observação", key=f"o_{f_id}")
    st.divider()
    df_p = carregar_produtos()
    carrinho = []; total_v = 0.0
    if not df_p.empty:
        for i, r in df_p.iterrows():
            col_n, col_p, col_q = st.columns([2.5, 1.2, 1.3])
            p_u = float(str(r['preco']).replace(',', '.')); tipo = str(r.get('tipo', 'UN')).upper()
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
            novo = pd.DataFrame([{"id": int(datetime.now().timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "Pendente", "data": datetime.now().strftime("%d/%m/%Y"), "total": total_v, "pagamento": "PAGO" if pg_toggle else "A PAGAR", "obs": o_ped}])
            conn.update(worksheet="Pedidos", data=pd.concat([df_v, novo], ignore_index=True))
            st.session_state.form_id += 1; st.success("Pedido Salvo!"); st.rerun()

with aba2:
    st.header("🚜 Lista de Colheita")
    df_pedidos = carregar_pedidos()
    if not df_pedidos.empty:
        pendentes = df_pedidos[df_pedidos['status'].str.lower() == 'pendente']
        if not pendentes.empty:
            resumo = {}
            for _, ped in pendentes.iterrows():
                try:
                    for it in json.loads(ped['itens']):
                        chave = f"{it['nome']} ({it.get('tipo', 'UN')})"
                        resumo[chave] = resumo.get(chave, 0) + it['qtd']
                except: continue
            for item, qtd in resumo.items(): st.write(f"🟢 **{qtd}x** {item}")
            txt_zap = f"*COLHEITA {datetime.now().strftime('%d/%m/%Y')}*\n\n" + "\n".join([f"• {q}x {i}" for i, q in resumo.items()])
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_zap)}" target="_blank" class="btn-whatsapp">🟢 COMPARTILHAR NO WHATSAPP</a>', unsafe_allow_html=True)

# --- ABA 3: MONTAGEM (NOVA) ---
with aba3:
    st.header("⚖️ Montagem de Pedidos")
    df_m = carregar_pedidos()
    pendentes_m = df_m[df_m['status'].str.lower() == 'pendente']

    if not pendentes_m.empty:
        for idx, row in pendentes_m.iterrows():
            with st.container():
                st.markdown(f"""<div class="card-montagem">
                    <h3>{row['cliente']}</h3>
                    <p>📍 {row['endereco']}</p>
                    <small>💬 {row['obs'] if row['obs'] else 'Sem observações'}</small>
                </div>""", unsafe_allow_html=True)
                
                itens_montagem = json.loads(row['itens'])
                novo_total = 0.0
                alterou_kg = False

                for i, item in enumerate(itens_montagem):
                    c1, c2 = st.columns([3, 2])
                    if item.get('tipo') == "KG":
                        # Campo para inserir o valor pesado (R$)
                        valor_pesado = c2.number_input(f"R$ {item['nome']}", min_value=0.0, step=0.5, key=f"peso_{row['id']}_{i}")
                        if valor_pesado > 0:
                            item['subtotal'] = valor_pesado
                            alterou_kg = True
                        c1.write(f"⚖️ {item['nome']} (Pesar)")
                    else:
                        c1.write(f"✅ {item['qtd']}x {item['nome']}")
                    
                    novo_total += item.get('subtotal', 0)

                st.write(f"**Total Pedido: R$ {novo_total:.2f}** ({row['pagamento']})")

                # Botões de Ação
                col1, col2, col3 = st.columns(3)
                
                # 1. BOTÃO IMPRIMIR (50x30mm)
                txt_etiqueta = f"{row['cliente']}\n{row['endereco']}\n\nVALOR: R$ {novo_total:.2f}\n{row['pagamento']}"
                b64_etiqueta = base64.b64encode(txt_etiqueta.encode()).decode()
                # Link para o app RawBT (impressora térmica Bluetooth)
                link_print = f"intent:base64,{b64_etiqueta}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                col1.markdown(f'<a href="{link_print}"><button style="width:100%; height:3em; background:#444; color:white; border-radius:10px;">🖨️ Imprimir</button></a>', unsafe_allow_html=True)

                # 2. BOTÃO CONCLUÍDO (PAGO)
                if col2.button("✔️ Pago", key=f"ok_{row['id']}"):
                    df_m.at[idx, 'status'] = 'Concluido'
                    df_m.at[idx, 'total'] = novo_total
                    df_m.at[idx, 'itens'] = json.dumps(itens_montagem)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # 3. BOTÃO EXCLUIR
                if col3.button("🗑️", key=f"del_{row['id']}"):
                    df_m = df_m.drop(idx)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()
                st.divider()
    else:
        st.info("Nenhum pedido para montar.")
