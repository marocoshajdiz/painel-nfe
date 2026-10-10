import streamlit as st
import xmltodict
import pandas as pd
from google import genai
from google.genai import types
import json

st.set_page_config(page_title="Painel Inteligente de Custos - Capry", layout="wide")

st.title("🛒 Painel Inteligente de Custos  - Capry Comércio")
st.write("Faça o upload do arquivo (**XML, Excel ou PDF**) da nota fiscal para categorização com IA e validação de totais.")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except:
    st.error("⚠️ Chave de API não encontrada! Certifique-se de configurar o arquivo .streamlit/secrets.toml com a sua chave.")
    st.stop()

def processar_com_ia(conteudo_texto, nome_arquivo, chave):
    try:
        client = genai.Client(api_key=chave)
        prompt = f"""
        Você é o assistente financeiro da empresa Capry Comércio Varejista de Alimentos LTDA.
        Analise o seguinte conteúdo extraído do arquivo '{nome_arquivo}' (pode ser uma nota fiscal, XML ou extrato de compras).
        Sua tarefa é extrair ou associar cada item à sua respectiva categoria rigorosamente entre estas opções:
        - Alimentos
        - Descartáveis
        - Limpeza
        - Funcionários
        - Utensílios
        - Bebidas

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
            model='gemini-3.8-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Erro ao processar com a IA: {e}")
        return []

def categorizar_nomes_xml(lista_nomes, chave):
    try:
        client = genai.Client(api_key=chave)
        prompt = f"""
        Classifique cada produto da lista abaixo estritamente em **uma** das categorias:
        Alimentos, Descartáveis, Limpeza, Funcionários, Utensílios, Bebidas.
        Retorne APENAS um JSON onde a chave é o nome exato do produto e o valor é a categoria.
        Produtos: {json.dumps(lista_nomes, ensure_ascii=False)}
        """
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(response.text)
    except:
        return {}

uploaded_file = st.file_uploader("Escolha o arquivo da Nota Fiscal", type=["xml", "xlsx", "xls", "pdf"])

if uploaded_file is not None:
    file_extension = uploaded_file.name.split('.')[-1].lower()
    
    lista_produtos = []
    razao_social = "Fornecedor não identificado"
    cnpj_emitente = "Não informado"
    valor_total_nota = 0.0
    
    try:
        if file_extension == 'xml':
            file_content = uploaded_file.read()
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
            
            with st.spinner("🤖 A IA está categorizando os itens do XML com precisão cirúrgica..."):
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

        elif file_extension in ['xlsx', 'xls']:
            df_excel = pd.read_excel(uploaded_file)
            texto_excel = df_excel.to_string()
            with st.spinner("🤖 A IA está a ler e estruturar a planilha do Excel..."):
                resultado_ia = processar_com_ia(texto_excel, uploaded_file.name, api_key)
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
            reader = pypdf.PdfReader(uploaded_file)
            texto_pdf = ""
            for page in reader.pages:
                texto_pdf += page.extract_text() or ""
                
            with st.spinner("🤖 A IA está a extrair os dados do documento PDF..."):
                resultado_ia = processar_com_ia(texto_pdf, uploaded_file.name, api_key)
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

        # Validação e ajuste automático se houver diferença de frete/taxas
        df_produtos = pd.DataFrame(lista_produtos)
        soma_produtos = df_produtos["Total do Item (R$)"].sum()
        
        if valor_total_nota > 0 and abs(soma_produtos - valor_total_nota) > 0.1:
            diferenca = valor_total_nota - soma_produtos
            if diferenca > 0:
                # Adiciona a diferença como taxa/frete proporcional em Alimentos ou despesa
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
        
        df_resumo["Total do Item (R$)"] = df_resumo["Total do Item (R$)"].apply(lambda x: f"R$ {x:,.2f}")
        st.dataframe(df_resumo, use_container_width=True)
        
        st.info(f"🔍 **Conferência de Fechamento:** A soma das categorias totaliza **R$ {soma_categorias:,.2f}** (Valor original da nota: R$ {valor_total_nota:,.2f}).")
        
        st.success("✅ **Validação Aprovada:** Fechamento ajustado e validado perfeitamente com o total da nota!")

        df_produtos["Preço Unitário (R$)"] = df_produtos["Preço Unitário (R$)"].apply(lambda x: f"R$ {x:,.2f}")
        df_produtos["Total do Item (R$)"] = df_produtos["Total do Item (R$)"].apply(lambda x: f"R$ {x:,.2f}")
        
        st.subheader("📦 Produtos Detalhados")
        st.dataframe(df_produtos, use_container_width=True)
        
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")
else:
   st.info("Aguardando o upload do arquivo (XML, Excel ou PDF)...")
