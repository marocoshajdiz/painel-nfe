import streamlit as st
import xmltodict
import pandas as pd
from google import genai
from google.genai import types
import json
import time
import sqlite3
import io
from datetime import datetime

st.set_page_config(page_title="Painel de Custos & DRE Spoleto - Capry", layout="wide")

# ----------------- CONTROLE DE ACESSO -----------------
USUARIO_CORRETO = "admin"
SENHA_CORRETA = "massima"

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

def tela_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("### 🔐 Acesso ao Painel de Custos & DRE - Capry")
        st.write("Digite suas credenciais:")
        with st.form("form_login"):
            usuario = st.text_input("Usuário", placeholder="Digite o Usuario")
            senha = st.text_input("Senha", type="password", placeholder="Digite a Senha")
            if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                if usuario == USUARIO_CORRETO and senha == SENHA_CORRETA:
                    st.session_state.autenticado = True
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos!")

if not st.session_state.autenticado:
    tela_login()
    st.stop()

st.sidebar.write(f"👤 Logado como: **{USUARIO_CORRETO}**")
if st.sidebar.button("🚪 Sair do Sistema"):
    st.session_state.autenticado = False
    st.rerun()
st.sidebar.markdown("---")

# CSS para tela expandida
st.markdown("""
<style>
div[data-testid="stCameraInput"] { width: 100% !important; max-width: 900px !important; margin: 0 auto; }
div[data-testid="stCameraInput"] video { width: 100% !important; height: 70vh !important; min-height: 480px !important; border-radius: 14px; object-fit: cover !important; border: 2px solid #ff4b4b; }
div[data-testid="stCameraInput"] button { padding: 0.75rem 1.5rem !important; font-size: 1.1rem !important; border-radius: 10px !important; }
</style>
""", unsafe_allow_html=True)

