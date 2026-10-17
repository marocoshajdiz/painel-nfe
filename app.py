import streamlit as st
import xmltodict
import pandas as pd
from google import genai
from google.genai import types
import json
import math
import hashlib
import psycopg2
from urllib.parse import urlsplit
import io
import re
import time
import random
from datetime import datetime, date
from zoneinfo import ZoneInfo
import pypdf
from leitor_fiscal import ler_xml, ler_pdf, ler_imagem_ocr

st.set_page_config(page_title="Painel de Custos & DRE Spoleto - Capry", layout="wide")

# ----------------- CONTROLE DE ACESSO -----------------
USUARIO_CORRETO = st.secrets.get("LOGIN_USUARIO", "admin")
SENHA_CORRETA = st.secrets.get("LOGIN_SENHA", "")
if not SENHA_CORRETA:
    st.error("Configure LOGIN_SENHA nos Secrets do Streamlit para habilitar o acesso.")
    st.stop()

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False


def tela_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("### 🔐 Acesso ao Painel de Custos & DRE - Capry")
        st.write("Digite suas credenciais:")
        with st.form("form_login"):
            usuario = st.text_input("Usuário", placeholder="admin")
            senha = st.text_input("Senha", type="password", placeholder="Sua senha")
            if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                if usuario == USUARIO_CORRETO and senha == SENHA_CORRETA:
                    st.session_state.autenticado = True
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos!")


if not st.session_state.autenticado:
    tela_login()
    st.stop()

st.sidebar.markdown("""
<div class="capry-brand">
  <div class="capry-logo">S P O L E T O</div>
  <div class="capry-name">C A P R Y</div>
  <div class="capry-subtitle">Painel de Custos &amp; DRE</div>
</div>
<div class="capry-profile">
  <span class="capry-avatar">👤</span>
  <span><strong>Olá, administrador</strong><small>Gestão financeira</small></span>
</div>
""", unsafe_allow_html=True)

# Visual do menu lateral — não altera cálculos nem consultas ao Supabase.
st.markdown("""
<style>
:root { --capry-navy:#0b1d39; --capry-blue:#2563eb; }
section[data-testid="stSidebar"] {
  background:linear-gradient(155deg,#102b51 0%,#0b1d39 52%,#07152c 100%) !important;
  min-width:320px !important;
}
section[data-testid="stSidebar"] > div { background:transparent !important; }
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top:1.1rem; }
section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] small { color:#edf4ff; }
.capry-brand { padding:12px 12px 22px; border-bottom:1px solid #ffffff22; margin-bottom:18px; }
.capry-logo { font-size:23px; letter-spacing:2px; font-weight:800; color:#fff; white-space:nowrap; }
.capry-name { font-size:12px; letter-spacing:6px; color:#a9c8f9; margin-top:3px; }
.capry-subtitle { font-size:13px; color:#d7e6ff; margin-top:12px; }
.capry-profile { display:flex; align-items:center; gap:12px; padding:15px 12px;
 background:#ffffff12; border:1px solid #ffffff15; border-radius:15px; margin:0 3px 23px; }
.capry-avatar { display:flex; align-items:center; justify-content:center; width:43px; height:43px;
 background:#1b4e95; border-radius:13px; font-size:23px; }
.capry-profile strong { display:block; color:#fff; font-size:14px; }
.capry-profile small { display:block; color:#b9cbe5; font-size:12px; margin-top:2px; }
section[data-testid="stSidebar"] [data-testid="stSelectbox"] {
 background:#ffffff12; border:1px solid #ffffff14; padding:13px 11px 15px; border-radius:15px;
 margin-bottom:16px;
}
section[data-testid="stSidebar"] [data-testid="stSelectbox"] label p { font-weight:650; font-size:13px; }
section[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div {
 background:#f9fbff !important; border-radius:10px !important; }
section[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] * { color:#132746 !important; }
section[data-testid="stSidebar"] div[role="radiogroup"] { gap:9px; }
