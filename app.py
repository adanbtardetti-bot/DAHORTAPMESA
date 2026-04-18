import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
from datetime import datetime

st.set_page_config(page_title="Horta Gestão", layout="centered")

# Estilos para evitar quebras no celular e formatar os cards de montagem
st.markdown('''<style>
    div[data-testid="stColumn"]{display:flex;align-items:center;} 
    .btn-whatsapp{background-color:#25d366;color:white;padding:15px;border-radius:10px;text-align:center;text-decoration:none;display:block;font-weight:bold;margin-top:10px;}
    .card-montagem {border: 1px solid #2e7d32; padding: 10px; border-radius: 10px; background-color: #0e1117; margin-bottom: 10px;}
    .stButton>button {width:100%;}
</style>''', unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

def carregar_produtos():
    try:
        df = conn.read(worksheet="Produtos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df[df['status'].astype(str).str.lower() != 'oculto']
    except: return pd.DataFrame()

def carregar_pedidos():
    try:
        df = conn.read(worksheet="Pedidos", ttl=0).dropna(how="all")
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df
    except:
        return pd.DataFrame(columns=["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"])

# ADICIONADO A TERCEIRA ABA
aba1, aba2, aba3 = st.tabs(["🛒 Novo Pedido", "🚜 Colheita", "⚖️ Montagem"])

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

# NOVA ABA DE MONTAGEM
with aba3:
    st.header("⚖️ Montagem")
    df_m = carregar_pedidos()
    if not df_m.empty and 'status' in df_m.columns:
        pend_m = df_m[df_m['status'].str.lower() == 'pendente']
        
        for idx, row in pend_m.iterrows():
            with st.container():
                # Card Compacto: Nome, Endereço e Observação
                st.markdown(f'''<div class="card-montagem">
                    <b>👤 {row['cliente']}</b><br>
                    📍 {row['endereco']}<br>
                    <small>💬 {row.get('obs', '')}</small>
                </div>''', unsafe_allow_html=True)
                
                itens_m = json.loads(row['itens'])
                t_atual = 0.0
                
                for i, item in enumerate(itens_m):
                    c_it, c_v = st.columns([3, 2])
                    if str(item.get('tipo', '')).upper() == "KG":
                        # Campo para inserir o valor pesado
                        v_kg = c_v.number_input("Valor R$", min_value=0.0, step=0.1, key=f"m_{row['id']}_{i}", label_visibility="collapsed")
                        item['subtotal'] = v_kg
                        c_it.write(f"⚖️ {item['nome']}")
                    else:
                        c_it.write(f"✅ {item['qtd']}x {item['nome']}")
                        c_v.write(f"R$ {item.get('subtotal', 0.0):.2f}")
                    t_atual += item.get('subtotal', 0.0)

                st.write(f"**Total: R$ {t_atual:.2f}** | {row.get('pagamento', '')}")
                
                # Botões: OK (Pronto), Impressora, Pago e Excluir
                b1, b2, b3, b4 = st.columns([1, 1, 0.8, 0.6])
                
                # Botão OK: Salva pesos e tira da tela
                if b1.button("📦 OK", key=f"ok_{row['id']}"):
                    df_m.at[idx, 'status'] = 'Pronto'
                    df_m.at[idx, 'total'] = t_atual
                    df_m.at[idx, 'itens'] = json.dumps(itens_m)
                    conn.update(worksheet="Pedidos", data=df_m)
                    st.rerun()

                # Impressão (Etiqueta 50x30mm sem títulos)
                txt_e = f"{row['cliente']}\n{row['endereco']}\n\nR$ {t_atual:.2f}\n{row.get('pagamento', '')}"
                b64_e = base64.b64encode(txt_e.encode()).decode()
                l_p = f"intent:base64,{b64_e}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;"
                b2.markdown(f'<a href="{l_p}"><button style="width:100%; height:2.2rem; background:#444; color:white