# ----------------- CATÁLOGO DOS 132 INDICADORES DO DRE SPOLETO -----------------
CATALOGO_DRE_SPOLETO = {
    # IMPOSTOS
    "Simples": {"dre": "Imposto", "detalhamento": "Imposto Federal"},
    "Icms": {"dre": "Imposto", "detalhamento": "Imposto Estadual"},
    "Pis": {"dre": "Imposto", "detalhamento": "Imposto Federal"},
    "Cofins": {"dre": "Imposto", "detalhamento": "Imposto Federal"},
    "Iss": {"dre": "Imposto", "detalhamento": "Imposto Federal"},

    # CMV
    "Demais Alimentos": {"dre": "Alimentos", "detalhamento": "Alimentos"},
    "Proteínas": {"dre": "Alimentos", "detalhamento": "Alimentos"},
    "Laticínios": {"dre": "Alimentos", "detalhamento": "Alimentos"},
    "Molhos": {"dre": "Alimentos", "detalhamento": "Alimentos"},
    "Massas, Farinhas E Cereais": {"dre": "Alimentos", "detalhamento": "Alimentos"},
    "Hortaliças": {"dre": "Alimentos", "detalhamento": "Alimentos"},
    "Conservas": {"dre": "Alimentos", "detalhamento": "Alimentos"},
    "Sobremesas": {"dre": "Alimentos", "detalhamento": "Alimentos"},
    "Bebidas": {"dre": "Bebidas", "detalhamento": "Bebidas"},
    "Embalagens E Descartáveis": {"dre": "Descartáveis", "detalhamento": "Descartáveis"},
    "Frete FBD": {"dre": "Frete", "detalhamento": "Fretes"},
    "Custo de Armazenagem": {"dre": "Frete", "detalhamento": "Fretes"},
    "Outros (Frete)": {"dre": "Frete", "detalhamento": "Fretes"},

    # OCUPAÇÃO
    "Aluguel": {"dre": "Ocupação", "detalhamento": "Aluguel"},
    "Aluguel Estoque Remoto": {"dre": "Ocupação", "detalhamento": "Aluguel"},
    "Condomínio": {"dre": "Ocupação", "detalhamento": "Condomínio"},
    "Fundo De Promoção": {"dre": "Ocupação", "detalhamento": "Fundo De Promoção"},
    "Taxa Associação Lojista": {"dre": "Ocupação", "detalhamento": "Taxas E Outros"},
    "Taxa De Incêndio E Seguro": {"dre": "Ocupação", "detalhamento": "Taxas E Outros"},
    "Taxa Administrativa": {"dre": "Ocupação", "detalhamento": "Taxas E Outros"},
    "Fundo De Reserva": {"dre": "Ocupação", "detalhamento": "Taxas E Outros"},
    "Dedetização Shopping": {"dre": "Ocupação", "detalhamento": "Taxas E Outros"},
    "Iptu": {"dre": "Ocupação", "detalhamento": "Iptu"},
    "Ar Condicionado": {"dre": "Ocupação", "detalhamento": "Ar Condicionado"},

    # PESSOAL
    "Salário": {"dre": "Pessoal", "detalhamento": "Salário"},
    "Adiantamento": {"dre": "Pessoal", "detalhamento": "Adiantamento"},
    "Alimentação Funcionário": {"dre": "Pessoal", "detalhamento": "Benefícios"},
    "Vale Transporte": {"dre": "Pessoal", "detalhamento": "Benefícios"},
    "Vale Refeição": {"dre": "Pessoal", "detalhamento": "Benefícios"},
    "Plano De Saúde": {"dre": "Pessoal", "detalhamento": "Benefícios"},
    "Fgts": {"dre": "Pessoal", "detalhamento": "Encargos"},
    "Inss": {"dre": "Pessoal", "detalhamento": "Encargos"},
    "Férias": {"dre": "Pessoal", "detalhamento": "Férias"},
    "13 Salário": {"dre": "Pessoal", "detalhamento": "13 Salário"},
    "Provisão 13 Salário": {"dre": "Pessoal", "detalhamento": "Provisões"},
    "Provisão Férias": {"dre": "Pessoal", "detalhamento": "Provisões"},
    "Rescisão": {"dre": "Pessoal", "detalhamento": "Rescisão"},
    "Hora Extra": {"dre": "Pessoal", "detalhamento": "Outros (pessoal)"},
    "Auxílio Combustível": {"dre": "Pessoal", "detalhamento": "Outros (pessoal)"},
    "Farmácia": {"dre": "Pessoal", "detalhamento": "Outros (pessoal)"},
    "Contribuição Sindical": {"dre": "Pessoal", "detalhamento": "Outros (pessoal)"},
    "Recrutamento/Seleção": {"dre": "Pessoal", "detalhamento": "Outros (pessoal)"},
    "Treinamento": {"dre": "Pessoal", "detalhamento": "Outros (pessoal)"},

    # UTILIDADES
    "Gás": {"dre": "Utilidades", "detalhamento": "Gás"},
    "Energia Elétrica": {"dre": "Utilidades", "detalhamento": "Energia Elétrica"},
    "Água E Esgoto": {"dre": "Utilidades", "detalhamento": "Água E Esgoto"},
    "Telefone": {"dre": "Utilidades", "detalhamento": "Telefone"},
    "Celular Loja": {"dre": "Utilidades", "detalhamento": "Telefone"},
    "Internet": {"dre": "Utilidades", "detalhamento": "Internet"},
    "Taxa De Lixo": {"dre": "Utilidades", "detalhamento": "Outros (utilidades)"},

    # SERVIÇOS & TERCEIROS
    "Advogado": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Terceiros"},
    "Contabilidade": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Terceiros"},
    "Assessoria/Consultoria": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Terceiros"},
    "Laboratório": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Terceiros"},
    "Suporte Informática": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Terceiros"},
    "Dedetização": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Terceiros"},
    "Cartório": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Serviços"},
    "Correio/Malote": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Serviços"},
    "Aluguel Pos": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Serviços"},
    "Fee Gcom": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Serviços"},
    "Fee Clastech": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Serviços"},
    "Fee Totem": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Serviços"},
    "Tef": {"dre": "Serviços_Gerais_Terceiros", "detalhamento": "Serviços"},

    # MATERIAIS DE USO & LIMPEZA
    "Material De Escritório": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Material De Escritório"},
    "Material De Limpeza": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Material De Limpeza"},
    "Pan Clean (Detergente Neutro)": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Material De Limpeza"},
    "Virex Flv": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Material De Limpeza"},
    "Suma Grill (Desincrustante)": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Material De Limpeza"},
    "Break Up (Desengordurante)": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Material De Limpeza"},
    "Suma Chlor": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Material De Limpeza"},
    "Block Whitener": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Material De Limpeza"},
    "Rolo Bactericida": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Material De Limpeza"},
    "Uniformes": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Uniformes"},
    "Utensílios De Cozinha": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Utensílios"},
    "Alcool Gel": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Outros Materiais De Uso E Consumo"},
    "Alcool Líquido": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Outros Materiais De Uso E Consumo"},
    "Cloro": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Outros Materiais De Uso E Consumo"},
    "Esponja Fibraço": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Outros Materiais De Uso E Consumo"},
    "Esponja Dupla Face": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Outros Materiais De Uso E Consumo"},
    "Bobina Pdv": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Outros Materiais De Uso E Consumo"},
    "Filme Pvc": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Outros Materiais De Uso E Consumo"},
    "Saco De Lixo": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Outros Materiais De Uso E Consumo"},
    "Mop": {"dre": "Material_De_Uso_E_Consumo", "detalhamento": "Outros Materiais De Uso E Consumo"},

    # MANUTENÇÃO
    "Serviço - Manutenção E Reparos": {"dre": "Manutenção", "detalhamento": "Serviço - Manutenção E Reparos"},
    "Material - Manutenção E Reparos": {"dre": "Manutenção", "detalhamento": "Material - Manutenção E Reparos"},

    # DELIVERY, MARKETING, FINANCEIRO E OUTROS
    "Comissão Agregadores": {"dre": "Delivery", "detalhamento": "Comissão Agregadores"},
    "Custo Com Entrega (Motoqueiros)": {"dre": "Delivery", "detalhamento": "Custo Com Entrega (Motoqueiros)"},
    "Anúncios/Propagandas": {"dre": "Marketing", "detalhamento": "Anúncios/Propagandas"},
    "Royalties": {"dre": "Taxas_Franqueador", "detalhamento": "Royalties"},
    "Fundo De Marketing": {"dre": "Taxas_Franqueador", "detalhamento": "Fundo De Marketing"},
    "Custo Cartão De Crédito": {"dre": "Financeiro", "detalhamento": "Custo Cartão De Crédito"},
    "Custo Cartão De Débito": {"dre": "Financeiro", "detalhamento": "Custo Cartão De Débito"},
    "Capex": {"dre": "Despesas_Não_Operacionais", "detalhamento": "Capex"},
    "Pro Labore": {"dre": "Despesas_Não_Operacionais", "detalhamento": "Pro Labore"}
}

LISTA_TODAS_CLASSIFICACOES = sorted(list(CATALOGO_DRE_SPOLETO.keys()))

