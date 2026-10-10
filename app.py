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

# CSS para expandir o visor da câmera
st.markdown("""
<style>
div[data-testid="stCameraInput"] {
    width: 100% !important;
    max-width: 900px !important;
    margin: 0 auto;
}
div[data-testid="stCameraInput"] video {
    width: 100% !important;
    height: 70vh !important;
    min-height: 480px !important;
    border-radius: 14px;
    object-fit: cover !important;
    border: 2px solid #ff4b4b;
}
div[data-testid="stCameraInput"] button {
    padding: 0.75rem 1.5rem !important;
    font-size: 1.1rem !important;
    border-radius: 10px !important;
}
</style>
""", unsafe_allow_html=True)

# ----------------- BASE DE DADOS (SQLite) -----------------
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
    # Tabela de memória de regras/classificações corrigidas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regras_classificacao (
            produto TEXT PRIMARY KEY,
            categoria TEXT
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
    
    # Memorizar as categorias corrigidas pelo utilizador para futuras notas
    for item in lista_produtos:
        prod = str(item.get("Produto", "")).strip().upper()
        cat = str(item.get("Categoria", "")).strip()
        if prod:
            cursor.execute("""
                INSERT INTO regras_classificacao (produto, categoria)
                VALUES (?, ?)
                ON CONFLICT(produto) DO UPDATE SET categoria=excluded.categoria
            """, (prod, cat))
            
    conn.commit()
    conn.close()

def carregar_regras():
    conn = sqlite3.connect("notas_fiscais.db")
    cursor = conn.cursor()
    cursor.execute("SELECT produto, categoria FROM regras_classificacao")
    regras = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return regras

def listar_notas():
    conn = sqlite3.connect("notas_fiscais.db")
    df = pd.read_sql_query("SELECT id, data_registo, razao_social, cnpj, valor_total FROM notas ORDER BY id DESC", conn)
    conn.close()
    return df

def obter_detalhes_nota(nota_id):
    conn = sqlite3.connect("notas_fiscais.db")
    cursor = conn.cursor()
    cursor.execute("SELECT itens_json, valor_total, razao_social FROM notas WHERE id = ?", (nota_id,))
    linha = cursor.fetchone()
    conn.close()
    if linha:
        itens = json.loads(linha[0])
        return itens, linha[1], linha[2]
    return [], 0.0, ""

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
    st.error("⚠️ Chave de API não encontrada! Configure o secrets.toml com GEMINI_API_KEY.")
    st.stop()

LISTA_CATEGORIAS = ["Alimentos", "Descartáveis", "Limpeza", "Funcionários", "Utensílios", "Bebidas"]
CATEGORIAS_VALIDAS = ", ".join(LISTA_CATEGORIAS)
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
    regras = carregar_regras()
    exemplo_regras = json.dumps(regras, ensure_ascii=False) if regras else "Nenhuma ainda."
    
    prompt = f"""
    Você é o assistente financeiro da empresa Capry Comércio Varejista de Alimentos LTDA.
    Analise o seguinte conteúdo extraído do ficheiro '{nome_arquivo}'.
    Classifique cada item obrigatoriamente entre: {CATEGORIAS_VALIDAS}.
    
    IMPORTANTE: Dê prioridade a estas classificações memorizadas anteriormente pelo utilizador:
    {exemplo_regras}

    Retorne APENAS um JSON no formato de lista de dicionários com:
    "Produto", "Quantidade", "Unid", "PrecoUnitario", "TotalItem", "Categoria".
    Conteúdo:
    {conteudo_texto[:15000]}
    """
    res = chamar_gemini_com_fallback(chave, prompt)
    return res if isinstance(res, list) else []

def processar_multiplas_imagens_com_ia(lista_partes_imagem, chave):
    regras = carregar_regras()
    exemplo_regras = json.dumps(regras, ensure_ascii=False) if regras else "Nenhuma ainda."
    
    prompt = f"""
    Você é o assistente financeiro da empresa Capry Comércio Varejista de Alimentos LTDA.
    Analise as imagens anexadas que compõem uma ou mais páginas da mesma nota/cupão fiscal.
    Junte todos os itens de todas as fotos sem duplicar, totalizando a compra completa.
    
    Categorias válidas: {CATEGORIAS_VALIDAS}.
    IMPORTANTE: Respeite rigorosamente as preferências já ensinadas pelo utilizador:
    {exemplo_regras}

    Extraia:
    1. 'razao_social': Nome do estabelecimento / fornecedor.
    2. 'cnpj': CNPJ do emitente.
    3. 'valor_total': Valor total final da nota (float).
    4. 'itens': Lista com cada item comprado ("Produto", "Quantidade", "Unid", "PrecoUnitario", "TotalItem", "Categoria").

    Retorne APENAS um JSON:
    {{
      "razao_social": "...",
      "cnpj": "...",
      "valor_total": 0.0,
      "itens": [{{"Produto": "...", "Quantidade": 1.0, "Unid": "UN", "PrecoUnitario": 10.0, "TotalItem": 10.0, "Categoria": "Alimentos"}}]
    }}
    """
    conteudos = [prompt] + lista_partes_imagem
    return chamar_gemini_com_fallback(chave, conteudos)

