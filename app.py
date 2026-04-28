import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import urllib.parse
import base64
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- CONFIGURAÇÕES E ESTILOS ---
st.set_page_config(page_title="Horta Gestão", page_icon="🥬", layout="wide")

def obter_data_br():
    return datetime.now(timezone(timedelta(hours=-3)))

def aplicar_estilos():
    st.markdown("""
        <style>
            .hero-banner {background-color: #0f1d12; color: white; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px;}
            .hero-title {font-size: 24px; font-weight: bold;}
            .btn-zap {background-color: #25d366; color: white !important; padding: 10px; border-radius: 5px; text-decoration: none; display: block; text-align: center; font-weight: bold;}
            .btn-print {text-decoration:none; display:block; text-align:center; background:#f0f2f6; padding:8px; border-radius:5px; color:black; border:1px solid #ddd;}
            .total-badge {background:#f0f2f6; padding:10px; border-radius:5px; font-weight:bold; margin-bottom:10px; color:black;}
            .m-total {font-size: 20px; font-weight: bold; margin-top: 10px; color: #1e1e1e;}
            hr {margin: 0.5rem 0 !important; border-bottom: 1px solid rgba(49, 51, 63, 0.2) !important;}
            .edit-section {background-color: #f9f9f9; padding: 15px; border-radius: 10px; border: 1px dashed #ccc; margin-top: 10px;}
        </style>
    """, unsafe_allow_html=True)

aplicar_estilos()
conn = st.connection("gsheets", type=GSheetsConnection)

STATUS_PENDENTE = "pendente"
STATUS_PRONTO = "pronto"
PAGAMENTO_PAGO = "PAGO"
PAGAMENTO_A_PAGAR = "A PAGAR"

def limpar_texto(texto):
    if not texto: return ""
    return "".join(c for c in unicodedata.normalize('NFD', str(texto)) if unicodedata.category(c) != 'Mn').replace("*", "")

def gerar_b64_etiqueta(cliente, endereco, valor, pagamento):
    largura = 32
    marca = "@dahortapmesa".center(largura)
    cli = limpar_texto(cliente).upper().center(largura)
    end = limpar_texto(endereco).upper().center(largura)
    val_txt = f"R$ {valor:.2f}"
    status_txt = f"({pagamento})" if pagamento == PAGAMENTO_PAGO else ""
    linha_val = f"{val_txt} {status_txt}".strip().center(largura)
    corpo = f"{marca}\n\n{cli}\n\n{end}\n\n{linha_val}\n"
    return base64.b64encode(corpo.encode('ascii', 'ignore')).decode()

def parse_float(val):
    try: return float(str(val).strip().replace(",", "."))
    except: return 0.0

def ler_aba(aba, ttl=0):
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None or df.empty:
            cols = ["id", "cliente", "endereco", "itens", "status", "data", "total", "pagamento", "obs"]
            if aba == "Produtos": cols = ["id", "nome", "preco", "tipo", "status"]
            return pd.DataFrame(columns=cols)
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    conn.reset()

# --- CARREGAR DADOS ---
if "df_pedidos" not in st.session_state or st.session_state.get("reload_pedidos", False):
    st.session_state.df_pedidos = ler_aba("Pedidos", ttl=0)
    st.session_state.reload_pedidos = False
df_pedidos = st.session_state.df_pedidos

if "df_produtos" not in st.session_state or st.session_state.get("reload_produtos", False):
    st.session_state.df_produtos = ler_aba("Produtos", ttl=0)
    st.session_state.reload_produtos = False
df_produtos = st.session_state.df_produtos

st.markdown('<div class="hero-banner"><div class="hero-title">Horta Gestao</div></div>', unsafe_allow_html=True)
aba1, aba2, aba3, aba4, aba5, aba6 = st.tabs(["🛒 Novo", "🚜 Colheita", "⚖️ Montagem", "📜 Histórico", "💰 Financeiro", "📦 Produtos"])

