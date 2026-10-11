import streamlit as st
import xmltodict
import pandas as pd
from google import genai
from google.genai import types
import json
import sqlite3
import io
import re
from datetime import datetime
import pypdf

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

st.sidebar.write(f"👤 Logado como: **{USUARIO_CORRETO}**")
if st.sidebar.button("🚪 Sair do Sistema"):
    st.session_state.autenticado = False
    st.rerun()
st.sidebar.markdown("---")

st.markdown("""
<style>
div[data-testid="stCameraInput"] { width: 100% !important; max-width: 900px !important; margin: 0 auto; }
div[data-testid="stCameraInput"] video { width: 100% !important; height: 70vh !important; min-height: 480px !important; border-radius: 14px; object-fit: cover !important; border: 2px solid #ff4b4b; }
div[data-testid="stCameraInput"] button { padding: 0.75rem 1.5rem !important; font-size: 1.1rem !important; border-radius: 10px !important; }
</style>
""", unsafe_allow_html=True)

# ----------------- 7 CATEGORIAS ESSENCIAIS MAPEADAS NO DRE -----------------
MAPA_7_CATEGORIAS = {
    "Demais Alimentos": {"dre": "Alimentos", "det": "Alimentos"},
    "Descartáveis": {"dre": "Descartáveis", "det": "Descartáveis"},
    "Limpeza": {"dre": "Material_De_Uso_E_Consumo", "det": "Material De Limpeza"},
    "Utensílios": {"dre": "Material_De_Uso_E_Consumo", "det": "Utensílios"},
    "Bebidas": {"dre": "Bebidas", "det": "Bebidas"},
    "Horte": {"dre": "Alimentos", "det": "Alimentos"},
    "Uniformes": {"dre": "Material_De_Uso_E_Consumo", "det": "Uniformes"},
}
LISTA_7_CATEGORIAS = list(MAPA_7_CATEGORIAS.keys())
MODELO_GEMINI = "gemini-3.8-flash"


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
    "2027-07", "2027-08", "2027-09", "2027-10", "2027-11", "2027-12",
]
NOMES_MESES = {
    "2026-10": "Outubro / 2026", "2026-11": "Novembro / 2026", "2026-12": "Dezembro / 2026",
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
st.sidebar.markdown("---")


def salvar_nota_e_lancar_dre(mes_ref, razao_social, cnpj, valor_total, lista_produtos):
    conn = sqlite3.connect("notas_fiscais.db")
    try:
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
            col_cat = "Categoria" if "Categoria" in df_temp.columns else "Classificacao"
            if col_tot in df_temp.columns and col_cat in df_temp.columns:
                df_temp[col_tot] = pd.to_numeric(df_temp[col_tot], errors="coerce").fillna(0)
                totais = df_temp.groupby(col_cat)[col_tot].sum().to_dict()
                data_hoje = datetime.now().strftime("%Y-%m-%d")

                for cat_nome, valor in totais.items():
                    if valor > 0:
                        cfg = MAPA_7_CATEGORIAS.get(cat_nome, {"dre": "Alimentos", "det": "Alimentos"})
                        cursor.execute("""
                            INSERT INTO lancamentos_dre
                            (mes_referencia, data, fornecedor, descricao, valor, dre, classificacao, detalhamento)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            mes_ref, data_hoje, razao_social.upper(), str(cat_nome).upper(),
                            float(valor), cfg["dre"], cat_nome, cfg["det"]
                        ))

                for item in lista_produtos:
                    prod = str(item.get("Produto", "")).strip().upper()
                    categoria = str(item.get(col_cat, "")).strip()
                    if prod and categoria in LISTA_7_CATEGORIAS:
                        cursor.execute("""
                            INSERT INTO regras_classificacao (produto, categoria)
                            VALUES (?, ?)
                            ON CONFLICT(produto) DO UPDATE SET categoria=excluded.categoria
                        """, (prod, categoria))
        conn.commit()
    finally:
        conn.close()


def carregar_regras():
    conn = sqlite3.connect("notas_fiscais.db")
    try:
        c = conn.cursor()
        c.execute("SELECT produto, categoria FROM regras_classificacao")
        return {row[0]: row[1] for row in c.fetchall()}
    finally:
        conn.close()


def obter_lancamentos_mes(mes_ref):
    conn = sqlite3.connect("notas_fiscais.db")
    try:
        return pd.read_sql_query(
            """SELECT id, data, fornecedor, descricao, valor, dre, classificacao, detalhamento
               FROM lancamentos_dre WHERE mes_referencia = ? ORDER BY id DESC""",
            conn, params=(mes_ref,)
        )
    finally:
        conn.close()


def obter_ajustes_dre(mes_ref):
    conn = sqlite3.connect("notas_fiscais.db")
    try:
        c = conn.cursor()
        c.execute("SELECT conta, valor FROM ajustes_dre WHERE mes_referencia = ?", (mes_ref,))
        return {row[0]: float(row[1]) for row in c.fetchall()}
    finally:
        conn.close()


def salvar_ajustes_dre(mes_ref, dict_valores):
    conn = sqlite3.connect("notas_fiscais.db")
    try:
        c = conn.cursor()
        for conta, val in dict_valores.items():
            c.execute("""
                INSERT INTO ajustes_dre (mes_referencia, conta, valor)
                VALUES (?, ?, ?)
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


# ----------------- CONFIGURAÇÕES IA -----------------
try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    st.error("⚠️ Configure a GEMINI_API_KEY no arquivo .streamlit/secrets.toml.")
    st.stop()


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
Categorias permitidas, escolha exatamente uma:
["Demais Alimentos", "Descartáveis", "Limpeza", "Utensílios", "Bebidas", "Horte", "Uniformes"].
Use "Horte" para hortifrúti. Não confunda valor total da nota com subtotal dos produtos.
"""


def chamar_gemini(conteudos, chave):
    client = genai.Client(api_key=chave)
    response = client.models.generate_content(
        model=MODELO_GEMINI,
        contents=conteudos,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return parse_json_resposta(response.text if response else None)


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
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            st.warning("⚠️ Limite de requisições da IA atingido. Tente novamente mais tarde ou lance os produtos manualmente.")
        else:
            st.error(f"Erro ao interpretar as fotos com a IA: {e}")
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
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            st.warning("⚠️ Limite de requisições da IA atingido. Tente novamente mais tarde ou lance os produtos manualmente.")
        else:
            st.error(f"Erro ao interpretar o PDF com a IA: {e}")
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
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            st.warning("⚠️ Limite de requisições da IA atingido. Tente novamente mais tarde ou lance os produtos manualmente.")
        else:
            st.error(f"Erro ao processar o arquivo com a IA: {e}")
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


def resetar_processamento_nota():
    st.session_state.fotos_acumuladas = []
    st.session_state.dados_extraidos = None
    st.session_state.uploader_key += 1


# ----------------- NAVEGAÇÃO -----------------
menu = st.sidebar.radio("Módulo:", [
    f"📊 DRE Spoleto ({NOMES_MESES[mes_ativo]})",
    "📸 Escanear & Alimentar Nota",
    "📝 Lançamentos do Mês",
    "🧠 Regras Inteligentes",
])

# ==============================================================================
# 1. ABA DO DRE OFICIAL
# ==============================================================================
if menu.startswith("📊 DRE Spoleto"):
    st.subheader(f"📊 Demonstrativo de Resultados (DRE) — {NOMES_MESES[mes_ativo]}")
    st.write("Insira e ajuste os valores de Condomínio, Gás, Energia, Aluguel e Salários diretamente na tabela abaixo.")

    df_l = obter_lancamentos_mes(mes_ativo)
    somas_escaneadas = df_l.groupby("detalhamento")["valor"].sum().to_dict() if not df_l.empty else {}
    ajustes_banco = obter_ajustes_dre(mes_ativo)

    CONTAS_DRE_PAINEL = [
        ("Faturamento Balcão", None, 0.0),
        ("Faturamento Delivery", None, 0.0),
        ("Imposto Federal", "Imposto Federal", 0.0),
        ("Imposto Estadual", "Imposto Estadual", 0.0),
        ("Alimentos (Demais Alimentos + Horte)", "Alimentos", 0.0),
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
        ("Total Bonificação", None, 0.0),
    ]

    lista_linhas_editaveis = []
    for nome_conta, chave_det, val_padrao in CONTAS_DRE_PAINEL:
        val_escaneado = float(somas_escaneadas.get(chave_det, 0.0)) if chave_det else 0.0
        val_ajuste = float(ajustes_banco.get(nome_conta, val_padrao))
        val_final = val_escaneado if (val_escaneado > 0 and val_ajuste == 0.0) else (val_escaneado + val_ajuste)
        lista_linhas_editaveis.append({"CONTA": nome_conta, "VALOR (R$)": float(round(val_final, 2))})

    df_base_editavel = pd.DataFrame(lista_linhas_editaveis)
    st.write("👇 **Tabela de Lançamentos do DRE (Clique para editar e depois clique em Salvar):**")
    qtd_lanc = len(df_l)
    df_dre_editado = st.data_editor(
        df_base_editavel,
        column_config={
            "CONTA": st.column_config.TextColumn("Conta / Indicador", disabled=True),
            "VALOR (R$)": st.column_config.NumberColumn("VALOR (R$)", format="R$ %.2f", min_value=0.0, step=10.0, required=True),
        },
        use_container_width=True,
        num_rows="fixed",
        height=520,
        key=f"editor_dre_{mes_ativo}_v{qtd_lanc}",
    )

    col_save_dre, _ = st.columns([2, 3])
    with col_save_dre:
        if st.button("💾 Salvar Lançamentos e Ajustes do DRE na Base de Dados", type="primary", use_container_width=True):
            novos_ajustes = dict(zip(df_dre_editado["CONTA"], df_dre_editado["VALOR (R$)"]))
            salvar_ajustes_dre(mes_ativo, novos_ajustes)
            st.success("✅ Valores gravados com sucesso!")

    v_map = dict(zip(df_dre_editado["CONTA"], df_dre_editado["VALOR (R$)"]))

    def v(k):
        return float(v_map.get(k, 0.0) or 0.0)

    fat_balcao = v("Faturamento Balcão")
    fat_delivery = v("Faturamento Delivery")
    venda_bruta = fat_balcao + fat_delivery
    imp_fed = v("Imposto Federal")
    imp_est = v("Imposto Estadual")
    rec_liquida = venda_bruta - (imp_fed + imp_est)

    cmv_alim = v("Alimentos (Demais Alimentos + Horte)")
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
        total_util + total_serv + total_mat + total_manut + total_deliv + total_mkt + total_fin
    )
    res_operacional = venda_bruta - total_despesas
    res_final = res_operacional + v("Total Bonificação")

    def pct(val):
        return f"{(val / venda_bruta) * 100:.2f}%" if venda_bruta > 0 else "0.00%"

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
        {"CONTA": "  • Alimentos (Demais Alimentos + Horte)", "VALOR": cmv_alim, "%": pct(cmv_alim)},
        {"CONTA": "  • Bebidas", "VALOR": cmv_beb, "%": pct(cmv_beb)},
        {"CONTA": "  • Descartáveis", "VALOR": cmv_desc, "%": pct(cmv_desc)},
        {"CONTA": "  • Fretes", "VALOR": cmv_fret, "%": pct(cmv_fret)},
        {"CONTA": "🔹 LUCRO BRUTO", "VALOR": lucro_bruto, "%": pct(lucro_bruto)},
        {"CONTA": "----------------------------------------", "VALOR": None, "%": ""},
        {"CONTA": "🏢 TOTAL OCUPAÇÃO", "VALOR": total_ocup, "%": pct(total_ocup)},
        {"CONTA": "  • Condomínio", "VALOR": v("Condomínio"), "%": pct(v("Condomínio"))},
        {"CONTA": "  • Aluguel / Outros", "VALOR": total_ocup - v("Condomínio"), "%": pct(total_ocup - v("Condomínio"))},
        {"CONTA": "👥 TOTAL PESSOAL", "VALOR": total_pess, "%": pct(total_pess)},
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
        {"CONTA": "🔴 TOTAL DESPESAS", "VALOR": total_despesas, "%": pct(total_despesas)},
        {"CONTA": "🏆 RESULTADO OPERACIONAL", "VALOR": res_operacional, "%": pct(res_operacional)},
        {"CONTA": "💰 RESULTADO FINAL LÍQUIDO", "VALOR": res_final, "%": pct(res_final)},
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
        use_container_width=True,
    )

# ==============================================================================
# 2. ABA DE ESCANEAR NOTA & ALIMENTAR DRE
# ==============================================================================
elif menu.startswith("📸 Escanear"):
    st.subheader(f"📸 Escanear Nota Fiscal para o DRE de: {NOMES_MESES[mes_ativo]}")
    st.info("💡 As notas de compras são classificadas em: **Demais Alimentos, Descartáveis, Limpeza, Utensílios, Bebidas, Horte e Uniformes**.")

    ukey = st.session_state.uploader_key
    aba_foto, aba_cam, aba_arq = st.tabs([
        "📸 Fotos Nítidas (Telemóvel / Galeria)", "🖥️ Câmara ao Vivo", "📁 Arquivo (XML / Excel / PDF)"
    ])

    with aba_foto:
        f_upload = st.file_uploader(
            "Fotos do cupom/nota:", type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True, key=f"file_uploader_{ukey}"
        )
        if f_upload and st.button("➕ Adicionar fotos à fila", key=f"btn_add_f_{ukey}"):
            st.session_state.fotos_acumuladas = [f.getvalue() for f in f_upload]
            st.success(f"{len(f_upload)} foto(s) da nova nota carregada(s)!")

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
                with st.spinner("🤖 Lendo itens e classificando nas 7 categorias..."):
                    res = processar_multiplas_imagens_com_ia(st.session_state.fotos_acumuladas, api_key)
                    if res:
                        st.session_state.dados_extraidos = res
                    # Em caso de falha, não cria nota fictícia nem limpa as fotos.
                    else:
                        st.warning("A nota não foi carregada. Corrija o arquivo ou tente novamente; as fotos continuam na fila.")
                if st.session_state.dados_extraidos:
                    st.rerun()
        with col_desc:
            if st.button("🗑️ Descartar Fotos", use_container_width=True):
                resetar_processamento_nota()
                st.rerun()

    with aba_arq:
        doc = st.file_uploader(
            "Enviar XML da NF-e, PDF ou Excel da Compra:",
            type=["xml", "xlsx", "xls", "pdf"], key=f"doc_uploader_{ukey}"
        )
        if doc and st.button("Processar Arquivo", key=f"btn_doc_{ukey}"):
            st.session_state.dados_extraidos = None
            ext = doc.name.rsplit(".", 1)[-1].lower()

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
                    st.session_state.dados_extraidos = {
                        "razao_social": emit.get("xNome", "Fornecedor não identificado"),
                        "cnpj": emit.get("CNPJ") or emit.get("CPF") or "Não informado",
                        "valor_total": numero_seguro(tot.get("vNF")),
                        "itens": itens_x,
                    }
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao ler XML: {e}")

            elif ext == "pdf":
                try:
                    bytes_pdf = doc.getvalue()
                    # Tenta primeiro a leitura direta por visão da IA. Isso também permite PDFs digitalizados.
                    with st.spinner("🤖 Analisando o PDF e extraindo os produtos..."):
                        res_pdf = processar_pdf_com_ia(bytes_pdf, doc.name, api_key)

                    # Se o modelo/endpoint não aceitar PDF, tenta o texto extraído como alternativa.
                    if not res_pdf:
                        try:
                            reader = pypdf.PdfReader(io.BytesIO(bytes_pdf))
                            texto_pdf = "\n".join(page.extract_text() or "" for page in reader.pages)
                            if texto_pdf.strip():
                                with st.spinner("Tentando novamente usando o texto extraído do PDF..."):
                                    res_pdf = processar_texto_com_ia(texto_pdf, doc.name, api_key)
                        except Exception as e:
                            st.warning(f"Não foi possível extrair texto alternativo do PDF: {e}")

                    if res_pdf:
                        st.session_state.dados_extraidos = res_pdf
                        st.success(f"PDF lido: {len(res_pdf['itens'])} produto(s) identificado(s).")
                        st.rerun()
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
                        st.session_state.dados_extraidos = res_xl
                        st.success(f"Planilha lida: {len(res_xl['itens'])} produto(s) identificado(s).")
                        st.rerun()
                    else:
                        st.error("Não foi possível identificar produtos válidos na planilha. Nenhum item fictício foi criado.")
                except Exception as e:
                    st.error(f"Erro ao ler Excel: {e}")

    # ----------------- REVISÃO DA NOTA -----------------
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
                linhas_validas = df_edit[(df_edit["Produto"] != "") & (df_edit["TotalItem"] > 0)]
                if linhas_validas.empty:
                    st.warning("⚠️ Insira ao menos um produto com valor maior que R$ 0,00.")
                else:
                    # Só salva linhas identificadas e com valor positivo.
                    lista_salvar = linhas_validas[colunas_padrao].to_dict(orient="records")
                    total_salvar = float(linhas_validas["TotalItem"].sum())
                    salvar_nota_e_lancar_dre(
                        mes_ref=mes_ativo,
                        razao_social=fornec_input.strip() or "Fornecedor não identificado",
                        cnpj=cnpj_input.strip() or "Não informado",
                        valor_total=total_salvar,
                        lista_produtos=lista_salvar,
                    )
                    st.success(f"✅ {len(lista_salvar)} produto(s) lançados no DRE de {NOMES_MESES[mes_ativo]}!")
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
            st.write("")
            if st.button("Eliminar Lançamento", type="secondary", use_container_width=True):
                conn = sqlite3.connect("notas_fiscais.db")
                try:
                    conn.execute("DELETE FROM lancamentos_dre WHERE id = ?", (id_del,))
                    conn.commit()
                finally:
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