def categorizar_nomes_xml(lista_nomes, chave):
    regras = carregar_regras()
    mapa = {}
    pendentes = []
    for nome in lista_nomes:
        if nome.strip().upper() in regras:
            mapa[nome] = regras[nome.strip().upper()]
        else:
            pendentes.append(nome)
            
    if pendentes:
        prompt = f"""
        Classifique cada produto da lista abaixo estritamente em uma das categorias: {CATEGORIAS_VALIDAS}.
        Retorne APENAS um JSON com o par produto: categoria.
        Produtos: {json.dumps(pendentes, ensure_ascii=False)}
        """
        res = chamar_gemini_com_fallback(chave, prompt)
        if isinstance(res, dict):
            mapa.update(res)
    return mapa

# Inicialização de variáveis de sessão
if "fotos_acumuladas" not in st.session_state:
    st.session_state.fotos_acumuladas = []
if "dados_extraidos" not in st.session_state:
    st.session_state.dados_extraidos = None

# ----------------- NAVEGAÇÃO -----------------
menu_principal = st.sidebar.radio("Navegação:", ["📄 Capturar / Enviar Nota", "🗄️ Histórico & Consultas", "🧠 Dicionário de Classificações"])

if menu_principal == "📄 Capturar / Enviar Nota":
    st.info("💡 **Dica:** Pode capturar ou anexar várias fotos da mesma nota. Elas ficam acumuladas até clicar no botão verde de processar!")
    
    aba_alta_res, aba_camera_web, aba_ficheiros = st.tabs([
        "📸 Fotos Nítidas (Telemóvel / Galeria)", 
        "🖥️ Câmara ao Vivo", 
        "📁 Ficheiro (XML / Excel / PDF)"
    ])

    with aba_alta_res:
        fotos_upload = st.file_uploader(
            "Selecione uma ou mais fotos do documento (permite fotos múltiplas):", 
            type=["jpg", "jpeg", "png", "webp"], 
            accept_multiple_files=True,
            key="upload_multiplas_fotos"
        )
        if fotos_upload:
            if st.button("➕ Adicionar estas fotos à lista de espera", key="btn_add_upload"):
                for f in fotos_upload:
                    st.session_state.fotos_acumuladas.append({
                        "bytes": f.getvalue(),
                        "mime": "image/jpeg" if f.name.lower().endswith(('jpg', 'jpeg')) else f"image/{f.name.split('.')[-1].lower()}",
                        "nome": f.name
                    })
                st.success(f"{len(fotos_upload)} foto(s) adicionada(s)!")

    with aba_camera_web:
        foto_web = st.camera_input("Tire uma foto", key="camera_viva")
        if foto_web is not None:
            if st.button("➕ Adicionar esta foto capturada", key="btn_add_camera"):
                st.session_state.fotos_acumuladas.append({
                    "bytes": foto_web.getvalue(),
                    "mime": "image/jpeg",
                    "nome": f"foto_cam_{len(st.session_state.fotos_acumuladas) + 1}.jpg"
                })
                st.success("Foto adicionada à lista de espera!")

    # Painel de gestão de fotos acumuladas
    if st.session_state.fotos_acumuladas:
        st.write(f"### 📷 Fotos prontas para leitura: **{len(st.session_state.fotos_acumuladas)} foto(s)**")
        col_c1, col_c2 = st.columns([2, 1])
        with col_c1:
            if st.button("🚀 Processar Fotos Acumuladas com a IA", type="primary", use_container_width=True):
                partes = [types.Part.from_bytes(data=f["bytes"], mime_type=f["mime"]) for f in st.session_state.fotos_acumuladas]
                with st.spinner("🤖 A IA está a juntar e analisar todas as páginas da nota..."):
                    res = processar_multiplas_imagens_com_ia(partes, api_key)
                    if res and isinstance(res, dict):
                        st.session_state.dados_extraidos = {
                            "razao_social": res.get('razao_social') or "Fornecedor não identificado",
                            "cnpj": res.get('cnpj') or "Não informado",
                            "valor_total": float(res.get('valor_total') or 0.0),
                            "itens": res.get('itens', [])
                        }
                        st.session_state.fotos_acumuladas = []
                        st.rerun()
        with col_c2:
            if st.button("🗑️ Limpar Fotos", use_container_width=True):
                st.session_state.fotos_acumuladas = []
                st.rerun()

    with aba_ficheiros:
        arquivo_doc = st.file_uploader("Envie XML, PDF ou Excel", type=["xml", "xlsx", "xls", "pdf"], key="doc_file")
        if arquivo_doc is not None and st.button("Processar Ficheiro"):
            ext = arquivo_doc.name.split('.')[-1].lower()
            if ext == 'xml':
                data = xmltodict.parse(arquivo_doc.read())
                inf_nfe = data.get('nfeProc', data).get('NFe', {}).get('infNFe', {})
                emitente = inf_nfe.get('emit', {})
                total = inf_nfe.get('total', {}).get('ICMSTot', {})
                detalhes = inf_nfe.get('det', [])
                if not isinstance(detalhes, list):
                    detalhes = [detalhes]
                nomes = [i.get('prod', {}).get('xProd', '') for i in detalhes]
                mapa_cat = categorizar_nomes_xml(nomes, api_key)
                
                itens_xml = []
                for item in detalhes:
                    prod = item.get('prod', {})
                    nome = prod.get('xProd', 'Desconhecido')
                    itens_xml.append({
                        "Categoria": mapa_cat.get(nome, 'Alimentos'),
                        "Produto": nome,
                        "Quantidade": float(prod.get('qCom', 0)),
                        "Unid": prod.get('uCom', ''),
                        "PrecoUnitario": float(prod.get('vUnCom', 0)),
                        "TotalItem": float(prod.get('vProd', 0))
                    })
                st.session_state.dados_extraidos = {
                    "razao_social": emitente.get('xNome', 'Não informado'),
                    "cnpj": emitente.get('CNPJ', 'Não informado'),
                    "valor_total": float(total.get('vNF', 0.0)),
                    "itens": itens_xml
                }
                st.rerun()

            elif ext in ['xlsx', 'xls', 'pdf']:
                texto = ""
                if ext == 'pdf':
                    import pypdf
                    reader = pypdf.PdfReader(arquivo_doc)
                    texto = "".join([p.extract_text() or "" for p in reader.pages])
                else:
                    texto = pd.read_excel(arquivo_doc).to_string()
                    
                res_itens = processar_com_ia(texto, arquivo_doc.name, api_key)
                st.session_state.dados_extraidos = {
                    "razao_social": "Ficheiro importado",
                    "cnpj": "Não informado",
                    "valor_total": sum(float(i.get('TotalItem', 0)) for i in res_itens),
                    "itens": res_itens
                }
                st.rerun()

    # ----------------- RESULTADO & EDIÇÃO INTERATIVA -----------------
    if st.session_state.dados_extraidos:
        dados = st.session_state.dados_extraidos
        st.markdown("---")
        st.subheader("📋 Resumo da Compra")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Fornecedor", dados["razao_social"])
        col2.metric("CNPJ", dados["cnpj"])
        col3.metric("Valor Total Registado", f"R$ {dados['valor_total']:,.2f}")

        st.subheader("✏️ Itens Identificados (Ajuste ou Corrija Categorias)")
        st.write("Edite as categorias se necessário antes de guardar:")

        df_editavel = pd.DataFrame(dados["itens"])
        if not df_editavel.empty:
            if "TotalItem" not in df_editavel.columns and "Total do Item (R$)" in df_editavel.columns:
                df_editavel.rename(columns={"Total do Item (R$)": "TotalItem", "Preço Unitário (R$)": "PrecoUnitario"}, inplace=True)

            # Tabela global editável
            df_alterado = st.data_editor(
                df_editavel,
                column_config={
                    "Categoria": st.column_config.SelectboxColumn(
                        "Categoria",
                        options=LISTA_CATEGORIAS,
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
                key="editor_tabela_itens"
            )

            # Totais por Categoria
            st.subheader("📊 Totais por Categoria Atualizados")
            df_resumo = df_alterado.groupby("Categoria")["TotalItem"].sum().reset_index()
            soma_todas_categorias = float(df_resumo["TotalItem"].sum())

            df_resumo_tabela = df_resumo.copy()
            df_resumo_tabela["TotalItem"] = df_resumo_tabela["TotalItem"].apply(lambda x: f"R$ {x:,.2f}")
            df_resumo_tabela.rename(columns={"TotalItem": "Total da Categoria (R$)"}, inplace=True)
            st.dataframe(df_resumo_tabela, use_container_width=True)

            col_tot1, col_tot2 = st.columns([1, 1])
            with col_tot1:
                st.metric(
                    label="💰 Soma Total de Todas as Categorias",
                    value=f"R$ {soma_todas_categorias:,.2f}"
                )
            with col_tot2:
                diferenca_nota = abs(soma_todas_categorias - dados['valor_total'])
                if dados['valor_total'] > 0:
                    if diferenca_nota < 0.1:
                        st.success("✅ A soma das categorias bate exatamente com o valor total da nota!")
                    else:
                        st.warning(f"⚠️ Diferença de R$ {diferenca_nota:,.2f} em relação ao valor da nota (R$ {dados['valor_total']:,.2f}).")

            # ----------------- ITENS SEPARADOS POR CATEGORIA -----------------
            st.subheader("📦 Itens Detalhados por Categoria Separada")
            categorias_existentes = sorted(df_alterado["Categoria"].dropna().unique())

            for cat in categorias_existentes:
                df_cat = df_alterado[df_alterado["Categoria"] == cat].copy()
                subtotal_cat = df_cat["TotalItem"].sum()
                qtd_itens_cat = len(df_cat)

                with st.expander(f"🏷️ **{cat.upper()}** — {qtd_itens_cat} item(ns) | Subtotal: **R$ {subtotal_cat:,.2f}**", expanded=True):
                    df_cat_show = df_cat.copy()
                    df_cat_show["PrecoUnitario"] = df_cat_show["PrecoUnitario"].apply(lambda x: f"R$ {float(x):,.2f}")
                    df_cat_show["TotalItem"] = df_cat_show["TotalItem"].apply(lambda x: f"R$ {float(x):,.2f}")
                    df_cat_show.rename(columns={
                        "Produto": "Produto",
                        "Quantidade": "Qtd",
                        "Unid": "Unid",
                        "PrecoUnitario": "Preço Unitário (R$)",
                        "TotalItem": "Total do Item (R$)"
                    }, inplace=True)
                    # Não precisa exibir a coluna Categoria aqui pois já está agrupada
                    cols_para_exibir = [c for c in ["Produto", "Qtd", "Unid", "Preço Unitário (R$)", "Total do Item (R$)"] if c in df_cat_show.columns]
                    st.dataframe(df_cat_show[cols_para_exibir], use_container_width=True)

            st.markdown("---")
            col_guardar, col_descartar = st.columns([2, 1])
            with col_guardar:
                if st.button("💾 Guardar e Ensinar IA com estas Correções", type="primary", use_container_width=True):
                    itens_finais = df_alterado.to_dict(orient="records")
                    salvar_nota(dados["razao_social"], dados["cnpj"], dados["valor_total"] or soma_todas_categorias, itens_finais)
                    st.success("✅ Nota gravada e a IA memorizou as suas categorias corrigidas!")
                    st.session_state.dados_extraidos = None
                    st.rerun()

            with col_descartar:
                if st.button("❌ Descartar Análise", use_container_width=True):
                    st.session_state.dados_extraidos = None
                    st.rerun()

# ----------------- HISTÓRICO COM ITENS SEPARADOS POR CATEGORIA -----------------
elif menu_principal == "🗄️ Histórico & Consultas":
    st.subheader("🗄️ Histórico de Notas Salvas")
    df_historico = listar_notas()

    if df_historico.empty:
        st.info("Ainda não existem notas guardadas na base de dados.")
    else:
        df_historico_show = df_historico.copy()
        df_historico_show["valor_total"] = df_historico_show["valor_total"].apply(lambda x: f"R$ {x:,.2f}")
        df_historico_show.rename(columns={
            "id": "ID", 
            "data_registo": "Data/Hora", 
            "razao_social": "Fornecedor", 
            "cnpj": "CNPJ", 
            "valor_total": "Valor Total"
        }, inplace=True)

        st.dataframe(df_historico_show, use_container_width=True)

        st.markdown("---")
        st.subheader("🔍 Consultar Detalhes da Nota")

        col_select, col_del = st.columns([2, 1])
        with col_select:
            nota_selecionada = st.selectbox("Selecione o registo pelo ID para abrir a nota completa:", df_historico["id"].tolist())

        with col_del:
            st.write("&nbsp;")
            if st.button("🗑️ Eliminar Nota", type="secondary", use_container_width=True):
                excluir_nota(nota_selecionada)
                st.warning(f"Nota #{nota_selecionada} eliminada!")
                st.rerun()

        if nota_selecionada:
            itens_recuperados, valor_tot_bd, fornecedor_bd = obter_detalhes_nota(nota_selecionada)
            if itens_recuperados:
                df_itens = pd.DataFrame(itens_recuperados)

                # Padronizar nomes de colunas
                col_map = {}
                if "TotalItem" in df_itens.columns:
                    col_map["TotalItem"] = "Total"
                elif "Total do Item (R$)" in df_itens.columns:
                    col_map["Total do Item (R$)"] = "Total"

                if "PrecoUnitario" in df_itens.columns:
                    col_map["PrecoUnitario"] = "PrecoUnit"
                elif "Preço Unitário (R$)" in df_itens.columns:
                    col_map["Preço Unitário (R$)"] = "PrecoUnit"

                df_itens.rename(columns=col_map, inplace=True)
                df_itens["Total"] = pd.to_numeric(df_itens["Total"], errors="coerce").fillna(0.0)

                st.write(f"### 📄 Detalhes da Nota #{nota_selecionada} — {fornecedor_bd}")

                # 1. Tabela com o subtotal de cada categoria
                st.write("#### 📊 Subtotais por Categoria")
                df_cat_subtotais = df_itens.groupby("Categoria")["Total"].sum().reset_index()
                soma_categorias_hist = float(df_cat_subtotais["Total"].sum())

                df_cat_show = df_cat_subtotais.copy()
                df_cat_show["Subtotal"] = df_cat_show["Total"].apply(lambda x: f"R$ {x:,.2f}")
                df_cat_show.drop(columns=["Total"], inplace=True)
                df_cat_show.rename(columns={"Categoria": "Categoria", "Subtotal": "Subtotal da Categoria (R$)"}, inplace=True)

                st.dataframe(df_cat_show, use_container_width=True)

                st.metric(
                    label="💰 Total Somado das Categorias",
                    value=f"R$ {soma_categorias_hist:,.2f}"
                )

                # 2. Itens separados por categoria
                st.write("#### 📦 Itens Detalhados da Compra (Separados por Categoria)")
                cats_hist = sorted(df_itens["Categoria"].dropna().unique())

                for cat in cats_hist:
                    df_sub = df_itens[df_itens["Categoria"] == cat].copy()
                    subtot_cat = df_sub["Total"].sum()
                    qtd_sub = len(df_sub)

                    with st.expander(f"🏷️ **{cat.upper()}** — {qtd_sub} item(ns) | Subtotal: **R$ {subtot_cat:,.2f}**", expanded=True):
                        df_sub_show = df_sub.copy()
                        df_sub_show["PrecoUnit"] = df_sub_show["PrecoUnit"].apply(lambda x: f"R$ {float(x):,.2f}" if pd.notnull(x) else "R$ 0,00")
                        df_sub_show["Total"] = df_sub_show["Total"].apply(lambda x: f"R$ {float(x):,.2f}")
                        df_sub_show.rename(columns={
                            "Produto": "Produto",
                            "Quantidade": "Qtd",
                            "Unid": "Unid",
                            "PrecoUnit": "Preço Unitário (R$)",
                            "Total": "Total do Item (R$)"
                        }, inplace=True)

                        cols_hist = [c for c in ["Produto", "Qtd", "Unid", "Preço Unitário (R$)", "Total do Item (R$)"] if c in df_sub_show.columns]
                        st.dataframe(df_sub_show[cols_hist], use_container_width=True)

# ----------------- MEMÓRIA DE REGRAS -----------------
elif menu_principal == "🧠 Dicionário de Classificações":
    st.subheader("🧠 Classificações Memorizadas pela IA")
    st.write("Estes são os produtos que corrigiu e que a IA já aprendeu a categorizar automaticamente:")
    regras_atuais = carregar_regras()
    if regras_atuais:
        df_regras = pd.DataFrame(list(regras_atuais.items()), columns=["Produto", "Categoria"]).sort_values("Produto")
        st.dataframe(df_regras, use_container_width=True)
    else:
        st.info("Ainda não foram memorizadas personalizações. Sempre que guardar uma nota corrigida, os itens aparecem aqui.")