# --- 1. NOVO PEDIDO (Mantido original) ---
with aba1:
    if 'f_id' not in st.session_state: st.session_state.f_id = 0
    f = st.session_state.f_id
    st.header("🛒 Novo Pedido")
    c1, c2, c3 = st.columns([2, 2, 1])
    n_cli, e_cli = c1.text_input("Cliente", key=f"n_{f}").upper(), c2.text_input("Endereço", key=f"e_{f}").upper()
    pg, o_ped = c3.toggle("Pago?", key=f"p_{f}"), st.text_input("Observação", key=f"o_{f}").upper()
    carrinho, total_v = [], 0.0
    if not df_produtos.empty:
        prods = df_produtos[df_produtos['status'].astype(str).str.lower() != "inativo"]
        for idx, r in prods.iterrows():
            col_n, col_p, col_q = st.columns([3.4, 1.3, 1.1])
            col_n.markdown(f"**{limpar_texto(r['nome'])}**")
            col_p.caption(f"R$ {r['preco']} / {r['tipo']}")
            qtd = col_q.number_input("Q", 0, step=1, key=f"q_{idx}_{f}", label_visibility="collapsed")
            if qtd > 0:
                p_u = parse_float(r['preco'])
                sub = 0.0 if str(r['tipo']).upper() == "KG" else (qtd * p_u)
                total_v += sub
                carrinho.append({"nome": r['nome'], "qtd": qtd, "preco": p_u, "subtotal": sub, "tipo": r['tipo']})
            st.divider()
    st.markdown(f"<div class='total-badge'>Total parcial: R$ {total_v:.2f}</div>", unsafe_allow_html=True)
    if st.button("💾 SALVAR PEDIDO", type="primary", use_container_width=True):
        if n_cli and carrinho:
            agora_br = obter_data_br()
            df_at = ler_aba("Pedidos", ttl=0)
            novo = pd.DataFrame([{"id": int(agora_br.timestamp()), "cliente": n_cli, "endereco": e_cli, "itens": json.dumps(carrinho), "status": "pendente", "data": agora_br.strftime("%d/%m/%Y"), "total": total_v, "pagamento": PAGAMENTO_PAGO if pg else PAGAMENTO_A_PAGAR, "obs": o_ped}])
            salvar_aba("Pedidos", pd.concat([df_at, novo], ignore_index=True)); st.session_state.f_id += 1; st.session_state.reload_pedidos = True; st.rerun()

# --- 2. COLHEITA (Mantido original) ---
with aba2:
    st.header("🚜 Colheita")
    if not df_pedidos.empty:
        pend = df_pedidos[df_pedidos["status"].str.lower() == STATUS_PENDENTE]
        if not pend.empty:
            res = {}
            for _, p in pend.iterrows():
                for it in json.loads(p['itens']):
                    k = f"{it['nome']} ({it['tipo']})"
                    res[k] = res.get(k, 0) + it['qtd']
            for k, v in res.items(): st.write(f"🟢 **{v}x** {k}")
            txt_z = "*LISTA DE COLHEITA*\n" + "\n".join([f"• {v}x {k}" for k, v in res.items()])
            st.markdown(f'<a href="https://wa.me/?text={urllib.parse.quote(txt_z)}" target="_blank" class="btn-zap">ENVIAR WHATSAPP</a>', unsafe_allow_html=True)

