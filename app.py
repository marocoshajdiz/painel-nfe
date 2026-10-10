import streamlit as st
import xmltodict
import pandas as pd
from google import genai
from google.genai import types
import json
import time
import sqlite3
from datetime import datetime

st.set_page_config(page_title="Painel Inteligente de Custos - Capry", layout="wide")

# CSS para ampliar a área da câmara no ecrã (computador e telemóvel)
st.markdown("""
    <style>
    [data-testid="stCameraInput"] video {
        width: 100% !important;
        max-height: 550px !important;
        border-radius: 12px;
        object-fit: cover;
    }
    [data-testid="stCameraInput"] {
        width: 100% !important;
    }
    </style>
""", unsafe_allow_html=True)

# ----------------- BANCO DE DADOS (SQLite) -----------------
def init_db():
    conn = sqlite3.connect("notas_fiscais.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_registo TEXT,
            razao_social TEXT,
            cnpj TEXT,
            valor_total REAL,
            itens_json TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def salvar_nota(razao_social, cnpj, valor_total, lista_produtos):
    conn = sqlite3.connect("notas_fiscais.db")
    cursor = conn.cursor()
    data_registo = datetime.now().strftime("%d/%m/%Y %H:%M")
    itens_json = json.dumps(lista_produtos, ensure_ascii=False)
    cursor.execute("""
        INSERT INTO notas (data_registo, razao_social, cnpj, valor_total, itens_json)
        VALUES (?, ?, ?, ?, ?)
    """, (data_registo, razao_social, cnpj, valor_total, itens_json))
    conn.commit()
    conn.close()

def listar_notas():
    conn = sqlite3.connect("notas_fiscais.db")
    df = pd.read_sql_query("SELECT id, data_registo, razao_social, cnpj, valor_total FROM notas ORDER BY id DESC", conn)
    conn.close()
    return df

def obter_detalhes_nota(nota_id):
    conn = sqlite3.connect("notas_fiscais.db")
    cursor = conn.cursor()
    cursor.execute("SELECT itens_json FROM notas WHERE id = ?", (nota_id,))
    linha = cursor.fetchone()
    conn.close()
    if linha:
        return json.loads(linha[0])
    return []

def excluir_nota(nota_id):
    conn = sqlite3.connect("notas_fiscais.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notas WHERE id = ?", (nota_id,))
    conn.commit()
    conn.close()

# ----------------- CONFIGURAÇÕES & IA -----------------
st.title("🛒 Painel Inteligente de Custos - Capry Comércio")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    st.error("⚠️ Chave de API não encontrada! Certifique-se de configurar o ficheiro .streamlit/secrets.toml.")
    st.stop()

CATEGORIAS_VALIDAS = "Alimentos, Descartáveis, Limpeza, Funcionários, Utensílios, Bebidas"
MODELOS_IA = ["gemini-3.8-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

def chamar_gemini_com_fallback(chave, conteudos):
    client = genai.Client(api_key=chave)
    ultimo_erro = None
    for modelo in MODELOS_IA:
        for _ in range(2):
            try:
                response = client.models.generate_content(
                    model=modelo,
                    contents=conteudos,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                if response.text:
                    return json.loads(response.text)
            except Exception as e:
                ultimo_erro = e
                time.sleep(2)
                continue
    st.error(f"Erro ao processar com a IA: {ultimo_erro}")
    return None

def processar_com_ia(conteudo_texto, nome_arquivo, chave):
    prompt = f"""
    Você é o assistente financeiro da empresa Capry Comércio Varejista de Alimentos LTDA.
    Analise o seguinte conteúdo extraído do arquivo '{nome_arquivo}'.
    Classifique cada item obrigatoriamente entre: {CATEGORIAS_VALIDAS}.
    Retorne APENAS um JSON no formato de lista de dicionários com:
    "Produto", "Quantidade", "Unid", "PrecoUnitario", "TotalItem", "Categoria".
    Conteúdo:
    {conteudo_texto[:15000]}
    """
    res = chamar_gemini_com_fallback(chave, prompt)
    return res if isinstance(res, list) else []

def processar_imagem_com_ia(bytes_imagem, mime_type, chave):
    prompt = f"""
    Você é o assistente financeiro da empresa Capry Comércio Varejista de Alimentos LTDA.
    Analise a imagem desta nota ou cupom fiscal.
    Extraia:
    1. 'razao_social': Nome do estabelecimento / fornecedor.
    2. 'cnpj': CNPJ do emitente.
    3. 'valor_total': Valor total final da nota (float).
    4. 'itens': Lista com cada item comprado ("Produto", "Quantidade", "Unid", "PrecoUnitario", "TotalItem", "Categoria" entre {CATEGORIAS_VALIDAS}).

    Retorne APENAS um JSON:
    {{
      "razao_social": "...",
      "cnpj": "...",
      "valor_total": 0.0,
      "itens": [{{"Produto": "...", "Quantidade": 1.0, "Unid": "UN", "PrecoUnitario": 10.0, "TotalItem": 10.0, "Categoria": "Alimentos"}}]
    }}
    """
    part_imagem = types.Part.from_bytes(data=bytes_imagem, mime_type=mime_type)
    return chamar_gemini_com_fallback(chave, [prompt, part_imagem])

def categorizar_nomes_xml(lista_nomes, chave):
    prompt = f"""
    Classifique cada produto da lista abaixo estritamente em uma das categorias: {CATEGORIAS_VALIDAS}.
    Retorne APENAS um JSON com o par produto: categoria.
    Produtos: {json.dumps(lista_nomes, ensure_ascii=False)}
    """
    res = chamar_gemini_com_fallback(chave, prompt)
    return res if isinstance(res, dict) else {}

# ----------------- NAVEGAÇÃO PRINCIPAL -----------------
menu_principal = st.sidebar.radio("Selecione a secção:", ["📄 Leitor de Notas & Cupões", "🗄️ Histórico & Consultas"])

if menu_principal == "📄 Leitor de Notas & Cupões":
    aba_camera, aba_upload = st.tabs(["📸 Tirar Foto com a Câmera", "📁 Enviar Ficheiro ou Foto"])

    arquivo_ativo = None
    origem_camera = False

    with aba_camera:
        st.write("Aponte a câmara para a nota fiscal:")
        foto_camera = st.camera_input("Capturar Nota Fiscal")
        if foto_camera is not None:
            arquivo_ativo = foto_camera
            origem_camera = True

    with aba_upload:
        uploaded_file = st.file_uploader(
            "Carregue XML, Excel, PDF ou Foto", 
            type=["xml", "xlsx", "xls", "pdf", "jpg", "jpeg", "png", "webp"]
        )
        if uploaded_file is not None:
            arquivo_ativo = uploaded_file
            origem_camera = False

    if arquivo_ativo is not None:
        file_extension = "jpg" if origem_camera else arquivo_ativo.name.split('.')[-1].lower()
        lista_produtos = []
        razao_social = "Fornecedor não identificado"
        cnpj_emitente = "Não informado"
        valor_total_nota = 0.0

        try:
            if origem_camera or file_extension in ['jpg', 'jpeg', 'png', 'webp']:
                mime = "image/jpeg" if file_extension in ['jpg', 'jpeg'] else f"image/{file_extension}"
                with st.spinner("🤖 A IA está a ler a imagem da nota..."):
                    resultado_foto = processar_imagem_com_ia(arquivo_ativo.getvalue(), mime, api_key)
                
                if resultado_foto and isinstance(resultado_foto, dict):
                    razao_social = resultado_foto.get('razao_social') or "Fornecedor não identificado"
                    cnpj_emitente = resultado_foto.get('cnpj') or "Não informado"
                    valor_total_nota = float(resultado_foto.get('valor_total') or 0.0)
                    for item in resultado_foto.get('itens', []):
                        lista_produtos.append({
                            "Categoria": item.get('Categoria', 'Alimentos'),
                            "Produto": item.get('Produto', 'Desconhecido'),
                            "Quantidade": float(item.get('Quantidade') or 1.0),
                            "Unid": item.get('Unid', 'UN'),
                            "Preço Unitário (R$)": float(item.get('PrecoUnitario') or 0.0),
                            "Total do Item (R$)": float(item.get('TotalItem') or 0.0)
                        })

            elif file_extension == 'xml':
                data = xmltodict.parse(arquivo_ativo.read())
                nfe_proc = data.get('nfeProc', data)
                inf_nfe = nfe_proc.get('NFe', {}).get('infNFe', {})
                emitente = inf_nfe.get('emit', {})
                total = inf_nfe.get('total', {}).get('ICMSTot', {})
                razao_social = emitente.get('xNome', 'Não informado')
                cnpj_emitente = emitente.get('CNPJ', 'Não informado')
                valor_total_nota = float(total.get('vNF', 0.0))
                
                detalhes = inf_nfe.get('det', [])
                if not isinstance(detalhes, list):
                    detalhes = [detalhes]
                nomes = [i.get('prod', {}).get('xProd', '') for i in detalhes]
                
                with st.spinner("🤖 Categorizando itens com IA..."):
                    mapa_cat = categorizar_nomes_xml(nomes, api_key)
                for item in detalhes:
                    prod = item.get('prod', {})
                    nome = prod.get('xProd', 'Desconhecido')
                    lista_produtos.append({
                        "Categoria": mapa_cat.get(nome, 'Alimentos'),
                        "Produto": nome,
                        "Quantidade": float(prod.get('qCom', 0)),
                        "Unid": prod.get('uCom', ''),
                        "Preço Unitário (R$)": float(prod.get('vUnCom', 0)),
                        "Total do Item (R$)": float(prod.get('vProd', 0))
                    })

            elif file_extension in ['xlsx', 'xls']:
                df_excel = pd.read_excel(arquivo_ativo)
                with st.spinner("🤖 Processando folha de cálculo..."):
                    resultado_ia = processar_com_ia(df_excel.to_string(), arquivo_ativo.name, api_key)
                for item in resultado_ia:
                    v_tot = float(item.get('TotalItem', 0))
                    valor_total_nota += v_tot
                    lista_produtos.append({
                        "Categoria": item.get('Categoria', 'Alimentos'),
                        "Produto": item.get('Produto', 'Desconhecido'),
                        "Quantidade": float(item.get('Quantidade', 1)),
                        "Unid": item.get('Unid', 'UN'),
                        "Preço Unitário (R$)": float(item.get('PrecoUnitario', 0)),
                        "Total do Item (R$)": v_tot
                    })

            elif file_extension == 'pdf':
                import pypdf
                reader = pypdf.PdfReader(arquivo_ativo)
                texto = "".join([p.extract_text() or "" for p in reader.pages])
                with st.spinner("🤖 Processando PDF..."):
                    resultado_ia = processar_com_ia(texto, arquivo_ativo.name, api_key)
                for item in resultado_ia:
                    v_tot = float(item.get('TotalItem', 0))
                    valor_total_nota += v_tot
                    lista_produtos.append({
                        "Categoria": item.get('Categoria', 'Alimentos'),
                        "Produto": item.get('Produto', 'Desconhecido'),
                        "Quantidade": float(item.get('Quantidade', 1)),
                        "Unid": item.get('Unid', 'UN'),
                        "Preço Unitário (R$)": float(item.get('PrecoUnitario', 0)),
                        "Total do Item (R$)": v_tot
                    })

            if lista_produtos:
                df_produtos = pd.DataFrame(lista_produtos)
                soma_produtos = df_produtos["Total do Item (R$)"].sum()
                if valor_total_nota == 0.0:
                    valor_total_nota = soma_produtos

                st.subheader("📋 Resumo da Compra")
                col1, col2, col3 = st.columns(3)
                col1.metric("Fornecedor", razao_social)
                col2.metric("CNPJ", cnpj_emitente)
                col3.metric("Valor Total", f"R$ {valor_total_nota:,.2f}")

                st.subheader("📊 Totais por Categoria")
                df_resumo = df_produtos.groupby("Categoria")["Total do Item (R$)"].sum().reset_index()
                df_resumo_format = df_resumo.copy()
                df_resumo_format["Total do Item (R$)"] = df_resumo_format["Total do Item (R$)"].apply(lambda x: f"R$ {x:,.2f}")
                st.dataframe(df_resumo_format, use_container_width=True)

                st.subheader("📦 Produtos Identificados")
                df_prod_format = df_produtos.copy()
                df_prod_format["Preço Unitário (R$)"] = df_prod_format["Preço Unitário (R$)"].apply(lambda x: f"R$ {x:,.2f}")
                df_prod_format["Total do Item (R$)"] = df_prod_format["Total do Item (R$)"].apply(lambda x: f"R$ {x:,.2f}")
                st.dataframe(df_prod_format, use_container_width=True)

                st.markdown("---")
                col_save, _ = st.columns([1, 4])
                with col_save:
                    if st.button("💾 Guardar Nota na Base de Dados", type="primary", use_container_width=True):
                        salvar_nota(razao_social, cnpj_emitente, valor_total_nota, lista_produtos)
                        st.success("✅ Nota fiscal guardada com sucesso! Já pode consultá-la no menu lateral.")
            else:
                st.warning("Nenhum item detetado. Tente posicionar a câmara com boa iluminação.")

        except Exception as e:
            st.error(f"Erro no processamento: {e}")

# ----------------- ABA DE HISTÓRICO & EXCLUSÃO -----------------
elif menu_principal == "🗄️ Histórico & Consultas":
    st.subheader("🗄️ Histórico de Notas Guardadas")
    df_historico = listar_notas()

    if df_historico.empty:
        st.info("Ainda não há notas guardadas
