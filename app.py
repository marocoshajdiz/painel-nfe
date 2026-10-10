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
            usuario = st.text_input("Usuário", placeholder="admin")
            senha = st.text_input("Senha", type="password", placeholder="massima")
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

# CSS para visor expandido da câmera
st.markdown("""
<style>
div[data-testid="stCameraInput"] { width: 100% !important; max-width: 900px !important; margin: 0 auto; }
div[data-testid="stCameraInput"] video { width: 100% !important; height: 70vh !important; min-height: 480px !important; border-radius: 14px; object-fit: cover !important; border: 2px solid #ff4b4b; }
div[data-testid="stCameraInput"] button { padding: 0.75rem 1.5rem !important; font-size: 1.1rem !important; border-radius: 10px !important; }
</style>
""", unsafe_allow_html=True)

# ----------------- BASE DE DADOS (SQLite com Migração Automática) -----------------
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
    # Migração garantida: se a tabela já existia sem a coluna, adiciona sem perda de dados
    try:
        cursor.execute("ALTER TABLE dados_mensais ADD COLUMN ultima_atualizacao TEXT")
    except Exception:
        pass

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

MAPA_DRE_REGRAS = {
    "Alimentos": {"desc": "ALIMENTOS", "dre": "Alimentos", "class": "Demais Alimentos", "det": "Alimentos"},
    "Bebidas": {"desc": "BEBIDAS", "dre": "Bebidas", "class": "Bebidas", "det": "Bebidas"},
    "Descartáveis": {"desc": "DESCARTAVEIS", "dre": "Descartáveis", "class": "Embalagens E Descartáveis", "det": "Descartáveis"},
    "Limpeza": {"desc": "LIMPEZA", "dre": "Material_De_Uso_E_Consumo", "class": "Material De Limpeza", "det": "Material De Limpeza"},
    "Funcionários": {"desc": "FUNCIONARIO", "dre": "Pessoal", "class": "Alimentação Funcionário", "det": "Benefícios"},
    "Utensílios": {"desc": "UTENSILIOS", "dre": "Material_De_Uso_E_Consumo", "class": "Utensílios De Cozinha", "det": "Utensílios"}
}

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
        totais = df_temp.groupby("Categoria")[col_tot].sum().to_dict()
        data_hoje = datetime.now().strftime("%Y-%m-%d")

        for cat, v in totais.items():
            if v > 0:
                cfg = MAPA_DRE_REGRAS.get(cat, {
                    "desc": cat.upper(), "dre": "Alimentos", "class": "Demais Alimentos", "det": "Alimentos"
                })
                cursor.execute("""
                    INSERT INTO lancamentos_dre (mes_referencia, data, fornecedor, descricao, valor, dre, classificacao, detalhamento)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (mes_ref, data_hoje, razao_social.upper(), cfg["desc"], float(v), cfg["dre"], cfg["class"], cfg["det"]))

        for item in lista_produtos:
            prod = str(item.get("Produto", "")).strip().upper()
            c = str(item.get("Categoria", "")).strip()
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

def obter_dados_mensais(mes_ref):
    conn = sqlite3.connect("notas_fiscais.db")
    c = conn.cursor()
    try:
        c.execute("SELECT fat_balcao, fat_delivery, imposto_estadual, gas, terceiros, bonificacao, ultima_atualizacao FROM dados_mensais WHERE mes_referencia = ?", (mes_ref,))
        row = c.fetchone()
        if row:
            return {
                "balcao": float(row[0] or 0.0),
                "delivery": float(row[1] or 0.0),
                "imposto_est": float(row[2] or 0.0),
                "gas": float(row[3] or 0.0),
                "terceiros": float(row[4] or 0.0),
                "bonificacao": float(row[5] or 0.0),
                "atualizado_em": str(row[6]) if len(row) > 6 and row[6] else "Nunca"
            }
    except Exception:
        pass
    finally:
        conn.close()

    return {
        "balcao": 0.0, "delivery": 0.0, "imposto_est": 0.0,
        "gas": 0.0, "terceiros": 0.0, "bonificacao": 0.0, "atualizado_em": "Nunca"
    }

def salvar_dados_mensais_seguro(mes_ref, dados):
    conn = sqlite3.connect("notas_fiscais.db")
    c = conn.cursor()
    horario_agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    c.execute("""
        INSERT INTO dados_mensais (mes_referencia, fat_balcao, fat_delivery, imposto_estadual, gas, terceiros, bonificacao, ultima_atualizacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mes_referencia) DO UPDATE SET
            fat_balcao=excluded.fat_balcao,
            fat_delivery=excluded.fat_delivery,
            imposto_estadual=excluded.imposto_estadual,
            gas=excluded.gas,
            terceiros=excluded.terceiros,
            bonificacao=excluded.bonificacao,
            ultima_atualizacao=excluded.ultima_atualizacao
    """, (mes_ref, dados["balcao"], dados["delivery"], dados["imposto_est"], dados["gas"], dados["terceiros"], dados["bonificacao"], horario_agora))
    conn.commit()
    conn.close()
    return horario_agora

# ----------------- GERADOR EXCEL -----------------
def gerar_excel_dre(nome_mes, linhas_dre, df_lancamentos):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export = pd.DataFrame([{
            "CONTA": item["CONTA"].replace("🔹 ", "").replace("📦 ", "").replace("🏢 ", "").replace("👥 ", "").replace("💡 ", "").replace("🧹 ", "").replace("🔧 ", "").replace("🛵 ", "").replace("📢 ", "").replace("💳 ", "").replace("🔴 ", "").replace("🏆 ", "").replace("💰 ", ""),
            "VALOR (R$)": item["VALOR"],
            "% SOBRE VENDA": item["%"]
        } for item in linhas_dre if "----" not in item["CONTA"]])
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

LISTA_CATEGORIAS = ["Alimentos", "Descartáveis", "Limpeza", "Funcionários", "Utensílios", "Bebidas"]
CATEGORIAS_VALIDAS = ", ".join(LISTA_CATEGORIAS)
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
    Você é o assistente financeiro da franquia Spoleto (Capry Comércio).
    Analise as imagens anexadas do cupom/nota fiscal.
    Categorias obrigatórias: {CATEGORIAS_VALIDAS}.
    Priorize este histórico de regras: {ex_regras}
    Extraia: 'razao_social', 'cnpj', 'valor_total' (float) e 'itens' [Produto, Quantidade, Unid, PrecoUnitario, TotalItem, Categoria].
    Retorne APENAS um JSON válido.
    """
    return chamar_gemini_com_fallback(chave, [prompt] + partes_img)

def processar_texto_com_ia(texto, nome_arq, chave):
    regras = carregar_regras()
    ex_regras = json.dumps(regras, ensure_ascii=False) if regras else "Nenhuma."
    prompt = f"""
    Analise o arquivo '{nome_arq}'. Categorias obrigatórias: {CATEGORIAS_VALIDAS}.
    Regras conhecidas: {ex_regras}.
    Retorne lista JSON com: Produto, Quantidade, Unid, PrecoUnitario, TotalItem, Categoria.
    Texto: {texto[:15000]}
    """
    res = chamar_gemini_com_fallback(chave, prompt)
    return res if isinstance(res, list) else []

def categorizar_nomes_xml(nomes, chave):
    regras = carregar_regras()
    mapa = {n: regras[n.strip().upper()] for n in nomes if n.strip().upper() in regras}
    faltam = [n for n in nomes if n.strip().upper() not in regras]
    if faltam:
        p = f"Classifique os itens em {CATEGORIAS_VALIDAS}: {json.dumps(faltam, ensure_ascii=False)}. Retorne JSON objeto {{\"nome\": \"categoria\"}}."
        res = chamar_gemini_com_fallback(chave, p)
        if isinstance(res, dict):
            mapa.update(res)
    return mapa

# ----------------- NAVEGAÇÃO -----------------
menu = st.sidebar.radio("Módulo:", [
    f"📊 DRE Spoleto ({NOMES_MESES[mes_ativo]})",
    "📸 Escanear & Alimentar Nota",
    "📝 Lançamentos do Mês",
    "🧠 Regras Inteligentes"
])

if "fotos_acumuladas" not in st.session_state:
    st.session_state.fotos_acumuladas = []
if "dados_extraidos" not in st.session_state:
    st.session_state.dados_extraidos = None

# ==============================================================================
# 1. ABA DO DRE OFICIAL (TEMPO REAL & GRAVAÇÃO SEGURA)
# ==============================================================================
if menu.startswith("📊 DRE Spoleto"):
    st.subheader(f"📊 Demonstrativo de Resultados (DRE) — {NOMES_MESES[mes_ativo]}")
    st.write("Todos os custos escaneados neste mês entram automaticamente no cálculo de CMV e despesas operacionais abaixo[cite: 7, 8].")

    dados_bd = obter_dados_mensais(mes_ativo)

    prefixo = f"dre_{mes_ativo}_"
    if f"{prefixo}balcao" not in st.session_state:
        st.session_state[f"{prefixo}balcao"] = dados_bd["balcao"]
    if f"{prefixo}delivery" not in st.session_state:
        st.session_state[f"{prefixo}delivery"] = dados_bd["delivery"]
    if f"{prefixo}imposto_est" not in st.session_state:
        st.session_state[f"{prefixo}imposto_est"] = dados_bd["imposto_est"]
    if f"{prefixo}gas" not in st.session_state:
        st.session_state[f"{prefixo}gas"] = dados_bd["gas"]
    if f"{prefixo}terceiros" not in st.session_state:
        st.session_state[f"{prefixo}terceiros"] = dados_bd["terceiros"]
    if f"{prefixo}bonificacao" not in st.session_state:
        st.session_state[f"{prefixo}bonificacao"] = dados_bd["bonificacao"]

    with st.expander("⚙️ Painel de Vendas & Parâmetros do Mês (Atualização em Tempo Real)", expanded=True):
        st.write("Altere qualquer valor abaixo: **o DRE recalcula na hora**. Clique em salvar para gravar com segurança na base de dados.")
        
        c_fb, c_fd, c_ie, c_gas, c_terc, c_bon = st.columns(6)
        with c_fb:
            fat_b = st.number_input("Fat. Balcão (R$)", min_value=0.0, step=100.0, key=f"{prefixo}balcao")
        with c_fd:
            fat_d = st.number_input("Fat. Delivery (R$)", min_value=0.0, step=100.0, key=f"{prefixo}delivery")
        with c_ie:
            imp_e = st.number_input("Imposto Estadual (R$)", min_value=0.0, step=50.0, key=f"{prefixo}imposto_est")
        with c_gas:
            val_gas = st.number_input("Gás (R$)", min_value=0.0, step=50.0, key=f"{prefixo}gas")
        with c_terc:
            val_terc = st.number_input("Serv. Terceiros (R$)", min_value=0.0, step=100.0, key=f"{prefixo}terceiros")
        with c_bon:
            val_bon = st.number_input("Bonificações (R$)", min_value=0.0, step=50.0, key=f"{prefixo}bonificacao")

        col_salvar, col_status = st.columns([2, 3])
        with col_salvar:
            if st.button("💾 Salvar Parâmetros do Mês na Base de Dados", type="primary", use_container_width=True):
                horario_salvo = salvar_dados_mensais_seguro(mes_ativo, {
                    "balcao": fat_b,
                    "delivery": fat_d,
                    "imposto_est": imp_e,
                    "gas": val_gas,
                    "terceiros": val_terc,
                    "bonificacao": val_bon
                })
                st.success(f"🔒 **Gravado com Sucesso!** Base de dados atualizada e confirmada às **{horario_salvo}**.")
        with col_status:
            st.info(f"🕒 **Última gravação confirmada no banco:** {dados_bd['atualizado_em']}")

    df_l = obter_lancamentos_mes(mes_ativo)
    somas_det = df_l.groupby("detalhamento")["valor"].sum().to_dict() if not df_l.empty else {}

    def get_v(det_nome):
        return float(somas_det.get(det_nome, 0.0))

    venda_bruta = fat_b + fat_d
    imposto_fed = get_v("Imposto Federal")
    imposto_est = imp_e
    rec_liquida = venda_bruta - (imposto_fed + imposto_est)

    cmv_alimentos = get_v("Alimentos")
    cmv_bebidas = get_v("Bebidas")
    cmv_descartaveis = get_v("Descartáveis")
    cmv_fretes = get_v("Fretes")
    subtotal_cmv = cmv_alimentos + cmv_bebidas + cmv_descartaveis
    total_cmv = subtotal_cmv + cmv_fretes
    lucro_bruto = rec_liquida - total_cmv

    ocup_aluguel = get_v("Aluguel")
    ocup_ar = get_v("Ar Condicionado")
    ocup_condo = get_v("Condomínio")
    ocup_fundo = get_v("Fundo De Promoção")
    ocup_iptu = get_v("Iptu")
    ocup_taxas = get_v("Taxas E Outros")
    total_ocupacao = ocup_aluguel + ocup_ar + ocup_condo + ocup_fundo + ocup_iptu + ocup_taxas

    pess_salario = get_v("Salário")
    pess_adiant = get_v("Adiantamento")
    pess_benef = get_v("Benefícios")
    pess_encargos = get_v("Encargos")
    pess_ferias = get_v("Férias")
    pess_13 = get_v("13 Salário")
    pess_provis = get_v("Provisões")
    pess_rescisao = get_v("Rescisão")
    pess_outros = get_v("Outros (pessoal)")
    total_pessoal = pess_salario + pess_adiant + pess_benef + pess_encargos + pess_ferias + pess_13 + pess_provis + pess_rescisao + pess_outros

    util_agua = get_v("Água E Esgoto")
    util_energia = get_v("Energia Elétrica")
    util_gas = val_gas + get_v("Gás")
    util_internet = get_v("Internet")
    util_tel = get_v("Telefone")
    util_outros = get_v("Outros (utilidades)")
    total_utilidades = util_agua + util_energia + util_gas + util_internet + util_tel + util_outros

    serv_proprios = get_v("Serviços")
    serv_terceiros = val_terc + get_v("Terceiros")
    total_servicos = serv_proprios + serv_terceiros

    mat_escritorio = get_v("Material De Escritório")
    mat_limpeza = get_v("Material De Limpeza")
    mat_uniformes = get_v("Uniformes")
    mat_utensilios = get_v("Utensílios")
    mat_outros = get_v("Outros Materiais De Uso E Consumo")
    total_materiais = mat_escritorio + mat_limpeza + mat_uniformes + mat_utensilios + mat_outros

    manut_serv = get_v("Serviço - Manutenção E Reparos")
    manut_mat = get_v("Material - Manutenção E Reparos")
    total_manutencao = manut_serv + manut_mat

    total_delivery = get_v("Custo Com Entrega (Motoqueiros)") + get_v("Comissão Agregadores")
    total_marketing = get_v("Anúncios/Propagandas") + get_v("Fundo De Marketing") + get_v("Royalties")
    total_financeiro = get_v("Custo Cartão De Crédito") + get_v("Custo Cartão De Débito")

    total_despesas_operacionais = (
        imposto_fed + imposto_est + total_cmv + total_ocupacao + total_pessoal +
        total_utilidades + total_servicos + total_materiais + total_manutencao +
        total_delivery + total_marketing + total_financeiro
    )
    resultado_operacional = venda_bruta - total_despesas_operacionais
    resultado_final = resultado_operacional + val_bon

    def fmt_pct(val):
        if venda_bruta > 0:
            return f"{(val / venda_bruta) * 100:.2f}%"
        return "0.00%"

    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
    col_kpi1.metric("🔹 Venda Bruta", f"R$ {venda_bruta:,.2f}")
    col_kpi2.metric("📦 C M V Total", f"R$ {total_cmv:,.2f}", delta=fmt_pct(total_cmv), delta_color="inverse")
    col_kpi3.metric("🔹 Lucro Bruto", f"R$ {lucro_bruto:,.2f}", delta=fmt_pct(lucro_bruto))
    col_kpi4.metric("💰 Resultado Final", f"R$ {resultado_final:,.2f}", delta=fmt_pct(resultado_final))

    linhas_dre = [
        {"CONTA": "🔹 VENDA BRUTA", "VALOR": venda_bruta, "%": "100.00%"},
        {"CONTA": "  • Faturamento Balcão", "VALOR": fat_b, "%": fmt_pct(fat_b)},
        {"CONTA": "  • Faturamento Delivery", "VALOR": fat_d, "%": fmt_pct(fat_d)},
        {"CONTA": "(-) Imposto Federal", "VALOR": imposto_fed, "%": fmt_pct(imposto_fed)},
        {"CONTA": "(-) Imposto Estadual", "VALOR": imposto_est, "%": fmt_pct(imposto_est)},
        {"CONTA": "🔹 RECEITA LÍQUIDA", "VALOR": rec_liquida, "%": fmt_pct(rec_liquida)},
        {"CONTA": "----------------------------------------", "VALOR": None, "%": ""},
        {"CONTA": "📦 C M V (Custo de Mercadoria Vendida)", "VALOR": total_cmv, "%": fmt_pct(total_cmv)},
        {"CONTA": "  • Alimentos (Escaneado)", "VALOR": cmv_alimentos, "%": fmt_pct(cmv_alimentos)},
        {"CONTA": "  • Bebidas (Escaneado)", "VALOR": cmv_bebidas, "%": fmt_pct(cmv_bebidas)},
        {"CONTA": "  • Descartáveis (Escaneado)", "VALOR": cmv_descartaveis, "%": fmt_pct(cmv_descartaveis)},
        {"CONTA": "  • Fretes", "VALOR": cmv_fretes, "%": fmt_pct(cmv_fretes)},
        {"CONTA": "🔹 LUCRO BRUTO", "VALOR": lucro_bruto, "%": fmt_pct(lucro_bruto)},
        {"CONTA": "----------------------------------------", "VALOR": None, "%": ""},
        {"CONTA": "🏢 TOTAL OCUPAÇÃO", "VALOR": total_ocupacao, "%": fmt_pct(total_ocupacao)},
        {"CONTA": "  • Aluguel / Condomínio / Fundo", "VALOR": ocup_aluguel + ocup_condo + ocup_fundo, "%": fmt_pct(ocup_aluguel + ocup_condo + ocup_fundo)},
        {"CONTA": "👥 TOTAL PESSOAL", "VALOR": total_pessoal, "%": fmt_pct(total_pessoal)},
        {"CONTA": "  • Alimentação Funcionários (Escaneado)", "VALOR": pess_benef, "%": fmt_pct(pess_benef)},
        {"CONTA": "💡 TOTAL UTILIDADES (Água, Energia, Gás)", "VALOR": total_utilidades, "%": fmt_pct(total_utilidades)},
        {"CONTA": "🧹 MATERIAIS DE USO & LIMPEZA (Escaneado)", "VALOR": total_materiais, "%": fmt_pct(total_materiais)},
        {"CONTA": "  • Material de Limpeza", "VALOR": mat_limpeza, "%": fmt_pct(mat_limpeza)},
        {"CONTA": "  • Utensílios de Cozinha", "VALOR": mat_utensilios, "%": fmt_pct(mat_utensilios)},
        {"CONTA": "🔧 MANUTENÇÃO", "VALOR": total_manutencao, "%": fmt_pct(total_manutencao)},
        {"CONTA": "🛵 DELIVERY & TAXAS", "VALOR": total_delivery, "%": fmt_pct(total_delivery)},
        {"CONTA": "📢 MARKETING & FRANQUEADOR", "VALOR": total_marketing, "%": fmt_pct(total_marketing)},
        {"CONTA": "💳 CUSTO FINANCEIRO (Cartões)", "VALOR": total_financeiro, "%": fmt_pct(total_financeiro)},
        {"CONTA": "----------------------------------------", "VALOR": None, "%": ""},
        {"CONTA": "🔴 TOTAL DESPESAS GERAIS", "VALOR": total_despesas_operacionais, "%": fmt_pct(total_despesas_operacionais)},
        {"CONTA": "🏆 RESULTADO OPERACIONAL", "VALOR": resultado_operacional, "%": fmt_pct(resultado_operacional)},
        {"CONTA": "💰 RESULTADO FINAL LÍQUIDO", "VALOR": resultado_final, "%": fmt_pct(resultado_final)}
    ]

    df_view = pd.DataFrame(linhas_dre)
    df_view["VALOR"] = df_view["VALOR"].apply(lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "")
    st.dataframe(df_view, use_container_width=True, height=650)

    st.markdown("### 📥 Exportar Relatório Oficial")
    dados_excel = gerar_excel_dre(NOMES_MESES[mes_ativo], linhas_dre, df_l)
    st.download_button(
        label="📊 Baixar DRE em Excel (.xlsx)",
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
    st.info(f"Ao confirmar o salvamento, todos os itens serão classificados e entrarão direto no DRE de **{NOMES_MESES[mes_ativo]}**[cite: 7, 8]!")

    aba_foto, aba_cam, aba_arq = st.tabs([
        "📸 Fotos Nítidas (Telemóvel / Galeria)",
        "🖥️ Câmara ao Vivo",
        "📁 Arquivo (XML / Excel / PDF)"
    ])

    with aba_foto:
        f_upload = st.file_uploader("Fotos do cupom/nota:", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)
        if f_upload and st.button("➕ Adicionar fotos à fila"):
            for f in f_upload:
                st.session_state.fotos_acumuladas.append({
                    "bytes": f.getvalue(),
                    "mime": "image/jpeg" if f.name.lower().endswith(('jpg', 'jpeg')) else f"image/{f.name.split('.')[-1].lower()}"
                })
            st.success(f"{len(f_upload)} foto(s) pronta(s)!")

    with aba_cam:
        f_cam = st.camera_input("Capturar foto")
        if f_cam and st.button("➕ Adicionar captura à fila"):
            st.session_state.fotos_acumuladas.append({"bytes": f_cam.getvalue(), "mime": "image/jpeg"})
            st.success("Foto capturada adicionada!")

    if st.session_state.fotos_acumuladas:
        st.write(f"**Total acumulado:** {len(st.session_state.fotos_acumuladas)} foto(s)")
        c1, c2 = st.columns([2, 1])
        with c1:
            if st.button("🚀 Processar Fotos com IA & Alimentar DRE", type="primary", use_container_width=True):
                partes = [types.Part.from_bytes(data=f["bytes"], mime_type=f["mime"]) for f in st.session_state.fotos_acumuladas]
                with st.spinner("🤖 Lendo itens e classificando categorias do Spoleto..."):
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
        with c2:
            if st.button("🗑️ Descartar Fotos", use_container_width=True):
                st.session_state.fotos_acumuladas = []
                st.rerun()

    with aba_arq:
        doc = st.file_uploader("Enviar XML, PDF ou Excel:", type=["xml", "xlsx", "xls", "pdf"])
        if doc and st.button("Processar Arquivo"):
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
                        "Categoria": mapa.get(nm, "Alimentos"),
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

    if st.session_state.dados_extraidos:
        dados = st.session_state.dados_extraidos
        st.markdown("---")
        st.subheader("📋 Resumo da Compra Identificada")
        c_a, c_b, c_c = st.columns(3)
        c_a.metric("Fornecedor", dados["razao_social"])
        c_b.metric("CNPJ", dados["cnpj"])
        c_c.metric("Valor Total", f"R$ {dados['valor_total']:,.2f}")

        df_itens = pd.DataFrame(dados["itens"])
        if not df_itens.empty:
            df_edit = st.data_editor(
                df_itens,
                column_config={"Categoria": st.column_config.SelectboxColumn("Categoria", options=LISTA_CATEGORIAS, required=True)},
                use_container_width=True,
                num_rows="dynamic",
                key="editor_nota_ativa"
            )

            somas_cat = df_edit.groupby("Categoria")["TotalItem"].sum().to_dict()
            st.write("#### 📊 Subtotais por Categoria que alimentarão o DRE:")
            c_grid = st.columns(len(somas_cat))
            for idx, (cat_n, val_n) in enumerate(somas_cat.items()):
                c_grid[idx].metric(cat_n, f"R$ {val_n:,.2f}")

            st.markdown("---")
            c_salvar, c_limpar = st.columns([2, 1])
            with c_salvar:
                if st.button(f"🚀 Confirmar & Lançar no DRE ({NOMES_MESES[mes_ativo]})", type="primary", use_container_width=True):
                    salvar_nota_e_lancar_dre(
                        mes_ref=mes_ativo,
                        razao_social=dados["razao_social"],
                        cnpj=dados["cnpj"],
                        valor_total=dados["valor_total"] or sum(somas_cat.values()),
                        lista_produtos=df_edit.to_dict(orient="records")
                    )
                    st.success(f"✅ Sucesso! Os valores foram incorporados à aba LANÇAMENTOS e o DRE de {NOMES_MESES[mes_ativo]} foi atualizado automaticamente[cite: 7, 8].")
                    st.session_state.dados_extraidos = None
                    st.rerun()
            with c_limpar:
                if st.button("❌ Cancelar", use_container_width=True):
                    st.session_state.dados_extraidos = None
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
        df_r = pd.DataFrame(list(regras.items()), columns=["Produto", "Categoria"]).sort_values("Produto")
        st.dataframe(df_r, use_container_width=True)
    else:
        st.info("Nenhuma regra personalizada ainda. Sempre que corrigir e salvar uma nota, a IA memoriza aqui.")