# --- 3. MONTAGEM (CORRIGIDO) ---
with aba3:
    st.header("⚖️ Montagem")
    if not df_pedidos.empty:
        pend_m = df_pedidos[df_pedidos["status"].str.lower() == STATUS_PENDENTE]
        for _, row in pend_m.iterrows():
            stpg = str(row.get("pagamento")).upper()
            with st.expander(f"👤 {row['cliente']} | {stpg}", expanded=True):
                if row.get('obs'): st.warning(f"⚠️ {row['obs']}")
                
                edit_key = f"edit_mode_{row['id']}"
                if edit_key not in st.session_state: st.session_state[edit_key] = False

                if st.session_state[edit_key]:
                    st.markdown('<div class="edit-section">', unsafe_allow_html=True)
                    novo_nome = st.text_input("Editar Cliente", row['cliente'], key=f"edit_n_{row['id']}").upper()
                    novo_end = st.text_input("Editar Endereço", row['endereco'], key=f"edit_e_{row['id']}").upper()
                    
                    # --- SEÇÃO ADICIONAR ITEM ---
                    st.write("➕ **Adicionar novo item:**")
                    c_add_p, c_add_q, c_add_b = st.columns([2.5, 1, 1])
                    lista_produtos = ["-- Selecionar --"] + sorted(df_produtos[df_produtos['status'].astype(str).str.lower() == "ativo"]['nome'].tolist())
                    prod_selecionado = c_add_p.selectbox("Produto", lista_produtos, key=f"sel_extra_{row['id']}", label_visibility="collapsed")
                    qtd_selecionada = c_add_q.number_input("Qtd", 1, step=1, key=f"qtd_extra_{row['id']}", label_visibility="collapsed")
                    
                    if c_add_b.button("Adicionar", key=f"btn_add_extra_{row['id']}"):
                        if prod_selecionado != "-- Selecionar --":
                            itens_atuais = json.loads(row['itens'])
                            p_info = df_produtos[df_produtos['nome'] == prod_selecionado].iloc[0]
                            
                            novo_item = {
                                "nome": prod_selecionado, 
                                "qtd": qtd_selecionada, 
                                "preco": parse_float(p_info['preco']), 
                                "tipo": p_info['tipo'],
                                "subtotal": 0.0 if p_info['tipo'] == "KG" else (qtd_selecionada * parse_float(p_info['preco']))
                            }
                            itens_atuais.append(novo_item)
                            
                            # Salva imediatamente para refletir na tela
                            df_f = ler_aba("Pedidos", ttl=0)
                            df_f.loc[df_f["id"].astype(str) == str(row["id"]), "itens"] = json.dumps(itens_atuais)
                            salvar_aba("Pedidos", df_f)
                            st.session_state.reload_pedidos = True
                            st.rerun()

                    st.write("---")
                    # --- LISTA DE ITENS PARA EDIÇÃO ---
                    itens_m = json.loads(row['itens'])
                    novos_itens_finais = []
                    total_editado = 0.0

                    for i, it in enumerate(itens_m):
                        c_n, c_q, c_del = st.columns([3, 1, 0.5])
                        c_n.markdown(f"**{it['nome']}**")
                        nova_qtd = c_q.number_input("Q", value=int(it['qtd']), min_value=0, key=f"ed_q_{row['id']}_{i}", label_visibility="collapsed")
                        
                        if c_del.button("🗑️", key=f"del_it_{row['id']}_{i}"):
                            nova_qtd = 0 # Marcar para remoção

                        if nova_qtd > 0:
                            it['qtd'] = nova_qtd
                            if str(it['tipo']).upper() != "KG":
                                it['subtotal'] = nova_qtd * parse_float(it['preco'])
                            novos_itens_finais.append(it)
                            total_editado += parse_float(it['subtotal'])
                    
                    st.write(f"**Total parcial: R$ {total_editado:.2f}**")
                    
                    col_save, col_cancel = st.columns(2)
                    if col_save.button("💾 SALVAR ALTERAÇÕES", key=f"save_edit_{row['id']}", type="primary", use_container_width=True):
                        df_f = ler_aba("Pedidos", ttl=0)
                        df_f.loc[df_f["id"].astype(str) == str(row["id"]), ["cliente", "endereco", "itens", "total"]] = [novo_nome, novo_end, json.dumps(novos_itens_finais), total_editado]
                        salvar_aba("Pedidos", df_f)
                        st.session_state[edit_key] = False
                        st.session_state.reload_pedidos = True
                        st.rerun()
                    
                    if col_cancel.button("Cancelar", key=f"canc_edit_{row['id']}", use_container_width=True):
                        st.session_state[edit_key] = False
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                
                else:
                    # Layout normal de exibição (Pesagem)
                    st.write(f"📍 {row['endereco']}")
                    itens_m, total_m = json.loads(row['itens']), 0.0
                    for i, it in enumerate(itens_m):
                        c_i, c_v = st.columns([3.5, 1.4])
                        if str(it['tipo']).upper() == "KG":
                            val_input = c_v.number_input("R$", value=None, key=f"m_{row['id']}_{i}", label_visibility="collapsed", placeholder="0,00")
                            v_digitado = parse_float(val_input) if val_input is not None else 0.0
                            it['subtotal'] = v_digitado
                            if v_digitado > 0 and parse_float(it.get('preco', 0)) > 0:
                                it['qtd'] = round(v_digitado / parse_float(it['preco']), 3)
                            c_i.markdown(f"⚖️ {limpar_texto(it['nome'])}")
                        else:
                            c_i.markdown(f"✅ {it['qtd']}x {limpar_texto(it['nome'])}")
                            c_v.markdown(f"R$ {parse_float(it['subtotal']):.2f}")
                        total_m += parse_float(it['subtotal'])
                        st.divider()
                    st.markdown(f"<div class='m-total'>TOTAL: R$ {total_m:.2f}</div>", unsafe_allow_html=True)
                    
                    c_ok, c_pg, c_ed, c_pr, c_del = st.columns([1, 1, 1, 0.5, 0.5])
                    
                    if c_ok.button("📦 OK", key=f"ok_{row['id']}"):
                        df_f = ler_aba("Pedidos", ttl=0)
                        idx_list = df_f.index[df_f["id"].astype(str) == str(row["id"])].tolist()
                        if idx_list:
                            idx = idx_list[0]
                            df_f.at[idx, "status"], df_f.at[idx, "total"], df_f.at[idx, "itens"] = STATUS_PRONTO, total_m, json.dumps(itens_m)
                            salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()
                    
                    if stpg != PAGAMENTO_PAGO and c_pg.button("💵 Pago", key=f"pg_{row['id']}"):
                        df_f = ler_aba("Pedidos", ttl=0); df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO; salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()
                    
                    if c_ed.button("✏️ Editar", key=f"btn_ed_{row['id']}"):
                        st.session_state[edit_key] = True
                        st.rerun()

                    b64 = gerar_b64_etiqueta(row['cliente'], row['endereco'], total_m, stpg)
                    c_pr.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️</a>', unsafe_allow_html=True)
                    
                    if c_del.button("🗑️", key=f"del_{row['id']}"):
                        df_f = ler_aba("Pedidos", ttl=0); df_f = df_f[df_f["id"].astype(str) != str(row["id"])]; salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()

# --- 4, 5 e 6 (Histórico, Financeiro e Produtos) ---
# (O código para estas abas permanece igual ao seu original)