# ----------------- BASE DE DADOS (SQLite) -----------------
def init_db():
    conn = sqlite3.connect("notas_fiscais.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_referencia TEXT,
            data_registo TEXT,
            razao_social TEXT,
            cnpj TEXT,
            valor_total REAL,
            itens_json TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lancamentos_dre (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_referencia TEXT,
            data TEXT,
            fornecedor TEXT,
            descricao TEXT,
            valor REAL,
            dre TEXT,
            classificacao TEXT,
            detalhamento TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ajustes_dre (
            mes_referencia TEXT,
            conta TEXT,
            valor REAL,
            PRIMARY KEY (mes_referencia, conta)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dados_mensais (
            mes_referencia TEXT PRIMARY KEY,
            fat_balcao REAL DEFAULT 0,
            fat_delivery REAL DEFAULT 0,
            imposto_estadual REAL DEFAULT 0,
            gas REAL DEFAULT 0,
            terceiros REAL DEFAULT 0,
            bonificacao REAL DEFAULT 0,
            ultima_atualizacao TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regras_classificacao (
            produto TEXT PRIMARY KEY,
            categoria TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

MESES_DISPONIVEIS = [
    "2026-10", "2026-11", "2026-12",
    "2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06",
    "2027-07", "2027-08", "2027-09", "2027-10", "2027-11", "2027-12"
]
NOMES_MESES = {
    "2026-10": "Outubro / 2026", "2026-11": "Novembro / 2026", "2026-12": "Dezembro / 2026",
    "2027-01": "Janeiro / 2027", "2027-02": "Fevereiro / 2027", "2027-03": "Março / 2027",
    "2027-04": "Abril / 2027", "2027-05": "Maio / 2027", "2027-06": "Junho / 2027",
    "2027-07": "Julho / 2027", "2027-08": "Agosto / 2027", "2027-09": "Setembro / 2027",
    "2027-10": "Outubro / 2027", "2027-11": "Novembro / 2027", "2027-12": "Dezembro / 2027"
}

mes_ativo = st.sidebar.selectbox(
    "📅 Mês de Trabalho (DRE):",
    MESES_DISPONIVEIS,
    index=0,
    format_func=lambda m: NOMES_MESES[m]
)
st.sidebar.markdown("---")

def lancar_item_unico_dre(mes_ref, fornecedor, valor_total, classificacao_escolhida):
    """Insere o lançamento direto e limpa a tabela de ajustes para que o novo valor apareça imediatamente no DRE."""
    conn = sqlite3.connect("notas_fiscais.db")
    cursor = conn.cursor()
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    cfg = CATALOGO_DRE_SPOLETO.get(classificacao_escolhida, {"dre": "Ocupação", "detalhamento": classificacao_escolhida})
    
    cursor.execute("""
        INSERT INTO lancamentos_dre (mes_referencia, data, fornecedor, descricao, valor, dre, classificacao, detalhamento)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (mes_ref, data_hoje, fornecedor.strip().upper(), classificacao_escolhida.upper(), float(valor_total), cfg["dre"], classificacao_escolhida, cfg["detalhamento"]))
    
    # Se existia um ajuste manual antigo gravado nessa conta que bloqueava o valor escaneado, remove-o
    cursor.execute("DELETE FROM ajustes_dre WHERE mes_referencia = ? AND conta = ?", (mes_ref, classificacao_escolhida))
    conn.commit()
    conn.close()

def salvar_nota_e_lancar_dre(mes_ref, razao_social, cnpj, valor_total, lista_produtos):
    conn = sqlite3.connect("notas_fiscais.db")
    cursor = conn.cursor()
    data_registo = datetime.now().strftime("%Y-%m-%d %H:%M")
    itens_json = json.dumps(lista_produtos, ensure_ascii=False)
    cursor.execute("""
        INSERT INTO notas (mes_referencia, data_registo, razao_social, cnpj, valor_total, itens_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (mes_ref, data_registo, razao_social, cnpj, valor_total, itens_json))

    df_temp = pd.DataFrame(lista_produtos)
    if not df_temp.empty:
        col_tot = "TotalItem" if "TotalItem" in df_temp.columns else "Total do Item (R$)"
        col_class = "Classificacao" if "Classificacao" in df_temp.columns else "Categoria"
        totais = df_temp.groupby(col_class)[col_tot].sum().to_dict()
        data_hoje = datetime.now().strftime("%Y-%m-%d")

        for class_nome, v in totais.items():
            if v > 0:
                cfg = CATALOGO_DRE_SPOLETO.get(class_nome, {
                    "dre": "Alimentos", "detalhamento": "Alimentos"
                })
                cursor.execute("""
                    INSERT INTO lancamentos_dre (mes_referencia, data, fornecedor, descricao, valor, dre, classificacao, detalhamento)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (mes_ref, data_hoje, razao_social.upper(), class_nome.upper(), float(v), cfg["dre"], class_nome, cfg["detalhamento"]))

        for item in lista_produtos:
            prod = str(item.get("Produto", "")).strip().upper()
            c = str(item.get(col_class, "")).strip()
            if prod:
                cursor.execute("""
                    INSERT INTO regras_classificacao (produto, categoria)
                    VALUES (?, ?)
                    ON CONFLICT(produto) DO UPDATE SET categoria=excluded.categoria
                """, (prod, c))

    conn.commit()
    conn.close()

def carregar_regras():
    conn = sqlite3.connect("notas_fiscais.db")
    c = conn.cursor()
    c.execute("SELECT produto, categoria FROM regras_classificacao")
    r = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return r

def obter_lancamentos_mes(mes_ref):
    conn = sqlite3.connect("notas_fiscais.db")
    df = pd.read_sql_query("SELECT id, data, fornecedor, descricao, valor, dre, classificacao, detalhamento FROM lancamentos_dre WHERE mes_referencia = ? ORDER BY id DESC", conn, params=(mes_ref,))
    conn.close()
    return df

def obter_ajustes_dre(mes_ref):
    conn = sqlite3.connect("notas_fiscais.db")
    c = conn.cursor()
    c.execute("SELECT conta, valor FROM ajustes_dre WHERE mes_referencia = ?", (mes_ref,))
    res = {row[0]: float(row[1]) for row in c.fetchall()}
    conn.close()
    return res

def salvar_ajustes_dre(mes_ref, dict_valores):
    conn = sqlite3.connect("notas_fiscais.db")
    c = conn.cursor()
    for conta, val in dict_valores.items():
        c.execute("""
            INSERT INTO ajustes_dre (mes_referencia, conta, valor)
            VALUES (?, ?, ?)
            ON CONFLICT(mes_referencia, conta) DO UPDATE SET valor=excluded.valor
        """, (mes_ref, conta, float(val)))
    conn.commit()
    conn.close()

def gerar_excel_dre(nome_mes, df_dre_completo, df_lancamentos):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export = df_dre_completo.copy()
        df_export.to_excel(writer, sheet_name="DRE_MENSAL", index=False)
        if not df_lancamentos.empty:
            df_lanc_export = df_lancamentos.copy()
            df_lanc_export.to_excel(writer, sheet_name="LANÇAMENTOS", index=False)
    output.seek(0)
    return output.getvalue()

# ----------------- CONFIGURAÇÕES IA -----------------
try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    st.error("⚠️ Configure a GEMINI_API_KEY no arquivo .streamlit/secrets.toml.")
    st.stop()

MODELOS_IA = ["gemini-3.8-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

def chamar_gemini_com_fallback(chave, conteudos):
    client = genai.Client(api_key=chave)
    ultimo = None
    for m in MODELOS_IA:
        for _ in range(2):
            try:
                res = client.models.generate_content(
                    model=m,
                    contents=conteudos,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                if res.text:
                    return json.loads(res.text)
            except Exception as e:
                ultimo = e
                time.sleep(2)
                continue
    st.error(f"Erro IA: {ultimo}")
    return None

def processar_multiplas_imagens_com_ia(partes_img, chave):
    regras = carregar_regras()
    ex_regras = json.dumps(regras, ensure_ascii=False) if regras else "Nenhuma ainda."
    prompt = f"""
    Você é o assistente financeiro oficial da franquia Spoleto (Capry Comércio Varejista de Alimentos LTDA).
    Analise as imagens anexadas do cupom, boleto ou nota fiscal.
    Extraia com máxima atenção:
    1. 'razao_social': Nome do estabelecimento, condomínio ou fornecedor.
    2. 'cnpj': CNPJ do emitente (se visível).
    3. 'valor_total': Valor total final do documento (float numérico).
    4. 'itens': Lista com: "Produto", "Quantidade", "Unid", "PrecoUnitario", "TotalItem", "Classificacao" (ex: Condomínio, Gás, Energia Elétrica, Alimentos, etc).
    Regras memorizadas: {ex_regras}
    Retorne APENAS um JSON no formato:
    {{
      "razao_social": "...",
      "cnpj": "...",
      "valor_total": 0.0,
      "itens": [...]
    }}
    """
    return chamar_gemini_com_fallback(chave, [prompt] + partes_img)

def processar_texto_com_ia(texto, nome_arq, chave):
    regras = carregar_regras()
    ex_regras = json.dumps(regras, ensure_ascii=False) if regras else "Nenhuma."
    prompt = f"""
    Analise o arquivo '{nome_arq}'. Extraia os itens e classifique com as contas do Spoleto.
    Regras conhecidas: {ex_regras}.
    Retorne lista JSON com: Produto, Quantidade, Unid, PrecoUnitario, TotalItem, Classificacao.
    Texto: {texto[:15000]}
    """
    res = chamar_gemini_com_fallback(chave, prompt)
    return res if isinstance(res, list) else []

def categorizar_nomes_xml(nomes, chave):
    regras = carregar_regras()
    mapa = {n: regras[n.strip().upper()] for n in nomes if n.strip().upper() in regras}
    faltam = [n for n in nomes if n.strip().upper() not in regras]
    if faltam:
        p = f"""
        Classifique os produtos abaixo nas opções oficiais do DRE Spoleto:
        {json.dumps(faltam, ensure_ascii=False)}.
        Retorne JSON objeto {{\"nome_do_produto\": \"Classificacao\"}}.
        """
        res = chamar_gemini_com_fallback(chave, p)
        if isinstance(res, dict):
            mapa.update(res)
    return mapa

# ----------------- GERENCIAMENTO DE SESSÃO -----------------
if "fotos_acumuladas" not in st.session_state:
    st.session_state.fotos_acumuladas = []
if "dados_extraidos" not in st.session_state:
    st.session_state.dados_extraidos = None
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

def resetar_processamento_nota():
    st.session_state.fotos_acumuladas = []
    st.session_state.dados_extraidos = None
    st.session_state.uploader_key += 1

# ----------------- NAVEGAÇÃO -----------------
menu = st.sidebar.radio("Módulo:", [
    f"📊 DRE Spoleto ({NOMES_MESES[mes_ativo]})",
    "📸 Escanear & Alimentar Nota",
    "📝 Lançamentos do Mês",
    "🧠 Regras Inteligentes"
])

# ==============================================================================
# 1. ABA DO DRE OFICIAL (SOMA DINÂMICA REAL: ESCANEADOS + AJUSTES)
# ==============================================================================
if menu.startswith("📊 DRE Spoleto"):
    st.subheader(f"📊 Demonstrativo de Resultados (DRE) — {NOMES_MESES[mes_ativo]}")
    st.write("Todos os boletos e notas escaneados (Condomínio, Gás, Alimentos, etc.) entram automaticamente abaixo somados aos ajustes[cite: 7, 8].")

    # 1. Buscar todas as somas de boletos/notas escaneados
    df_l = obter_lancamentos_mes(mes_ativo)
    somas_escaneadas = df_l.groupby("detalhamento")["valor"].sum().to_dict() if not df_l.empty else {}
    ajustes_banco = obter_ajustes_dre(mes_ativo)

    CONTAS_DRE_PAINEL = [
        ("Faturamento Balcão", None, 0.0),
        ("Faturamento Delivery", None, 0.0),
        ("Imposto Federal", "Imposto Federal", 0.0),
        ("Imposto Estadual", "Imposto Estadual", 0.0),
        ("Alimentos", "Alimentos", 0.0),
        ("Bebidas", "Bebidas", 0.0),
        ("Descartáveis", "Descartáveis", 0.0),
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
        ("Total Bonificação", None, 0.0)
    ]

    # SOMA CORRETA E GARANTIDA: Escaneado + Ajuste manual (nunca mais ignora o escaneado)
    lista_linhas_editaveis = []
    for nome_conta, chave_det, val_padrao in CONTAS_DRE_PAINEL:
        val_escaneado = float(somas_escaneadas.get(chave_det, 0.0)) if chave_det else 0.0
        val_ajuste = float(ajustes_banco.get(nome_conta, val_padrao))
        val_final = val_escaneado if val_escaneado > 0 and val_ajuste == 0.0 else (val_escaneado + val_ajuste)

        lista_linhas_editaveis.append({
            "CONTA": nome_conta,
            "VALOR (R$)": float(round(val_final, 2))
        })

    df_base_editavel = pd.DataFrame(lista_linhas_editaveis)

    st.write("👇 **Tabela de Lançamentos do DRE (Altere qualquer valor e clique em salvar):**")
    
    # Key dinâmica atrelada à quantidade de lançamentos para forçar atualização em tempo real
    qtd_lanc = len(df_l)
    df_dre_editado = st.data_editor(
        df_base_editavel,
        column_config={
            "CONTA": st.column_config.TextColumn("Conta / Indicador", disabled=True),
            "VALOR (R$)": st.column_config.NumberColumn("VALOR (R$)", format="R$ %.2f", min_value=0.0, step=10.0, required=True)
        },
        use_container_width=True,
        num_rows="fixed",
        height=520,
        key=f"editor_dre_{mes_ativo}_v{qtd_lanc}"
    )

    col_save_dre, _ = st.columns([2, 3])
    with col_save_dre:
        if st.button("💾 Salvar Alterações do DRE na Base de Dados", type="primary", use_container_width=True):
            novos_ajustes = dict(zip(df_dre_editado["CONTA"], df_dre_editado["VALOR (R$)"]))
            salvar_ajustes_dre(mes_ativo, novos_ajustes)
            st.success("✅ **Alterações salvas com sucesso no banco de dados!**")

    v_map = dict(zip(df_dre_editado["CONTA"], df_dre_editado["VALOR (R$)"]))

    def v(k):
        return float(v_map.get(k, 0.0))

    fat_balcao = v("Faturamento Balcão")
    fat_delivery = v("Faturamento Delivery")
    venda_bruta = fat_balcao + fat_delivery
    imp_fed = v("Imposto Federal")
    imp_est = v("Imposto Estadual")
    rec_liquida = venda_bruta - (imp_fed + imp_est)

    cmv_alim = v("Alimentos")
    cmv_beb = v("Bebidas")
    cmv_desc = v("Descartáveis")
    cmv_fret = v("Fretes")
    total_cmv = cmv_alim + cmv_beb + cmv_desc + cmv_fret
    lucro_bruto = rec_liquida - total_cmv

    total_ocup = v("Aluguel") + v("Ar condicionado") + v("Condomínio") + v("Fundo de Promoção") + v("IPTU") + v("Taxas e Outros")
    total_pess = (
        v("Salário") + v("Adiantamento") + v("Benefícios (Alimentação Funcionários)") +
        v("Encargos") + v("Férias") + v("13 salário") + v("Provisões") + v("Rescisão") + v("Outros (pessoal)")
    )
    total_util = v("Água e Esgoto") + v("Energia Elétrica") + v("Gás") + v("Internet") + v("Telefone") + v("Outros (utilidades)")
    total_serv = v("Serviços") + v("Terceiros")
    total_mat = (
        v("Material de Escritório") + v("Material de Limpeza") + v("Uniformes") +
        v("Utensílios") + v("Outros Materiais de Uso e Consumo")
    )
    total_manut = v("Serviço - Manutenção e Reparos") + v("Material - Manutenção e Reparos")
    total_deliv = (v("Comissão agregadores") + v("Custo com entrega (motoqueiros)")) - v("Taxa de entrega arrecadada")
    total_mkt = v("Anúncios/Propagandas") + v("Fundo de Marketing") + v("Royalties")
    total_fin = v("Custo Cartão de Crédito") + v("Custo Cartão de Débito")

    total_despesas = (
        imp_fed + imp_est + total_cmv + total_ocup + total_pess +
        total_util + total_serv + total_mat + total_manut +
        total_deliv + total_mkt + total_fin
    )
    res_operacional = venda_bruta - total_despesas
    res_final = res_operacional + v("Total Bonificação")

    def pct(val):
        if venda_bruta > 0:
            return f"{(val / venda_bruta) * 100:.2f}%"
        return "0.00%"

    st.markdown("---")
    st.write("### 📈 Visão Consolidada em Tempo Real")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔹 Venda Bruta", f"R$ {venda_bruta:,.2f}")
    c2.metric("📦 CMV Total", f"R$ {total_cmv:,.2f}", delta=pct(total_cmv), delta_color="inverse")
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
        {"CONTA": "📦 C M V (Custo de Mercadoria Vendida)", "VALOR": total_cmv, "%": pct(total_cmv)},
        {"CONTA": "  • Alimentos", "VALOR": cmv_alim, "%": pct(cmv_alim)},
        {"CONTA": "  • Bebidas", "VALOR": cmv_beb, "%": pct(cmv_beb)},
        {"CONTA": "  • Descartáveis", "VALOR": cmv_desc, "%": pct(cmv_desc)},
        {"CONTA": "  • Fretes", "VALOR": cmv_fret, "%": pct(cmv_fret)},
        {"CONTA": "🔹 LUCRO BRUTO", "VALOR": lucro_bruto, "%": pct(lucro_bruto)},
        {"CONTA": "----------------------------------------", "VALOR": None, "%": ""},
        {"CONTA": "🏢 TOTAL OCUPAÇÃO", "VALOR": total_ocup, "%": pct(total_ocup)},
        {"CONTA": "  • Condomínio", "VALOR": v("Condomínio"), "%": pct(v("Condomínio"))},
        {"CONTA": "  • Aluguel / Taxas", "VALOR": total_ocup - v("Condomínio"), "%": pct(total_ocup - v("Condomínio"))},
        {"CONTA": "👥 TOTAL PESSOAL", "VALOR": total_pess, "%": pct(total_pess)},
        {"CONTA": "💡 TOTAL UTILIDADES", "VALOR": total_util, "%": pct(total_util)},
        {"CONTA": "  • Gás", "VALOR": v("Gás"), "%": pct(v("Gás"))},
        {"CONTA": "  • Energia Elétrica", "VALOR": v("Energia Elétrica"), "%": pct(v("Energia Elétrica"))},
        {"CONTA": "🧹 MATERIAIS DE USO & CONSUMO", "VALOR": total_mat, "%": pct(total_mat)},
        {"CONTA": "🔧 MANUTENÇÃO", "VALOR": total_manut, "%": pct(total_manut)},
        {"CONTA": "🛵 DELIVERY", "VALOR": total_deliv, "%": pct(total_deliv)},
        {"CONTA": "📢 MARKETING & FRANQUEADOR", "VALOR": total_mkt, "%": pct(total_mkt)},
        {"CONTA": "💳 CUSTO FINANCEIRO", "VALOR": total_fin, "%": pct(total_fin)},
        {"CONTA": "----------------------------------------", "VALOR": None, "%": ""},
        {"CONTA": "🔴 TOTAL DESPESAS", "VALOR": total_despesas, "%": pct(total_despesas)},
        {"CONTA": "🏆 RESULTADO OPERACIONAL", "VALOR": res_operacional, "%": pct(res_operacional)},
        {"CONTA": "💰 RESULTADO FINAL LÍQUIDO", "VALOR": res_final, "%": pct(res_final)}
    ]

    df_spoleto_view = pd.DataFrame(estrutura_dre_spoleto)
    df_spoleto_view["VALOR"] = df_spoleto_view["VALOR"].apply(lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "")
    st.dataframe(df_spoleto_view, use_container_width=True, height=550)

    st.markdown("### 📥 Baixar Relatório")
    dados_excel = gerar_excel_dre(NOMES_MESES[mes_ativo], pd.DataFrame(estrutura_dre_spoleto), df_l)
    st.download_button(
        label="📊 Baixar DRE Atualizado em Excel (.xlsx)",
        data=dados_excel,
        file_name=f"DRE_Spoleto_{mes_ativo}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )

# ==============================================================================
# 2. ABA DE ESCANEAR NOTA & ALIMENTAR DRE AUTOMATICAMENTE
# ==============================================================================
elif menu.startswith("📸 Escanear"):
    st.subheader(f"📸 Escanear Nota Fiscal para o DRE de: {NOMES_MESES[mes_ativo]}")

    ukey = st.session_state.uploader_key

    aba_foto, aba_cam, aba_arq = st.tabs([
        "📸 Fotos Nítidas (Telemóvel / Galeria)",
        "🖥️ Câmara ao Vivo",
        "📁 Arquivo (XML / Excel / PDF)"
    ])

    with aba_foto:
        f_upload = st.file_uploader(
            "Fotos do cupom/boleto/nota:",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key=f"file_uploader_{ukey}"
        )
        if f_upload and st.button("➕ Adicionar fotos à fila", key=f"btn_add_f_{ukey}"):
            st.session_state.fotos_acumuladas = []
            for f in f_upload:
                st.session_state.fotos_acumuladas.append({
                    "bytes": f.getvalue(),
                    "mime": "image/jpeg" if f.name.lower().endswith(('jpg', 'jpeg')) else f"image/{f.name.split('.')[-1].lower()}"
                })
            st.success(f"{len(f_upload)} foto(s) da nova nota carregada(s)!")

    with aba_cam:
        f_cam = st.camera_input("Capturar foto", key=f"cam_input_{ukey}")
        if f_cam and st.button("➕ Adicionar captura à fila", key=f"btn_add_cam_{ukey}"):
            st.session_state.fotos_acumuladas = [{"bytes": f_cam.getvalue(), "mime": "image/jpeg"}]
            st.success("Foto capturada pronta para leitura!")

    if st.session_state.fotos_acumuladas:
        st.write(f"**Total acumulado:** {len(st.session_state.fotos_acumuladas)} foto(s)")
        c1, c2 = st.columns([2, 1])
        with c1:
            if st.button("🚀 Processar Fotos com IA & Alimentar DRE", type="primary", use_container_width=True):
                partes = [types.Part.from_bytes(data=f["bytes"], mime_type=f["mime"]) for f in st.session_state.fotos_acumuladas]
                with st.spinner("🤖 Lendo itens e identificando o documento..."):
                    res = processar_multiplas_imagens_com_ia(partes, api_key)
                    if res and isinstance(res, dict):
                        st.session_state.dados_extraidos = {
                            "razao_social": res.get("razao_social") or "Fornecedor",
                            "cnpj": res.get("cnpj") or "Não informado",
                            "valor_total": float(res.get("valor_total") or 0.0),
                            "itens": res.get("itens", [])
                        }
                        st.session_state.fotos_acumuladas = []
                        st.rerun()
                    else:
                        st.error("Não foi possível extrair dados legíveis desta imagem. Tente capturar novamente com boa iluminação.")
        with c2:
            if st.button("🗑️ Descartar Fotos", use_container_width=True):
                resetar_processamento_nota()
                st.rerun()

    with aba_arq:
        doc = st.file_uploader("Enviar XML, PDF ou Excel:", type=["xml", "xlsx", "xls", "pdf"], key=f"doc_uploader_{ukey}")
        if doc and st.button("Processar Arquivo", key=f"btn_doc_{ukey}"):
            st.session_state.dados_extraidos = None
            ext = doc.name.split(".")[-1].lower()
            if ext == "xml":
                data = xmltodict.parse(doc.read())
                inf = data.get("nfeProc", data).get("NFe", {}).get("infNFe", {})
                emit = inf.get("emit", {})
                tot = inf.get("total", {}).get("ICMSTot", {})
                det = inf.get("det", [])
                if not isinstance(det, list):
                    det = [det]
                nomes = [i.get("prod", {}).get("xProd", "") for i in det]
                mapa = categorizar_nomes_xml(nomes, api_key)
                itens_x = []
                for i in det:
                    p = i.get("prod", {})
                    nm = p.get("xProd", "")
                    itens_x.append({
                        "Classificacao": mapa.get(nm, "Demais Alimentos"),
                        "Produto": nm,
                        "Quantidade": float(p.get("qCom", 0)),
                        "Unid": p.get("uCom", "UN"),
                        "PrecoUnitario": float(p.get("vUnCom", 0)),
                        "TotalItem": float(p.get("vProd", 0))
                    })
                st.session_state.dados_extraidos = {
                    "razao_social": emit.get("xNome", "Fornecedor"),
                    "cnpj": emit.get("CNPJ", "Não informado"),
                    "valor_total": float(tot.get("vNF", 0.0)),
                    "itens": itens_x
                }
                st.rerun()
            else:
                txt = doc.read().decode("latin1", errors="ignore") if ext == "pdf" else pd.read_excel(doc).to_string()
                res_it = processar_texto_com_ia(txt, doc.name, api_key)
                st.session_state.dados_extraidos = {
                    "razao_social": "Importação",
                    "cnpj": "Não informado",
                    "valor_total": sum(float(i.get("TotalItem", 0)) for i in res_it),
                    "itens": res_it
                }
                st.rerun()

    # ----------------- PAINEL DE RESULTADO ISOLADO DA NOTA -----------------
    if st.session_state.dados_extraidos:
        dados = st.session_state.dados_extraidos
        st.markdown("---")
        st.subheader("📋 Resumo do Documento Identificado")
        c_a, c_b, c_c = st.columns(3)
        c_a.metric("Fornecedor / Emitente", dados["razao_social"])
        c_b.metric("CNPJ", dados["cnpj"])
        c_c.metric("Valor Total", f"R$ {dados['valor_total']:,.2f}")

        tab_rapida, tab_detalhada = st.tabs([
            "⚡ Lançamento Rápido (Item Único: Condomínio, Gás, Energia...)",
            "📦 Destrinchar Vários Itens (Compras de Mercadoria)"
        ])

        with tab_rapida:
            st.write("💡 **Ideal para boletos e contas mensais:** o valor vai direto para a conta sem complicação[cite: 7, 8].")
            
            # Detecta se é Condomínio ou Gás no texto da razão social
            idx_sug = 0
            if "CONDOM" in dados["razao_social"].upper() and "Condomínio" in LISTA_TODAS_CLASSIFICACOES:
                idx_sug = LISTA_TODAS_CLASSIFICACOES.index("Condomínio")
            elif "GAS" in dados["razao_social"].upper() and "Gás" in LISTA_TODAS_CLASSIFICACOES:
                idx_sug = LISTA_TODAS_CLASSIFICACOES.index("Gás")
            
            c_rap1, c_rap2 = st.columns(2)
            with c_rap1:
                classificacao_rapida = st.selectbox(
                    "Selecione o Indicador do DRE:",
                    LISTA_TODAS_CLASSIFICACOES,
                    index=idx_sug,
                    key=f"sel_rapido_dre_{ukey}"
                )
            with c_rap2:
                valor_rapido = st.number_input(
                    "Valor a Lançar (R$):",
                    value=float(dados["valor_total"]),
                    min_value=0.01,
                    step=10.0,
                    key=f"val_rapido_dre_{ukey}"
                )

            if st.button(f"⚡ Lançar R$ {valor_rapido:,.2f} direto em '{classificacao_rapida}' no DRE", type="primary", use_container_width=True):
                lancar_item_unico_dre(
                    mes_ref=mes_ativo,
                    fornecedor=dados["razao_social"],
                    valor_total=valor_rapido,
                    classificacao_escolhida=classificacao_rapida
                )
                st.success(f"✅ Sucesso! R$ {valor_rapido:,.2f} lançado diretamente em **{classificacao_rapida}** no DRE de {NOMES_MESES[mes_ativo]}[cite: 7, 8]!")
                resetar_processamento_nota()
                st.rerun()

        with tab_detalhada:
            df_itens = pd.DataFrame(dados["itens"])
            if not df_itens.empty:
                if "Classificacao" not in df_itens.columns and "Categoria" in df_itens.columns:
                    df_itens.rename(columns={"Categoria": "Classificacao"}, inplace=True)

                df_itens["Classificacao"] = df_itens["Classificacao"].apply(
                    lambda x: x if x in CATALOGO_DRE_SPOLETO else "Demais Alimentos"
                )

                st.write("👇 **Revise cada item individual desta nota:**")
                df_edit = st.data_editor(
                    df_itens,
                    column_config={
                        "Classificacao": st.column_config.SelectboxColumn(
                            "Classificação Spoleto",
                            options=LISTA_TODAS_CLASSIFICACOES,
                            required=True
                        ),
                        "Produto": st.column_config.TextColumn("Produto", required=True),
                        "Quantidade": st.column_config.NumberColumn("Qtd", format="%.2f"),
                        "Unid": st.column_config.TextColumn("Unid"),
                        "PrecoUnitario": st.column_config.NumberColumn("Preço Unit. (R$)", format="R$ %.2f"),
                        "TotalItem": st.column_config.NumberColumn("Total Item (R$)", format="R$ %.2f"),
                    },
                    use_container_width=True,
                    num_rows="dynamic",
                    key=f"editor_nota_ativa_{ukey}"
                )

                somas_class = df_edit.groupby("Classificacao")["TotalItem"].sum().to_dict()
                st.write("#### 📊 Subtotais por Categoria:")
                c_grid = st.columns(min(len(somas_class), 4))
                for idx, (cl_n, val_n) in enumerate(somas_class.items()):
                    c_grid[idx % 4].metric(cl_n, f"R$ {val_n:,.2f}")

                st.markdown("---")
                col_save_det, col_canc = st.columns([2, 1])
                with col_save_det:
                    if st.button(f"🚀 Confirmar Itens Detalhados no DRE ({NOMES_MESES[mes_ativo]})", type="primary", use_container_width=True):
                        salvar_nota_e_lancar_dre(
                            mes_ref=mes_ativo,
                            razao_social=dados["razao_social"],
                            cnpj=dados["cnpj"],
                            valor_total=dados["valor_total"] or sum(somas_class.values()),
                            lista_produtos=df_edit.to_dict(orient="records")
                        )
                        st.success(f"✅ Sucesso! Itens detalhados incorporados à aba LANÇAMENTOS do DRE[cite: 7, 8]!")
                        resetar_processamento_nota()
                        st.rerun()
                with col_canc:
                    if st.button("❌ Descartar Nota", use_container_width=True):
                        resetar_processamento_nota()
                        st.rerun()

# ==============================================================================
# 3. ABA DE LANÇAMENTOS DO MÊS
# ==============================================================================
elif menu.startswith("📝 Lançamentos"):
    st.subheader(f"📝 Base de Lançamentos — {NOMES_MESES[mes_ativo]}")
    st.write("Esta tabela corresponde à aba **LANÇAMENTOS** da sua planilha Spoleto[cite: 7].")

    df_lanc = obter_lancamentos_mes(mes_ativo)
    if df_lanc.empty:
        st.info(f"Nenhum lançamento registrado ainda para {NOMES_MESES[mes_ativo]}. Use o menu de escanear notas para alimentar.")
    else:
        df_show = df_lanc.copy()
        df_show["valor"] = df_show["valor"].apply(lambda x: f"R$ {x:,.2f}")
        df_show.rename(columns={
            "id": "ID", "data": "DATA", "fornecedor": "FORNECEDOR", "descricao": "DESCRIÇÃO",
            "valor": "VALOR", "dre": "DRE", "classificacao": "CLASSIFICAÇÃO", "detalhamento": "DETALHAMENTO"
        }, inplace=True)
        st.dataframe(df_show, use_container_width=True)

        st.markdown("---")
        st.subheader("🗑️ Excluir Lançamento Específico")
        c_sel, c_del = st.columns([2, 1])
        with c_sel:
            id_del = st.selectbox("Selecione o lançamento pelo ID:", df_lanc["id"].tolist())
        with c_del:
            st.write("&nbsp;")
            if st.button("Eliminar Lançamento", type="secondary", use_container_width=True):
                conn = sqlite3.connect("notas_fiscais.db")
                conn.execute("DELETE FROM lancamentos_dre WHERE id = ?", (id_del,))
                conn.commit()
                conn.close()
                st.warning(f"Lançamento #{id_del} removido do DRE.")
                st.rerun()

# ==============================================================================
# 4. ABA DE REGRAS INTELIGENTES
# ==============================================================================
elif menu.startswith("🧠 Regras"):
    st.subheader("🧠 Dicionário Inteligente de Classificações")
    st.write("Produtos memorizados pelas suas correções anteriores:")
    regras = carregar_regras()
    if regras:
        df_r = pd.DataFrame(list(regras.items()), columns=["Produto", "Classificação Spoleto"]).sort_values("Produto")
        st.dataframe(df_r, use_container_width=True)
    else:
        st.info("Nenhuma regra personalizada ainda. Sempre que corrigir e salvar uma nota, a IA memoriza aqui.")
