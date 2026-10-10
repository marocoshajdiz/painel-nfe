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

# CSS para tela expandida
st.markdown("""
<style>
div[data-testid="stCameraInput"] { width: 100% !important; max-width: 900px !important; margin: 0 auto; }
div[data-testid="stCameraInput"] video { width: 100% !important; height: 70vh !important; min-height: 480px !important; border-radius: 14px; object-fit: cover !important; border: 2px solid #ff4b4b; }
div[data-testid="stCameraInput"] button { padding: 0.75rem 1.5rem !important; font-size: 1.1rem !important; border-radius: 10px !important; }
</style>
""", unsafe_allow_html=True)

# ----------------- BASE DE DADOS (SQLite com Ajustes Manuais do DRE) -----------------
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
# 1. ABA DO DRE OFICIAL (EDIÇÃO DIRETA NA TABELA & TEMPO REAL)
# ==============================================================================
if menu.startswith("📊 DRE Spoleto"):
    st.subheader(f"📊 Demonstrativo de Resultados (DRE) — {NOMES_MESES[mes_ativo]}")
    st.write("Edite qualquer valor na coluna **VALOR (R$)** da tabela abaixo. Os subtotais, totais e percentuais recalculam na hora[cite: 8, 9]!")

    # 1. Obter somas vindas das notas escaneadas na aba LANÇAMENTOS
    df_l = obter_lancamentos_mes(mes_ativo)
    somas_escaneadas = df_l.groupby("detalhamento")["valor"].sum().to_dict() if not df_l.empty else {}

    # 2. Obter ajustes manuais salvos anteriormente no banco para este mês
    ajustes_banco = obter_ajustes_dre(mes_ativo)

    # Definição das contas analíticas (editáveis) do DRE Spoleto
    # chave: (Nome exibido na tela, Categoria/Origem do detalhamento se houver)
    CONTAS_DRE = [
        # Receitas & Impostos
        ("Faturamento Balcão", None, 0.0),
        ("Faturamento Delivery", None, 0.0),
        ("Imposto Federal", "Imposto Federal", 0.0),
        ("Imposto Estadual", "Imposto Estadual", 0.0),
        # CMV
        ("Alimentos", "Alimentos", 0.0),
        ("Bebidas", "Bebidas", 0.0),
        ("Descartáveis", "Descartáveis", 0.0),
        ("Fretes", "Fretes", 0.0),
        # Ocupação
        ("Aluguel", "Aluguel", 0.0),
        ("Ar condicionado", "Ar Condicionado", 0.0),
        ("Condomínio", "Condomínio", 0.0),
        ("Fundo de Promoção", "Fundo De Promoção", 0.0),
        ("IPTU", "Iptu", 0.0),
        ("Taxas e Outros", "Taxas E Outros", 0.0),
        # Pessoal
        ("Salário", "Salário", 0.0),
        ("Adiantamento", "Adiantamento", 0.0),
        ("Benefícios (Alimentação Funcionários)", "Benefícios", 0.0),
        ("Encargos", "Encargos", 0.0),
        ("Férias", "Férias", 0.0),
        ("13 salário", "13 Salário", 0.0),
        ("Provisões", "Provisões", 0.0),
        ("Rescisão", "Rescisão", 0.0),
        ("Outros (pessoal)", "Outros (pessoal)", 0.0),
        # Utilidades
        ("Água e Esgoto", "Água E Esgoto", 0.0),
        ("Energia Elétrica", "Energia Elétrica", 0.0),
        ("Gás", "Gás", 0.0),
        ("Internet", "Internet", 0.0),
        ("Telefone", "Telefone", 0.0),
        ("Outros (utilidades)", "Outros (utilidades)", 0.0),
        # Serviços & Terceiros
        ("Serviços", "Serviços", 0.0),
        ("Terceiros", "Terceiros", 0.0),
        # Material de Uso & Consumo
        ("Material de Escritório", "Material De Escritório", 0.0),
        ("Material de Limpeza", "Material De Limpeza", 0.0),
        ("Uniformes", "Uniformes", 0.0),
        ("Utensílios", "Utensílios", 0.0),
        ("Outros Materiais de Uso e Consumo", "Outros Materiais De Uso E Consumo", 0.0),
        # Manutenção
        ("Serviço - Manutenção e Reparos", "Serviço - Manutenção E Reparos", 0.0),
        ("Material - Manutenção e Reparos", "Material - Manutenção E Reparos", 0.0),
        # Delivery & Marketing & Financeiro
        ("Taxa de entrega arrecadada", None, 0.0),
        ("Comissão agregadores", "Comissão Agregadores", 0.0),
        ("Custo com entrega (motoqueiros)", "Custo Com Entrega (Motoqueiros)", 0.0),
        ("Anúncios/Propagandas", "Anúncios/Propagandas", 0.0),
        ("Fundo de Marketing", "Fundo De Marketing", 0.0),
        ("Royalties", "Royalties", 0.0),
        ("Custo Cartão de Crédito", "Custo Cartão De Crédito", 0.0),
        ("Custo Cartão de Débito", "Custo Cartão De Débito", 0.0),
        # Bonificação / Extra
        ("Total Bonificação", None, 0.0)
    ]

    # Preencher valores: prioridade 1: Ajuste manual no banco; prioridade 2: Escaneado de notas
    lista_linhas_editaveis = []
    for nome_conta, chave_det, val_padrao in CONTAS_DRE:
        if nome_conta in ajustes_banco:
            val_atual = ajustes_banco[nome_conta]
        elif chave_det and chave_det in somas_escaneadas:
            val_atual = float(somas_escaneadas[chave_det])
        else:
            val_atual = val_padrao

        lista_linhas_editaveis.append({
            "CONTA": nome_conta,
            "VALOR (R$)": float(round(val_atual, 2))
        })

    df_base_editavel = pd.DataFrame(lista_linhas_editaveis)

    # Tabela com Edição Direta
    st.write("👇 **Tabela de Lançamentos do DRE (Clique no valor para editar):**")
    df_dre_editado = st.data_editor(
        df_base_editavel,
        column_config={
            "CONTA": st.column_config.TextColumn("Conta / Rubrica", disabled=True),
            "VALOR (R$)": st.column_config.NumberColumn("VALOR (R$)", format="R$ %.2f", min_value=0.0, step=10.0, required=True)
        },
        use_container_width=True,
        num_rows="fixed",
        height=520,
        key=f"editor_dre_{mes_ativo}"
    )

    # Botão para persistir qualquer alteração feita no DRE
    col_save_dre, _ = st.columns([2, 3])
    with col_save_dre:
        if st.button("💾 Salvar Alterações do DRE na Base de Dados", type="primary", use_container_width=True):
            novos_ajustes = dict(zip(df_dre_editado["CONTA"], df_dre_editado["VALOR (R$)"]))
            salvar_ajustes_dre(mes_ativo, novos_ajustes)
            st.success("✅ **Alterações salvas com sucesso no banco de dados!**")

    # Mapear valores editados para cálculo em cascata em tempo real
    v_map = dict(zip(df_dre_editado["CONTA"], df_dre_editado["VALOR (R$)"]))

    def v(k):
        return float(v_map.get(k, 0.0))

    # CÁLCULOS EXATOS DO DRE SPOLETO EM TEMPO REAL
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

    # RESUMO EXECUTIVO COM CARDS
    st.markdown("---")
    st.write("### 📈 Visão Consolidada em Tempo Real")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔹 Venda Bruta", f"R$ {venda_bruta:,.2f}")
    c2.metric("📦 CMV Total", f"R$ {total_cmv:,.2f}", delta=pct(total_cmv), delta_color="inverse")
    c3.metric("🔹 Lucro Bruto", f"R$ {lucro_bruto:,.2f}", delta=pct(lucro_bruto))
    c4.metric("💰 Resultado Final", f"R$ {res_final:,.2f}", delta=pct(res_final))

    # ESTRUTURA OFICIAL SINTÉTICA DO DRE SPOLETO
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
        {"CONTA": "👥 TOTAL PESSOAL", "VALOR": total_pess, "%": pct(total_pess)},
        {"CONTA": "💡 TOTAL UTILIDADES", "VALOR": total_util, "%": pct(total_util)},
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

    # Botão de Exportação Excel
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
