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
from datetime import datetime
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
section[data-testid="stSidebar"] div[role="radiogroup"] label {
 background:#ffffff0d; border:1px solid #ffffff12; border-radius:13px;
 padding:12px 11px !important; margin:0 !important; min-height:54px;
 transition:background .15s,border-color .15s; cursor:pointer;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:hover { background:#ffffff1d; border-color:#6ba5ff80; }
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked),
section[data-testid="stSidebar"] div[role="radiogroup"] label:has([aria-checked="true"]) {
 background:linear-gradient(105deg,#2563ebaa,#123e80); border:1px solid #60a5fa;
 box-shadow:0 3px 15px #2563eb33;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child { display:none !important; }
section[data-testid="stSidebar"] div[role="radiogroup"] label p { font-size:13px; font-weight:620; line-height:1.45; }
section[data-testid="stSidebar"] [data-testid="stRadio"] > label p {
 color:#9fb5d5 !important; font-size:11px; letter-spacing:1.3px; font-weight:750; text-transform:uppercase;
}
section[data-testid="stSidebar"] div.stButton > button {
 background:#ffffff0d !important; border:1px solid #7598c3 !important;
 color:#fff !important; border-radius:12px !important; width:100%;
 min-height:46px; font-weight:650; }
section[data-testid="stSidebar"] div.stButton > button:hover { background:#2563eb44 !important; }
section[data-testid="stSidebar"] hr { border-color:#ffffff26; }
/* Botões primários em azul, sem afetar tabelas ou operações. */
.stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {
 background:#2563eb !important; border-color:#2563eb !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
div[data-testid="stCameraInput"] { width: 100% !important; max-width: 900px !important; margin: 0 auto; }
div[data-testid="stCameraInput"] video { width: 100% !important; height: 70vh !important; min-height: 480px !important; border-radius: 14px; object-fit: cover !important; border: 2px solid #2563eb; }
div[data-testid="stCameraInput"] button { padding: 0.75rem 1.5rem !important; font-size: 1.1rem !important; border-radius: 10px !important; }
</style>
""", unsafe_allow_html=True)

# ----------------- CATEGORIAS DE CLASSIFICAÇÃO MAPEADAS NO DRE -----------------
MAPA_7_CATEGORIAS = {
    "Demais Alimentos": {"dre": "Alimentos", "det": "Alimentos"},
    "Descartáveis": {"dre": "Descartáveis", "det": "Descartáveis"},
    "Limpeza": {"dre": "Material_De_Uso_E_Consumo", "det": "Material De Limpeza"},
    "Materiais de Uso e Consumo": {"dre": "Material_De_Uso_E_Consumo", "det": "Outros Materiais De Uso E Consumo"},
    "Utensílios": {"dre": "Material_De_Uso_E_Consumo", "det": "Utensílios"},
    "Bebidas": {"dre": "Bebidas", "det": "Bebidas"},
    "Horte": {"dre": "Alimentos", "det": "Alimentos"},
    "Uniformes": {"dre": "Material_De_Uso_E_Consumo", "det": "Uniformes"},
    "Uniforme": {"dre": "Material_De_Uso_E_Consumo", "det": "Uniformes"},
    "Alimentação Funcionário": {"dre": "Benefícios", "det": "Benefícios"},
}
# Classificações adicionais para notas manuais e notas interpretadas pela IA.
# Não incluir CMV consolidado, totais, receitas nem bonificações: são indicadores
# ou valores calculados, e não despesas de itens de notas fiscais.
CLASSIFICACOES_DESPESAS = {
    "FGTS": ("Pessoal", "FGTS"),
    "Gcom": ("Serviços", "Gcom"),
    "Contador": ("Serviços", "Contador"),
    "Carro da Loja": ("Despesas_Nao_Operacionais", "Carro da Loja"),
    "Fretes": ("CMV", "Fretes"),
    "Aluguel": ("Ocupação", "Aluguel"),
    "Ar condicionado": ("Ocupação", "Ar Condicionado"),
    "Condomínio": ("Ocupação", "Condomínio"),
    "Fundo de Promoção": ("Ocupação", "Fundo De Promoção"),
    "IPTU": ("Ocupação", "Iptu"),
    "Taxas e Outros": ("Ocupação", "Taxas E Outros"),
    "Salário": ("Pessoal", "Salário"),
    "Adiantamento": ("Pessoal", "Adiantamento"),
    "Encargos": ("Pessoal", "Encargos"),
    "Férias": ("Pessoal", "Férias"),
    "13 salário": ("Pessoal", "13 Salário"),
    "Provisões": ("Pessoal", "Provisões"),
    "Rescisão": ("Pessoal", "Rescisão"),
    "Outros (pessoal)": ("Pessoal", "Outros (pessoal)"),
    "Água e Esgoto": ("Utilidades", "Água E Esgoto"),
    "Energia Elétrica": ("Utilidades", "Energia Elétrica"),
    "Gás": ("Utilidades", "Gás"),
    "Internet": ("Utilidades", "Internet"),
    "Telefone": ("Utilidades", "Telefone"),
    "Outros (utilidades)": ("Utilidades", "Outros (utilidades)"),
    "Serviços": ("Serviços", "Serviços"),
    "Terceiros": ("Serviços", "Terceiros"),
    "Material de Escritório": ("Material_De_Uso_E_Consumo", "Material De Escritório"),
    "Serviço - Manutenção e Reparos": ("Manutenção", "Serviço - Manutenção E Reparos"),
    "Material - Manutenção e Reparos": ("Manutenção", "Material - Manutenção E Reparos"),
    "Comissão agregadores": ("Delivery", "Comissão Agregadores"),
    "Custo com entrega (motoqueiros)": ("Delivery", "Custo Com Entrega (Motoqueiros)"),
    "Anúncios/Propagandas": ("Marketing", "Anúncios/Propagandas"),
    "Fundo de Marketing": ("Marketing", "Fundo De Marketing"),
    "Royalties": ("Marketing", "Royalties"),
    "Custo Cartão de Crédito": ("Financeiro", "Custo Cartão De Crédito"),
    "Custo Cartão de Débito": ("Financeiro", "Custo Cartão De Débito"),
    "Imposto Federal": ("Impostos", "Imposto Federal"),
    "Imposto Estadual": ("Impostos", "Imposto Estadual"),
}
# Novas categorias gerenciais do modelo de DRE enviado pelo usuário.
# A classificação é independente da classificação de estoque/CMV.
CLASSIFICACOES_NAO_OPERACIONAIS = {
    'Despesas de Viagens': ("Despesas_Nao_Operacionais", 'Viagens'),
    'Despesas de Convenção': ("Despesas_Nao_Operacionais", 'Convenção'),
    'Rateio de Escritório Administrativo': ("Despesas_Nao_Operacionais", 'Rateio de Escritório Administrativo'),
    'Pessoal - Supervisor e Nutricionista': ("Despesas_Nao_Operacionais", 'Pessoal - Supervisor e Nutricionista'),
    'Empréstimos Bancário': ("Despesas_Nao_Operacionais", 'Empréstimos Bancário'),
    'Pronampe': ("Despesas_Nao_Operacionais", 'Pronampe'),
    'Juros de Empréstimos': ("Despesas_Nao_Operacionais", 'Juros de Empréstimos'),
    'Empréstimo Folha de Pagamento': ("Despesas_Nao_Operacionais", 'Empréstimo Folha de Pagamento'),
    'Capex': ("Despesas_Nao_Operacionais", 'Capex'),
    'Pro Labore': ("Despesas_Nao_Operacionais", 'Pro Labore'),
}
CLASSIFICACOES_DESPESAS.update(CLASSIFICACOES_NAO_OPERACIONAIS)
LISTA_CATEGORIAS_ESTOQUE = list(MAPA_7_CATEGORIAS.keys())
for nome, (grupo, detalhamento) in CLASSIFICACOES_DESPESAS.items():
    MAPA_7_CATEGORIAS[nome] = {"dre": grupo, "det": detalhamento}

LISTA_7_CATEGORIAS = list(MAPA_7_CATEGORIAS.keys())



def formatar_numero_br(valor):
    """Formata número no padrão brasileiro: 1.234,56."""
    try:
        return f"{float(valor or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "0,00"


def converter_numero_br(valor):
    """Aceita números digitados como 1234,56 ou 1.234,56."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    if not texto:
        return 0.0
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0
MODELO_GEMINI = "gemini-3.8-flash"


# ----------------- BASE DE DADOS PERSISTENTE (SUPABASE) -----------------
def conectar_db():
    """Abre uma conexão nova para cada operação, evitando conexões expiradas."""
    try:
        url = st.secrets["DATABASE_URL"]
    except (KeyError, FileNotFoundError):
        st.error("DATABASE_URL não configurada nos Secrets do Streamlit.")
        st.stop()
    if not str(url).startswith(("postgresql://", "postgres://")):
        st.error("DATABASE_URL inválida: deve começar com postgresql://")
        st.stop()
    return psycopg2.connect(str(url), connect_timeout=12, sslmode="require")


def verificar_banco():
    """Confere conexão e estrutura sem modificar dados existentes."""
    try:
        with conectar_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.notas'), to_regclass('public.lancamentos_dre')")
                tabelas = cur.fetchone()
                if not all(tabelas):
                    st.error("Tabelas não encontradas no Supabase. Confira o SQL da etapa anterior.")
                    st.stop()
    except Exception as erro:
        st.error("Não foi possível conectar ao Supabase. Confira DATABASE_URL, senha e Session pooler.")
        st.caption(f"Detalhe técnico: {type(erro).__name__}")
        st.stop()


verificar_banco()

MESES_DISPONIVEIS = [
    "2026-09", "2026-10", "2026-11", "2026-12",
    "2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06",
    "2027-07", "2027-08", "2027-09", "2027-10", "2027-11", "2027-12",
]
NOMES_MESES = {
    "2026-09": "Setembro / 2026", "2026-10": "Outubro / 2026", "2026-11": "Novembro / 2026", "2026-12": "Dezembro / 2026",
    "2027-01": "Janeiro / 2027", "2027-02": "Fevereiro / 2027", "2027-03": "Março / 2027",
    "2027-04": "Abril / 2027", "2027-05": "Maio / 2027", "2027-06": "Junho / 2027",
    "2027-07": "Julho / 2027", "2027-08": "Agosto / 2027", "2027-09": "Setembro / 2027",
    "2027-10": "Outubro / 2027", "2027-11": "Novembro / 2027", "2027-12": "Dezembro / 2027",
}

mes_ativo = st.sidebar.selectbox(
    "📅 Mês de Trabalho (DRE):",
    MESES_DISPONIVEIS,
    index=0,
    format_func=lambda m: NOMES_MESES[m],
)



# CMV por inventário: valores calculados, nunca duplicados em ajustes_dre.
CONTAS_CMV = {"CMV Consolidado": "Total"}
CATEGORIAS_CMV = {
    "Demais Alimentos": "Alimentos", "Horte": "Horte",
    "Bebidas": "Bebidas", "Descartáveis": "Descartáveis",
}
GRUPOS_CMV = ("Alimentos", "Horte", "Bebidas", "Descartáveis")


def mes_anterior(mes):
    ano, numero = map(int, mes.split("-"))
    return f"{ano - 1:04d}-12" if numero == 1 else f"{ano:04d}-{numero - 1:02d}"


def preparar_saldos_iniciais():
    """Preserva saldos antigos e permite um único saldo inicial consolidado."""
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS saldos_iniciais_cmv (
                mes_referencia TEXT NOT NULL,
                categoria TEXT NOT NULL,
                valor NUMERIC(15,2) NOT NULL CHECK (valor >= 0),
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (mes_referencia, categoria)
            )""")
            cur.execute("""ALTER TABLE saldos_iniciais_cmv DROP CONSTRAINT IF EXISTS saldos_iniciais_cmv_categoria_check""")
        conn.commit()


def consultar_saldos_iniciais(mes):
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT categoria, valor FROM saldos_iniciais_cmv WHERE mes_referencia=%s", (mes,))
            return {categoria: float(valor) for categoria, valor in cur.fetchall()}


def salvar_saldos_iniciais(mes, valor):
    if not 0 <= valor < float('inf'):
        raise ValueError('Informe um valor inicial válido e não negativo.')
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM inventarios WHERE mes_referencia=%s FOR UPDATE", (mes,))
            inv = cur.fetchone()
            if inv and inv[0] == 'FECHADO':
                raise ValueError('Reabra o inventário para alterar o estoque inicial.')
            cur.execute("""INSERT INTO saldos_iniciais_cmv (mes_referencia,categoria,valor)
                VALUES (%s,'Total',%s) ON CONFLICT (mes_referencia,categoria)
                DO UPDATE SET valor=EXCLUDED.valor, atualizado_em=NOW()""", (mes,round(valor,2)))
        conn.commit()


def calcular_valor_inventario(cur, inv_id, referencia):
    """Apura valores por grupo e exige contagem/custo para itens ativos de CMV."""
    cur.execute("""SELECT p.produto,p.categoria,p.ativo,ii.quantidade,
                          ii.custo_unitario,p.preco_unitario
                   FROM produtos_inventario p
                   LEFT JOIN inventario_itens ii ON ii.produto_id=p.id AND ii.inventario_id=%s
                   WHERE p.ativo=TRUE OR ii.id IS NOT NULL""", (inv_id,))
    totais = {grupo: 0.0 for grupo in GRUPOS_CMV}
    for nome, categoria, ativo, quantidade, custo, preco in cur.fetchall():
        if categoria not in CATEGORIAS_CMV:
            if ativo and (categoria is None or categoria == 'Não classificado'):
                raise ValueError(f"Classifique o produto '{nome}' antes de apurar o CMV.")
            continue
        if quantidade is None:
            if ativo:
                raise ValueError(f"Falta contagem de '{nome}' em {referencia}. Informe 0 quando não houver estoque.")
            continue
        custo_final = custo if custo is not None else preco
        if (custo_final is None or float(custo_final) <= 0) and float(quantidade) != 0:
            raise ValueError(f"Informe custo unitário válido para '{nome}' em {referencia}.")
        totais[CATEGORIAS_CMV[categoria]] += float(quantidade) * float(custo_final or 0)
    return totais


def apurar_cmv_automatico(mes):
    """CMV consolidado: saldo inicial total + compras elegíveis - estoque final total."""
    anterior = mes_anterior(mes)
    try:
        with conectar_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT categoria,valor FROM saldos_iniciais_cmv WHERE mes_referencia=%s", (mes,))
                manuais = {c:float(v) for c,v in cur.fetchall()}
                cur.execute("SELECT mes_referencia,id,status FROM inventarios WHERE mes_referencia IN (%s,%s)", (anterior,mes))
                inv = {r[0]:(r[1],r[2]) for r in cur.fetchall()}
                if mes not in inv or inv[mes][1] != 'FECHADO':
                    return None, f'Feche o inventário de {mes} para apurar o CMV.'
                if 'Total' in manuais:
                    inicial = manuais['Total']
                elif anterior in inv and inv[anterior][1] == 'FECHADO':
                    inicial = sum(calcular_valor_inventario(cur, inv[anterior][0], anterior).values())
                else:
                    return None, f'Informe o estoque inicial total de {mes} ou feche o inventário de {anterior}.'
                final_por_grupo = calcular_valor_inventario(cur, inv[mes][0], mes)
                final = sum(final_por_grupo.values())
                cur.execute("""SELECT detalhamento,COALESCE(SUM(valor),0)
                               FROM lancamentos_dre WHERE mes_referencia=%s
                               AND detalhamento IN ('Alimentos','Bebidas','Descartáveis')
                               GROUP BY detalhamento""", (mes,))
                compras_por_grupo = {str(k):float(v) for k,v in cur.fetchall()}
                compras = sum(compras_por_grupo.values())
                # O detalhamento 'Alimentos' inclui Horte: não adicionar Horte novamente.
                cur.execute("""SELECT COALESCE(SUM(valor),0) FROM lancamentos_dre
                               WHERE mes_referencia=%s AND classificacao='Horte'
                               AND detalhamento='Alimentos'""", (mes,))
                compras_horte = float(cur.fetchone()[0] or 0)
        return {'CMV Consolidado':round(inicial+compras-final,2),
                'Compras de Horte':round(compras_horte,2),
                'Estoque Inicial':round(inicial,2),
                'Compras Elegíveis':round(compras,2),
                'Estoque Final':round(final,2)}, None
    except ValueError as erro:
        return None,str(erro)


preparar_saldos_iniciais()

def validar_nota_para_gravacao(valor_total, lista_produtos):
    """Valida dados conferidos pelo operador antes de qualquer INSERT."""
    try:
        total = float(valor_total)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("total inválido: informe um valor numérico válido.")
    if not math.isfinite(total) or total <= 0:
        raise ValueError("O total inválido deve ser maior que zero e finito.")
    if not isinstance(lista_produtos, list) or not lista_produtos:
        raise ValueError("A nota precisa conter pelo menos um item.")
    normalizados = []
    for indice, item in enumerate(lista_produtos, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Item {indice} inválido.")
        categoria = str(item.get("Categoria", item.get("Classificacao", ""))).strip()
        if categoria not in MAPA_7_CATEGORIAS:
            raise ValueError(f"Revise a classificação do item {indice}: {categoria or 'não informada'}.")
        nome = str(item.get("Produto", "")).strip()
        if not nome:
            raise ValueError(f"Informe o produto do item {indice}.")
        valor_bruto = item.get("TotalItem", item.get("Total do Item (R$)"))
        try:
            valor = float(valor_bruto)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"Valor inválido no item {indice}.")
        if not math.isfinite(valor) or valor <= 0:
            raise ValueError(f"Valor inválido no item {indice}: deve ser maior que zero.")
        normalizados.append((nome.upper(), categoria, round(valor, 2)))
    soma = round(sum(x[2] for x in normalizados), 2)
    if abs(soma - round(total, 2)) > 0.01:
        raise ValueError("O total da nota não confere com a soma dos itens. Revise antes de lançar.")
    return total, normalizados


def salvar_nota_e_lancar_dre(mes_ref, razao_social, cnpj, valor_total, lista_produtos):
    total, normalizados = validar_nota_para_gravacao(valor_total, lista_produtos)
    # Assinatura estável para bloquear uma segunda gravação do mesmo conjunto de itens.
    assinatura = json.dumps({"mes": mes_ref, "cnpj": str(cnpj).strip(),
                            "total": round(total, 2), "itens": sorted(normalizados)},
                           ensure_ascii=False, sort_keys=True)
    chave = hashlib.sha256(assinatura.encode("utf-8")).hexdigest()
    conn = conectar_db()
    try:
        cursor = conn.cursor()
        # Lock transacional impede dois operadores de gravarem simultaneamente a mesma nota.
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (chave,))
        cursor.execute("""SELECT valor_total, itens_json, cnpj FROM notas
                          WHERE mes_referencia=%s AND cnpj=%s AND valor_total=%s""",
                       (mes_ref, cnpj, total))
        for valor_antigo, itens_antigos, cnpj_antigo in cursor.fetchall():
            try:
                antigos = json.loads(itens_antigos) if isinstance(itens_antigos, str) else itens_antigos
                _, itens_norm_antigos = validar_nota_para_gravacao(valor_antigo, antigos)
                if sorted(itens_norm_antigos) == sorted(normalizados):
                    raise ValueError("Esta nota já foi lançada neste mês. Verifique o histórico.")
            except ValueError as erro:
                if "já foi lançada" in str(erro):
                    raise
                # Notas históricas incompletas não devem impedir lançamentos novos.
                continue
        data_registo = datetime.now().strftime("%Y-%m-%d %H:%M")
        itens_json = json.dumps(lista_produtos, ensure_ascii=False)
        cursor.execute("""INSERT INTO notas
            (mes_referencia, data_registo, razao_social, cnpj, valor_total, itens_json)
            VALUES (%s, %s, %s, %s, %s, %s)""",
            (mes_ref, data_registo, razao_social, cnpj, total, itens_json))
        totais = {}
        for _, categoria, valor in normalizados:
            totais[categoria] = totais.get(categoria, 0.0) + valor
        data_hoje = datetime.now().strftime("%Y-%m-%d")
        for cat_nome, valor in totais.items():
            cfg = MAPA_7_CATEGORIAS[cat_nome]
            cursor.execute("""INSERT INTO lancamentos_dre
                (mes_referencia, data, fornecedor, descricao, valor, dre, classificacao, detalhamento)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (mes_ref, data_hoje, razao_social.upper(), cat_nome.upper(),
                 round(valor, 2), cfg["dre"], cat_nome, cfg["det"]))
        for item in lista_produtos:
            prod = str(item.get("Produto", "")).strip().upper()
            categoria = str(item.get("Categoria", item.get("Classificacao", ""))).strip()
            cursor.execute("""INSERT INTO regras_classificacao (produto, categoria)
                VALUES (%s, %s) ON CONFLICT(produto)
                DO UPDATE SET categoria=excluded.categoria""", (prod, categoria))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def carregar_regras():
    conn = conectar_db()
    try:
        c = conn.cursor()
        c.execute("SELECT produto, categoria FROM regras_classificacao")
        return {row[0]: row[1] for row in c.fetchall()}
    finally:
        conn.close()


def obter_lancamentos_mes(mes_ref):
    conn = conectar_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """SELECT id, data, fornecedor, descricao, valor, dre, classificacao, detalhamento
                   FROM lancamentos_dre WHERE mes_referencia = %s ORDER BY id DESC""",
                (mes_ref,)
            )
            nomes = [col[0] for col in cursor.description]
            linhas = cursor.fetchall()
            resultado = pd.DataFrame(linhas, columns=nomes)
            if not resultado.empty:
                resultado["valor"] = resultado["valor"].astype(float)
            return resultado
    finally:
        conn.close()


def obter_ajustes_dre(mes_ref):
    conn = conectar_db()
    try:
        c = conn.cursor()
        c.execute("SELECT conta, valor FROM ajustes_dre WHERE mes_referencia = %s", (mes_ref,))
        return {row[0]: float(row[1]) for row in c.fetchall()}
    finally:
        conn.close()


def salvar_ajustes_dre(mes_ref, dict_valores):
    conn = conectar_db()
    try:
        c = conn.cursor()
        for conta, val in dict_valores.items():
            c.execute("""
                INSERT INTO ajustes_dre (mes_referencia, conta, valor)
                VALUES (%s, %s, %s)
                ON CONFLICT(mes_referencia, conta) DO UPDATE SET valor=excluded.valor
            """, (mes_ref, conta, float(val)))
        conn.commit()
    finally:
        conn.close()


def gerar_excel_dre(nome_mes, df_dre_completo, df_lancamentos):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_dre_completo.copy().to_excel(writer, sheet_name="DRE_MENSAL", index=False)
        if not df_lancamentos.empty:
            df_lancamentos.copy().to_excel(writer, sheet_name="LANÇAMENTOS", index=False)
    output.seek(0)
    return output.getvalue()


# ----------------- CONFIGURAÇÕES IA (3 CHAVES) -----------------
def carregar_chaves_gemini():
    """Lê chaves dos Secrets sem expor seus valores."""
    chaves = []
    for nome in ("GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"):
        chave = str(st.secrets.get(nome, "")).strip()
        if chave and chave not in chaves:
            chaves.append(chave)
    # Compatibilidade com a configuração antiga, caso ainda não tenha migrado.
    if not chaves:
        antiga = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
        if antiga:
            chaves.append(antiga)
    return chaves

CHAVES_GEMINI = carregar_chaves_gemini()
if not CHAVES_GEMINI:
    st.error("Configure GEMINI_API_KEY_1, GEMINI_API_KEY_2 e GEMINI_API_KEY_3 nos Secrets.")
    st.stop()

# Mantém compatibilidade com as chamadas existentes de todas as abas.
api_key = CHAVES_GEMINI[0]

def parse_json_resposta(texto):
    if not texto:
        return None
    if isinstance(texto, (dict, list)):
        return texto
    texto = str(texto).strip()
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        pass
    # Tenta remover cercas Markdown sem aceitar texto arbitrário como resultado.
    texto_limpo = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.IGNORECASE).strip()
    try:
        return json.loads(texto_limpo)
    except (json.JSONDecodeError, TypeError):
        return None


def numero_seguro(valor, padrao=0.0):
    """Converte números retornados pela IA sem derrubar o processamento."""
    if valor is None or valor == "":
        return padrao
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("R$", "").replace(" ", "")
    # Trata formatos brasileiros como 1.234,56 e formatos como 1234.56.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return padrao


def validar_e_normalizar_resultado(dados):
    """Valida o JSON da IA e padroniza os itens; não cria itens fictícios."""
    if not isinstance(dados, dict):
        return None, "A IA não retornou um objeto JSON válido."

    itens = dados.get("itens")
    if not isinstance(itens, list):
        return None, "A resposta não contém uma lista de produtos."

    itens_validos = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        produto = str(item.get("Produto") or item.get("produto") or "").strip()
        if not produto:
            continue

        quantidade = numero_seguro(item.get("Quantidade", item.get("quantidade", 0)))
        preco = numero_seguro(item.get("PrecoUnitario", item.get("preco_unitario", 0)))
        total = numero_seguro(item.get("TotalItem", item.get("total_item", 0)))
        if total <= 0 and quantidade > 0 and preco > 0:
            total = quantidade * preco

        categoria = str(item.get("Categoria") or item.get("Classificacao") or item.get("categoria") or "Demais Alimentos").strip()
        if categoria not in LISTA_7_CATEGORIAS:
            categoria = "Demais Alimentos"

        itens_validos.append({
            "Produto": produto,
            "Quantidade": quantidade,
            "Unid": str(item.get("Unid") or item.get("unid") or "UN").strip(),
            "PrecoUnitario": preco,
            "TotalItem": total,
            "Categoria": categoria,
        })

    if not itens_validos:
        return None, "Nenhum produto foi identificado. Confira se o arquivo está legível e tente novamente."

    fornecedor = str(dados.get("razao_social") or dados.get("fornecedor") or "").strip()
    cnpj = str(dados.get("cnpj") or "").strip()
    valor_total = numero_seguro(dados.get("valor_total", dados.get("valorTotal", 0)))

    # Não substitui ausência de valor total pelo somatório sem deixar explícito:
    # se a IA não trouxe o total, o somatório dos itens é uma estimativa útil.
    soma_itens = sum(item["TotalItem"] for item in itens_validos)
    if valor_total <= 0 and soma_itens > 0:
        valor_total = soma_itens

    return {
        "razao_social": fornecedor or "Fornecedor não identificado",
        "cnpj": cnpj or "Não informado",
        "valor_total": valor_total,
        "itens": itens_validos,
    }, None


PROMPT_NOTA = """
Você é um assistente de leitura de documentos fiscais brasileiros.
Leia o documento e extraia somente informações visíveis nele. Nunca invente fornecedor,
CNPJ, produto, quantidade ou preço. Se algum campo não estiver legível, use texto vazio
ou zero para esse campo; não crie produtos fictícios.

Retorne apenas JSON válido neste formato:
{
  "razao_social": "nome do emitente/fornecedor",
  "cnpj": "CNPJ do emitente",
  "valor_total": 0.0,
  "itens": [
    {
      "Produto": "nome do produto",
      "Quantidade": 1.0,
      "Unid": "UN",
      "PrecoUnitario": 0.0,
      "TotalItem": 0.0,
      "Categoria": "Demais Alimentos"
    }
  ]
}

Cada produto deve corresponder a uma linha real do documento. Use ponto decimal para números.
Categorias permitidas: utilize apenas uma classificação da lista disponibilizada
pelo aplicativo. Para itens de alimentação, bebidas e descartáveis, mantenha as
categorias de compras correspondentes.
Use "Horte" para hortifrúti. Não confunda valor total da nota com subtotal dos produtos.
"""


def erro_temporario_gemini(erro):
    """Distingue indisponibilidade temporária de erro de configuração."""
    texto = str(erro).upper()
    return any(marca in texto for marca in (
        "503", "UNAVAILABLE", "HIGH DEMAND", "OVERLOADED",
        "429", "RESOURCE_EXHAUSTED", "RATE LIMIT",
        "500", "INTERNAL SERVER ERROR", "DEADLINE_EXCEEDED", "504",
    ))


def avisar_erro_gemini(erro):
    """Exibe código e motivo sem revelar chave de API."""
    codigo = getattr(erro, "code", None) or getattr(erro, "status_code", None)
    texto = str(erro)
    # Oculta credenciais caso o provedor as inclua no detalhe.
    for chave in CHAVES_GEMINI:
        texto = texto.replace(chave, "[CHAVE_OCULTA]")
    texto = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[CHAVE_OCULTA]", texto)
    texto = texto[:1000]
    if erro_temporario_gemini(erro):
        st.warning("A API Gemini atingiu um limite ou está temporariamente indisponível.")
    else:
        st.error("A API Gemini rejeitou a solicitação. Veja o diagnóstico abaixo.")
    st.code(f"Código: {codigo or 'não informado'}\nTipo: {type(erro).__name__}\nDetalhe: {texto}", language="text")


def erro_cota_gemini(erro):
    texto = str(erro).upper()
    return any(marca in texto for marca in (
        "429", "RESOURCE_EXHAUSTED", "RATE LIMIT", "QUOTA EXCEEDED"
    ))


def codigo_erro_gemini(erro):
    codigo = getattr(erro, "code", None) or getattr(erro, "status_code", None)
    try:
        return int(codigo)
    except (TypeError, ValueError):
        achado = re.search(r"\\b(400|401|403|404|408|429|500|502|503|504)\\b", str(erro))
        return int(achado.group(1)) if achado else None


def modelos_disponiveis_gemini(cliente):
    """Descobre modelos com generateContent para a chave atual; cache de 30 minutos."""
    modelos = []
    for item in cliente.models.list():
        nome = str(getattr(item, "name", "") or "").removeprefix("models/")
        metodos = (getattr(item, "supported_actions", None)
                   or getattr(item, "supported_generation_methods", None))
        if metodos and not any("generatecontent" in str(m).lower() for m in metodos):
            continue
        if "flash" in nome.lower() and not any(
            palavra in nome.lower() for palavra in ("image", "tts", "live", "embedding")
        ):
            modelos.append(nome)
    # Preferência por modelo configurado, se estiver realmente disponível.
    return sorted(set(modelos), key=lambda m: (m != MODELO_GEMINI, "preview" in m, m))


def chamar_gemini(conteudos, chave):
    """Alterna chaves em 429, aplica espera progressiva em 503 e descobre modelos em 404."""
    chaves = CHAVES_GEMINI
    estado = st.session_state
    bloqueios = estado.setdefault("gemini_bloqueios", {})
    agora = time.time()
    bloqueios = {k: v for k, v in bloqueios.items() if v > agora}
    estado["gemini_bloqueios"] = bloqueios
    estado["gemini_ultima_falha_servico"] = False

    # Se o serviço inteiro estiver em pausa, não repete três chamadas para cada PDF.
    pausa_servico = estado.get("gemini_pausa_servico_ate", 0)
    if pausa_servico > agora:
        estado["gemini_ultima_falha_servico"] = True
        raise RuntimeError(
            f"Gemini temporariamente indisponível. Aguarde cerca de "
            f"{int(pausa_servico - agora) + 1} segundos antes de tentar novamente."
        )

    inicio = estado.get("gemini_indice_ativo", 0) % len(chaves)
    ultimo_erro = None
    falhas_503 = 0

    for deslocamento in range(len(chaves)):
        indice = (inicio + deslocamento) % len(chaves)
        chave_atual = chaves[indice]
        identificador = hashlib.sha256(chave_atual.encode()).hexdigest()
        if bloqueios.get(identificador, 0) > time.time():
            continue

        cliente = genai.Client(
            api_key=chave_atual,
            http_options=types.HttpOptions(
                timeout=25000,
                retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )
        # O cache de modelos é específico de cada chave.
        cache_modelos = estado.setdefault("gemini_modelos_cache", {})
        registro = cache_modelos.get(identificador, {})
        if registro.get("ate", 0) > time.time():
            modelos = registro["modelos"]
        else:
            modelos = [MODELO_GEMINI]

        tentados = set()
        while modelos:
            modelo = modelos.pop(0)
            if modelo in tentados:
                continue
            tentados.add(modelo)
            try:
                resposta = cliente.models.generate_content(
                    model=modelo,
                    contents=conteudos,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                resultado = parse_json_resposta(resposta.text if resposta else None)
                if resultado is None:
                    raise ValueError("A IA não retornou JSON válido.")
                estado["gemini_indice_ativo"] = indice
                estado["gemini_ultima_falha_servico"] = False
                estado.pop("gemini_pausa_servico_ate", None)
                st.caption(f"🔑 Leitura concluída: API {indice + 1}, modelo {modelo}.")
                return resultado
            except Exception as erro:
                ultimo_erro = erro
                codigo = codigo_erro_gemini(erro)
                texto = str(erro).upper()

                if codigo == 404:
                    try:
                        descobertos = modelos_disponiveis_gemini(cliente)
                        cache_modelos[identificador] = {
                            "modelos": descobertos, "ate": time.time() + 1800
                        }
                        modelos = [m for m in descobertos if m not in tentados][:3]
                        if modelos:
                            st.info(f"API {indice + 1}: modelo não disponível. Tentando outro modelo listado pelo Google.")
                            continue
                    except Exception as erro_lista:
                        st.warning(f"API {indice + 1}: não foi possível consultar os modelos disponíveis ({type(erro_lista).__name__}).")
                    break

                if codigo == 429 or erro_cota_gemini(erro):
                    diario = any(x in texto for x in (
                        "PER DAY", "PER_DAY", "DAILY", "REQUESTS_PER_DAY"
                    ))
                    bloqueios[identificador] = time.time() + (86400 if diario else 65)
                    estado["gemini_bloqueios"] = bloqueios
                    st.warning(f"API {indice + 1}: cota atingida (429). Tentando outra chave.")
                    break

                if codigo in (500, 502, 503, 504) or any(
                    x in texto for x in ("TIMEOUT", "TIMED OUT", "DEADLINE_EXCEEDED")
                ):
                    if codigo == 503:
                        falhas_503 += 1
                    st.warning(f"API {indice + 1}: serviço temporariamente indisponível ({codigo or 'timeout'}).")
                    # Uma espera curta, progressiva, antes de testar a próxima chave.
                    if deslocamento < len(chaves) - 1:
                        time.sleep(min(2 ** deslocamento, 4))
                    break

                # Erros 400/401/403 e respostas inválidas não são falhas de cota.
                raise

    estado["gemini_ultima_falha_servico"] = True
    if falhas_503 >= len(chaves):
        estado["gemini_pausa_servico_ate"] = time.time() + 90
        st.warning("Modelo sobrecarregado nas três APIs. Novas tentativas ficam pausadas por 90 segundos.")
    if ultimo_erro is not None:
        raise ultimo_erro
    raise RuntimeError("As três chaves estão temporariamente indisponíveis ou sem cota.")

def processar_multiplas_imagens_com_ia(lista_fotos_bytes, chave):
    conteudos = [PROMPT_NOTA + "\nAnalise todas as imagens como páginas da mesma nota, se fizerem parte do mesmo documento."]
    for dados_foto in lista_fotos_bytes:
        # Detecta o tipo real da imagem pelo cabeçalho para não tratar PNG/WebP como JPEG.
        if dados_foto.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif dados_foto.startswith(b"RIFF") and dados_foto[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            mime = "image/jpeg"
        conteudos.append(types.Part.from_bytes(data=dados_foto, mime_type=mime))

    try:
        resultado = chamar_gemini(conteudos, chave)
        normalizado, erro = validar_e_normalizar_resultado(resultado)
        if erro:
            st.error(erro)
            return None
        return normalizado
    except Exception as e:
        avisar_erro_gemini(e)
        return None


def processar_pdf_com_ia(arquivo_bytes, nome_arq, chave):
    """Envia o PDF original para a IA, inclusive quando é um PDF digitalizado."""
    try:
        conteudos = [
            PROMPT_NOTA + f'\nAnalise o arquivo PDF chamado "{nome_arq}". Extraia os dados de todas as páginas.'
            ,
            types.Part.from_bytes(data=arquivo_bytes, mime_type="application/pdf"),
        ]
        resultado = chamar_gemini(conteudos, chave)
        normalizado, erro = validar_e_normalizar_resultado(resultado)
        if erro:
            st.error(erro)
            return None
        return normalizado
    except Exception as e:
        avisar_erro_gemini(e)
        return None


def processar_texto_com_ia(texto, nome_arq, chave):
    if not texto or not texto.strip():
        st.warning("O arquivo não contém texto extraível. Se for um PDF digitalizado, a leitura direta do PDF será usada.")
        return None
    prompt = (
        PROMPT_NOTA
        + f'\nAnalise o texto extraído do arquivo "{nome_arq}". '
        + "Extraia cada linha de produto visível. Não invente informações.\nTEXTO:\n"
        + texto[:30000]
    )
    try:
        resultado = chamar_gemini([prompt], chave)
        normalizado, erro = validar_e_normalizar_resultado(resultado)
        if erro:
            st.error(erro)
            return None
        return normalizado
    except Exception as e:
        avisar_erro_gemini(e)
        return None


def categorizar_nomes_xml(nomes, chave):
    regras = carregar_regras()
    mapa = {n: regras[n.strip().upper()] for n in nomes if n.strip().upper() in regras}
    faltam = [n for n in nomes if n.strip().upper() not in regras]
    if faltam:
        try:
            prompt = f"""
Classifique cada produto estritamente entre {json.dumps(LISTA_7_CATEGORIAS, ensure_ascii=False)}.
Use somente as categorias fornecidas. Retorne apenas JSON no formato
{{"nome exato do produto": "Categoria"}}.
Produtos: {json.dumps(faltam, ensure_ascii=False)}
"""
            resposta = chamar_gemini([prompt], chave)
            if isinstance(resposta, dict):
                for nome, categoria in resposta.items():
                    if categoria in LISTA_7_CATEGORIAS:
                        mapa[nome] = categoria
        except Exception as e:
            st.warning(f"Não foi possível classificar alguns produtos do XML; eles ficarão em Demais Alimentos. Detalhe: {e}")
    return mapa


# ----------------- GERENCIAMENTO DE SESSÃO -----------------
if "fotos_acumuladas" not in st.session_state:
    st.session_state.fotos_acumuladas = []
if "dados_extraidos" not in st.session_state:
    st.session_state.dados_extraidos = None
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "fila_notas_individuais" not in st.session_state:
    st.session_state.fila_notas_individuais = []
if "falhas_notas_lote" not in st.session_state:
    st.session_state.falhas_notas_lote = []


def resetar_processamento_nota():
    st.session_state.fotos_acumuladas = []
    st.session_state.dados_extraidos = None
    st.session_state.uploader_key += 1


def avancar_fila_notas():
    """Abre a próxima nota já extraída; nunca mistura fornecedores ou itens."""
    fila = st.session_state.fila_notas_individuais
    if fila:
        proxima = fila.pop(0)
        st.session_state.dados_extraidos = proxima["dados"]
        st.session_state["nome_nota_ativa"] = proxima["nome"]
        st.session_state.uploader_key += 1
    else:
        resetar_processamento_nota()
        st.session_state.pop("nome_nota_ativa", None)


def processar_documento_fiscal_individual(doc, api_key):
    """Processa um arquivo por vez; retorna a nota, sem gravar ou misturar fornecedores."""
    ext = doc.name.rsplit(".", 1)[-1].lower()
    resultado_documento = None
    if ext == "xml":
        try:
            data = xmltodict.parse(doc.getvalue())
            raiz = data.get("nfeProc", data)
            inf = raiz.get("NFe", {}).get("infNFe", {})
            if not inf:
                raise ValueError("O XML não parece conter uma NF-e no formato esperado.")
            emit = inf.get("emit", {})
            tot = inf.get("total", {}).get("ICMSTot", {})
            det = inf.get("det", [])
            if isinstance(det, dict):
                det = [det]
            nomes = [i.get("prod", {}).get("xProd", "") for i in det]
            mapa = categorizar_nomes_xml(nomes, api_key)
            itens_x = []
            for i in det:
                p = i.get("prod", {})
                nome = p.get("xProd", "").strip()
                if not nome:
                    continue
                itens_x.append({
                    "Categoria": mapa.get(nome, "Demais Alimentos"),
                    "Produto": nome,
                    "Quantidade": numero_seguro(p.get("qCom")),
                    "Unid": p.get("uCom", "UN"),
                    "PrecoUnitario": numero_seguro(p.get("vUnCom")),
                    "TotalItem": numero_seguro(p.get("vProd")),
                })
            if not itens_x:
                raise ValueError("Nenhum produto foi encontrado no XML.")
            total_xml = numero_seguro(tot.get("vNF"))
            soma_produtos_xml = round(sum(item["TotalItem"] for item in itens_x), 2)
            if abs(total_xml - soma_produtos_xml) > 0.01:
                st.warning(
                    f"O total fiscal do XML (R$ {formatar_numero_br(total_xml)}) difere "
                    f"da soma dos produtos (R$ {formatar_numero_br(soma_produtos_xml)}). "
                    "Confira descontos, fretes e outros valores antes de confirmar."
                )
            resultado_documento = {
                "razao_social": emit.get("xNome", "Fornecedor não identificado"),
                "cnpj": emit.get("CNPJ") or emit.get("CPF") or "Não informado",
                "valor_total": total_xml,
                "itens": itens_x,
            }
            return resultado_documento
        except Exception as e:
            st.error(f"Erro ao ler XML: {e}")

    elif ext == "pdf":
        try:
            bytes_pdf = doc.getvalue()
            # Tenta primeiro a leitura direta por visão da IA. Isso também permite PDFs digitalizados.
            with st.spinner("🤖 Analisando o PDF e extraindo os produtos..."):
                res_pdf = processar_pdf_com_ia(bytes_pdf, doc.name, api_key)

            # Se o modelo/endpoint não aceitar PDF, tenta o texto extraído como alternativa.
            if not res_pdf and not st.session_state.get("gemini_ultima_falha_servico", False):
                try:
                    reader = pypdf.PdfReader(io.BytesIO(bytes_pdf))
                    texto_pdf = "\n".join(page.extract_text() or "" for page in reader.pages)
                    if texto_pdf.strip():
                        with st.spinner("Tentando novamente usando o texto extraído do PDF..."):
                            res_pdf = processar_texto_com_ia(texto_pdf, doc.name, api_key)
                except Exception as e:
                    st.warning(f"Não foi possível extrair texto alternativo do PDF: {e}")

            if not res_pdf:
                st.info("A IA não conseguiu ler o PDF. Tentando extração fiscal local...")
                try:
                    res_pdf = ler_pdf(bytes_pdf, carregar_regras())
                    st.warning("Leitura local: confira todos os itens e compare o total com a nota original antes de salvar.")
                except Exception as erro_fallback:
                    st.warning(f"Leitor fiscal local não concluiu a leitura: {erro_fallback}")
            if res_pdf:
                resultado_documento = res_pdf
                st.success(f"PDF lido: {len(res_pdf['itens'])} produto(s) identificado(s).")
                return resultado_documento
            else:
                st.error("Não foi possível identificar produtos válidos nesse PDF. Nenhum item fictício foi criado. Confira a qualidade do documento e tente novamente.")
        except Exception as e:
            st.error(f"Erro ao processar PDF: {e}")

    elif ext in ["xlsx", "xls"]:
        try:
            df_planilha = pd.read_excel(doc)
            if df_planilha.empty:
                raise ValueError("A planilha está vazia.")
            texto_excel = df_planilha.head(100).to_string(index=False)
            res_xl = processar_texto_com_ia(texto_excel, doc.name, api_key)
            if res_xl:
                resultado_documento = res_xl
                st.success(f"Planilha lida: {len(res_xl['itens'])} produto(s) identificado(s).")
                return resultado_documento
            else:
                st.error("Não foi possível identificar produtos válidos na planilha. Nenhum item fictício foi criado.")
        except Exception as e:
            st.error(f"Erro ao ler Excel: {e}")

    return resultado_documento


# ----------------- NAVEGAÇÃO -----------------
menu = st.sidebar.radio("Módulo:", [
    f"📊 DRE Spoleto ({NOMES_MESES[mes_ativo]})",
    "📸 Escanear & Alimentar Nota",
    "📝 Lançamentos do Mês",
    "🧠 Regras Inteligentes",
    "📋 Contagem de Estoque",
    "📦 Inventário e Produtos",
])

st.sidebar.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
if st.sidebar.button("↪  Sair do Sistema", key="capry_sair", use_container_width=True):
    st.session_state.autenticado = False
    st.rerun()

# ==============================================================================
# 1. ABA DO DRE OFICIAL
# ==============================================================================
if menu.startswith("📊 DRE Spoleto"):
    st.subheader(f"📊 Demonstrativo de Resultados (DRE) — {NOMES_MESES[mes_ativo]}")
    st.write("Insira e ajuste os valores de todas as contas diretamente na tabela abaixo. Os subtotais e resultados serão recalculados.")

    df_l = obter_lancamentos_mes(mes_ativo)
    somas_escaneadas = df_l.groupby("detalhamento")["valor"].sum().to_dict() if not df_l.empty else {}
    # Indicadores de compras: independem do fechamento do inventário.
    # A classificação Horte possui detalhamento Alimentos, portanto não pode
    # ser somada uma segunda vez ao total de alimentos.
    categorias_compras = ("Demais Alimentos", "Horte", "Bebidas", "Descartáveis")
    compras_por_categoria = (
        df_l[df_l["classificacao"].isin(categorias_compras)]
        .groupby("classificacao")["valor"].sum().to_dict()
        if not df_l.empty else {}
    )
    compras_alimentos = float(compras_por_categoria.get("Demais Alimentos", 0))
    compras_horte = float(compras_por_categoria.get("Horte", 0))
    compras_bebidas = float(compras_por_categoria.get("Bebidas", 0))
    compras_descartaveis = float(compras_por_categoria.get("Descartáveis", 0))
    total_compras_cmv = sum((compras_alimentos, compras_horte, compras_bebidas, compras_descartaveis))
    ajustes_banco = obter_ajustes_dre(mes_ativo)
    cmv_auto, aviso_cmv = apurar_cmv_automatico(mes_ativo)
    if aviso_cmv:
        st.info("📦 CMV automático pendente: " + aviso_cmv + " Até o fechamento, compras e fretes são considerados provisoriamente no resultado.")
    else:
        st.success("📦 CMV consolidado calculado pelo inventário fechado: alimentos, Horte, bebidas e descartáveis.")
        if cmv_auto["CMV Consolidado"] < 0:
            st.warning("Há CMV negativo. Confira compras, quantidades e custos antes de utilizar a DRE.")

    CONTAS_DRE_PAINEL = [
        ("Faturamento Balcão", None, 0.0),
        ("Faturamento Delivery", None, 0.0),
        ("Imposto Federal", "Imposto Federal", 0.0),
        ("Imposto Estadual", "Imposto Estadual", 0.0),
        ("CMV Consolidado", None, 0.0),
        ("Fretes", "Fretes", 0.0),
        ("Aluguel", "Aluguel", 0.0),
        ("Ar condicionado", "Ar Condicionado", 0.0),
        ("Condomínio", "Condomínio", 0.0),
        ("Fundo de Promoção", "Fundo De Promoção", 0.0),
        ("IPTU", "Iptu", 0.0),
        ("Taxas e Outros", "Taxas E Outros", 0.0),
        ("Salário", "Salário", 0.0),
        ("Adiantamento", "Adiantamento", 0.0),
        ("Benefícios (Alimentação Funcionários)", "Benefícios", 0.0),
        ("Encargos", "Encargos", 0.0),
        ("FGTS", "FGTS", 0.0),
        ("Férias", "Férias", 0.0),
        ("13 salário", "13 Salário", 0.0),
        ("Provisões", "Provisões", 0.0),
        ("Rescisão", "Rescisão", 0.0),
        ("Outros (pessoal)", "Outros (pessoal)", 0.0),
        ("Água e Esgoto", "Água E Esgoto", 0.0),
        ("Energia Elétrica", "Energia Elétrica", 0.0),
        ("Gás", "Gás", 0.0),
        ("Internet", "Internet", 0.0),
        ("Telefone", "Telefone", 0.0),
        ("Outros (utilidades)", "Outros (utilidades)", 0.0),
        ("Serviços", "Serviços", 0.0),
        ("Terceiros", "Terceiros", 0.0),
        ("Gcom", "Gcom", 0.0),
        ("Contador", "Contador", 0.0),
        ("Material de Escritório", "Material De Escritório", 0.0),
        ("Material de Limpeza", "Material De Limpeza", 0.0),
        ("Uniformes", "Uniformes", 0.0),
        ("Utensílios", "Utensílios", 0.0),
        ("Outros Materiais de Uso e Consumo", "Outros Materiais De Uso E Consumo", 0.0),
        ("Serviço - Manutenção e Reparos", "Serviço - Manutenção E Reparos", 0.0),
        ("Material - Manutenção e Reparos", "Material - Manutenção E Reparos", 0.0),
        ("Taxa de entrega arrecadada", None, 0.0),
        ("Comissão agregadores", "Comissão Agregadores", 0.0),
        ("Custo com entrega (motoqueiros)", "Custo Com Entrega (Motoqueiros)", 0.0),
        ("Anúncios/Propagandas", "Anúncios/Propagandas", 0.0),
        ("Fundo de Marketing", "Fundo De Marketing", 0.0),
        ("Royalties", "Royalties", 0.0),
        ("Custo Cartão de Crédito", "Custo Cartão De Crédito", 0.0),
        ("Custo Cartão de Débito", "Custo Cartão De Débito", 0.0),
        ("Total Bonificação", None, 0.0),
        ("Carro da Loja", "Carro da Loja", 0.0),
        ('Despesas de Viagens', 'Viagens', 0.0),
        ('Despesas de Convenção', 'Convenção', 0.0),
        ('Rateio de Escritório Administrativo', 'Rateio de Escritório Administrativo', 0.0),
        ('Pessoal - Supervisor e Nutricionista', 'Pessoal - Supervisor e Nutricionista', 0.0),
        ('Empréstimos Bancário', 'Empréstimos Bancário', 0.0),
        ('Pronampe', 'Pronampe', 0.0),
        ('Juros de Empréstimos', 'Juros de Empréstimos', 0.0),
        ('Empréstimo Folha de Pagamento', 'Empréstimo Folha de Pagamento', 0.0),
        ('Capex', 'Capex', 0.0),
        ('Pro Labore', 'Pro Labore', 0.0),

    ]

    lista_linhas_editaveis = []
    for nome_conta, chave_det, val_padrao in CONTAS_DRE_PAINEL:
        val_escaneado = float(somas_escaneadas.get(chave_det, 0.0)) if chave_det else 0.0
        val_ajuste = float(ajustes_banco.get(nome_conta, val_padrao))
        val_final = (cmv_auto[nome_conta] if cmv_auto is not None and nome_conta in CONTAS_CMV
                     else (0.0 if nome_conta in CONTAS_CMV else val_escaneado + val_ajuste))
        lista_linhas_editaveis.append({"CONTA": nome_conta, "VALOR (R$)": formatar_numero_br(round(val_final, 2))})

    df_base_editavel = pd.DataFrame(lista_linhas_editaveis)
    st.write("👇 **Tabela de Lançamentos do DRE (digite os valores com vírgula decimal, por exemplo 1.234,56, e depois clique em Salvar):**")
    qtd_lanc = len(df_l)
    df_dre_editado = st.data_editor(
        df_base_editavel,
        column_config={
            "CONTA": st.column_config.TextColumn("Conta / Indicador", disabled=True),
            "VALOR (R$)": st.column_config.TextColumn("VALOR (R$) — padrão 1.234,56", help="O CMV é automático após fechamento; demais valores podem ser editados."),
        },
        use_container_width=True,
        num_rows="fixed",
        height=520,
        key=f"editor_dre_{mes_ativo}_v{qtd_lanc}",
    )

    # Reservamos o espaço da própria tabela DRE logo após o editor. O conteúdo
    # é calculado mais abaixo, mas renderizado aqui em cada rerun do Streamlit.
    painel_dre_atualizado = st.empty()

    # Resumo reativo: o Streamlit recalcula quando a edição de uma célula é
    # confirmada (Enter ou clique fora). Não é necessário clicar em Salvar.
    valores_ao_vivo = {
        str(linha["CONTA"]): converter_numero_br(linha["VALOR (R$)"])
        for _, linha in df_dre_editado.iterrows()
    }
    def valor_ao_vivo(nome):
        return float(valores_ao_vivo.get(nome, 0.0) or 0.0)

    grupos_operacionais_ao_vivo = {
        "Impostos": ["Imposto Federal", "Imposto Estadual"],
        "Ocupação": ["Aluguel", "Ar condicionado", "Condomínio", "Fundo de Promoção", "IPTU", "Taxas e Outros"],
        "Pessoal": ["Salário", "Adiantamento", "Benefícios (Alimentação Funcionários)", "Encargos", "FGTS", "Férias", "13 salário", "Provisões", "Rescisão", "Outros (pessoal)"],
        "Utilidades": ["Água e Esgoto", "Energia Elétrica", "Gás", "Internet", "Telefone", "Outros (utilidades)"],
        "Serviços": ["Serviços", "Terceiros", "Gcom", "Contador"],
        "Materiais de uso e consumo": ["Material de Escritório", "Material de Limpeza", "Uniformes", "Utensílios", "Outros Materiais de Uso e Consumo"],
        "Manutenção": ["Serviço - Manutenção e Reparos", "Material - Manutenção e Reparos"],
        "Delivery": ["Comissão agregadores", "Custo com entrega (motoqueiros)"],
        "Marketing e franqueador": ["Anúncios/Propagandas", "Fundo de Marketing", "Royalties"],
        "Financeiro": ["Custo Cartão de Crédito", "Custo Cartão de Débito"],
    }
    subtotais_ao_vivo = {
        grupo: sum(valor_ao_vivo(conta) for conta in contas)
        for grupo, contas in grupos_operacionais_ao_vivo.items()
    }
    subtotais_ao_vivo["Delivery"] -= valor_ao_vivo("Taxa de entrega arrecadada")
    subtotais_ao_vivo["Estoque/CMV e fretes"] = (
        float(cmv_auto.get("CMV Consolidado", 0.0)) if cmv_auto else total_compras_cmv
    ) + valor_ao_vivo("Fretes")
    total_operacional_ao_vivo = sum(subtotais_ao_vivo.values())
    contas_nao_operacionais_ao_vivo = [
        "Carro da Loja", "Despesas de Viagens", "Despesas de Convenção",
        "Rateio de Escritório Administrativo", "Pessoal - Supervisor e Nutricionista",
        "Empréstimos Bancário", "Pronampe", "Juros de Empréstimos",
        "Empréstimo Folha de Pagamento", "Capex", "Pro Labore",
    ]
    total_nao_operacional_ao_vivo = sum(
        valor_ao_vivo(conta) for conta in contas_nao_operacionais_ao_vivo
    )
    st.info(
        "A tabela DRE completa, logo abaixo, atualiza os subtotais e resultados "
        "quando você confirma uma célula. As alterações só são gravadas ao clicar em Salvar."
    )

    col_save_dre, _ = st.columns([2, 3])
    with col_save_dre:
        if st.button("💾 Salvar Lançamentos e Ajustes do DRE na Base de Dados", type="primary", use_container_width=True):
            novos_ajustes = {}
            for conta, valor in zip(df_dre_editado["CONTA"], df_dre_editado["VALOR (R$)"]):
                conta = str(conta)
                if conta == "CMV Consolidado":
                    continue  # CMV apurado não é ajuste manual.
                base_nota = float(somas_escaneadas.get(next((det for nome, det, _ in CONTAS_DRE_PAINEL if nome == conta), None), 0.0))
                novos_ajustes[conta] = converter_numero_br(valor) - base_nota
            salvar_ajustes_dre(mes_ativo, novos_ajustes)
            st.success("✅ Valores gravados com sucesso!")
            st.rerun()

    v_map = {str(conta): converter_numero_br(valor) for conta, valor in zip(df_dre_editado["CONTA"], df_dre_editado["VALOR (R$)"])}
    if cmv_auto is not None:
        v_map.update(cmv_auto)  # A DRE nunca usa edição manual no lugar do CMV fechado.


    def v(k):
        return float(v_map.get(k, 0.0) or 0.0)

    fat_balcao = v("Faturamento Balcão")
    fat_delivery = v("Faturamento Delivery")
    venda_bruta = fat_balcao + fat_delivery
    imp_fed = v("Imposto Federal")
    imp_est = v("Imposto Estadual")
    rec_liquida = venda_bruta - (imp_fed + imp_est)

    cmv_consolidado = cmv_auto["CMV Consolidado"] if cmv_auto else 0.0
    cmv_fret = v("Fretes")
    # Enquanto o inventário não estiver fechado, as compras são uma
    # aproximação gerencial do CMV; não apresentamos lucro bruto inflado.
    cmv_para_resultado = cmv_consolidado if cmv_auto is not None else total_compras_cmv
    total_cmv = cmv_para_resultado + cmv_fret
    lucro_bruto = rec_liquida - total_cmv

    total_ocup = v("Aluguel") + v("Ar condicionado") + v("Condomínio") + v("Fundo de Promoção") + v("IPTU") + v("Taxas e Outros")
    total_pess = (
        v("Salário") + v("Adiantamento") + v("Benefícios (Alimentação Funcionários)") +
        v("Encargos") + v("FGTS") + v("Férias") + v("13 salário") + v("Provisões") + v("Rescisão") + v("Outros (pessoal)")
    )
    total_util = v("Água e Esgoto") + v("Energia Elétrica") + v("Gás") + v("Internet") + v("Telefone") + v("Outros (utilidades)")
    total_serv = v("Serviços") + v("Terceiros") + v("Gcom") + v("Contador")
    total_mat = (
        v("Material de Escritório") + v("Material de Limpeza") + v("Uniformes") +
        v("Utensílios") + v("Outros Materiais de Uso e Consumo")
    )
    total_manut = v("Serviço - Manutenção e Reparos") + v("Material - Manutenção e Reparos")
    total_deliv = (v("Comissão agregadores") + v("Custo com entrega (motoqueiros)")) - v("Taxa de entrega arrecadada")
    total_mkt = v("Anúncios/Propagandas") + v("Fundo de Marketing") + v("Royalties")
    total_fin = v("Custo Cartão de Crédito") + v("Custo Cartão de Débito")
    # Gestão provisória: antes do fechamento do inventário, usar as compras
    # como referência TEMPORÁRIA de gasto operacional. Após o fechamento,
    # substituir pelas informações de CMV consolidado, sem duplicar compras.
    compras_provisorias = total_compras_cmv if cmv_auto is None else 0.0
    custo_estoque_para_despesas = (cmv_consolidado if cmv_auto is not None else compras_provisorias)
    grupos_operacionais = {
        "Impostos": imp_fed + imp_est,
        ("CMV consolidado + fretes" if cmv_auto is not None
         else "Compras do mês (provisório) + fretes"): custo_estoque_para_despesas + cmv_fret,
        "Ocupação": total_ocup,
        "Pessoal (inclui FGTS)": total_pess,
        "Utilidades": total_util,
        "Serviços (inclui Gcom e Contador)": total_serv,
        "Materiais de uso e consumo": total_mat,
        "Manutenção": total_manut,
        "Delivery": total_deliv,
        "Marketing e franqueador": total_mkt,
        "Financeiro": total_fin,
    }
    total_despesas_operacionais = sum(grupos_operacionais.values())
    res_operacional = venda_bruta - total_despesas_operacionais
    bonificacao = v("Total Bonificação")
    resultado_final_operacional = res_operacional + bonificacao

    total_viagens = v("Despesas de Viagens") + v("Despesas de Convenção")
    total_administrativas = (
        v("Rateio de Escritório Administrativo") +
        v("Pessoal - Supervisor e Nutricionista")
    )
    total_emprestimos = (
        v("Empréstimos Bancário") + v("Pronampe") +
        v("Juros de Empréstimos") + v("Empréstimo Folha de Pagamento")
    )
    total_investimentos = v("Capex")
    total_pro_labore = v("Pro Labore")
    despesas_nao_operacionais = (
        v("Carro da Loja") + total_viagens + total_administrativas +
        total_emprestimos + total_investimentos + total_pro_labore
    )
    grupos_nao_operacionais = {
        "Viagens": total_viagens,
        "Despesas administrativas": total_administrativas,
        "Empréstimos": total_emprestimos,
        "Investimentos": total_investimentos,
        "Pró-labore": total_pro_labore,
        "Carro da Loja": v("Carro da Loja"),
    }
    despesas_nao_operacionais = sum(grupos_nao_operacionais.values())
    total_geral_despesas = total_despesas_operacionais + despesas_nao_operacionais
    res_final = resultado_final_operacional - despesas_nao_operacionais

    def pct(val):
        return f"{(val / venda_bruta) * 100:.2f}%" if venda_bruta > 0 else "0.00%"

    st.markdown("---")
    st.write("### 📈 Visão Consolidada em Tempo Real")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔹 Venda Bruta", f"R$ {venda_bruta:,.2f}")
    c2.metric("📦 CMV consolidado" if cmv_auto is not None else "📦 Compras + fretes (provisório)",
              f"R$ {formatar_numero_br(total_cmv)}", delta=pct(total_cmv), delta_color="inverse")
    st.metric("🥬 Compras de Horte (indicador)", f"R$ {formatar_numero_br(compras_horte)}")
    st.caption("Antes do fechamento, compras + fretes substituem provisoriamente o CMV no resultado; depois, usa-se somente o CMV consolidado + fretes.")
    st.markdown("#### 🧾 Compras do mês para composição do CMV")
    col_a, col_h, col_b, col_d, col_t = st.columns(5)
    col_a.metric("Alimentos", f"R$ {formatar_numero_br(compras_alimentos)}")
    col_h.metric("Horte", f"R$ {formatar_numero_br(compras_horte)}")
    col_b.metric("Bebidas", f"R$ {formatar_numero_br(compras_bebidas)}")
    col_d.metric("Descartáveis", f"R$ {formatar_numero_br(compras_descartaveis)}")
    col_t.metric("Total de compras", f"R$ {formatar_numero_br(total_compras_cmv)}")
    if cmv_auto is None:
        st.warning("Resultado e lucro bruto provisórios: usamos compras + fretes como estimativa do CMV até fechar o inventário. Compras não são necessariamente iguais ao custo das mercadorias vendidas.")
    c3.metric("🔹 Lucro Bruto", f"R$ {lucro_bruto:,.2f}", delta=pct(lucro_bruto))
    c4.metric("💰 Resultado Final", f"R$ {res_final:,.2f}", delta=pct(res_final))

    estrutura_dre_spoleto = [
        {"CONTA": "🔹 VENDA BRUTA", "VALOR": venda_bruta, "%": "100.00%"},
        {"CONTA": "  • Faturamento Balcão", "VALOR": fat_balcao, "%": pct(fat_balcao)},
        {"CONTA": "  • Faturamento Delivery", "VALOR": fat_delivery, "%": pct(fat_delivery)},
        {"CONTA": "(-) Imposto Federal", "VALOR": imp_fed, "%": pct(imp_fed)},
        {"CONTA": "(-) Imposto Estadual", "VALOR": imp_est, "%": pct(imp_est)},
        {"CONTA": "🔹 RECEITA LÍQUIDA", "VALOR": rec_liquida, "%": pct(rec_liquida)},
        {"CONTA": "----------------------------------------", "VALOR": None, "%": ""},
        {"CONTA": "📦 C M V (Custo de Mercadoria Vendida)" if cmv_auto is not None else "📦 COMPRAS + FRETES (CMV provisório)", "VALOR": total_cmv, "%": pct(total_cmv)},
        {"CONTA": "  • CMV Consolidado (pendente de fechamento)" if cmv_auto is None else "  • CMV Consolidado (Alimentos, Horte, Bebidas e Descartáveis)", "VALOR": None if cmv_auto is None else cmv_consolidado, "%": "" if cmv_auto is None else pct(cmv_consolidado)},
        {"CONTA": "  • Compras de Alimentos (informativo)", "VALOR": compras_alimentos, "%": pct(compras_alimentos)},
        {"CONTA": "  • Compras de Horte (informativo)", "VALOR": compras_horte, "%": pct(compras_horte)},
        {"CONTA": "  • Compras de Bebidas (informativo)", "VALOR": compras_bebidas, "%": pct(compras_bebidas)},
        {"CONTA": "  • Compras de Descartáveis (informativo)", "VALOR": compras_descartaveis, "%": pct(compras_descartaveis)},
        {"CONTA": ("  • TOTAL COMPRAS PARA CMV (informativo; já substituído pelo CMV)"
                    if cmv_auto is not None else
                    "  • TOTAL COMPRAS DO MÊS (incluído provisoriamente nas despesas)"),
         "VALOR": total_compras_cmv, "%": pct(total_compras_cmv)},
        {"CONTA": "  • Fretes", "VALOR": cmv_fret, "%": pct(cmv_fret)},
        {"CONTA": "🔹 LUCRO BRUTO", "VALOR": lucro_bruto, "%": pct(lucro_bruto)},
        {"CONTA": "----------------------------------------", "VALOR": None, "%": ""},
        {"CONTA": "🏢 TOTAL OCUPAÇÃO", "VALOR": total_ocup, "%": pct(total_ocup)},
        {"CONTA": "  • Condomínio", "VALOR": v("Condomínio"), "%": pct(v("Condomínio"))},
        {"CONTA": "  • Aluguel / Outros", "VALOR": total_ocup - v("Condomínio"), "%": pct(total_ocup - v("Condomínio"))},
        {"CONTA": "👥 TOTAL PESSOAL", "VALOR": total_pess, "%": pct(total_pess)},
        {"CONTA": "  • FGTS", "VALOR": v("FGTS"), "%": pct(v("FGTS"))},
        {"CONTA": "🧾 TOTAL SERVIÇOS", "VALOR": total_serv, "%": pct(total_serv)},
        {"CONTA": "  • Gcom", "VALOR": v("Gcom"), "%": pct(v("Gcom"))},
        {"CONTA": "  • Contador", "VALOR": v("Contador"), "%": pct(v("Contador"))},
        {"CONTA": "💡 TOTAL UTILIDADES", "VALOR": total_util, "%": pct(total_util)},
        {"CONTA": "  • Gás", "VALOR": v("Gás"), "%": pct(v("Gás"))},
        {"CONTA": "  • Energia Elétrica", "VALOR": v("Energia Elétrica"), "%": pct(v("Energia Elétrica"))},
        {"CONTA": "🧹 MATERIAIS DE USO & CONSUMO", "VALOR": total_mat, "%": pct(total_mat)},
        {"CONTA": "  • Limpeza", "VALOR": v("Material de Limpeza"), "%": pct(v("Material de Limpeza"))},
        {"CONTA": "  • Utensílios", "VALOR": v("Utensílios"), "%": pct(v("Utensílios"))},
        {"CONTA": "  • Uniformes", "VALOR": v("Uniformes"), "%": pct(v("Uniformes"))},
        {"CONTA": "🔧 MANUTENÇÃO", "VALOR": total_manut, "%": pct(total_manut)},
        {"CONTA": "🛵 DELIVERY", "VALOR": total_deliv, "%": pct(total_deliv)},
        {"CONTA": "📢 MARKETING & FRANQUEADOR", "VALOR": total_mkt, "%": pct(total_mkt)},
        {"CONTA": "💳 CUSTO FINANCEIRO", "VALOR": total_fin, "%": pct(total_fin)},
        {"CONTA": "----------------------------------------", "VALOR": None, "%": ""},
        {"CONTA": ('🔴 TOTAL DESPESAS OPERACIONAIS (provisório)' if cmv_auto is None
                   else '🔴 TOTAL DESPESAS OPERACIONAIS'),
         "VALOR": total_despesas_operacionais, "%": pct(total_despesas_operacionais)},
        {"CONTA": '🏆 RESULTADO OPERACIONAL', "VALOR": res_operacional, "%": pct(res_operacional)},
        {"CONTA": '🎁 Total Bonificação', "VALOR": bonificacao, "%": pct(bonificacao)},
        {"CONTA": '🏅 RESULTADO FINAL OPERACIONAL', "VALOR": resultado_final_operacional, "%": pct(resultado_final_operacional)},
        {"CONTA": "──────── DESPESAS NÃO OPERACIONAIS ────────", "VALOR": None, "%": ""},
        {"CONTA": '  • Carro da Loja', "VALOR": v("Carro da Loja"), "%": pct(v("Carro da Loja"))},
        {"CONTA": '✈️ VIAGENS', "VALOR": total_viagens, "%": pct(total_viagens)},
        {"CONTA": '  • Despesas de Viagens', "VALOR": v("Despesas de Viagens"), "%": pct(v("Despesas de Viagens"))},
        {"CONTA": '  • Despesas de Convenção', "VALOR": v("Despesas de Convenção"), "%": pct(v("Despesas de Convenção"))},
        {"CONTA": '🗂️ DESPESAS ADMINISTRATIVAS', "VALOR": total_administrativas, "%": pct(total_administrativas)},
        {"CONTA": '  • Rateio de Escritório Administrativo', "VALOR": v("Rateio de Escritório Administrativo"), "%": pct(v("Rateio de Escritório Administrativo"))},
        {"CONTA": '  • Pessoal - Supervisor e Nutricionista', "VALOR": v("Pessoal - Supervisor e Nutricionista"), "%": pct(v("Pessoal - Supervisor e Nutricionista"))},
        {"CONTA": '🏦 EMPRÉSTIMOS', "VALOR": total_emprestimos, "%": pct(total_emprestimos)},
        {"CONTA": '  • Empréstimos Bancário', "VALOR": v("Empréstimos Bancário"), "%": pct(v("Empréstimos Bancário"))},
        {"CONTA": '  • Pronampe', "VALOR": v("Pronampe"), "%": pct(v("Pronampe"))},
        {"CONTA": '  • Juros de Empréstimos', "VALOR": v("Juros de Empréstimos"), "%": pct(v("Juros de Empréstimos"))},
        {"CONTA": '  • Empréstimo Folha de Pagamento', "VALOR": v("Empréstimo Folha de Pagamento"), "%": pct(v("Empréstimo Folha de Pagamento"))},
        {"CONTA": '🏗️ INVESTIMENTOS', "VALOR": total_investimentos, "%": pct(total_investimentos)},
        {"CONTA": '  • Capex', "VALOR": v("Capex"), "%": pct(v("Capex"))},
        {"CONTA": '👤 PRÓ-LABORE', "VALOR": total_pro_labore, "%": pct(total_pro_labore)},
        {"CONTA": '  • Pro Labore', "VALOR": v("Pro Labore"), "%": pct(v("Pro Labore"))},
        {"CONTA": '🔵 SUBTOTAL DESPESAS NÃO OPERACIONAIS', "VALOR": despesas_nao_operacionais, "%": pct(despesas_nao_operacionais)},
        {"CONTA": '🔴 TOTAL GERAL DE DESPESAS', "VALOR": total_geral_despesas, "%": pct(total_geral_despesas)},
        {"CONTA": '💰 RESULTADO FINAL', "VALOR": res_final, "%": pct(res_final)},
    ]
    df_spoleto_view = pd.DataFrame(estrutura_dre_spoleto)
    df_spoleto_view["VALOR"] = df_spoleto_view["VALOR"].apply(lambda x: f"R$ {formatar_numero_br(x)}" if pd.notnull(x) else "")
    st.caption(
        "Critério gerencial: o Total Geral de Despesas inclui saídas como amortização "
        "de empréstimos e Capex, conforme o modelo enviado. Para uma DRE contábil, "
        "principal de empréstimos e investimentos normalmente não são despesas do período; "
        "consulte o contador para conciliação. Antes do inventário, compras são "
        "incluídas provisoriamente nas despesas operacionais, sem duplicar o CMV."
    )
    with painel_dre_atualizado.container():
        st.markdown("### 📊 DRE atualizada conforme os lançamentos")
        st.caption(
            "A própria tabela abaixo é recalculada quando você confirma uma alteração "
            "na tabela de lançamentos (Enter ou clique fora). "
            "Para persistir os valores no Supabase, clique em Salvar."
        )
        st.dataframe(
            df_spoleto_view, use_container_width=True, height=660,
            hide_index=True, key=f"dre_visualizacao_ao_vivo_{mes_ativo}",
        )
        st.markdown(
            f"**Total despesas operacionais:** R$ {formatar_numero_br(total_despesas_operacionais)}"
            f"  |  **Subtotal não operacionais:** R$ {formatar_numero_br(despesas_nao_operacionais)}"
            f"  |  **Total geral:** R$ {formatar_numero_br(total_geral_despesas)}"
        )

    with st.expander("🔎 Conferência dos subtotais — veja de onde vem o Total de Despesas"):
        st.markdown("**Despesas operacionais — composição sem duplicidade**")
        st.dataframe(
            pd.DataFrame([
                {"Grupo": nome, "Valor (R$)": formatar_numero_br(valor)}
                for nome, valor in grupos_operacionais.items()
            ]), hide_index=True, use_container_width=True,
        )
        st.markdown(f"**Subtotal operacional: R$ {formatar_numero_br(total_despesas_operacionais)}**")
        st.markdown("**Despesas não operacionais — composição**")
        st.dataframe(
            pd.DataFrame([
                {"Grupo": nome, "Valor (R$)": formatar_numero_br(valor)}
                for nome, valor in grupos_nao_operacionais.items()
            ]), hide_index=True, use_container_width=True,
        )
        st.markdown(f"**Subtotal não operacional: R$ {formatar_numero_br(despesas_nao_operacionais)}**")
        st.markdown(f"### Total geral de despesas: R$ {formatar_numero_br(total_geral_despesas)}")
        st.caption(
            "Antes de fechar o inventário, as compras entram provisoriamente no total operacional. "
            "Após o fechamento, o CMV consolidado substitui as compras no cálculo, sem duplicidade."
        )

    st.markdown("### 📥 Baixar Relatório")
    dados_excel = gerar_excel_dre(NOMES_MESES[mes_ativo], pd.DataFrame(estrutura_dre_spoleto), df_l)
    st.download_button(
        label="📊 Baixar DRE Atualizado em Excel (.xlsx)",
        data=dados_excel,
        file_name=f"DRE_Spoleto_{mes_ativo}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

# ==============================================================================
# 2. ABA DE ESCANEAR NOTA & ALIMENTAR DRE
# ==============================================================================
elif menu.startswith("📸 Escanear"):
    st.subheader(f"📸 Escanear Nota Fiscal para o DRE de: {NOMES_MESES[mes_ativo]}")
    st.info("💡 Classificações: **Demais Alimentos, Descartáveis, Limpeza, Materiais de Uso e Consumo, Utensílios, Bebidas, Horte, Uniformes, Uniforme e Alimentação Funcionário**.")

    ukey = st.session_state.uploader_key
    aba_foto, aba_cam, aba_arq, aba_manual = st.tabs([
        "📸 Fotos / Galeria", "🖥️ Câmara ao Vivo",
        "📁 Arquivo (XML / Excel / PDF)", "✍️ Lançar Nota Manualmente"
    ])

    st.caption("🤖 A IA é sempre a primeira opção. Se não conseguir ler a nota, o leitor fiscal local será acionado automaticamente.")

    with aba_manual:
        st.markdown("#### ✍️ Cadastro manual de nota fiscal")
        st.caption(
            "Preencha o fornecedor e os produtos. Você poderá revisar a nota "
            "antes de gravá-la no Supabase e na DRE."
        )
        with st.form(key=f"form_nota_manual_{ukey}"):
            col_fornec, col_cnpj = st.columns([2, 1])
            with col_fornec:
                fornecedor_manual = st.text_input(
                    "Fornecedor / Emitente *", placeholder="Nome do fornecedor"
                )
            with col_cnpj:
                cnpj_manual = st.text_input(
                    "CNPJ (opcional)", placeholder="00.000.000/0000-00"
                )

            st.markdown("**Produtos da nota**")
            st.caption(
                "Adicione ou exclua linhas pelo editor. Informe quantidade e preço "
                "unitário; o subtotal será calculado na revisão quando estiver zerado."
            )
            df_manual_base = pd.DataFrame([
                {
                    "Produto": "", "Quantidade": 1.0, "Unid": "UN",
                    "PrecoUnitario": 0.0, "TotalItem": 0.0,
                    "Categoria": "Demais Alimentos"
                }
                for _ in range(3)
            ])
            df_manual = st.data_editor(
                df_manual_base,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                key=f"editor_manual_{ukey}",
                column_config={
                    "Produto": st.column_config.TextColumn("Produto", required=True),
                    "Quantidade": st.column_config.NumberColumn(
                        "Quantidade", min_value=0.0, format="%.3f"
                    ),
                    "Unid": st.column_config.TextColumn("Unidade"),
                    "PrecoUnitario": st.column_config.NumberColumn(
                        "Preço unitário (R$)", min_value=0.0, format="%.2f"
                    ),
                    "TotalItem": st.column_config.NumberColumn(
                        "Subtotal (R$) — opcional", min_value=0.0, format="%.2f"
                    ),
                    "Categoria": st.column_config.SelectboxColumn(
                        "Classificação", options=LISTA_7_CATEGORIAS, required=True
                    ),
                },
            )
            preparar_manual = st.form_submit_button(
                "📋 Revisar nota manual", type="primary", use_container_width=True
            )

        if preparar_manual:
            fornecedor_limpo = fornecedor_manual.strip()
            df_validar = df_manual.copy()
            df_validar["Produto"] = df_validar["Produto"].fillna("").astype(str).str.strip()
            df_validar = df_validar[df_validar["Produto"] != ""].copy()
            for coluna in ("Quantidade", "PrecoUnitario", "TotalItem"):
                df_validar[coluna] = pd.to_numeric(
                    df_validar[coluna], errors="coerce"
                ).fillna(0.0)
            df_validar["Categoria"] = df_validar["Categoria"].fillna(
                "Demais Alimentos"
            )
            df_validar["Unid"] = df_validar["Unid"].fillna("UN")
            sem_subtotal = df_validar["TotalItem"] <= 0
            df_validar.loc[sem_subtotal, "TotalItem"] = (
                df_validar.loc[sem_subtotal, "Quantidade"]
                * df_validar.loc[sem_subtotal, "PrecoUnitario"]
            )
            if not fornecedor_limpo:
                st.error("Informe o nome do fornecedor.")
            elif df_validar.empty:
                st.error("Inclua pelo menos um produto.")
            elif (df_validar["TotalItem"] <= 0).any():
                st.error(
                    "Todos os produtos precisam ter subtotal maior que zero. "
                    "Informe quantidade e preço, ou preencha o subtotal."
                )
            elif not df_validar["Categoria"].isin(LISTA_7_CATEGORIAS).all():
                st.error("Revise a classificação dos produtos.")
            else:
                st.session_state.dados_extraidos = {
                    "razao_social": fornecedor_limpo,
                    "cnpj": cnpj_manual.strip() or "Não informado",
                    "valor_total": round(float(df_validar["TotalItem"].sum()), 2),
                    "itens": df_validar[
                        ["Produto", "Quantidade", "Unid",
                         "PrecoUnitario", "TotalItem", "Categoria"]
                    ].to_dict(orient="records"),
                }
                st.success(
                    "Nota manual preparada! Confira a seção 'Resumo da Compra' "
                    "abaixo e clique em 'Confirmar & Lançar no DRE'."
                )


    with aba_foto:
        st.markdown("**Escolha como as fotos devem ser interpretadas:**")
        modo_fotos = st.radio(
            "Organização das fotos",
            ["Notas diferentes (uma nota por foto)", "Uma única nota com várias páginas"],
            horizontal=True, key="modo_fotos_nota",
        )
        f_upload = st.file_uploader(
            "Selecione as fotos dos cupons/notas:", type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True, key=f"file_uploader_{ukey}"
        )
        if f_upload and modo_fotos.startswith("Notas diferentes"):
            st.caption(f"{len(f_upload)} nota(s) selecionada(s). Cada imagem será lida separadamente, sem juntar supermercados.")
            if st.button("🚀 Destrinchar todas as notas separadamente", type="primary", key=f"btn_lote_{ukey}"):
                if st.session_state.dados_extraidos or st.session_state.fila_notas_individuais:
                    st.warning("Conclua ou descarte a nota em revisão e a fila atual antes de iniciar outro lote.")
                else:
                    fila_nova = []
                    falhas = []
                    progresso = st.progress(0, text="Iniciando leitura das notas...")
                    regras_fallback = None
                    for idx, arquivo in enumerate(f_upload):
                        progresso.progress(idx / len(f_upload), text=f"Lendo nota {idx + 1}/{len(f_upload)}: {arquivo.name}")
                        dados_imagem = arquivo.getvalue()
                        resultado = processar_multiplas_imagens_com_ia([dados_imagem], api_key)
                        if not resultado:
                            try:
                                if regras_fallback is None:
                                    regras_fallback = carregar_regras()
                                resultado = ler_imagem_ocr(dados_imagem, regras_fallback)
                            except Exception:
                                resultado = None
                        if isinstance(resultado, dict) and resultado.get("itens"):
                            fila_nova.append({"nome": arquivo.name, "dados": resultado})
                        else:
                            falhas.append(arquivo.name)
                    progresso.progress(1.0, text="Leitura do lote concluída")
                    st.session_state.falhas_notas_lote = falhas
                    if fila_nova:
                        st.session_state.fila_notas_individuais = fila_nova
                        st.session_state.fotos_acumuladas = []
                        avancar_fila_notas()
                        st.rerun()
                    else:
                        st.error("Nenhuma nota foi identificada. As imagens originais não foram gravadas no banco.")
        elif f_upload and st.button("➕ Carregar páginas da mesma nota", key=f"btn_add_f_{ukey}"):
            st.session_state.fotos_acumuladas = [f.getvalue() for f in f_upload]
            st.success(f"{len(f_upload)} página(s) da mesma nota carregada(s)!")

    with aba_cam:
        f_cam = st.camera_input("Capturar foto", key=f"cam_input_{ukey}")
        if f_cam and st.button("➕ Adicionar captura à fila", key=f"btn_add_cam_{ukey}"):
            st.session_state.fotos_acumuladas = [f_cam.getvalue()]
            st.success("Foto capturada pronta para leitura!")

    if st.session_state.fotos_acumuladas:
        st.write(f"**Total acumulado:** {len(st.session_state.fotos_acumuladas)} foto(s)")
        col_proc, col_desc = st.columns([2, 1])
        with col_proc:
            if st.button("🚀 Processar Fotos com IA & Destrinchar", type="primary", use_container_width=True):
                with st.spinner("🤖 Lendo itens e classificando os produtos..."):
                    res = processar_multiplas_imagens_com_ia(st.session_state.fotos_acumuladas, api_key)
                    if res:
                        st.session_state.dados_extraidos = res
                    # Em caso de falha, não cria nota fictícia nem limpa as fotos.
                    else:
                        st.info("A IA não conseguiu ler a nota. Tentando agora o leitor fiscal local (OCR)...")
                        try:
                            regras_fallback = carregar_regras()
                            if len(st.session_state.fotos_acumuladas) != 1:
                                st.warning("O OCR alternativo trabalha com uma foto por vez. Para evitar duplicidades, envie uma foto única ou use o lançamento manual.")
                            else:
                                res_local = ler_imagem_ocr(st.session_state.fotos_acumuladas[0], regras_fallback)
                                st.session_state.dados_extraidos = res_local
                                st.success("Leitura alternativa concluída. Confira cuidadosamente os itens, fornecedor e total antes de salvar.")
                        except Exception as erro_fallback:
                            st.warning(f"O leitor alternativo também não conseguiu separar os itens: {erro_fallback}")
                            st.info("As fotos continuam disponíveis. Você pode tentar novamente ou lançar a nota manualmente.")
                if st.session_state.dados_extraidos:
                    st.rerun()
        with col_desc:
            if st.button("🗑️ Descartar Fotos", use_container_width=True):
                resetar_processamento_nota()
                st.rerun()

    with aba_arq:
        documentos = st.file_uploader(
            "Enviar várias notas XML, PDF ou Excel (fornecedores diferentes):",
            type=["xml", "xlsx", "xls", "pdf"],
            accept_multiple_files=True,
            key=f"doc_uploader_{ukey}",
        )
        if documentos:
            st.caption(
                f"{len(documentos)} arquivo(s) selecionado(s). Cada arquivo será interpretado "
                "como uma nota independente, com fornecedor, CNPJ e produtos próprios."
            )
            if st.button("🚀 Destrinchar arquivos separadamente", type="primary", key=f"btn_doc_{ukey}"):
                if st.session_state.dados_extraidos or st.session_state.fila_notas_individuais:
                    st.warning("Conclua ou descarte a nota em revisão e a fila atual antes de iniciar outro lote.")
                else:
                    fila_nova = []
                    falhas = []
                    progresso = st.progress(0, text="Preparando leitura dos documentos...")
                    for indice, documento in enumerate(documentos):
                        progresso.progress(
                            indice / len(documentos),
                            text=f"Lendo documento {indice + 1}/{len(documentos)}: {documento.name}",
                        )
                        try:
                            resultado = processar_documento_fiscal_individual(documento, api_key)
                        except Exception as erro:
                            st.warning(f"Falha ao ler {documento.name}: {type(erro).__name__}.")
                            resultado = None
                        if isinstance(resultado, dict) and resultado.get("itens"):
                            fila_nova.append({"nome": documento.name, "dados": resultado})
                        else:
                            falhas.append(documento.name)
                    progresso.progress(1.0, text="Leitura dos documentos concluída")
                    st.session_state.falhas_notas_lote = falhas
                    if fila_nova:
                        st.session_state.fila_notas_individuais = fila_nova
                        avancar_fila_notas()
                        st.rerun()
                    else:
                        st.error("Nenhum documento pôde ser lido. Nenhuma nota foi gravada.")

    # ----------------- REVISÃO DA NOTA -----------------
    if st.session_state.falhas_notas_lote:
        st.warning("Arquivos/fotos que precisam de nova leitura individual: " + ", ".join(st.session_state.falhas_notas_lote))
    if st.session_state.dados_extraidos and st.session_state.get("nome_nota_ativa"):
        st.info("📄 Revisando: **" + st.session_state["nome_nota_ativa"] + "** — "
                + str(len(st.session_state.fila_notas_individuais))
                + " nota(s) aguardando. Cada nota será gravada individualmente após sua confirmação.")
    if st.session_state.dados_extraidos:
        dados = st.session_state.dados_extraidos
        st.markdown("---")
        st.subheader("📋 Resumo da Compra")

        c_a, c_b, c_c = st.columns(3)
        with c_a:
            fornec_input = st.text_input("Fornecedor / Emitente:", value=dados.get("razao_social") or "Fornecedor não identificado")
        with c_b:
            cnpj_input = st.text_input("CNPJ:", value=dados.get("cnpj") or "Não informado")
        with c_c:
            st.metric("Valor Total Identificado", f"R$ {numero_seguro(dados.get('valor_total')):,.2f}")

        df_itens = pd.DataFrame(dados.get("itens", []))
        colunas_padrao = ["Produto", "Quantidade", "Unid", "PrecoUnitario", "TotalItem", "Categoria"]
        if df_itens.empty:
            st.warning("Nenhum produto foi extraído. Você pode adicionar linhas manualmente.")
            df_itens = pd.DataFrame(columns=colunas_padrao)
        if "Classificacao" in df_itens.columns and "Categoria" not in df_itens.columns:
            df_itens.rename(columns={"Classificacao": "Categoria"}, inplace=True)
        for col in colunas_padrao:
            if col not in df_itens.columns:
                if col == "Categoria":
                    df_itens[col] = "Demais Alimentos"
                elif col == "Unid":
                    df_itens[col] = "UN"
                elif col == "Produto":
                    df_itens[col] = ""
                else:
                    df_itens[col] = 0.0
        df_itens = df_itens[colunas_padrao]
        df_itens["Categoria"] = df_itens["Categoria"].apply(
            lambda x: x if x in LISTA_7_CATEGORIAS else "Demais Alimentos"
        )
        for col in ["Quantidade", "PrecoUnitario", "TotalItem"]:
            df_itens[col] = pd.to_numeric(df_itens[col], errors="coerce").fillna(0.0)

        st.write("👇 **Revise os produtos e valores antes de lançar no DRE:**")
        df_edit = st.data_editor(
            df_itens,
            column_config={
                "Categoria": st.column_config.SelectboxColumn("Categoria", options=LISTA_7_CATEGORIAS, required=True),
                "Produto": st.column_config.TextColumn("Produto", required=True),
                "Quantidade": st.column_config.NumberColumn("Qtd", format="%.3f", min_value=0.0),
                "Unid": st.column_config.TextColumn("Unid"),
                "PrecoUnitario": st.column_config.NumberColumn("Preço Unit. (R$)", format="R$ %.2f", min_value=0.0),
                "TotalItem": st.column_config.NumberColumn("Total Item (R$)", format="R$ %.2f", min_value=0.0, required=True),
            },
            use_container_width=True,
            num_rows="dynamic",
            key=f"editor_nota_ativa_{ukey}",
        )

        df_edit = df_edit.copy()
        for col in ["Quantidade", "PrecoUnitario", "TotalItem"]:
            df_edit[col] = pd.to_numeric(df_edit[col], errors="coerce").fillna(0.0)
        df_edit["Produto"] = df_edit["Produto"].fillna("").astype(str).str.strip()
        # Calcula o total quando ele estiver vazio/zerado e houver quantidade e preço unitário.
        mascara_calcular = (df_edit["TotalItem"] <= 0) & (df_edit["Quantidade"] > 0) & (df_edit["PrecoUnitario"] > 0)
        df_edit.loc[mascara_calcular, "TotalItem"] = (
            df_edit.loc[mascara_calcular, "Quantidade"] * df_edit.loc[mascara_calcular, "PrecoUnitario"]
        )

        itens_com_nome = df_edit[df_edit["Produto"] != ""]
        somas_cat = itens_com_nome.groupby("Categoria")["TotalItem"].sum().to_dict()
        soma_total_itens = float(itens_com_nome["TotalItem"].sum())

        st.write("#### 📊 Subtotais por Categoria:")
        if somas_cat:
            c_grid = st.columns(min(len(somas_cat), 4))
            for idx, (cl_n, val_n) in enumerate(somas_cat.items()):
                c_grid[idx % 4].metric(cl_n, f"R$ {val_n:,.2f}")
        else:
            st.info("Adicione produtos à tabela para visualizar os subtotais.")

        st.markdown("---")
        col_save_det, col_canc = st.columns([2, 1])
        with col_save_det:
            if st.button(f"🚀 Confirmar & Lançar no DRE ({NOMES_MESES[mes_ativo]})", type="primary", use_container_width=True):
                linhas_preenchidas = df_edit[df_edit["Produto"] != ""].copy()
                linhas_validas = linhas_preenchidas[linhas_preenchidas["TotalItem"] > 0]
                if linhas_validas.empty:
                    st.warning("⚠️ Insira ao menos um produto com valor maior que R$ 0,00.")
                elif len(linhas_validas) != len(linhas_preenchidas):
                    st.error("Há produtos com subtotal zerado ou inválido. Corrija todos antes de gravar a nota.")
                elif not linhas_validas["Categoria"].isin(LISTA_7_CATEGORIAS).all():
                    st.error("Revise as classificações dos produtos antes de gravar.")
                else:
                    # Só salva linhas identificadas e com valor positivo.
                    lista_salvar = linhas_validas[colunas_padrao].to_dict(orient="records")
                    total_salvar = float(linhas_validas["TotalItem"].sum())
                    try:
                        salvar_nota_e_lancar_dre(
                            mes_ref=mes_ativo,
                            razao_social=fornec_input.strip() or "Fornecedor não identificado",
                            cnpj=cnpj_input.strip() or "Não informado",
                            valor_total=total_salvar,
                            lista_produtos=lista_salvar,
                        )
                    except ValueError as erro:
                        st.error(f"Nota não lançada: {erro}")
                    except Exception:
                        st.error("Não foi possível gravar a nota. Os dados conferidos foram mantidos; tente novamente após verificar a conexão.")
                    else:
                        st.success(f"✅ {len(lista_salvar)} produto(s) lançados no DRE de {NOMES_MESES[mes_ativo]}!")
                        if st.session_state.get("nome_nota_ativa"):
                            avancar_fila_notas()
                        else:
                            resetar_processamento_nota()
                        st.rerun()
        with col_canc:
            if st.button("❌ Descartar Nota", use_container_width=True):
                if st.session_state.get("nome_nota_ativa"):
                    avancar_fila_notas()
                else:
                    resetar_processamento_nota()
                st.rerun()

# ==============================================================================
# 3. ABA DE LANÇAMENTOS DO MÊS
# ==============================================================================
elif menu.startswith("📝 Lançamentos"):
    st.subheader(f"📝 Base de Lançamentos — {NOMES_MESES[mes_ativo]}")
    st.write("Esta tabela corresponde à base de lançamentos do mês.")
    df_lanc = obter_lancamentos_mes(mes_ativo)
    if df_lanc.empty:
        st.info(f"Nenhum lançamento registrado ainda para {NOMES_MESES[mes_ativo]}. Use o menu de escanear notas para alimentar.")
    else:
        df_show = df_lanc.copy()
        df_show["valor"] = df_show["valor"].apply(lambda x: f"R$ {x:,.2f}")
        df_show.rename(columns={
            "id": "ID", "data": "DATA", "fornecedor": "FORNECEDOR", "descricao": "DESCRIÇÃO",
            "valor": "VALOR", "dre": "DRE", "classificacao": "CLASSIFICAÇÃO", "detalhamento": "DETALHAMENTO",
        }, inplace=True)
        st.dataframe(df_show, use_container_width=True)

        st.markdown("---")
        st.subheader("🗑️ Excluir Lançamento Específico")
        c_sel, c_del = st.columns([2, 1])
        with c_sel:
            id_del = st.selectbox("Selecione o lançamento pelo ID:", df_lanc["id"].tolist())
        with c_del:
            confirmar_exclusao = st.checkbox(
                "Confirmo a exclusão deste lançamento",
                key=f"confirmar_exclusao_{mes_ativo}_{id_del}",
            )
            st.caption("A nota fiscal original será preservada. A exclusão altera os totais da DRE e pode afetar o CMV.")
            if st.button("Eliminar Lançamento", type="secondary", use_container_width=True,
                         disabled=not confirmar_exclusao):
                conn = conectar_db()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("DELETE FROM lancamentos_dre WHERE id = %s AND mes_referencia = %s",
                                       (int(id_del), mes_ativo))
                        removidos = cursor.rowcount
                    conn.commit()
                except Exception:
                    conn.rollback()
                    st.error("Não foi possível excluir o lançamento.")
                else:
                    if removidos:
                        st.warning(f"Lançamento #{id_del} removido do DRE. A nota original permanece no histórico.")
                    else:
                        st.info("O lançamento não foi encontrado neste mês.")
                    st.rerun()
                finally:
                    conn.close()

# ==============================================================================
# 4. ABA DE REGRAS INTELIGENTES
# ==============================================================================
elif menu.startswith("🧠 Regras"):
    st.subheader("🧠 Dicionário Inteligente de Classificações")
    st.write("Produtos memorizados pelas suas correções anteriores:")
    regras = carregar_regras()
    if regras:
        df_r = pd.DataFrame(list(regras.items()), columns=["Produto", "Categoria"]).sort_values("Produto")
        st.dataframe(df_r, use_container_width=True)
    else:
        st.info("Nenhuma regra personalizada ainda. Sempre que corrigir e salvar uma nota, a IA memoriza aqui.")


# ======================= INVENTÁRIO SUPABASE =======================
def listar_produtos_estoque():
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT id, codigo, produto, categoria, unidade, preco_unitario
                           FROM produtos_inventario WHERE ativo = TRUE ORDER BY produto, id""")
            return cur.fetchall()


def inventario_do_mes(mes):
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, status FROM inventarios WHERE mes_referencia=%s", (mes,))
            return cur.fetchone()


def quantidades_do_mes(mes):
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT ii.produto_id, ii.quantidade FROM inventario_itens ii
                           JOIN inventarios i ON i.id=ii.inventario_id
                           WHERE i.mes_referencia=%s""", (mes,))
            return {int(i): float(q) for i, q in cur.fetchall()}


def cadastrar_produto_estoque(nome, unidade, categoria, preco, codigo=None):
    nome = nome.strip().upper()
    if not nome or not unidade.strip():
        raise ValueError("Informe nome e unidade do produto.")
    if preco < 0:
        raise ValueError("O preço não pode ser negativo.")
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT id FROM produtos_inventario
                           WHERE UPPER(TRIM(produto))=%s AND ativo=TRUE""", (nome,))
            if cur.fetchone():
                raise ValueError("Este produto já está cadastrado.")
            cur.execute("""INSERT INTO produtos_inventario
                           (codigo, produto, unidade, categoria, preco_unitario, ativo)
                           VALUES (%s,%s,%s,%s,%s,TRUE)""",
                        (codigo or None, nome, unidade.strip().upper(), categoria, preco))
        conn.commit()


def atualizar_precos_produtos(alteracoes):
    """Atualiza preços no cadastro; preserva quantidades e demais dados."""
    if not alteracoes:
        return 0
    with conectar_db() as conn:
        with conn.cursor() as cur:
            for produto_id, preco in alteracoes:
                if preco < 0:
                    raise ValueError("O preço unitário não pode ser negativo.")
                cur.execute("""UPDATE produtos_inventario SET preco_unitario=%s
                               WHERE id=%s AND ativo=TRUE""", (round(preco, 6), int(produto_id)))
                if cur.rowcount != 1:
                    raise ValueError(f"Produto {produto_id} não encontrado.")
        conn.commit()
    return len(alteracoes)


def interface_editar_precos():
    with st.expander("💲 Editar preços dos produtos", expanded=False):
        st.caption("Altere o preço unitário diretamente na tabela e clique em Salvar preços. "
                   "Os preços são do cadastro geral e afetam o valor das contagens que os utilizam.")
        produtos_preco = listar_produtos_estoque()
        if not produtos_preco:
            st.info("Nenhum produto cadastrado.")
            return
        dados = pd.DataFrame([{
            "ID": int(pid), "Produto": nome, "Unidade": unidade,
            "Categoria": categoria, "Preço unitário (R$)": float(preco or 0)
        } for pid, codigo, nome, categoria, unidade, preco in produtos_preco])
        st.caption(f"{len(dados)} produtos. Preços zerados: "
                   f"{int((dados['Preço unitário (R$)'] == 0).sum())}.")
        with st.form("form_editar_precos_produtos"):
            editado = st.data_editor(
                dados, hide_index=True, use_container_width=True, num_rows="fixed",
                disabled=["ID", "Produto", "Unidade", "Categoria"],
                column_config={
                    "ID": None,
                    "Preço unitário (R$)": st.column_config.NumberColumn(
                        "Preço unitário (R$)", min_value=0.0, step=0.01,
                        format="R$ %.2f", required=True)
                }, key="editor_precos_produtos"
            )
            confirmar = st.checkbox("Confirmo que revisei os preços alterados")
            salvar = st.form_submit_button("💾 Salvar preços alterados")
        if salvar:
            if not confirmar:
                st.warning("Marque a confirmação antes de salvar.")
                return
            originais = dict(zip(dados["ID"], dados["Preço unitário (R$)"]))
            alteracoes = []
            try:
                for _, linha in editado.iterrows():
                    pid = int(linha["ID"])
                    novo = float(linha["Preço unitário (R$)"])
                    if not pd.notna(novo) or novo < 0:
                        raise ValueError("Informe preços válidos e não negativos.")
                    if abs(novo - originais[pid]) > 0.0000001:
                        alteracoes.append((pid, novo))
                if not alteracoes:
                    st.info("Nenhum preço foi alterado.")
                    return
                quantidade = atualizar_precos_produtos(alteracoes)
                st.success(f"{quantidade} preço(s) atualizado(s) no Supabase!")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível salvar os preços: {erro}")


def excluir_produto_estoque(produto_id):
    """Desativa um produto sem apagar contagens históricas ou movimentações."""
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT produto, ativo FROM produtos_inventario WHERE id=%s FOR UPDATE", (produto_id,))
            registro = cur.fetchone()
            if not registro or not registro[1]:
                raise ValueError("Produto não encontrado ou já excluído.")
            cur.execute("SELECT EXISTS (SELECT 1 FROM inventario_itens WHERE produto_id=%s)", (produto_id,))
            possui_contagens = cur.fetchone()[0]
            cur.execute("SELECT EXISTS (SELECT 1 FROM movimentacoes_estoque WHERE produto_id=%s)", (produto_id,))
            possui_movimentacoes = cur.fetchone()[0]
            if possui_contagens or possui_movimentacoes:
                raise ValueError("Este produto já possui contagens ou movimentações. Para preservar o histórico, não é possível excluí-lo por esta tela.")
            cur.execute("UPDATE produtos_inventario SET ativo=FALSE WHERE id=%s", (produto_id,))
        conn.commit()


def excluir_todos_produtos_estoque():
    """Retira todos os produtos das listas ativas, preservando o histórico no banco."""
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE produtos_inventario SET ativo=FALSE WHERE ativo=TRUE")
            total = cur.rowcount
        conn.commit()
    return total


def interface_excluir_produto():
    with st.expander("🗑️ Excluir item cadastrado", expanded=False):
        produtos_exclusao = listar_produtos_estoque()
        if not produtos_exclusao:
            st.info("Não há produtos para excluir.")
            return
        opcoes = {int(p[0]): f"{p[2]} — {p[4]} (ID {p[0]})" for p in produtos_exclusao}
        escolhido = st.selectbox("Selecione o produto", options=list(opcoes),
                                 format_func=lambda pid: opcoes[pid], key="produto_para_excluir")
        st.warning("A exclusão retira o item das próximas contagens. Itens com histórico não podem ser excluídos por esta tela.")
        confirmar = st.checkbox("Confirmo que quero excluir este produto", key="confirmar_exclusao_produto")
        if st.button("🗑️ Excluir produto selecionado", disabled=not confirmar, key="btn_excluir_produto"):
            try:
                excluir_produto_estoque(escolhido)
                st.success("Produto excluído da lista de itens ativos.")
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível excluir: {erro}")

        st.divider()
        st.markdown("**🗑️ Excluir todos os produtos de uma vez**")
        st.warning("Remove TODOS os produtos das listas de contagem e inventário, inclusive os que possuem histórico. Os registros anteriores ficam preservados no banco. Esta ação afeta todos os meses, não apenas o mês selecionado.")
        confirmacao = st.text_input('Para confirmar, digite EXCLUIR TUDO', key='confirmar_excluir_todos', placeholder='EXCLUIR TUDO')
        if st.button('🗑️ Excluir todos os itens', disabled=confirmacao.strip() != 'EXCLUIR TUDO', key='btn_excluir_todos', type='secondary'):
            try:
                total = excluir_todos_produtos_estoque()
                st.success(f'{total} produto(s) removido(s) das listas ativas. Histórico preservado.')
                st.rerun()
            except Exception as erro:
                st.error(f'Não foi possível excluir todos os produtos: {erro}')


def salvar_contagem_estoque(mes, quantidades):
    """Atualiza somente os itens informados, sem zerar produtos não exibidos."""
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO inventarios (mes_referencia, status)
                           VALUES (%s, 'ABERTO') ON CONFLICT (mes_referencia) DO NOTHING""", (mes,))
            cur.execute("SELECT id, status FROM inventarios WHERE mes_referencia=%s FOR UPDATE", (mes,))
            inv_id, status = cur.fetchone()
            if status != 'ABERTO':
                raise ValueError("Inventário fechado. Reabra-o antes de alterar a contagem.")
            for prod_id, qtd in quantidades.items():
                cur.execute("""INSERT INTO inventario_itens
                               (inventario_id, produto_id, quantidade, custo_unitario)
                               SELECT %s, id, %s, preco_unitario FROM produtos_inventario
                               WHERE id=%s AND ativo=TRUE
                               ON CONFLICT (inventario_id, produto_id)
                               DO UPDATE SET quantidade=EXCLUDED.quantidade,
                                             custo_unitario=EXCLUDED.custo_unitario""",
                            (inv_id, qtd, prod_id))
        conn.commit()


def fechar_ou_reabrir(mes, fechar):
    with conectar_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, status FROM inventarios WHERE mes_referencia=%s FOR UPDATE", (mes,))
            registro = cur.fetchone()
            if not registro:
                raise ValueError("Não há inventário cadastrado para este mês.")
            if fechar:
                # Confere contagem e custo dos itens ativos antes de permitir o fechamento.
                calcular_valor_inventario(cur, registro[0], mes)
            cur.execute("""UPDATE inventarios SET status=%s,
                           fechado_em=CASE WHEN %s THEN NOW() ELSE NULL END
                           WHERE mes_referencia=%s""",
                        ('FECHADO' if fechar else 'ABERTO', fechar, mes))
        conn.commit()


def sugerir_categoria_estoque(nome):
    """Sugestão por nome; sempre revisável pelo responsável."""
    n = str(nome).upper().strip()
    bebidas = ('COCA ', 'FANTA ', 'SPRITE', 'SCHWEPPES', 'ÁGUA CRYSTAL', 'AGUA CRYSTAL',
               'ÁGUA SABORIZADA', 'AGUA SABORIZADA', 'ICE TEA', 'SUCO ', 'CERVEJA ', 'VINHO ')
    limpeza = ('CLORO ', 'ALCOOL ', 'ÁLCOOL ', 'CIF ', 'SUMA ', 'REXONA SAB',
               'GALÃO ALCOOL', 'GALAO ALCOOL', 'PULVERISADOR', 'ESPONJA ',
               'SACO DE LIXO', 'PANO MULTIUSO', 'PAPEL TOALHA', 'PASTILHA AZUL', 'PASTILHA VERDE')
    descartaveis = ('REDE CABELO', 'AVENTAL DESCART', 'LUVA ', 'DEDEIRA', 'COPO DE PAPEL',
                    'SACO MASSA', 'KIT GARFO', 'TAÇA SUPORTE', 'TACA SUPORTE',
                    'CANUDO ', 'PAPEL DE HAMB', 'SACO TORRADA', 'GUARDANAPO',
                    'EMBALAGEM ', 'SACOLA ', 'SACO SPOLETO', 'SACO TALHER',
                    'LACRE ', 'PAPEL BANDEJA', 'TAMPA PARA ', 'POTE MOLHO',
                    'TOUCA BRANCA', 'BOBINA PICT')
    utensilios = ('PUMP BOMBONA', 'MANGA DE CONFEITEIRO', 'COLHER DE SOBREMESA',
                  'BOBINA PDV', 'BOBINA BALANÇA', 'BOBINA BALANCA', 'ETIQUETA DE VALIDADE',
                  'ROLO PACK FILM', 'PALITO SACHE')
    horte = ('ALHO PORO', 'ALHO PORÓ', 'BROCOLIS', 'BRÓCOLIS', 'CEBOLA', 'CEBOLINHA',
             'CENOURA', 'MANJERICÃO', 'MANJERICAO', 'SALSA', 'TOMATE', 'ABOBRINHA',
             'ALECRIN', 'ALFACE', 'ESPINAFRE', 'BERINGELA', 'SALVIA', 'SÁLVIA')
    uso_consumo = ('BOBINA PDV', 'BOBINA BALANÇA', 'BOBINA BALANCA', 'BOBINA PICOTADA',
                   'BOBINA PICT', 'ETIQUETA DE VALIDADE', 'ESPONJA ' , 'FILME PVC',
                   'ROLO PACK FILM', 'PAPEL DE ESCRITÓRIO', 'PAPEL DE ESCRITORIO',
                   'MATERIAL DE ESCRITÓRIO', 'MATERIAL DE ESCRITORIO', 'BORRIFADOR',
                   'REDE DE PROTEÇÃO', 'REDE DE PROTECAO', 'TOUCA DESCARTÁVEL',
                   'TOUCA DESCARTAVEL', 'LUVA LATEX', 'LUVA LÁTEX', 'MOP')
    if n.startswith(uso_consumo): return 'Materiais de Uso e Consumo'
    if n.startswith(bebidas): return 'Bebidas'
    if n.startswith(limpeza): return 'Limpeza'
    if n.startswith(descartaveis): return 'Descartáveis'
    if n.startswith(utensilios): return 'Utensílios'
    if n.startswith(horte): return 'Horte'
    return 'Demais Alimentos'


def interface_classificar_estoque():
    with st.expander('🏷️ Classificar produtos para o CMV', expanded=False):
        st.caption('Revise as sugestões antes de aplicar. O botão atualiza as categorias dos produtos ativos, sem alterar quantidades ou preços.')
        produtos_class = listar_produtos_estoque()
        if not produtos_class:
            st.info('Importe os produtos antes de classificá-los.')
            return
        categorias_validas = ['Não classificado'] + LISTA_CATEGORIAS_ESTOQUE
        linhas_class = []
        for pid, codigo, nome, categoria, unidade, preco in produtos_class:
            sugestao = sugerir_categoria_estoque(nome)
            linhas_class.append({'ID': int(pid), 'Produto': nome, 'Categoria atual': categoria or 'Não classificado',
                                 'Nova categoria': categoria if categoria in LISTA_CATEGORIAS_ESTOQUE else sugestao})
        df_class = pd.DataFrame(linhas_class)
        with st.form('form_classificacao_inventario'):
            revisado = st.data_editor(df_class, hide_index=True, use_container_width=True,
                                      disabled=['ID', 'Produto', 'Categoria atual'],
                                      column_config={'ID': None,
                                                     'Nova categoria': st.column_config.SelectboxColumn('Nova categoria', options=categorias_validas, required=True)},
                                      key='editor_classificacao_inventario')
            confirmado = st.checkbox('Revisei as categorias e autorizo a atualização em massa')
            if st.form_submit_button('💾 Salvar classificação de todos os produtos', type='primary'):
                if not confirmado:
                    st.warning('Marque a confirmação antes de salvar.')
                else:
                    try:
                        alteracoes = [(str(linha['Nova categoria']), int(linha['ID'])) for linha in revisado.to_dict('records')
                                      if linha['Nova categoria'] in LISTA_CATEGORIAS_ESTOQUE]
                        with conectar_db() as conn:
                            with conn.cursor() as cur:
                                cur.executemany('UPDATE produtos_inventario SET categoria=%s WHERE id=%s AND ativo=TRUE', alteracoes)
                            conn.commit()
                        st.success(f'{len(alteracoes)} produtos classificados!')
                        st.rerun()
                    except Exception as erro:
                        st.error(f'Não foi possível salvar: {erro}')


def importar_planilha_estoque(arquivo):
    """Importa A=produto, B=unidade, C=preço da planilha Spoleto."""
    df = pd.read_excel(arquivo, sheet_name=0, header=None, usecols="A:C")
    validos = []
    for linha in df.itertuples(index=False, name=None):
        nome, unidade, preco = linha
        if pd.isna(nome) or pd.isna(unidade):
            continue
        nome, unidade = str(nome).strip(), str(unidade).strip()
        valor = 0.0 if pd.isna(preco) or str(preco).strip() == "" else converter_numero_br(preco)
        if not nome or not unidade or unidade.lower() in ('r$', 'quant.') or (nome.upper() in ('PRODUTO', 'DESCRIÇÃO', 'ITEM') and unidade.lower() in ('unidade', 'unid')):
            continue
        if isinstance(preco, str) and preco.strip() and not re.search(r"\d", preco):
            continue
        if valor < 0:
            continue
        validos.append((nome.upper(), unidade.upper(), valor))
    if not validos:
        raise ValueError("Nenhum produto válido encontrado nas colunas A, B e C.")
    inseridos = 0
    ignorados = 0
    with conectar_db() as conn:
        with conn.cursor() as cur:
            for nome, unidade, preco in validos:
                cur.execute("SELECT id FROM produtos_inventario WHERE UPPER(TRIM(produto))=%s AND ativo=TRUE", (nome,))
                if cur.fetchone():
                    ignorados += 1
                    continue
                cur.execute("""INSERT INTO produtos_inventario
                               (produto, unidade, categoria, preco_unitario, ativo)
                               VALUES (%s,%s,%s,%s,TRUE)""", (nome, unidade, sugerir_categoria_estoque(nome), preco))
                inseridos += 1
        conn.commit()
    return inseridos, ignorados


def interface_cadastro_produto():
    with st.expander("➕ Adicionar novo item", expanded=False):
        with st.form("form_novo_produto_estoque", clear_on_submit=True):
            nome = st.text_input("Nome do produto")
            c1, c2 = st.columns(2)
            unidade = c1.selectbox("Unidade", ["UNIDADE", "KG", "G", "L", "ML", "CX", "PACOTE", "FARDO", "OUTRO"])
            preco_txt = c2.text_input("Preço unitário (R$)", value="0,00")
            categoria = st.selectbox("Categoria", ["Não classificado"] + LISTA_CATEGORIAS_ESTOQUE)
            if st.form_submit_button("Salvar novo produto", type="primary"):
                try:
                    cadastrar_produto_estoque(nome, unidade, categoria, converter_numero_br(preco_txt))
                    st.success("Produto cadastrado! Ele já aparece na contagem e no inventário.")
                    st.rerun()
                except Exception as erro:
                    st.error(f"Não foi possível cadastrar: {erro}")


# ======================= TELAS DE ESTOQUE =======================
if menu == "📋 Contagem de Estoque":
    st.subheader(f"📋 Contagem de Estoque — {NOMES_MESES[mes_ativo]}")
    st.caption("Preencha apenas as quantidades. Deixe vazio o que ainda não contou; digite 0 para registrar estoque zerado.")
    interface_cadastro_produto()
    interface_excluir_produto()
    inv = inventario_do_mes(mes_ativo)
    fechado = bool(inv and inv[1] == 'FECHADO')
    if fechado:
        st.warning("🔒 Este inventário está fechado. A contagem não pode ser alterada.")
    if "resultado_importacao_estoque" in st.session_state:
        st.success(st.session_state.pop("resultado_importacao_estoque"))
    produtos = listar_produtos_estoque()
    if not produtos:
        st.info("Nenhum produto cadastrado. Use 'Adicionar novo item' ou importe a planilha na aba Inventário e Produtos.")
    else:
        busca = st.text_input("🔎 Pesquisar produto", placeholder="Digite parte do nome")
        exibidos = [p for p in produtos if busca.casefold() in str(p[2]).casefold()]
        quantidades_atuais = quantidades_do_mes(mes_ativo)
        st.caption(f"{len(exibidos)} produto(s) exibido(s). Quantidades já salvas aparecem preenchidas.")
        with st.form(f"contagem_{mes_ativo}_{busca}"):
            df = pd.DataFrame([{
                "ID": p[0], "PRODUTO": p[2],
                "QUANTIDADE": (formatar_numero_br(quantidades_atuais[p[0]]) if p[0] in quantidades_atuais else "")
            } for p in exibidos])
            editado = st.data_editor(df, hide_index=True, use_container_width=True, num_rows="fixed",
                                     disabled=["ID", "PRODUTO"],
                                     column_config={"ID": None, "PRODUTO": st.column_config.TextColumn("Produto"),
                                                    "QUANTIDADE": st.column_config.TextColumn("Quantidade (ex.: 2,5)")})
            salvar = st.form_submit_button("💾 Salvar contagem no inventário", type="primary", disabled=fechado or not exibidos)
            if salvar:
                try:
                    mudancas = {}
                    for linha in editado.to_dict('records'):
                        entrada = str(linha['QUANTIDADE'] or '').strip()
                        if not entrada:
                            continue
                        numero = converter_numero_br(entrada)
                        if numero < 0 or not re.fullmatch(r"[0-9., ]+", entrada):
                            raise ValueError(f"Quantidade inválida para {linha['PRODUTO']}: {entrada}")
                        mudancas[int(linha['ID'])] = numero
                    if not mudancas:
                        st.warning("Preencha ao menos uma quantidade antes de salvar.")
                    else:
                        salvar_contagem_estoque(mes_ativo, mudancas)
                        st.success(f"{len(mudancas)} quantidade(s) salvas no inventário de {NOMES_MESES[mes_ativo]}!")
                        st.rerun()
                except Exception as erro:
                    st.error(f"Erro ao salvar a contagem: {erro}")

elif menu == "📦 Inventário e Produtos":
    st.subheader(f"📦 Inventário e Produtos — {NOMES_MESES[mes_ativo]}")
    interface_cadastro_produto()
    interface_excluir_produto()
    interface_classificar_estoque()
    interface_editar_precos()
    # Saldo inicial único: inclui Alimentos, Horte, Bebidas e Descartáveis.
    with st.expander("💰 Estoque inicial do mês — valor total", expanded=False):
        st.caption("Informe apenas o valor total do inventário anterior (Alimentos + Horte + Bebidas + Descartáveis). "
                   "Se informado, prevalece sobre o inventário anterior fechado.")
        saldos = consultar_saldos_iniciais(mes_ativo)
        inv_estado = inventario_do_mes(mes_ativo)
        bloqueado = bool(inv_estado and inv_estado[1] == 'FECHADO')
        if bloqueado:
            st.warning("Inventário fechado: reabra para editar o estoque inicial.")
        with st.form(f"form_saldo_inicial_{mes_ativo}"):
            campo = st.text_input("Estoque inicial total (R$)",
                value=formatar_numero_br(saldos['Total']) if 'Total' in saldos else "",
                placeholder="Ex.: 8.000,00", disabled=bloqueado)
            if st.form_submit_button("💾 Salvar estoque inicial total", disabled=bloqueado):
                try:
                    if not campo.strip() or not re.fullmatch(r"[0-9., ]+", campo.strip()):
                        raise ValueError("Informe um valor em reais, por exemplo 8.000,00.")
                    salvar_saldos_iniciais(mes_ativo, converter_numero_br(campo))
                    st.success("Estoque inicial total salvo no Supabase!")
                    st.rerun()
                except Exception as erro:
                    st.error(f"Não foi possível salvar: {erro}")
        if 'Total' in saldos:
            st.info("Saldo inicial total registrado. Será utilizado após o fechamento do inventário.")
    if "resultado_importacao_estoque" in st.session_state:
        st.success(st.session_state.pop("resultado_importacao_estoque"))
    produtos = listar_produtos_estoque()
    if not produtos:
        with st.expander("📥 Importar produtos da planilha Excel", expanded=True):
            arquivo = st.file_uploader("Planilha de inventário (colunas A: nome, B: unidade, C: preço)", type=["xlsx"], key="importar_estoque")
            if arquivo and st.button("Importar produtos para o Supabase"):
                try:
                    qtd, repetidos = importar_planilha_estoque(arquivo)
                    st.session_state.resultado_importacao_estoque = f"{qtd} produtos importados; {repetidos} já cadastrados foram mantidos."
                    st.rerun()
                except Exception as erro:
                    st.error(f"Erro na importação: {erro}")
    else:
        with st.expander("📥 Importar mais produtos da planilha"):
            arquivo = st.file_uploader("Planilha Excel", type=["xlsx"], key="importar_estoque_adicional")
            if arquivo and st.button("Importar itens que ainda não existem"):
                try:
                    qtd, repetidos = importar_planilha_estoque(arquivo)
                    st.session_state.resultado_importacao_estoque = f"{qtd} novos produtos; {repetidos} já cadastrados."
                    st.rerun()
                except Exception as erro:
                    st.error(f"Erro na importação: {erro}")
    produtos = listar_produtos_estoque()
    contagem = quantidades_do_mes(mes_ativo)
    linhas = []
    for pid, codigo, nome, cat, unid, preco in produtos:
        qtd = contagem.get(pid)
        preco = float(preco or 0)
        linhas.append({"Produto": nome, "Unidade": unid, "Categoria": cat,
                       "Preço unitário": preco, "Quantidade": qtd,
                       "Valor em estoque": round(qtd * preco, 2) if qtd is not None else None})
    df_inv = pd.DataFrame(linhas)
    if df_inv.empty:
        st.info("Cadastre ou importe produtos para começar.")
    else:
        st.metric("Valor dos itens contados", f"R$ {formatar_numero_br(df_inv['Valor em estoque'].sum())}")
        st.dataframe(df_inv, use_container_width=True, hide_index=True)
        st.download_button("📥 Baixar inventário em CSV", df_inv.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig'),
                           file_name=f"inventario_{mes_ativo}.csv", mime='text/csv')
    inv = inventario_do_mes(mes_ativo)
    if inv and inv[1] == 'FECHADO':
        st.success("🔒 Inventário fechado")
        cmv_fechado, aviso_fechado = apurar_cmv_automatico(mes_ativo)
        if aviso_fechado:
            st.warning("CMV ainda pendente: " + aviso_fechado)
        else:
            st.write("**CMV automático da DRE:**")
            st.dataframe(pd.DataFrame([{"Indicador": k, "Valor (R$)": v}
                                      for k, v in cmv_fechado.items()]), hide_index=True, use_container_width=True)
        with st.expander("Reabrir inventário (responsável)"):
            if st.checkbox("Confirmo que quero permitir novas alterações", key=f"confirmar_reabrir_{mes_ativo}"):
                if st.button("Reabrir inventário"):
                    fechar_ou_reabrir(mes_ativo, False)
                    st.rerun()
    elif inv:
        st.info("Inventário aberto. Confira as quantidades antes de fechar.")
        if st.checkbox("Confirmo que revisei a contagem", key=f"confirmar_fechar_{mes_ativo}"):
            if st.button("🔒 Fechar inventário"):
                fechar_ou_reabrir(mes_ativo, True)
                st.rerun()
