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
            .edit-box {background-color: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px dashed #ccc; margin-bottom: 15px; color: black;}
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
    cli = limpar_texto(cliente).upper().center(largura)
    end = limpar_texto(endereco).upper().center(largura)
    val_txt = f"R$ {valor:.2f}"
    status_txt = f"({pagamento})" if pagamento == PAGAMENTO_PAGO else ""
    linha_val = f"{val_txt} {status_txt}".strip().center(largura)
    corpo = f"@dahortapmesa\n\n{cli}\n\n{end}\n\n{linha_val}\n"
    return base64.b64encode(corpo.encode('ascii', 'ignore')).decode()

def parse_float(val):
    try: return float(str(val).strip().replace(",", "."))
    except: return 0.0

def ler_aba(aba, ttl=0):
    try:
        df = conn.read(worksheet=aba, ttl=ttl)
        if df is None: return pd.DataFrame()
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.fillna("")
    except: return pd.DataFrame()

def salvar_aba(aba, df):
    conn.update(worksheet=aba, data=df)
    conn.reset()

# Carregar dados
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

# --- ABA 3: MONTAGEM ---
with aba3:
    st.header("⚖️ Montagem")
    if not df_pedidos.empty:
        pend_m = df_pedidos[df_pedidos["status"].str.lower() == STATUS_PENDENTE]
        for _, row in pend_m.iterrows():
            stpg = str(row.get("pagamento")).upper()
            with st.expander(f"👤 {row['cliente']} | {stpg}", expanded=True):
                
                edit_key = f"edit_active_{row['id']}"
                if edit_key not in st.session_state: st.session_state[edit_key] = False

                if st.session_state[edit_key]:
                    st.markdown('<div class="edit-box"><b>Edição de Pedido</b>', unsafe_allow_html=True)
                    novo_n = st.text_input("Nome", row['cliente'], key=f"inp_n_{row['id']}").upper()
                    novo_e = st.text_input("Endereço", row['endereco'], key=f"inp_e_{row['id']}").upper()
                    
                    itens_edit = json.loads(row['itens'])
                    
                    st.write("➕ **Adicionar Item:**")
                    c_a1, c_a2, c_a3 = st.columns([2.5, 1, 1])
                    lista_p = ["-- Selecione --"] + sorted(df_produtos[df_produtos['status'].astype(str).str.lower() == "ativo"]['nome'].tolist())
                    p_sel = c_a1.selectbox("Produto", lista_p, key=f"add_p_{row['id']}", label_visibility="collapsed")
                    q_sel = c_a2.number_input("Qtd", 1, key=f"add_q_{row['id']}", label_visibility="collapsed")
                    
                    if c_a3.button("Adicionar", key=f"btn_a_{row['id']}"):
                        if p_sel != "-- Selecione --":
                            p_info = df_produtos[df_produtos['nome'] == p_sel].iloc[0]
                            itens_edit.append({
                                "nome": p_sel, "qtd": q_sel, "preco": parse_float(p_info['preco']), 
                                "tipo": p_info['tipo'], "subtotal": 0.0 if p_info['tipo']=="KG" else (q_sel * parse_float(p_info['preco']))
                            })
                            df_f = ler_aba("Pedidos", 0)
                            df_f.loc[df_f["id"].astype(str) == str(row["id"]), "itens"] = json.dumps(itens_edit)
                            salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()

                    st.write("---")
                    novos_itens_final = []
                    total_ed = 0.0
                    for i, it in enumerate(itens_edit):
                        c_en, c_eq, c_ed = st.columns([3, 1, 0.5])
                        c_en.write(f"{it['nome']}")
                        nq = c_eq.number_input("Q", value=int(it['qtd']), min_value=0, key=f"edq_{row['id']}_{i}", label_visibility="collapsed")
                        if nq > 0:
                            it['qtd'] = nq
                            if it['tipo'] != "KG": it['subtotal'] = nq * it['preco']
                            novos_itens_final.append(it)
                            total_ed += it['subtotal']
                        if c_ed.button("🗑️", key=f"delit_{row['id']}_{i}"):
                            itens_edit.pop(i)
                            df_f = ler_aba("Pedidos", 0)
                            df_f.loc[df_f["id"].astype(str) == str(row["id"]), "itens"] = json.dumps(itens_edit)
                            salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()

                    if st.button("💾 SALVAR ALTERAÇÕES", key=f"save_{row['id']}", type="primary", use_container_width=True):
                        df_f = ler_aba("Pedidos", 0)
                        df_f.loc[df_f["id"].astype(str) == str(row["id"]), ["cliente", "endereco", "total", "itens"]] = [novo_n, novo_e, total_ed, json.dumps(novos_itens_final)]
                        salvar_aba("Pedidos", df_f)
                        st.session_state[edit_key] = False
                        st.session_state.reload_pedidos = True; st.rerun()
                    
                    if st.button("Sair sem salvar", key=f"canc_{row['id']}", use_container_width=True):
                        st.session_state[edit_key] = False; st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                
                else:
                    if row.get('obs'): st.warning(f"⚠️ {row['obs']}")
                    st.write(f"📍 {row['endereco']}")
                    itens_m, total_m = json.loads(row['itens']), 0.0
                    for i, it in enumerate(itens_m):
                        c_i, c_v = st.columns([3.5, 1.4])
                        if str(it['tipo']).upper() == "KG":
                            val_in = c_v.number_input("R$", value=None, key=f"m_{row['id']}_{i}", label_visibility="collapsed", placeholder="0,00")
                            v_dig = parse_float(val_in) if val_in is not None else 0.0
                            it['subtotal'] = v_dig
                            if v_dig > 0 and parse_float(it.get('preco', 0)) > 0:
                                it['qtd'] = round(v_dig / parse_float(it['preco']), 3)
                            c_i.markdown(f"⚖️ {limpar_texto(it['nome'])}")
                        else:
                            c_i.markdown(f"✅ {it['qtd']}x {limpar_texto(it['nome'])}")
                            c_v.markdown(f"R$ {parse_float(it['subtotal']):.2f}")
                        total_m += parse_float(it['subtotal'])
                        st.divider()
                    
                    st.markdown(f"<div class='m-total'>TOTAL: R$ {total_m:.2f}</div>", unsafe_allow_html=True)
                    
                    c_ok, c_pg, c_edit, c_pr, c_del = st.columns([1, 1, 1, 0.5, 0.5])
                    
                    if c_ok.button("📦 OK", key=f"ok_{row['id']}"):
                        df_f = ler_aba("Pedidos", 0)
                        idx_l = df_f.index[df_f["id"].astype(str) == str(row["id"])].tolist()
                        if idx_l:
                            df_f.at[idx_l[0], "status"], df_f.at[idx_l[0], "total"], df_f.at[idx_l[0], "itens"] = STATUS_PRONTO, total_m, json.dumps(itens_m)
                            salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()
                    
                    if stpg != PAGAMENTO_PAGO and c_pg.button("💵 Pago", key=f"pg_{row['id']}"):
                        df_f = ler_aba("Pedidos", 0); df_f.loc[df_f["id"].astype(str) == str(row["id"]), "pagamento"] = PAGAMENTO_PAGO; salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()
                    
                    if c_edit.button("✏️ Editar", key=f"edit_btn_{row['id']}"):
                        st.session_state[edit_key] = True; st.rerun()

                    b64 = gerar_b64_etiqueta(row['cliente'], row['endereco'], total_m, stpg)
                    c_pr.markdown(f'<a href="intent:base64,{b64}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;" class="btn-print">🖨️</a>', unsafe_allow_html=True)
                    
                    if c_del.button("🗑️", key=f"del_{row['id']}"):
                        df_f = ler_aba("Pedidos", 0); df_f = df_f[df_f["id"].astype(str) != str(row["id"])]; salvar_aba("Pedidos", df_f); st.session_state.reload_pedidos = True; st.rerun()
