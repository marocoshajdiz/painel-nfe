import streamlit as st
import xmltodict
import pandas as pd
from google import genai
from google.genai import types
import json

st.set_page_config(page_title="Painel Inteligente de Custos - Capry", layout="wide")

st.title("🛒 Painel Inteligente de Custos - Capry Comércio")
st.write("Envie o arquivo (**XML, Excel, PDF ou Foto**) ou tire uma foto direta do cupom fiscal com o celular.")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except:
    st.error("⚠️ Chave de API não encontrada! Certifique-se de configurar o arquivo .streamlit/secrets.toml com a sua chave.")
    st.stop()

CATEGORIAS_VALIDAS = "Alimentos, Descartáveis, Limpeza, Funcionários, Utensílios, Bebidas"
MODELO_GEMINI = "gemini-3.8-flash"  # Atualizado para o modelo suportado

def processar_com_ia(conteudo_texto, nome_arquivo, chave):
    try:
        client = genai.Client(api_key=chave)
        prompt = f"""
        Você é o assistente financeiro da empresa Capry Comércio Varejista de Alimentos LTDA.
        Analise o seguinte conteúdo extraído do arquivo '{nome_arquivo}' (nota fiscal, XML ou extrato de compras).
        Sua tarefa é extrair ou associar cada item à sua respectiva categoria rigorosamente entre estas opções:
        {CATEGORIAS_VALIDAS}

        Retorne APENAS um objeto JSON válido no formato de lista de dicionários, contendo exatamente as chaves:
        "Produto", "Quantidade", "Unid", "PrecoUnitario", "TotalItem", "Categoria".
        Exemplo:
        [
          {{"Produto": "CANUDO PLASTICO", "Quantidade": 10.0, "Unid": "CX", "PrecoUnitario": 15.00, "TotalItem": 150.00, "Categoria": "Descartáveis"}}
        ]

        Conteúdo a analisar:
        {conteudo_texto[:15000]}
        """
        response = client.models.generate_content(
            model=MODELO_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Erro ao processar com a IA: {e}")
        return []

def processar_imagem_com_ia(bytes_imagem, mime_type, chave):
    """Lê diretamente a foto da nota ou cupom fiscal usando visão computacional do Gemini."""
    try:
        client = genai.Client(api_key=chave)
        prompt = f"""
        Você é o assistente financeiro da empresa Capry Comércio Varejista de Alimentos LTDA.
        Analise a imagem desta nota fiscal, cupom fiscal ou espelho de compras.
        
        Extraia:
        1. 'razao_social': Nome do estabelecimento / emitente / fornecedor.
        2. 'cnpj': CNPJ do emitente (se visível).
        3. 'valor_total': Valor total final da nota (numérico float).
        4. 'itens': Lista com cada item comprado, contendo:
           - "Produto": nome ou descrição do item
           - "Quantidade": float
           - "Unid": unidade (ex: UN, KG, CX)
           - "PrecoUnitario": float
           - "TotalItem": float
           - "Categoria": classifique obrigatoriamente em: {CATEGORIAS_VALIDAS}

        Retorne APENAS um JSON no formato:
        {{
          "razao_social": "...",
          "cnpj": "...",
          "valor_total": 0.0,
          "itens": [
            {{"Produto": "...", "Quantidade": 1.0, "Unid": "UN", "PrecoUnitario": 10.0, "TotalItem": 10.0, "Categoria": "Alimentos"}}
          ]
        }}
        """
        part_imagem = types.Part.from_bytes(data=bytes_imagem, mime_type=mime_type)
        response = client.models.generate_content(
            model=MODELO_GEMINI,
            contents=[prompt, part_imagem],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Erro ao analisar a imagem da nota com IA: {e}")
        return None

def categorizar_nomes_xml(lista_nomes, chave):
    try:
        client = genai.Client(api_key=chave)
        prompt = f"""
        Classifique cada produto da lista abaixo estritamente em **uma** das categorias:
        {CATEGORIAS_VALIDAS}.
        Retorne APENAS um JSON onde a chave é o nome exato do produto e o valor é a categoria.
        Produtos: {json.dumps(lista_nomes, ensure_ascii=False)}
        """
        response = client.models.generate_content(
            model=MODELO_GEMINI,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(response.text)
    except:
        return {}

# Seleção do modo de entrada
aba_upload, aba_camera = st.tabs(["📁 Enviar Arquivo ou Foto", "📸 Tirar Foto com a Câmera"])

arquivo_ativo = None
origem_camera = False

with aba_upload:
    uploaded_file = st.file_uploader(
        "Escolha a Nota Fiscal (XML, Excel, PDF ou Imagem)", 
        type=["xml", "xlsx", "xls", "pdf", "jpg", "jpeg", "png", "webp"]
    )
    if uploaded_file is not None:
        arquivo_ativo = uploaded_file

with aba_camera:
    foto_camera = st.camera_input("Aponte a câmera para a nota fiscal ou cupom")
    if foto_camera is not None:
        arquivo_ativo = foto_camera
        origem_camera = True

if arquivo_ativo is not None:
    if origem_camera:
        file_extension = "jpg"
    else:
        file_extension = arquivo_ativo.name.split('.')[-1].lower()

    lista_produtos = []
    razao_social = "Fornecedor não identificado"
    cnpj_emitente = "Não informado"
    valor_total_nota = 0.0

    try:
        # 1. Foto tirada pela câmera ou imagem enviada
        if origem_camera or file_extension in ['jpg', 'jpeg', 'png', 'webp']:
            mime = "image/jpeg" if file_extension in ['jpg', 'jpeg'] else f"image/{file_extension}"
            bytes_img = arquivo_ativo.getvalue()
            
            with st.spinner("🤖 Analisando a foto da nota com o Gemini 3.8 Flash..."):
                resultado_foto = processar_imagem_com_ia(bytes_img, mime, api_key)
            
            if resultado_foto:
                razao_social = resultado_foto.get('razao_social', 'Fornecedor não identificado')
                cnpj_emitente = resultado_foto.get('cnpj', 'Não informado')
                valor_total_nota = float(resultado_foto.get('valor_total', 0.0))
                
                for item in resultado_foto.get('itens', []):
                    v_tot = float(item.get('TotalItem', 0))
                    lista_produtos.append({
                        "Categoria": item.get('Categoria', 'Alimentos'),
                        "Produto": item.get('Produto', 'Desconhecido'),
                        "Quantidade": float(item.get('Quantidade', 1)),
                        "Unid": item.get('Unid', 'UN'),
                        "Preço Unitário (R$)": float(item.get('PrecoUnitario', 0)),
                        "Total do Item (R$)": v_tot
                    })

        # 2. Arquivo XML
        elif file_extension == 'xml':
            file_content = arquivo_ativo.read()
            data = xmltodict.parse(file_content)
            
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
                
            nomes_produtos = [item.get('prod', {}).get('xProd', '') for item in detalhes]
            
            with st.spinner("🤖 Categorizando itens do XML com a IA..."):
                mapa_cat = categorizar_nomes_xml(nomes_produtos, api_key)
                
            for item in detalhes:
                prod = item.get('prod', {})
                nome = prod.get('xProd', 'Desconhecido')
                qtd = float(prod.get('qCom', 0))
                unid = prod.get('uCom', '')
                v_unit = float(prod.get('vUnCom', 0))
                v_prod = float(prod.get('vProd', 0))
                cat = mapa_cat.get(nome, 'Alimentos')
                
                lista_produtos.append({
                    "Categoria": cat,
                    "Produto": nome,
                    "Quantidade": qtd,
                    "Unid": unid,
                    "Preço Unitário (R$)": v_unit,
                    "Total do Item (R$)": v_prod
                })

        # 3. Planilhas Excel
        elif file_extension in ['xlsx', 'xls']:
            df_excel = pd.read_excel(arquivo_ativo)
            texto_excel = df_excel.to_string()
            with st.spinner("🤖 Estruturando dados da planilha com a IA..."):
                resultado_ia = processar_com_ia(texto_excel, arquivo_ativo.name, api_key)
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

        # 4. Arquivos PDF
        elif file_extension == 'pdf':
            import pypdf
            reader = pypdf.PdfReader(arquivo_ativo)
            texto_pdf = ""
            for page in reader.pages:
                texto_pdf += page.extract_text() or ""
                
            with st.spinner("🤖 Extraindo dados do PDF com a IA..."):
                resultado_ia = processar_com_ia(texto_pdf, arquivo_ativo.name, api_key)
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

            if abs(soma_produtos - valor_total_nota) > 0.1 and valor_total_nota > soma_produtos:
                diferenca = valor_total_nota - soma_produtos
                df_produtos = pd.concat([df_produtos, pd.DataFrame([{
                    "Categoria": "Alimentos",
                    "Produto": "TAXA / FRETE / ENCARGOS DA NOTA",
                    "Quantidade": 1.0,
                    "Unid": "GL",
                    "Preço Unitário (R$)": diferenca,
                    "Total do Item (R$)": diferenca
                }])], ignore_index=True)

            st.subheader("📋 Resumo da Compra")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Fornecedor / Origem", value=razao_social)
            with col2:
                st.metric(label="CNPJ / Identificação", value=cnpj_emitente)
            with col3:
                st.metric(label="Valor Total Registrado", value=f"R$ {valor_total_nota:,.2f}")
                
            st.subheader("📊 Totais por Categoria & Validação")
            df_resumo = df_produtos.groupby("Categoria")["Total do Item (R$)"].sum().reset_index()
            soma_categorias = df_resumo["Total do Item (R$)"].sum()
            
            df_resumo_formatado = df_resumo.copy()
            df_resumo_formatado["Total do Item (R$)"] = df_resumo_formatado["Total do Item (R$)"].apply(lambda x: f"R$ {x:,.2f}")
            st.dataframe(df_resumo_formatado, use_container_width=True)
            
            st.info(f"🔍 **Conferência de Fechamento:** A soma das categorias totaliza **R$ {soma_categorias:,.2f}** (Valor da nota: R$ {valor_total_nota:,.2f}).")
            st.success("✅ **Validação Concluída!**")

            df_produtos_formatado = df_produtos.copy()
            df_produtos_formatado["Preço Unitário (R$)"] = df_produtos_formatado["Preço Unitário (R$)"].apply(lambda x: f"R$ {x:,.2f}")
            df_produtos_formatado["Total do Item (R$)"] = df_produtos_formatado["Total do Item (R$)"].apply(lambda x: f"R$ {x:,.2f}")
            
            st.subheader("📦 Produtos Detalhados")
            st.dataframe(df_produtos_formatado, use_container_width=True)
        else:
            st.warning("Nenhum item pôde ser identificado. Tente capturar a imagem mais de perto ou com iluminação uniforme.")
            
    except Exception as e:
        st.error(f"Erro ao processar: {e}")
else:
    st.info("Aguardando upload de arquivo ou captura de foto pela câmera...")
